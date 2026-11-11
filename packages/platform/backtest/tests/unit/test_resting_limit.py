"""Known-answer tests for deterministic OHLC resting-limit execution.

Purpose: verify causal activation, touch thresholds, fill price, fee class,
expiry, OCO ambiguity, validation, fingerprints, and public result accounting.

USAGE:
    uv run pytest packages/platform/backtest/tests/unit/test_resting_limit.py -q
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Mapping

import polars as pl
import pytest
from backtest import (
    BacktestConfig,
    BacktestResult,
    PreparedRestingLimitInput,
    prepare_resting_limit_execution,
    prepared_resting_limit_fingerprint,
    run_resting_limit_backtest,
)
from backtest.errors import BacktestContractError, BacktestEngineExecutionError

from execution import (
    InstrumentKey,
    InstrumentSpec,
    OrderStatus,
    RestingLimitExecutionResult,
    RestingLimitOrder,
    RestingLimitPlan,
)

# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

T0 = datetime(2024, 1, 1, tzinfo=UTC)
CALENDAR = tuple(T0 + timedelta(minutes=index) for index in range(4))
KEY = InstrumentKey(venue="BINANCE", symbol="BTCUSDT")
WIRE = "BINANCE:BTCUSDT"


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


def _bars(overrides: Mapping[datetime, tuple[float, float, float, float]] | None = None) -> pl.DataFrame:
    values = overrides or {}
    rows: list[dict[str, object]] = []
    for timestamp in CALENDAR:
        open_price, high, low, close = values.get(timestamp, (100.0, 101.0, 99.5, 100.0))
        rows.append(
            {
                "instrument": WIRE,
                "source_timestamp": timestamp,
                "ts_event": timestamp,
                "ts_init": timestamp,
                "open": open_price,
                "high": high,
                "low": low,
                "close": close,
                "volume": 10.0,
            }
        )
    return pl.DataFrame(rows)


def _order(
    order_id: str = "buy",
    *,
    quantity: str = "1",
    limit: str = "99",
    activate_at: datetime = T0,
    expires_at: datetime = CALENDAR[2],
    oco_group_id: str | None = None,
) -> RestingLimitOrder:
    return RestingLimitOrder(
        order_id=order_id,
        instrument=KEY,
        quantity=Decimal(quantity),
        limit_price=Decimal(limit),
        activate_at=activate_at,
        expires_at=expires_at,
        oco_group_id=oco_group_id,
    )


def _prepare(
    *,
    plan: RestingLimitPlan | None = None,
    bars: pl.DataFrame | None = None,
) -> PreparedRestingLimitInput:
    return prepare_resting_limit_execution(
        plan=plan or RestingLimitPlan(plan_id="plan-1", orders=(_order(),)),
        bars=bars if bars is not None else _bars(),
        instrument_specs=(_spec(),),
        execution_calendar=CALENDAR,
        reporting_times=(CALENDAR[0], CALENDAR[-1]),
    )


def _run(
    *,
    plan: RestingLimitPlan | None = None,
    bars: pl.DataFrame | None = None,
) -> BacktestResult:
    return run_resting_limit_backtest(
        prepared=_prepare(plan=plan, bars=bars),
        config=BacktestConfig(initial_capital=100_000, frequency="1m", metrics=[]),
    )


# --------------------------------------------------------------------------- #
# Known-answer fills and timing
# --------------------------------------------------------------------------- #


def test_exact_buy_boundary_fills_at_limit_after_activation_bar() -> None:
    bars = _bars(
        {
            T0: (100.0, 101.0, 98.0, 100.0),
            CALENDAR[1]: (100.0, 101.0, 99.0, 100.0),
        }
    )
    result = _run(bars=bars)
    execution = result.resting_limit_execution

    assert isinstance(execution, RestingLimitExecutionResult)
    assert execution.outcomes[0].status is OrderStatus.FILLED
    assert execution.fills[0].filled_at == CALENDAR[1]
    assert execution.fills[0].price == Decimal("99")
    assert execution.fills[0].fee == Decimal("0.0198")


def test_activation_candle_touch_is_ignored() -> None:
    bars = _bars(
        {
            T0: (100.0, 101.0, 90.0, 100.0),
            CALENDAR[1]: (100.0, 101.0, 99.5, 100.0),
            CALENDAR[2]: (100.0, 101.0, 99.5, 100.0),
        }
    )
    execution = _run(bars=bars).resting_limit_execution

    assert isinstance(execution, RestingLimitExecutionResult)
    assert execution.outcomes[0].status is OrderStatus.EXPIRED
    assert execution.fills == ()


def test_gap_through_fills_at_limit_and_charges_taker_fee() -> None:
    bars = _bars({CALENDAR[1]: (98.0, 100.0, 97.0, 99.0)})
    execution = _run(bars=bars).resting_limit_execution

    assert isinstance(execution, RestingLimitExecutionResult)
    assert execution.fills[0].price == Decimal("99")
    assert execution.fills[0].fee == Decimal("0.0396")


def test_penetration_threshold_is_inclusive() -> None:
    plan = RestingLimitPlan(
        plan_id="plan-1",
        orders=(_order(limit="99"),),
        penetration_bps=Decimal("10"),
    )
    threshold = 98.901
    bars = _bars(
        {
            CALENDAR[1]: (100.0, 101.0, 98.902, 100.0),
            CALENDAR[2]: (100.0, 101.0, threshold, 100.0),
        }
    )
    execution = _run(plan=plan, bars=bars).resting_limit_execution

    assert isinstance(execution, RestingLimitExecutionResult)
    assert execution.fills[0].filled_at == CALENDAR[2]


def test_sell_touch_is_symmetric() -> None:
    plan = RestingLimitPlan(plan_id="plan-1", orders=(_order("sell", quantity="-1", limit="101"),))
    bars = _bars({CALENDAR[1]: (100.0, 101.0, 99.0, 100.0)})
    execution = _run(plan=plan, bars=bars).resting_limit_execution

    assert isinstance(execution, RestingLimitExecutionResult)
    assert execution.fills[0].quantity == Decimal("-1")
    assert execution.fills[0].price == Decimal("101")
    assert execution.fills[0].fee == Decimal("0.0202")


def test_touch_on_inclusive_expiry_bar_fills() -> None:
    bars = _bars(
        {
            CALENDAR[1]: (100.0, 101.0, 99.5, 100.0),
            CALENDAR[2]: (100.0, 101.0, 99.0, 100.0),
        }
    )
    execution = _run(bars=bars).resting_limit_execution

    assert isinstance(execution, RestingLimitExecutionResult)
    assert execution.outcomes[0].status is OrderStatus.FILLED
    assert execution.fills[0].filled_at == CALENDAR[2]


# --------------------------------------------------------------------------- #
# OCO state machine
# --------------------------------------------------------------------------- #


def _oco_plan() -> RestingLimitPlan:
    return RestingLimitPlan(
        plan_id="plan-1",
        orders=(
            _order("buy", quantity="1", limit="99", oco_group_id="entry"),
            _order("sell", quantity="-1", limit="101", oco_group_id="entry"),
        ),
    )


def test_oco_one_side_touch_fills_and_cancels_peer() -> None:
    bars = _bars({CALENDAR[1]: (100.0, 100.5, 99.0, 100.0)})
    execution = _run(plan=_oco_plan(), bars=bars).resting_limit_execution

    assert isinstance(execution, RestingLimitExecutionResult)
    statuses = {outcome.order.order_id: outcome.status for outcome in execution.outcomes}
    assert statuses == {"buy": OrderStatus.FILLED, "sell": OrderStatus.CANCELED}
    assert execution.ambiguous_double_touch_count == 0


def test_oco_open_through_one_side_resolves_at_taker_fee() -> None:
    bars = _bars({CALENDAR[1]: (98.0, 100.0, 97.5, 99.5)})
    execution = _run(plan=_oco_plan(), bars=bars).resting_limit_execution

    assert isinstance(execution, RestingLimitExecutionResult)
    assert execution.fills[0].slice_id == "buy"
    assert execution.fills[0].fee == Decimal("0.0396")


def test_oco_ambiguous_double_touch_cancels_both_and_counts() -> None:
    bars = _bars({CALENDAR[1]: (100.0, 102.0, 98.0, 100.0)})
    execution = _run(plan=_oco_plan(), bars=bars).resting_limit_execution

    assert isinstance(execution, RestingLimitExecutionResult)
    assert {outcome.status for outcome in execution.outcomes} == {OrderStatus.CANCELED}
    assert execution.fills == ()
    assert execution.ambiguous_double_touch_count == 1


# --------------------------------------------------------------------------- #
# Preparation and fingerprint contracts
# --------------------------------------------------------------------------- #


def test_marketable_at_activation_is_rejected() -> None:
    plan = RestingLimitPlan(plan_id="plan-1", orders=(_order(limit="100"),))
    with pytest.raises(BacktestContractError, match="marketable"):
        _prepare(plan=plan)


def test_missing_calendar_bar_is_rejected() -> None:
    bars = _bars().filter(pl.col("ts_init") != CALENDAR[2])
    with pytest.raises(BacktestContractError, match="cover every"):
        _prepare(bars=bars)


def test_overlapping_non_oco_windows_are_rejected() -> None:
    plan = RestingLimitPlan(
        plan_id="plan-1",
        orders=(
            _order("one", expires_at=CALENDAR[2]),
            _order("two", limit="98", activate_at=CALENDAR[1], expires_at=CALENDAR[3]),
        ),
    )
    with pytest.raises(BacktestContractError, match="overlapping"):
        _prepare(plan=plan)


def test_quantity_increment_violation_is_rejected() -> None:
    plan = RestingLimitPlan(plan_id="plan-1", orders=(_order(quantity="1.0005"),))
    with pytest.raises(BacktestContractError, match="quantity_increment"):
        _prepare(plan=plan)


def test_fingerprint_is_order_invariant_and_fill_sensitive() -> None:
    bars = _bars()
    first = _prepare(bars=bars)
    shuffled = _prepare(bars=bars.reverse())
    changed = _prepare(
        bars=_bars({CALENDAR[1]: (100.0, 101.0, 99.49, 100.0)}),
    )

    assert first.prepared_payload_sha256 == shuffled.prepared_payload_sha256
    assert prepared_resting_limit_fingerprint(first) == first.prepared_payload_sha256
    assert changed.prepared_payload_sha256 != first.prepared_payload_sha256


def test_public_result_keeps_frozen_schema_and_accounting_identity() -> None:
    bars = _bars({CALENDAR[1]: (100.0, 101.0, 99.0, 100.0), CALENDAR[3]: (102.0, 103.0, 101.0, 102.0)})
    result = _run(bars=bars)
    frame = result.to_dataframe()

    assert frame.columns == [
        "equity",
        "benchmark_equity",
        "price_return",
        "funding_return",
        "cost_return",
        "net_return",
        "turnover",
    ]
    assert result.engine_used == "resting_limit"
    assert result.equity[-1] == pytest.approx(100_002.9802, rel=0, abs=1e-9)


def test_run_fails_closed_when_fill_fee_makes_equity_nonpositive() -> None:
    plan = RestingLimitPlan(plan_id="plan-1", orders=(_order(quantity="1000"),))
    bars = _bars({CALENDAR[1]: (100.0, 101.0, 99.0, 99.0)})
    prepared = _prepare(plan=plan, bars=bars)

    with pytest.raises(BacktestEngineExecutionError, match="equity must remain positive"):
        run_resting_limit_backtest(
            prepared=prepared,
            config=BacktestConfig(initial_capital=10, frequency="1m", metrics=[]),
        )
