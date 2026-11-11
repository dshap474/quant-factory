"""Engine-neutral BacktestResult stream and metric assembly.

Purpose: derive canonical equity, return, turnover, benchmark, and metric
streams from shared account points, fills, marks, and instrument metadata.

USAGE:
    >>> from backtest.projection import build_result_streams  # doctest: +SKIP
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Mapping, Sequence

import numpy as np
import polars as pl

from execution import AccountPoint, Fill, InstrumentKey, InstrumentSpec

from ..config import BacktestConfig
from ..errors import BacktestContractError, BacktestEngineExecutionError
from ..metrics import MetricContext, compute_metrics
from ..preparation import instrument_key_wire

# --------------------------------------------------------------------------- #
# Result bundle
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class ResultStreams:
    """Typed internal series bundle for BacktestResult construction."""

    equity: pl.Series
    benchmark_equity: pl.Series
    price_return: pl.Series
    funding_return: pl.Series
    cost_return: pl.Series
    net_return: pl.Series
    turnover: pl.Series
    metrics: Mapping[str, float]


# --------------------------------------------------------------------------- #
# Public assembly
# --------------------------------------------------------------------------- #


def build_result_streams(
    *,
    account_path: Sequence[AccountPoint],
    fills: Sequence[Fill],
    marks_history: Sequence[tuple[datetime, dict[InstrumentKey, Decimal]]],
    reporting_times: Sequence[datetime],
    config: BacktestConfig,
    instrument_specs: Mapping[InstrumentKey, InstrumentSpec],
) -> ResultStreams:
    """Build canonical result series from an already reconciled event ledger."""
    if len(account_path) != len(reporting_times):
        raise BacktestEngineExecutionError(
            f"account_path length {len(account_path)} != reporting_times {len(reporting_times)}"
        )
    for point, ts in zip(account_path, reporting_times, strict=True):
        if point.timestamp != ts:
            raise BacktestEngineExecutionError("account_path timestamps must match reporting_times")

    equities = [float(point.equity) for point in account_path]
    equity = pl.Series("equity", equities)
    price_rets: list[float] = []
    funding_rets: list[float] = []
    cost_rets: list[float] = []
    net_rets: list[float] = []
    turnovers: list[float] = []

    for previous, current in zip(account_path, account_path[1:], strict=False):
        prior_equity = float(previous.equity)
        if prior_equity == 0:
            raise BacktestEngineExecutionError("prior report equity is zero")
        previous_trading_pnl = float(previous.realized_pnl + previous.unrealized_pnl)
        current_trading_pnl = float(current.realized_pnl + current.unrealized_pnl)
        price_return = (current_trading_pnl - previous_trading_pnl) / prior_equity
        funding_return = float(current.funding - previous.funding) / prior_equity
        cost_return = float(current.fees - previous.fees) / prior_equity
        net_return = price_return + funding_return - cost_return
        equity_return = (float(current.equity) - prior_equity) / prior_equity
        if abs(net_return - equity_return) > 1e-9:
            raise BacktestEngineExecutionError(
                "net_return/equity identity failed at "
                f"{current.timestamp.isoformat()}: net={net_return} equity_delta={equity_return}"
            )
        absolute_notional = _absolute_fill_notional(
            fills,
            instrument_specs=instrument_specs,
            start_exclusive=previous.timestamp,
            end_inclusive=current.timestamp,
        )
        price_rets.append(price_return)
        funding_rets.append(funding_return)
        cost_rets.append(cost_return)
        net_rets.append(net_return)
        turnovers.append(absolute_notional / prior_equity)

    benchmark_prices = _benchmark_prices(
        marks_history=marks_history,
        reporting_times=reporting_times,
        config=config,
        instrument_keys=tuple(instrument_specs),
    )
    if not benchmark_prices:
        raise BacktestContractError("benchmark price series is empty")
    initial = float(config.initial_capital)
    first = benchmark_prices[0]
    benchmark_equity = pl.Series(
        "benchmark_equity",
        [initial * (price / first) for price in benchmark_prices],
    )
    benchmark_returns = np.array(
        [(benchmark_equity[index] / benchmark_equity[index - 1]) - 1.0 for index in range(1, len(benchmark_equity))],
        dtype=np.float64,
    )

    context = MetricContext(
        equity=np.asarray(equities, dtype=np.float64),
        net_return=np.asarray(net_rets, dtype=np.float64),
        price_return=np.asarray(price_rets, dtype=np.float64),
        benchmark_return=benchmark_returns,
        funding_return=np.asarray(funding_rets, dtype=np.float64),
        cost_return=np.asarray(cost_rets, dtype=np.float64),
        turnover=np.asarray(turnovers, dtype=np.float64),
        frequency=config.frequency,
    )
    return ResultStreams(
        equity=equity,
        benchmark_equity=benchmark_equity,
        price_return=pl.Series("price_return", price_rets),
        funding_return=pl.Series("funding_return", funding_rets),
        cost_return=pl.Series("cost_return", cost_rets),
        net_return=pl.Series("net_return", net_rets),
        turnover=pl.Series("turnover", turnovers),
        metrics=compute_metrics(context, list(config.metrics)),
    )


# --------------------------------------------------------------------------- #
# Mechanical helpers
# --------------------------------------------------------------------------- #


def _absolute_fill_notional(
    fills: Sequence[Fill],
    *,
    instrument_specs: Mapping[InstrumentKey, InstrumentSpec],
    start_exclusive: datetime,
    end_inclusive: datetime,
) -> float:
    total = Decimal(0)
    for fill in fills:
        if start_exclusive < fill.filled_at <= end_inclusive:
            spec = instrument_specs[fill.instrument]
            total += abs(fill.quantity) * fill.price * spec.multiplier
    return float(total)


def _benchmark_prices(
    *,
    marks_history: Sequence[tuple[datetime, dict[InstrumentKey, Decimal]]],
    reporting_times: Sequence[datetime],
    config: BacktestConfig,
    instrument_keys: Sequence[InstrumentKey],
) -> list[float]:
    if not instrument_keys:
        raise BacktestContractError("no instruments for benchmark")
    benchmark_key = _resolve_benchmark_key(config.benchmark, instrument_keys)
    marks_by_time = {timestamp: marks for timestamp, marks in marks_history}
    prices: list[float] = []
    for timestamp in reporting_times:
        candidates = [candidate for candidate in marks_by_time if candidate <= timestamp]
        if not candidates:
            raise BacktestContractError(f"no mark at/before report {timestamp.isoformat()}")
        latest = max(candidates)
        marks = marks_by_time[latest]
        if benchmark_key not in marks:
            raise BacktestContractError(
                f"missing benchmark mark for {instrument_key_wire(benchmark_key)} at {latest.isoformat()}"
            )
        prices.append(float(marks[benchmark_key]))
    return prices


def _resolve_benchmark_key(
    benchmark: str | None,
    instrument_keys: Sequence[InstrumentKey],
) -> InstrumentKey:
    if benchmark is None:
        return instrument_keys[0]
    wire_matches = [key for key in instrument_keys if instrument_key_wire(key) == benchmark]
    if len(wire_matches) == 1:
        return wire_matches[0]
    symbol_matches = [key for key in instrument_keys if key.symbol == benchmark]
    if len(symbol_matches) == 1:
        return symbol_matches[0]
    if len(wire_matches) > 1 or len(symbol_matches) > 1:
        raise BacktestContractError(f"ambiguous benchmark identity: {benchmark!r}")
    raise BacktestContractError(f"benchmark not found among instruments: {benchmark!r}")


__all__ = ["ResultStreams", "build_result_streams"]
