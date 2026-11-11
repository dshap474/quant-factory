"""Nautilus-backed ordinary portfolio adapter.

This module keeps Nautilus imports lazy so importing ``backtest`` never requires
``nautilus_trader`` unless the Nautilus engine is selected.

USAGE:
    result = run_nautilus_backtest(
        prices=prices,
        weights=weights,
        funding_rates=None,
        config=config,
        timestamp_col="timestamp",
    )
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import numpy as np
import polars as pl

from ...config import BacktestConfig
from ...costs import compute_cost_returns, compute_turnover
from ...errors import (
    BacktestContractError,
    BacktestEngineExecutionError,
    BacktestEngineUnavailableError,
    BacktestUnsupportedFeatureError,
)
from ...funding import compute_funding_returns
from ...inputs import prepare_inputs
from ...metrics import MetricContext, compute_metrics
from ...result import BacktestResult
from ...returns import compute_benchmark_equity

# --------------------------------------------------------------------------- #
# Public engine entry
# --------------------------------------------------------------------------- #


def run_nautilus_backtest(
    *,
    prices: pl.DataFrame,
    weights: pl.DataFrame,
    funding_rates: pl.DataFrame | None,
    config: BacktestConfig,
    timestamp_col: str,
) -> BacktestResult:
    """Run backtest using Nautilus Trader as the execution kernel.

    Strategy weights are treated as a target-holdings schedule. A lightweight
    replay strategy submits delta market orders per timestamp to track the
    desired weight path.
    """
    nt = _import_nautilus()

    # Validate and align contracts first using existing deterministic checks.
    inputs = prepare_inputs(
        prices=prices,
        weights=weights,
        funding_rates=funding_rates,
        timestamp_col=timestamp_col,
    )

    asset_cols = [c for c in inputs.assets if c != "CASH"]
    if not asset_cols:
        raise BacktestContractError("Nautilus engine requires at least one non-CASH asset column.")

    # Build venue/engine.
    venue = nt["Venue"]("SIM")
    engine = nt["BacktestEngine"](
        config=nt["BacktestEngineConfig"](
            trader_id="QF-BACKTEST-001",
            logging=nt["LoggingConfig"](log_level="ERROR"),
        ),
    )

    try:
        engine.add_venue(
            venue=venue,
            oms_type=nt["OmsType"].NETTING,
            account_type=nt["AccountType"].MARGIN,
            base_currency=nt["USD"],
            starting_balances=[nt["Money"](config.initial_capital, nt["USD"])],
            default_leverage=Decimal("1"),
            bar_execution=True,
            use_random_ids=False,
        )

        # Create instruments + bars per asset.
        freq = _parse_frequency(config.frequency, nt)
        instruments: list[Any] = []
        bar_types: list[Any] = []
        instrument_by_asset: dict[str, Any] = {}

        timestamps = _timestamps_to_ns(inputs.prices.get_column(timestamp_col), nt)
        price_rows = inputs.prices.to_dicts()

        for asset in asset_cols:
            instrument = _build_currency_pair(asset=asset, venue=venue, nt=nt)
            instrument_by_asset[asset] = instrument
            instruments.append(instrument)
            engine.add_instrument(instrument)

            bar_type = nt["BarType"](
                instrument.id,
                nt["BarSpecification"](
                    step=freq["step"],
                    aggregation=freq["aggregation"],
                    price_type=nt["PriceType"].LAST,
                ),
            )
            bar_types.append(bar_type)

            bars = []
            for i, row in enumerate(price_rows):
                px = float(row[asset])
                ts_ns = timestamps[i]
                bars.append(
                    nt["Bar"](
                        bar_type=bar_type,
                        open=instrument.make_price(px),
                        high=instrument.make_price(px),
                        low=instrument.make_price(px),
                        close=instrument.make_price(px),
                        volume=nt["Quantity"].from_str("1.000000"),
                        ts_event=ts_ns,
                        ts_init=ts_ns,
                    )
                )
            engine.add_data(bars)

        weight_schedule = _build_weight_schedule(
            weights_df=inputs.weights,
            timestamp_col=timestamp_col,
            timestamp_ns=timestamps,
            asset_cols=asset_cols,
            instrument_by_asset=instrument_by_asset,
        )

        strategy = _build_weight_replay_strategy(
            nt=nt,
            venue=venue,
            instruments=instruments,
            bar_types=bar_types,
            weight_schedule=weight_schedule,
            initial_capital=config.initial_capital,
            random_seed=config.random_seed,
        )
        engine.add_strategy(strategy)

        engine.run()

        equity_curve = _extract_equity_curve(
            strategy=strategy,
            timestamps=timestamps,
            initial_capital=config.initial_capital,
            nt=nt,
            venue=venue,
            engine=engine,
        )

        if len(equity_curve) < 2:
            raise BacktestEngineExecutionError(
                "Nautilus engine produced insufficient equity history to compute returns."
            )

        # Price return is sourced from Nautilus replay.
        price_return = np.diff(equity_curve) / equity_curve[:-1]

        # Preserve legacy funding/cost decomposition as explicit post-processing.
        if config.include_funding:
            funding_return = compute_funding_returns(
                weights=inputs.weight_values,
                funding_rates=inputs.funding_values,
            )
        else:
            funding_return = np.zeros_like(price_return)

        turnover = compute_turnover(weights=inputs.weight_values)
        cost_return = compute_cost_returns(
            turnover=turnover,
            trade_cost_bps=config.trade_cost_bps,
        )

        net_return = price_return + funding_return - cost_return

        net_equity = np.empty(len(net_return) + 1, dtype=np.float64)
        net_equity[0] = config.initial_capital
        if len(net_return) > 0:
            net_equity[1:] = config.initial_capital * np.cumprod(1.0 + net_return)

        benchmark_equity = compute_benchmark_equity(
            prices_df=inputs.prices,
            asset_cols=asset_cols,
            initial_capital=config.initial_capital,
            benchmark=config.benchmark or config.benchmark_asset,
        )
        benchmark_values = benchmark_equity.to_numpy().astype(np.float64)
        benchmark_return = np.diff(benchmark_values) / benchmark_values[:-1]

        metrics = compute_metrics(
            MetricContext(
                equity=net_equity,
                net_return=net_return,
                price_return=price_return,
                benchmark_return=benchmark_return,
                funding_return=funding_return,
                cost_return=cost_return,
                turnover=turnover,
                frequency=config.frequency,
            ),
            list(config.metrics),
        )

        return BacktestResult(
            equity=pl.Series("equity", net_equity),
            benchmark_equity=benchmark_equity,
            price_return=pl.Series("price_return", price_return),
            funding_return=pl.Series("funding_return", funding_return),
            cost_return=pl.Series("cost_return", cost_return),
            net_return=pl.Series("net_return", net_return),
            turnover=pl.Series("turnover", turnover),
            metrics=metrics,
            engine_used="nautilus",
            engine_meta={
                "nautilus_version": nt["nautilus_version"],
            },
        )

    except (BacktestContractError, BacktestUnsupportedFeatureError):
        raise
    except Exception as exc:  # noqa: BLE001
        raise BacktestEngineExecutionError(f"Nautilus engine failed: {exc}") from exc
    finally:
        try:
            engine.dispose()
        except Exception:
            pass


@dataclass
class _ReplayState:
    current_ts: int | None
    seen_ids: set[str]
    latest_prices: dict[str, float]
    processed_ts: set[int]
    equity_points: list[tuple[int, float]]


def _build_weight_replay_strategy(
    *,
    nt: dict[str, Any],
    venue: Any,
    instruments: list[Any],
    bar_types: list[Any],
    weight_schedule: dict[int, dict[str, float]],
    initial_capital: float,
    random_seed: int,
):
    StrategyConfig = nt["StrategyConfig"]
    Strategy = nt["Strategy"]
    OrderSide = nt["OrderSide"]
    TimeInForce = nt["TimeInForce"]

    class _WeightReplayConfig(StrategyConfig, frozen=True):
        venue: Any
        instruments: tuple[Any, ...]
        bar_types: tuple[Any, ...]
        weight_schedule: dict[int, dict[str, float]]
        initial_capital: float
        random_seed: int

    class _WeightReplayStrategy(Strategy):
        def __init__(self, config: _WeightReplayConfig):
            super().__init__(config=config)
            self._state = _ReplayState(
                current_ts=None,
                seen_ids=set(),
                latest_prices={},
                processed_ts=set(),
                equity_points=[],
            )

        def on_start(self):
            for bar_type in self.config.bar_types:
                self.subscribe_bars(bar_type)

        def on_bar(self, bar):
            ts = int(bar.ts_event)
            instrument_id = str(bar.bar_type.instrument_id)
            self._state.latest_prices[instrument_id] = float(bar.close)

            if self._state.current_ts != ts:
                self._state.current_ts = ts
                self._state.seen_ids.clear()

            self._state.seen_ids.add(instrument_id)
            if len(self._state.seen_ids) < len(self.config.instruments):
                return

            if ts in self._state.processed_ts:
                return
            self._state.processed_ts.add(ts)

            targets = self.config.weight_schedule.get(ts)
            if targets is None:
                self._append_equity(ts)
                return

            current_equity = self._current_equity()
            for instrument in self.config.instruments:
                iid = str(instrument.id)
                target_weight = float(targets.get(iid, 0.0))
                last_price = self._state.latest_prices.get(iid)
                if last_price is None or last_price <= 0:
                    continue

                target_qty = (target_weight * current_equity) / last_price
                current_position = self.portfolio.net_position(instrument.id)
                current_qty = float(current_position) if current_position is not None else 0.0
                delta_qty = target_qty - current_qty

                min_step = float(instrument.size_increment)
                if abs(delta_qty) < max(min_step, 1e-9):
                    continue

                order = self.order_factory.market(
                    instrument_id=instrument.id,
                    order_side=OrderSide.BUY if delta_qty > 0 else OrderSide.SELL,
                    quantity=instrument.make_qty(abs(delta_qty)),
                    time_in_force=TimeInForce.GTC,
                )
                self.submit_order(order)

            self._append_equity(ts)

        def _append_equity(self, ts: int) -> None:
            self._state.equity_points.append((ts, self._current_equity()))

        def _current_equity(self) -> float:
            pnl_value = 0.0
            for instrument in self.config.instruments:
                total_pnl = self.portfolio.total_pnl(instrument.id)
                if total_pnl is not None:
                    pnl_value += float(total_pnl)
            return self.config.initial_capital + pnl_value

        @property
        def equity_points(self) -> list[tuple[int, float]]:
            return self._state.equity_points

    cfg = _WeightReplayConfig(
        venue=venue,
        instruments=tuple(instruments),
        bar_types=tuple(bar_types),
        weight_schedule=weight_schedule,
        initial_capital=initial_capital,
        random_seed=random_seed,
    )
    return _WeightReplayStrategy(cfg)


def _extract_equity_curve(
    *,
    strategy: Any,
    timestamps: list[int],
    initial_capital: float,
    nt: dict[str, Any],
    venue: Any,
    engine: Any,
) -> np.ndarray:
    points = sorted(strategy.equity_points, key=lambda x: x[0])
    if points:
        by_ts = {ts: val for ts, val in points}
        values = [float(by_ts.get(ts, initial_capital)) for ts in timestamps]
        return np.asarray(values, dtype=np.float64)

    # Fallback to account report if strategy did not emit points.
    try:
        report = engine.trader.generate_account_report(venue)
    except Exception as exc:  # noqa: BLE001
        raise BacktestEngineExecutionError("Failed to extract Nautilus account report") from exc

    if report is None or report.empty:
        return np.asarray([initial_capital], dtype=np.float64)

    report_df = pl.from_pandas(report.reset_index().rename(columns={"index": "timestamp"}))
    if "total" not in report_df.columns:
        return np.asarray([initial_capital], dtype=np.float64)

    report_df = report_df.with_columns(
        pl.col("timestamp")
        .map_elements(
            lambda x: _datetime_to_ns(_coerce_datetime(x)),
            return_dtype=pl.Int64,
        )
        .alias("ts_ns"),
        pl.col("total").cast(pl.Float64),
    )
    report_df = report_df.group_by("ts_ns").agg(pl.col("total").last())
    by_ts = dict(zip(report_df["ts_ns"].to_list(), report_df["total"].to_list(), strict=False))
    values = [float(by_ts.get(ts, initial_capital)) for ts in timestamps]
    return np.asarray(values, dtype=np.float64)


def _build_weight_schedule(
    *,
    weights_df: pl.DataFrame,
    timestamp_col: str,
    timestamp_ns: list[int],
    asset_cols: list[str],
    instrument_by_asset: dict[str, Any],
) -> dict[int, dict[str, float]]:
    rows = weights_df.select([timestamp_col] + asset_cols).to_dicts()
    if len(rows) != len(timestamp_ns):
        raise BacktestContractError("weights rows and timestamp index are misaligned for Nautilus scheduling.")

    schedule: dict[int, dict[str, float]] = {}
    for i, row in enumerate(rows):
        ts = timestamp_ns[i]
        payload: dict[str, float] = {}
        for asset in asset_cols:
            instrument = instrument_by_asset[asset]
            payload[str(instrument.id)] = float(row[asset])
        schedule[ts] = payload
    return schedule


def _build_currency_pair(asset: str, venue: Any, nt: dict[str, Any]):
    Currency = nt["Currency"]
    Symbol = nt["Symbol"]
    InstrumentId = nt["InstrumentId"]
    CurrencyPair = nt["CurrencyPair"]
    Price = nt["Price"]
    Quantity = nt["Quantity"]

    raw_symbol = Symbol(f"{asset}USD")
    instrument_id = InstrumentId(raw_symbol, venue)

    try:
        base_ccy = Currency.from_str(asset)
    except Exception:
        base_ccy = nt["USD"]

    return CurrencyPair(
        instrument_id=instrument_id,
        raw_symbol=raw_symbol,
        base_currency=base_ccy,
        quote_currency=nt["USD"],
        price_precision=8,
        size_precision=6,
        price_increment=Price.from_str("0.00000001"),
        size_increment=Quantity.from_str("0.000001"),
        ts_event=0,
        ts_init=0,
    )


def _parse_frequency(frequency: str, nt: dict[str, Any]) -> dict[str, Any]:
    value = frequency.lower().strip()
    BarAggregation = nt["BarAggregation"]

    if value in {"daily", "1d", "day"}:
        return {"step": 1, "aggregation": BarAggregation.DAY}
    if value in {"hourly", "1h", "hour"}:
        return {"step": 1, "aggregation": BarAggregation.HOUR}
    if value in {"4h"}:
        return {"step": 4, "aggregation": BarAggregation.HOUR}
    if value in {"30m"}:
        return {"step": 30, "aggregation": BarAggregation.MINUTE}
    if value in {"15m"}:
        return {"step": 15, "aggregation": BarAggregation.MINUTE}
    if value in {"5m"}:
        return {"step": 5, "aggregation": BarAggregation.MINUTE}
    if value in {"1m", "minute"}:
        return {"step": 1, "aggregation": BarAggregation.MINUTE}

    # Safe default for unknown frequencies.
    return {"step": 1, "aggregation": BarAggregation.MINUTE}


def _timestamps_to_ns(series: pl.Series, nt: dict[str, Any]) -> list[int]:
    dt_to_unix_nanos = nt["dt_to_unix_nanos"]
    values = series.to_list()
    out: list[int] = []
    for item in values:
        dt = _coerce_datetime(item)
        out.append(int(dt_to_unix_nanos(dt)))
    return out


def _coerce_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    raise BacktestContractError(f"Expected datetime timestamps for Nautilus, got {type(value)}")


def _datetime_to_ns(value: datetime) -> int:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return int(value.timestamp() * 1_000_000_000)


def _import_nautilus() -> dict[str, Any]:
    try:
        import nautilus_trader
        from nautilus_trader.backtest.engine import BacktestEngine  # ty: ignore[unresolved-import]
        from nautilus_trader.config import BacktestEngineConfig, LoggingConfig, StrategyConfig
        from nautilus_trader.core.datetime import dt_to_unix_nanos
        from nautilus_trader.model.currencies import USD
        from nautilus_trader.model.data import (  # ty: ignore[unresolved-import]
            Bar,
            BarSpecification,
            BarType,
        )
        from nautilus_trader.model.enums import AccountType, BarAggregation, OmsType, OrderSide, PriceType, TimeInForce
        from nautilus_trader.model.identifiers import (  # ty: ignore[unresolved-import]
            InstrumentId,
            Symbol,
            Venue,
        )
        from nautilus_trader.model.instruments import CurrencyPair
        from nautilus_trader.model.objects import (  # ty: ignore[unresolved-import]
            Currency,
            Money,
            Price,
            Quantity,
        )
        from nautilus_trader.trading.strategy import Strategy  # ty: ignore[unresolved-import]
    except ImportError as exc:
        raise BacktestEngineUnavailableError(
            "Nautilus engine requested but `nautilus_trader` is not installed. "
            "It is a required dependency of the backtest package; run `uv sync --frozen --group dev`."
        ) from exc

    return {
        "nautilus_version": getattr(nautilus_trader, "__version__", "unknown"),
        "BacktestEngine": BacktestEngine,
        "BacktestEngineConfig": BacktestEngineConfig,
        "LoggingConfig": LoggingConfig,
        "StrategyConfig": StrategyConfig,
        "dt_to_unix_nanos": dt_to_unix_nanos,
        "USD": USD,
        "Bar": Bar,
        "BarSpecification": BarSpecification,
        "BarType": BarType,
        "AccountType": AccountType,
        "BarAggregation": BarAggregation,
        "OmsType": OmsType,
        "OrderSide": OrderSide,
        "PriceType": PriceType,
        "TimeInForce": TimeInForce,
        "InstrumentId": InstrumentId,
        "Symbol": Symbol,
        "Venue": Venue,
        "CurrencyPair": CurrencyPair,
        "Currency": Currency,
        "Money": Money,
        "Price": Price,
        "Quantity": Quantity,
        "Strategy": Strategy,
    }
