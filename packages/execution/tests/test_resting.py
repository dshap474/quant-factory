"""Contract tests for engine-neutral resting-limit plans and outcomes.

Purpose: prove OCO structure, full-fill conservation, terminal completeness,
and shared Fill provenance before the backtest matcher is involved.

USAGE:
    uv run --project packages/execution pytest packages/execution/tests/test_resting.py -q
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from helpers import DECISION, make_key

from execution import (
    Fill,
    OrderStatus,
    RestingLimitExecutionResult,
    RestingLimitOrder,
    RestingLimitOutcome,
    RestingLimitPlan,
)

# --------------------------------------------------------------------------- #
# Builders
# --------------------------------------------------------------------------- #


def _order(
    order_id: str,
    *,
    quantity: str = "1",
    limit_price: str = "100",
    oco_group_id: str | None = None,
) -> RestingLimitOrder:
    return RestingLimitOrder(
        order_id=order_id,
        instrument=make_key("BTCUSDT"),
        quantity=Decimal(quantity),
        limit_price=Decimal(limit_price),
        activate_at=DECISION,
        expires_at=DECISION + timedelta(minutes=2),
        oco_group_id=oco_group_id,
    )


def _fill(order: RestingLimitOrder) -> Fill:
    return Fill(
        target_id="plan-1",
        slice_id=order.order_id,
        instrument=order.instrument,
        fill_id=f"{order.order_id}:fill",
        quantity=order.quantity,
        price=order.limit_price,
        fee=Decimal("0.02"),
        fee_currency="USDT",
        filled_at=DECISION + timedelta(minutes=1),
    )


# --------------------------------------------------------------------------- #
# Plan validation
# --------------------------------------------------------------------------- #


def test_valid_two_member_oco_plan() -> None:
    plan = RestingLimitPlan(
        plan_id="plan-1",
        orders=(
            _order("buy", quantity="1", limit_price="99", oco_group_id="entry"),
            _order("sell", quantity="-1", limit_price="101", oco_group_id="entry"),
        ),
        penetration_bps=Decimal("5"),
    )

    assert plan.penetration_bps == Decimal("5")
    assert tuple(order.order_id for order in plan.orders) == ("buy", "sell")


@pytest.mark.parametrize(
    ("orders", "message"),
    [
        ((_order("buy", oco_group_id="entry"),), "exactly two"),
        (
            (
                _order("one", quantity="1", limit_price="99", oco_group_id="entry"),
                _order("two", quantity="1", limit_price="101", oco_group_id="entry"),
            ),
            "opposite signs",
        ),
        (
            (
                _order("buy", quantity="1", limit_price="101", oco_group_id="entry"),
                _order("sell", quantity="-1", limit_price="100", oco_group_id="entry"),
            ),
            "buy limit",
        ),
    ],
)
def test_invalid_oco_structure_fails(
    orders: tuple[RestingLimitOrder, ...],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        RestingLimitPlan(plan_id="plan-1", orders=orders)


# --------------------------------------------------------------------------- #
# Outcome reconciliation
# --------------------------------------------------------------------------- #


def test_filled_outcome_requires_one_complete_fill() -> None:
    order = _order("buy")
    fill = _fill(order)
    outcome = RestingLimitOutcome(
        order=order,
        status=OrderStatus.FILLED,
        fills=(fill,),
        terminal_at=fill.filled_at,
        unfilled_quantity=Decimal("0"),
    )

    assert outcome.fills == (fill,)


def test_canceled_outcome_requires_no_fill_and_complete_remainder() -> None:
    order = _order("buy")
    outcome = RestingLimitOutcome(
        order=order,
        status=OrderStatus.CANCELED,
        fills=(),
        terminal_at=DECISION + timedelta(minutes=1),
        unfilled_quantity=order.quantity,
        reason="ambiguous_double_touch",
    )

    assert outcome.status is OrderStatus.CANCELED


def test_execution_result_requires_exact_outcome_and_fill_coverage() -> None:
    order = _order("buy")
    plan = RestingLimitPlan(plan_id="plan-1", orders=(order,))
    fill = _fill(order)
    outcome = RestingLimitOutcome(
        order=order,
        status=OrderStatus.FILLED,
        fills=(fill,),
        terminal_at=fill.filled_at,
        unfilled_quantity=Decimal("0"),
    )

    result = RestingLimitExecutionResult(
        plan=plan,
        outcomes=(outcome,),
        fills=(fill,),
        holdings=(),
        account_path=(),
        funding_settlements=(),
    )
    assert result.fills == (fill,)

    with pytest.raises(ValueError, match="top-level fills"):
        RestingLimitExecutionResult(
            plan=plan,
            outcomes=(outcome,),
            fills=(),
            holdings=(),
            account_path=(),
            funding_settlements=(),
        )
