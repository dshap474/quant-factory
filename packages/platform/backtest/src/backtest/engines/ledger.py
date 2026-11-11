"""Ordinary portfolio ledger backtest engine.

Deterministic current-equity accounting for explicit ``BacktestConfig(engine="ledger")``.
Nautilus remains the default and the prepared-execution path; this module is a local
opt-in ordinary book, not a framework or plugin registry.

USAGE:
    from backtest import BacktestConfig, run_backtest

    result = run_backtest(
        prices=prices,
        weights=weights,
        config=BacktestConfig(engine="ledger"),
    )
"""

from __future__ import annotations

import numpy as np
import polars as pl

from ..config import BacktestConfig
from ..errors import BacktestContractError, BacktestEngineExecutionError
from ..inputs import prepare_inputs
from ..metrics import MetricContext, compute_metrics
from ..result import BacktestResult, LedgerDetail
from ..returns import compute_benchmark_equity

# --------------------------------------------------------------------------- #
# Public entry
# --------------------------------------------------------------------------- #


def run_ledger_backtest(
    *,
    prices: pl.DataFrame,
    weights: pl.DataFrame,
    funding_rates: pl.DataFrame | None,
    config: BacktestConfig,
    timestamp_col: str,
) -> BacktestResult:
    """Run the ordinary portfolio ledger over aligned price/weight rows.

    Timeline (T rows → T equity points and T−1 return intervals):
    - row ``i`` prices open interval ``[i, i+1]`` with target weights for that interval;
    - portfolio starts all-CASH; scheduled intervals rebalance from pre-trade equity; others hold quantities;
    - the final row is not traded (no following interval).
    """
    inputs = prepare_inputs(
        prices=prices,
        weights=weights,
        funding_rates=funding_rates,
        timestamp_col=timestamp_col,
        allow_inactive_missing_prices=config.allow_inactive_missing_prices,
        rebalance_every_bars=config.rebalance_every_bars,
    )

    asset_cols = list(inputs.assets)
    non_cash_idx = [i for i, name in enumerate(asset_cols) if name != "CASH"]
    if not non_cash_idx:
        raise BacktestContractError("Ledger engine requires at least one non-CASH asset column.")

    price_values = np.asarray(inputs.price_values, dtype=np.float64)
    weight_values = np.asarray(inputs.weight_values, dtype=np.float64)
    funding_values = np.asarray(inputs.funding_values, dtype=np.float64)

    n_rows = price_values.shape[0]
    if n_rows < 2:
        raise BacktestContractError("Ledger engine requires at least two rows to form one interval.")

    risky_prices = price_values[:, non_cash_idx]
    risky_weights = weight_values[:, non_cash_idx]
    if config.allow_inactive_missing_prices:
        benchmark = config.benchmark or config.benchmark_asset
        if benchmark not in asset_cols or benchmark == "CASH":
            raise BacktestContractError("Inactive missing prices require an explicit non-CASH benchmark.")
        if not np.isfinite(price_values[:, asset_cols.index(benchmark)]).all():
            raise BacktestContractError("Benchmark prices must be complete even while the benchmark is unheld.")
    if config.include_funding:
        cash_idx = asset_cols.index("CASH")
        if np.any(funding_values[:, cash_idx] != 0.0):
            raise BacktestContractError(
                "Ledger funding_rates.CASH must be zero; residual cash financing is not modeled."
            )
        risky_funding = funding_values[:, non_cash_idx]
    else:
        risky_funding = np.zeros_like(risky_prices)
    n_intervals = n_rows - 1

    equity = np.empty(n_rows, dtype=np.float64)
    equity[0] = float(config.initial_capital)
    current_notional = np.zeros(len(non_cash_idx), dtype=np.float64)

    price_return = np.empty(n_intervals, dtype=np.float64)
    funding_return = np.empty(n_intervals, dtype=np.float64)
    cost_return = np.empty(n_intervals, dtype=np.float64)
    net_return = np.empty(n_intervals, dtype=np.float64)
    turnover = np.empty(n_intervals, dtype=np.float64)

    cost_rate = float(config.trade_cost_bps) / 10_000.0
    # Opt-in capture of the loop's own per-asset vectors; it never feeds back into the arithmetic.
    detail = config.collect_ledger_detail
    detail_shape = (n_intervals if detail else 0, len(non_cash_idx))
    held, traded, price_flow, funding_flow, marked = (np.zeros(detail_shape, dtype=np.float64) for _ in range(5))

    for i in range(n_intervals):
        p_i = risky_prices[i]
        p_next = risky_prices[i + 1]
        w_i = risky_weights[i]

        e_pre = equity[i]

        target_notional = w_i * e_pre if i % config.rebalance_every_bars == 0 else current_notional
        traded_notional = float(np.abs(target_notional - current_notional).sum())
        cost = traded_notional * cost_rate

        turnover[i] = traded_notional / e_pre
        cost_return[i] = cost / e_pre

        if config.allow_inactive_missing_prices:
            # Validation established zero exposure wherever either mark is absent.
            # Keep original price NaNs; compute returns only for observed pairs.
            asset_rets = np.zeros_like(p_i)
            observed = np.isfinite(p_i) & np.isfinite(p_next)
            asset_rets[observed] = p_next[observed] / p_i[observed] - 1.0
        else:
            asset_rets = (p_next / p_i) - 1.0
        price_pnl = float((target_notional * asset_rets).sum())
        price_return[i] = price_pnl / e_pre

        funding_pnl = float(-(target_notional * risky_funding[i]).sum())
        funding_return[i] = funding_pnl / e_pre

        net = price_return[i] + funding_return[i] - cost_return[i]
        net_return[i] = net
        e_next = e_pre * (1.0 + net)

        if not np.isfinite(e_next) or e_next <= 0.0:
            dominant = _dominant_component(price_pnl=price_pnl, funding_pnl=funding_pnl, cost=cost)
            raise BacktestEngineExecutionError(
                f"Ledger equity exhausted at row {i}: pre-trade equity={e_pre}, "
                f"next equity={e_next}, dominant component={dominant}"
            )

        if detail:
            held[i], traded[i] = target_notional, target_notional - current_notional
            price_flow[i], funding_flow[i] = target_notional * asset_rets, -(target_notional * risky_funding[i])

        current_notional = target_notional * (1.0 + asset_rets)
        equity[i + 1] = e_next
        if detail:
            marked[i] = current_notional

    non_cash_names = [asset_cols[i] for i in non_cash_idx]
    benchmark_equity = compute_benchmark_equity(
        prices_df=inputs.prices,
        asset_cols=non_cash_names,
        initial_capital=config.initial_capital,
        benchmark=config.benchmark or config.benchmark_asset,
    )
    benchmark_values = benchmark_equity.to_numpy().astype(np.float64)
    benchmark_return = np.diff(benchmark_values) / benchmark_values[:-1]

    metrics = compute_metrics(
        MetricContext(
            equity=equity,
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
        equity=pl.Series("equity", equity),
        benchmark_equity=benchmark_equity,
        price_return=pl.Series("price_return", price_return),
        funding_return=pl.Series("funding_return", funding_return),
        cost_return=pl.Series("cost_return", cost_return),
        net_return=pl.Series("net_return", net_return),
        turnover=pl.Series("turnover", turnover),
        metrics=metrics,
        engine_used="ledger",
        engine_meta={
            "accounting": "ordinary_ledger",
            "turnover": "gross_non_cash",
            "rows": n_rows,
            "intervals": n_intervals,
            "allow_inactive_missing_prices": config.allow_inactive_missing_prices,
            "rebalance_every_bars": config.rebalance_every_bars,
        },
        ledger_detail=_ledger_detail(
            timestamps=inputs.timestamps, assets=non_cash_names, prices=risky_prices, equity=equity,
            held=held, traded=traded, price_flow=price_flow, funding_flow=funding_flow, marked=marked,
            cost_rate=cost_rate,
        ) if detail else None,
    )


def _ledger_detail(
    *,
    timestamps: pl.Series,
    assets: list[str],
    prices: np.ndarray,
    equity: np.ndarray,
    held: np.ndarray,
    traded: np.ndarray,
    price_flow: np.ndarray,
    funding_flow: np.ndarray,
    marked: np.ndarray,
    cost_rate: float,
) -> LedgerDetail:
    """Long frames of the captured interval vectors; see ``LedgerDetail`` for the schema."""
    n_intervals, k = held.shape
    start, end = prices[:-1], prices[1:]
    quantity = np.divide(held, start, out=np.zeros_like(held), where=held != 0)
    trade_quantity = np.divide(traded, start, out=np.zeros_like(traded), where=traded != 0)
    row = np.repeat(np.arange(n_intervals), k)
    asset = pl.Series("asset", assets).gather(np.tile(np.arange(k), n_intervals))

    def frame(at: pl.Series, columns: dict[str, np.ndarray]) -> pl.DataFrame:
        return pl.DataFrame({"timestamp": at.gather(row), "asset": asset,
                             **{name: values.reshape(-1) for name, values in columns.items()}})

    starts, ends = timestamps.slice(0, n_intervals).alias("timestamp"), timestamps.slice(1).alias("timestamp")
    positions = frame(starts, dict(quantity=quantity, price=start, notional=held,
                                   weight=held / equity[:-1, None])).filter(pl.col("notional") != 0)
    trades = frame(starts, dict(quantity=trade_quantity, price=start, notional=traded,
                                fee=np.abs(traded) * cost_rate)).filter(pl.col("notional") != 0)
    trades = trades.select("timestamp", "asset", pl.when(pl.col("notional") > 0).then(pl.lit("buy"))
                           .otherwise(pl.lit("sell")).alias("side"), "quantity", "price", "notional", "fee")
    attribution = frame(ends, dict(price=end, quantity=quantity, weight=marked / equity[1:, None],
                                   price_pnl=price_flow, funding_pnl=funding_flow,
                                   fees=np.abs(traded) * cost_rate)).with_columns(pl.col("price").fill_nan(None))
    return LedgerDetail(positions=positions, trades=trades, asset_attribution=attribution)


def _dominant_component(*, price_pnl: float, funding_pnl: float, cost: float) -> str:
    components = {
        "price": price_pnl,
        "funding": funding_pnl,
        "cost": -cost,
    }
    return max(components, key=lambda key: abs(components[key]))
