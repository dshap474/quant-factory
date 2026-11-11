"""On-demand post-trade PNG rendering for prepared execution results.

Purpose: turn one immutable target/instrument execution plus normalized OHLCV
bars into a deterministic two-panel transaction-cost-analysis chart.

USAGE:
    >>> path = render_execution_png(  # doctest: +SKIP
    ...     execution=result.execution,
    ...     bars=prepared.bars,
    ...     instrument_spec=spec,
    ...     output=Path("execution.png"),
    ... )
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Sequence

import polars as pl

from execution import ExecutionResult, InstrumentSpec

from ..errors import BacktestContractError

# --------------------------------------------------------------------------- #
# Internal chart model
# --------------------------------------------------------------------------- #

_BAR_COLUMNS = ("instrument", "ts_init", "open", "high", "low", "close")


@dataclass(frozen=True, slots=True)
class _RawFill:
    filled_at: datetime
    quantity: Decimal
    price: Decimal
    fee: Decimal


@dataclass(frozen=True, slots=True)
class _ExecutionChartData:
    instrument: str
    target_id: str
    decision_at: datetime
    terminal_at: datetime
    decision_price: Decimal
    arrival_price: Decimal
    intended_quantity: Decimal
    multiplier: Decimal
    bars: pl.DataFrame
    planned_times: tuple[datetime, ...]
    planned_notionals: tuple[Decimal, ...]
    actual_times: tuple[datetime, ...]
    actual_notionals: tuple[Decimal, ...]
    fills: tuple[_RawFill, ...]
    fill_vwap: Decimal | None
    completion_ratio: Decimal
    total_fee: Decimal
    shortfall_bps: Decimal
    title: str
    footer: str | None = None


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def render_execution_png(
    *,
    execution: ExecutionResult,
    bars: pl.DataFrame,
    instrument_spec: InstrumentSpec,
    output: Path,
    target_id: str | None = None,
    overwrite: bool = False,
) -> Path:
    """Render one target/instrument execution chart and return its PNG path."""
    if not isinstance(execution, ExecutionResult):
        raise TypeError("execution must be ExecutionResult")
    if not isinstance(instrument_spec, InstrumentSpec):
        raise TypeError("instrument_spec must be InstrumentSpec")
    key = instrument_spec.key
    quantities = [
        value
        for value in execution.target_quantities
        if value.instrument == key and (target_id is None or value.target_id == target_id)
    ]
    if len(quantities) != 1:
        detail = "specify target_id" if target_id is None else "check target_id and instrument_spec"
        raise BacktestContractError(f"execution chart requires exactly one target quantity; {detail}")
    quantity = quantities[0]
    target = next(value for value in execution.targets if value.target_id == quantity.target_id)
    shortfalls = [
        value for value in execution.shortfalls if value.target_id == quantity.target_id and value.instrument == key
    ]
    if len(shortfalls) != 1:
        raise BacktestContractError("execution chart requires exactly one matching shortfall")
    intents = tuple(
        (value.scheduled_at, value.quantity)
        for value in execution.intents
        if value.target_id == quantity.target_id and value.instrument == key
    )
    fills = tuple(
        _RawFill(value.filled_at, value.quantity, value.price, value.fee)
        for value in execution.fills
        if value.target_id == quantity.target_id and value.instrument == key
    )
    terminal_times = [
        value.terminal_at
        for value in execution.outcomes
        if value.intent.target_id == quantity.target_id and value.intent.instrument == key
    ]
    terminal_at = max(terminal_times, default=target.earliest_execution_at)
    data = _assemble_chart_data(
        bars=bars,
        instrument=f"{key.venue}:{key.symbol}",
        target_id=quantity.target_id,
        decision_at=quantity.decision_at,
        terminal_at=terminal_at,
        intended_quantity=quantity.delta_quantity,
        decision_price=shortfalls[0].decision_price,
        arrival_price=shortfalls[0].arrival_price,
        shortfall_total=shortfalls[0].total,
        multiplier=instrument_spec.multiplier,
        intents=intents,
        fills=fills,
        title=f"{key.venue}:{key.symbol} execution",
    )
    from .rendering import render_chart_data

    return render_chart_data(data, output=output, overwrite=overwrite)


# --------------------------------------------------------------------------- #
# Shared semantic assembly
# --------------------------------------------------------------------------- #


def _assemble_chart_data(
    *,
    bars: pl.DataFrame,
    instrument: str,
    target_id: str,
    decision_at: datetime,
    terminal_at: datetime,
    intended_quantity: Decimal,
    decision_price: Decimal,
    arrival_price: Decimal,
    shortfall_total: Decimal,
    multiplier: Decimal,
    intents: Sequence[tuple[datetime, Decimal]],
    fills: Sequence[_RawFill],
    title: str,
    footer: str | None = None,
) -> _ExecutionChartData:
    """Validate raw chart facts and derive exact cumulative trajectories."""
    if terminal_at < decision_at:
        raise BacktestContractError("chart terminal_at must be at or after decision_at")
    if intended_quantity == 0:
        raise BacktestContractError("chart intended_quantity must be non-zero")
    for name, value in (
        ("decision_price", decision_price),
        ("arrival_price", arrival_price),
        ("multiplier", multiplier),
    ):
        if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
            raise BacktestContractError(f"chart {name} must be a finite positive Decimal")
    normalized_bars = _validated_bars(
        bars,
        instrument=instrument,
        decision_at=decision_at,
        terminal_at=terminal_at,
    )
    ordered_intents = tuple(sorted(intents, key=lambda value: value[0]))
    ordered_fills = tuple(sorted(fills, key=lambda value: value.filled_at))
    if any(timestamp < decision_at or timestamp > terminal_at for timestamp, _ in ordered_intents):
        raise BacktestContractError("chart intent timestamp falls outside the chart window")
    if any(fill.filled_at < decision_at or fill.filled_at > terminal_at for fill in ordered_fills):
        raise BacktestContractError("chart fill timestamp falls outside the chart window")

    planned_times = [decision_at]
    planned_notionals = [Decimal(0)]
    planned = Decimal(0)
    for timestamp, quantity in ordered_intents:
        planned += abs(quantity * decision_price * multiplier)
        planned_times.append(timestamp)
        planned_notionals.append(planned)
    if planned_times[-1] < terminal_at:
        planned_times.append(terminal_at)
        planned_notionals.append(planned)

    actual_times = [decision_at]
    actual_notionals = [Decimal(0)]
    actual = Decimal(0)
    filled_quantity = Decimal(0)
    total_fee = Decimal(0)
    weighted_price = Decimal(0)
    absolute_quantity = Decimal(0)
    for fill in ordered_fills:
        actual += abs(fill.quantity * fill.price * multiplier)
        filled_quantity += fill.quantity
        total_fee += fill.fee
        absolute_quantity += abs(fill.quantity)
        weighted_price += abs(fill.quantity) * fill.price
        actual_times.append(fill.filled_at)
        actual_notionals.append(actual)
    if actual_times[-1] < terminal_at:
        actual_times.append(terminal_at)
        actual_notionals.append(actual)
    fill_vwap = weighted_price / absolute_quantity if absolute_quantity else None
    completion = abs(filled_quantity / intended_quantity)
    intended_notional = abs(intended_quantity * decision_price * multiplier)
    shortfall_bps = shortfall_total / intended_notional * Decimal("10000")
    return _ExecutionChartData(
        instrument=instrument,
        target_id=target_id,
        decision_at=decision_at,
        terminal_at=terminal_at,
        decision_price=decision_price,
        arrival_price=arrival_price,
        intended_quantity=intended_quantity,
        multiplier=multiplier,
        bars=normalized_bars,
        planned_times=tuple(planned_times),
        planned_notionals=tuple(planned_notionals),
        actual_times=tuple(actual_times),
        actual_notionals=tuple(actual_notionals),
        fills=ordered_fills,
        fill_vwap=fill_vwap,
        completion_ratio=completion,
        total_fee=total_fee,
        shortfall_bps=shortfall_bps,
        title=title,
        footer=footer,
    )


def _validated_bars(
    bars: pl.DataFrame,
    *,
    instrument: str,
    decision_at: datetime,
    terminal_at: datetime,
) -> pl.DataFrame:
    if not isinstance(bars, pl.DataFrame):
        raise TypeError("bars must be a polars DataFrame")
    missing = [name for name in _BAR_COLUMNS if name not in bars.columns]
    if missing:
        raise BacktestContractError(f"execution chart bars missing columns: {', '.join(missing)}")
    frame = bars.select(_BAR_COLUMNS).filter(
        (pl.col("instrument") == instrument) & pl.col("ts_init").is_between(decision_at, terminal_at, closed="both")
    )
    if frame.is_empty():
        raise BacktestContractError("execution chart has no bars for the selected instrument and window")
    if frame.null_count().sum_horizontal().item() > 0:
        raise BacktestContractError("execution chart bars must not contain nulls")
    if frame.get_column("ts_init").n_unique() != frame.height:
        raise BacktestContractError("execution chart bars must be unique on ts_init")
    frame = frame.sort("ts_init")
    values = frame.select("open", "high", "low", "close").to_numpy()
    if not all(math.isfinite(float(value)) and float(value) > 0 for row in values for value in row):
        raise BacktestContractError("execution chart OHLC values must be finite and positive")
    if any(float(row[1]) < max(float(row[0]), float(row[2]), float(row[3])) for row in values):
        raise BacktestContractError("execution chart bars contain an invalid high")
    if any(float(row[2]) > min(float(row[0]), float(row[1]), float(row[3])) for row in values):
        raise BacktestContractError("execution chart bars contain an invalid low")
    return frame


__all__ = ["render_execution_png"]
