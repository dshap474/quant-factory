"""Assemble ExecutionResult and BacktestResult streams from a completed execution run.

Purpose: replay reporting points, compute shortfalls, derive equity/return/
turnover series, and attach the immutable ExecutionResult without legacy
post-processing.

USAGE:
    >>> from backtest.engines.nautilus.assembly import assemble_backtest_result  # doctest: +SKIP
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Sequence

from execution import (
    ExecutionResult,
    InstrumentKey,
    OrderOutcome,
    compute_shortfall,
)

from ...config import BacktestConfig
from ...errors import BacktestContractError, BacktestEngineExecutionError
from ...preparation import instrument_key_wire
from ...projection import LinearPerpetualProjection, build_result_streams, replay_reporting
from ...result import BacktestResult
from .strategy import ExecutionRuntimeState

# --------------------------------------------------------------------------- #
# Public assembly
# --------------------------------------------------------------------------- #


def assemble_backtest_result(
    *,
    state: ExecutionRuntimeState,
    outcomes: Sequence[OrderOutcome],
    config: BacktestConfig,
    nautilus_version: str,
) -> BacktestResult:
    """Build immutable ExecutionResult and reporting BacktestResult streams."""
    prepared = state.prepared
    report_projection = LinearPerpetualProjection(
        initial_cash=(
            prepared.initial_state.cash if prepared.initial_state is not None else Decimal(str(config.initial_capital))
        ),
        instruments=state.specs,
        initial_state=prepared.initial_state,
    )
    holdings, account_path = replay_reporting(
        report_projection,
        marks=state.marks_history,
        funding=prepared.funding_settlements,
        fills=tuple(state.fills),
        reporting_times=prepared.reporting_times,
    )
    shortfalls = _build_shortfalls(state=state, outcomes=tuple(outcomes))
    execution = ExecutionResult(
        targets=prepared.targets,
        target_quantities=tuple(state.target_quantities),
        intents=tuple(state.intents),
        outcomes=tuple(outcomes),
        fills=tuple(state.fills),
        holdings=holdings,
        account_path=account_path,
        funding_settlements=prepared.funding_settlements,
        shortfalls=shortfalls,
        initial_state=prepared.initial_state,
    )
    streams = build_result_streams(
        account_path=account_path,
        fills=tuple(state.fills),
        marks_history=state.marks_history,
        reporting_times=prepared.reporting_times,
        config=config,
        instrument_specs=state.specs,
    )
    return BacktestResult(
        equity=streams.equity,
        benchmark_equity=streams.benchmark_equity,
        price_return=streams.price_return,
        funding_return=streams.funding_return,
        cost_return=streams.cost_return,
        net_return=streams.net_return,
        turnover=streams.turnover,
        metrics=streams.metrics,
        engine_used="nautilus",
        engine_meta={
            "nautilus_version": nautilus_version,
            "execution_model": "deterministic_bar_taker_m4",
            "venue": "BINANCE",
        },
        execution=execution,
    )


# --------------------------------------------------------------------------- #
# Shortfall
# --------------------------------------------------------------------------- #


def _build_shortfalls(
    *,
    state: ExecutionRuntimeState,
    outcomes: tuple[OrderOutcome, ...],
) -> tuple:
    prepared = state.prepared
    marks_by_time = {ts: marks for ts, marks in state.marks_history}
    outcomes_by_target: dict[str, list[OrderOutcome]] = {}
    for outcome in outcomes:
        outcomes_by_target.setdefault(outcome.intent.target_id, []).append(outcome)

    qty_by_key = {(q.target_id, q.instrument): q for q in state.target_quantities}
    shortfalls = []
    for target in prepared.targets:
        schedule = prepared.policy.schedule_times(target.decision_at, target.earliest_execution_at)
        arrival_at = schedule[0]
        terminal_at = schedule[-1]
        for weight in target.weights:
            key = weight.instrument
            tq = qty_by_key.get((target.target_id, key))
            if tq is None:
                raise BacktestEngineExecutionError(
                    f"missing target quantity for {target.target_id}/{instrument_key_wire(key)}"
                )
            target_fills = tuple(
                fill
                for outcome in outcomes_by_target.get(target.target_id, ())
                if outcome.intent.instrument == key
                for fill in outcome.fills
            )
            filled = sum((f.quantity for f in target_fills), Decimal(0))
            intended = tq.delta_quantity
            unfilled = intended - filled
            decision_price = next(ref.price for ref in target.reference_prices if ref.instrument == key)
            arrival_price = _require_mark(marks_by_time, arrival_at, key, "arrival")
            terminal_price = _require_mark(marks_by_time, terminal_at, key, "terminal")
            shortfalls.append(
                compute_shortfall(
                    target_id=target.target_id,
                    instrument=key,
                    intended_quantity=intended,
                    filled_quantity=filled,
                    decision_price=decision_price,
                    arrival_price=arrival_price,
                    terminal_price=terminal_price,
                    fills=target_fills,
                    unfilled_quantity=unfilled,
                    contract_multiplier=state.specs[key].multiplier,
                )
            )
    shortfalls.sort(key=lambda s: (s.target_id, s.instrument.sort_key()))
    return tuple(shortfalls)


def _require_mark(
    marks_by_time: dict[datetime, dict[InstrumentKey, Decimal]],
    ts: datetime,
    key: InstrumentKey,
    label: str,
) -> Decimal:
    marks = marks_by_time.get(ts)
    if marks is None or key not in marks:
        # Latest completed close at or before ts.
        candidates = [t for t in marks_by_time if t <= ts]
        if not candidates:
            raise BacktestContractError(f"missing {label} mark for {instrument_key_wire(key)} at {ts.isoformat()}")
        latest = max(candidates)
        if key not in marks_by_time[latest]:
            raise BacktestContractError(
                f"missing {label} mark for {instrument_key_wire(key)} at/before {ts.isoformat()}"
            )
        return marks_by_time[latest][key]
    return marks[key]
