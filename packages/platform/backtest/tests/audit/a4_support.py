"""A4 deterministic worlds and economic trace projections.

Purpose: keep metamorphic and lifecycle tests on the public prepared execution
path while comparing only the fields each declared relation preserves.

USAGE:
    immediate = core_world("immediate")
    result = run_public_world(immediate)
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal

from backtest import BacktestResult
from backtest.errors import BacktestContractError, BacktestEngineExecutionError

from .a1_world import SyntheticWorld, _run_public_world, input_hash, trace_hash
from .a2_support import CAL, decision, instrument, prices, world
from .a3_support import run as run_a3_packet
from .a3_support import valid_packet, valid_spec

# --------------------------------------------------------------------------- #
# Core deterministic worlds
# --------------------------------------------------------------------------- #


def core_world(kind: str) -> SyntheticWorld:
    """Return the literal immediate or TWAP lifecycle world."""
    if kind == "immediate":
        return world(
            "A4-core-immediate",
            instruments=(instrument("BTC", prices("100", "100", "110"), fee_rate="0.001"),),
            decisions=(decision(0, {"BTC": "0.5"}),),
            reports=(0, 1, 2),
            benchmark="BTCUSDT",
        )
    if kind == "twap":
        return world(
            "A4-core-twap",
            instruments=(
                instrument(
                    "BTC",
                    prices("100", "100", "110", "120"),
                    fee_rate="0.001",
                    quantity_increment="1",
                ),
            ),
            decisions=(decision(0, {"BTC": "0.006"}),),
            reports=(0, 1, 2, 3),
            policy_kind="twap",
            slice_count=3,
            benchmark="BTCUSDT",
        )
    raise ValueError(f"unknown A4 core world: {kind!r}")


def run_public_world(synthetic: SyntheticWorld) -> BacktestResult:
    """Run one world through the public preparation and connector path."""
    return _run_public_world(synthetic)


def replay_fingerprint(kind: str) -> tuple[str, str]:
    """Return canonical input and complete result hashes for one core world."""
    synthetic = core_world(kind)
    return input_hash(synthetic), trace_hash(run_public_world(synthetic))


def failure_then_success_fingerprint(kind: str) -> tuple[str, str]:
    """Reject one invalid target, then fingerprint a clean engine run."""
    packet = valid_packet()
    packet["instrument_specs"] = (valid_spec(min_quantity=Decimal("600")),)
    try:
        run_a3_packet(packet)
    except (BacktestContractError, BacktestEngineExecutionError) as exc:
        if "below min_quantity" not in str(exc):
            raise AssertionError(f"unexpected failure boundary: {exc}") from exc
    else:
        raise AssertionError("invalid target returned a usable result")
    return replay_fingerprint(kind)


# --------------------------------------------------------------------------- #
# Metamorphic projections
# --------------------------------------------------------------------------- #


def shift_world(synthetic: SyntheticWorld, delta: timedelta) -> SyntheticWorld:
    """Shift every timestamp by one constant duration without changing facts."""
    instruments = tuple(
        replace(item, closes={timestamp + delta: price for timestamp, price in item.closes.items()})
        for item in synthetic.instruments
    )
    decisions = tuple(replace(item, decision_at=item.decision_at + delta) for item in synthetic.decisions)
    funding = tuple(replace(item, settled_at=item.settled_at + delta) for item in synthetic.funding)
    return replace(
        synthetic,
        calendar=tuple(timestamp + delta for timestamp in synthetic.calendar),
        instruments=instruments,
        decisions=decisions,
        reporting_times=tuple(timestamp + delta for timestamp in synthetic.reporting_times),
        funding=funding,
    )


def account_economics(result: BacktestResult) -> tuple[tuple[Decimal, ...], ...]:
    """Project account records without absolute timestamps."""
    assert result.execution is not None
    return tuple(
        (
            item.cash,
            item.equity,
            item.realized_pnl,
            item.unrealized_pnl,
            item.fees,
            item.funding,
        )
        for item in result.execution.account_path
    )


def public_series(result: BacktestResult) -> tuple[tuple[float, ...], ...]:
    """Project all public numeric streams in schema order."""
    return tuple(
        tuple(series.to_list())
        for series in (
            result.equity,
            result.benchmark_equity,
            result.price_return,
            result.funding_return,
            result.cost_return,
            result.net_return,
            result.turnover,
        )
    )


def relative_event_times(result: BacktestResult, origin: datetime) -> tuple[tuple[Decimal, ...], ...]:
    """Project ordered event times as seconds from the world's origin."""
    assert result.execution is not None

    def offsets(values: tuple[datetime, ...]) -> tuple[Decimal, ...]:
        return tuple(Decimal(str((value - origin).total_seconds())) for value in values)

    execution = result.execution
    return (
        offsets(tuple(item.decision_at for item in execution.targets)),
        offsets(tuple(item.earliest_execution_at for item in execution.targets)),
        offsets(tuple(item.scheduled_at for item in execution.intents)),
        offsets(tuple(item.expires_at for item in execution.intents)),
        offsets(tuple(item.filled_at for item in execution.fills)),
        offsets(tuple(item.timestamp for item in execution.account_path)),
        offsets(tuple(item.timestamp for item in execution.holdings)),
        offsets(tuple(item.settled_at for item in execution.funding_settlements)),
    )


def instrument_economics(result: BacktestResult, wire: str) -> tuple[tuple[object, ...], ...]:
    """Project one instrument's quantities, fills, and holdings without IDs."""
    assert result.execution is not None
    execution = result.execution
    return (
        tuple(
            (item.current_quantity, item.desired_quantity, item.delta_quantity, item.reference_price)
            for item in execution.target_quantities
            if f"{item.instrument.venue}:{item.instrument.symbol}" == wire
        ),
        tuple(
            (item.quantity, item.price, item.fee, item.fee_currency)
            for item in execution.fills
            if f"{item.instrument.venue}:{item.instrument.symbol}" == wire
        ),
        tuple(
            (item.quantity, item.mark_price, item.notional)
            for item in execution.holdings
            if f"{item.instrument.venue}:{item.instrument.symbol}" == wire
        ),
    )


# --------------------------------------------------------------------------- #
# Frozen constants
# --------------------------------------------------------------------------- #

A4_ORIGIN = CAL[0]
