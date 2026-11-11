"""A10 invariants for deterministic OHLC resting-limit execution.

Purpose: supplement known answers with terminal conservation, exact accounting,
metamorphic penetration, deterministic ordering, and fingerprint sensitivity.

USAGE:
    uv run pytest packages/platform/backtest/tests/audit/test_a10_resting_limit.py -q
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import polars as pl
from backtest import (
    BacktestConfig,
    BacktestResult,
    PreparedRestingLimitInput,
    prepare_resting_limit_execution,
    run_resting_limit_backtest,
)
from polars.testing import assert_frame_equal

from execution import (
    InstrumentKey,
    InstrumentSpec,
    RestingLimitExecutionResult,
    RestingLimitOrder,
    RestingLimitPlan,
)

# --------------------------------------------------------------------------- #
# Synthetic world
# --------------------------------------------------------------------------- #

T0 = datetime(2024, 2, 1, tzinfo=UTC)
CALENDAR = tuple(T0 + timedelta(minutes=index) for index in range(4))
KEY = InstrumentKey("BINANCE", "BTCUSDT")


def _spec() -> InstrumentSpec:
    return InstrumentSpec(
        key=KEY,
        product="perpetual",
        base_currency="BTC",
        quote_currency="USDT",
        settlement_currency="USDT",
        is_inverse=False,
        multiplier=Decimal("1"),
        price_increment=Decimal("0.01"),
        quantity_increment=Decimal("0.001"),
        min_quantity=Decimal("0.001"),
        max_quantity=Decimal("1000000"),
        min_notional=Decimal("5"),
        max_notional=Decimal("100000000"),
        maker_fee_rate=Decimal("0.0002"),
        taker_fee_rate=Decimal("0.0004"),
    )


def _bars(*, first_low: float = 99.0, first_open: float = 100.0) -> pl.DataFrame:
    prices = (
        (100.0, 101.0, 99.5, 100.0),
        (first_open, 101.0, first_low, 100.0),
        (101.0, 102.0, 100.0, 101.0),
        (102.0, 103.0, 101.0, 102.0),
    )
    return pl.DataFrame(
        [
            {
                "instrument": "BINANCE:BTCUSDT",
                "source_timestamp": timestamp,
                "ts_event": timestamp,
                "ts_init": timestamp,
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
                "volume": 10.0,
            }
            for timestamp, (open_price, high, low, close) in zip(CALENDAR, prices, strict=True)
        ]
    )


def _plan(*, penetration_bps: str = "0", limit: str = "99") -> RestingLimitPlan:
    return RestingLimitPlan(
        plan_id="audit-plan",
        orders=(
            RestingLimitOrder(
                order_id="buy",
                instrument=KEY,
                quantity=Decimal("1"),
                limit_price=Decimal(limit),
                activate_at=CALENDAR[0],
                expires_at=CALENDAR[2],
            ),
        ),
        penetration_bps=Decimal(penetration_bps),
    )


def _prepared(*, plan: RestingLimitPlan | None = None, bars: pl.DataFrame | None = None) -> PreparedRestingLimitInput:
    return prepare_resting_limit_execution(
        plan=plan or _plan(),
        bars=bars if bars is not None else _bars(),
        instrument_specs=(_spec(),),
        execution_calendar=CALENDAR,
        reporting_times=(CALENDAR[0], CALENDAR[-1]),
    )


def _run(*, plan: RestingLimitPlan | None = None, bars: pl.DataFrame | None = None) -> BacktestResult:
    return run_resting_limit_backtest(
        prepared=_prepared(plan=plan, bars=bars),
        config=BacktestConfig(initial_capital=100_000, frequency="1m", metrics=[]),
    )


# --------------------------------------------------------------------------- #
# Conservation and independent known answer
# --------------------------------------------------------------------------- #


def test_terminal_and_quantity_conservation() -> None:
    execution = _run().resting_limit_execution
    assert isinstance(execution, RestingLimitExecutionResult)

    assert len(execution.outcomes) == len(execution.plan.orders) == 1
    assert tuple(fill for outcome in execution.outcomes for fill in outcome.fills) == execution.fills
    outcome = execution.outcomes[0]
    assert sum((fill.quantity for fill in outcome.fills), Decimal(0)) + outcome.unfilled_quantity == Decimal("1")


def test_hand_derived_fee_pnl_and_equity_identity() -> None:
    execution = _run().resting_limit_execution
    assert isinstance(execution, RestingLimitExecutionResult)
    final = execution.account_path[-1]

    # Buy 1 @ 99, maker fee 99 * 0.0002 = 0.0198, final mark 102.
    assert final.cash == Decimal("99999.9802")
    assert final.unrealized_pnl == Decimal("3")
    assert final.equity == Decimal("100002.9802")
    assert final.equity == final.cash + final.unrealized_pnl


# --------------------------------------------------------------------------- #
# Metamorphic and deterministic evidence
# --------------------------------------------------------------------------- #


def test_increasing_penetration_weakly_shrinks_single_order_fill_set() -> None:
    bars = _bars(first_low=98.95)
    loose = _run(plan=_plan(penetration_bps="0"), bars=bars).resting_limit_execution
    strict = _run(plan=_plan(penetration_bps="10"), bars=bars).resting_limit_execution
    assert isinstance(loose, RestingLimitExecutionResult)
    assert isinstance(strict, RestingLimitExecutionResult)
    assert {fill.slice_id for fill in strict.fills} <= {fill.slice_id for fill in loose.fills}


def test_repeated_and_reordered_inputs_are_exactly_deterministic() -> None:
    first_prepared = _prepared()
    reordered_prepared = _prepared(bars=_bars().reverse())
    config = BacktestConfig(initial_capital=100_000, frequency="1m", metrics=[])
    first = run_resting_limit_backtest(prepared=first_prepared, config=config)
    repeated = run_resting_limit_backtest(prepared=reordered_prepared, config=config)

    assert first_prepared.prepared_payload_sha256 == reordered_prepared.prepared_payload_sha256
    assert_frame_equal(first.to_dataframe(), repeated.to_dataframe(), check_exact=True)
    assert first.resting_limit_execution == repeated.resting_limit_execution


def test_fingerprint_changes_for_each_fill_determining_family() -> None:
    baseline = _prepared().prepared_payload_sha256
    changed_limit = _prepared(plan=_plan(limit="98")).prepared_payload_sha256
    changed_penetration = _prepared(plan=_plan(penetration_bps="5")).prepared_payload_sha256
    changed_low = _prepared(bars=_bars(first_low=98.99)).prepared_payload_sha256
    changed_open = _prepared(bars=_bars(first_open=99.5)).prepared_payload_sha256

    assert len({baseline, changed_limit, changed_penetration, changed_low, changed_open}) == 5
