"""Engine-neutral contracts for deterministic resting-limit research.

Purpose: represent explicit signed resting orders, two-member OCO plans, and
terminal results without depending on a backtest engine or market-data shape.

USAGE:
    >>> from decimal import Decimal
    >>> from execution import RestingLimitPlan
    >>> RestingLimitPlan(plan_id="p1", orders=(), penetration_bps=Decimal("0"))
    Traceback (most recent call last):
    ...
    ValueError: orders must be non-empty
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from execution._checks import require_finite_decimal, require_non_empty_str, require_unique_ids, require_utc
from execution.events import (
    AccountPoint,
    Fill,
    FundingSettlement,
    HoldingPoint,
    OrderStatus,
)
from execution.instruments import InstrumentKey
from execution.targets import InitialAccountState

# --------------------------------------------------------------------------- #
# Orders and plans
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class RestingLimitOrder:
    """One signed full-fill resting limit order with an inclusive expiry."""

    order_id: str
    instrument: InstrumentKey
    quantity: Decimal
    limit_price: Decimal
    activate_at: datetime
    expires_at: datetime
    oco_group_id: str | None = None

    def __post_init__(self) -> None:
        require_non_empty_str(self.order_id, "order_id")
        if not isinstance(self.instrument, InstrumentKey):
            raise TypeError("instrument must be InstrumentKey")
        object.__setattr__(self, "quantity", require_finite_decimal(self.quantity, "quantity", non_zero=True))
        object.__setattr__(
            self,
            "limit_price",
            require_finite_decimal(self.limit_price, "limit_price", positive=True),
        )
        require_utc(self.activate_at, "activate_at")
        require_utc(self.expires_at, "expires_at")
        if self.expires_at <= self.activate_at:
            raise ValueError("expires_at must be strictly after activate_at")
        if self.oco_group_id is not None:
            require_non_empty_str(self.oco_group_id, "oco_group_id")


@dataclass(frozen=True, slots=True)
class RestingLimitPlan:
    """Atomic collection of deterministic resting orders and touch penetration."""

    plan_id: str
    orders: tuple[RestingLimitOrder, ...]
    penetration_bps: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        require_non_empty_str(self.plan_id, "plan_id")
        object.__setattr__(self, "orders", tuple(self.orders))
        if not self.orders:
            raise ValueError("orders must be non-empty")
        if any(not isinstance(order, RestingLimitOrder) for order in self.orders):
            raise TypeError("orders must contain RestingLimitOrder values")
        require_unique_ids((order.order_id for order in self.orders), "order_id")
        object.__setattr__(
            self,
            "penetration_bps",
            require_finite_decimal(self.penetration_bps, "penetration_bps", non_negative=True),
        )
        _validate_oco_groups(self.orders)


# --------------------------------------------------------------------------- #
# Outcomes and aggregate result
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class RestingLimitOutcome:
    """Exactly one terminal outcome for one resting order."""

    order: RestingLimitOrder
    status: OrderStatus
    fills: tuple[Fill, ...]
    terminal_at: datetime
    unfilled_quantity: Decimal
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.order, RestingLimitOrder):
            raise TypeError("order must be RestingLimitOrder")
        if self.status not in (OrderStatus.FILLED, OrderStatus.EXPIRED, OrderStatus.CANCELED):
            raise ValueError("resting outcomes require FILLED, EXPIRED, or CANCELED status")
        object.__setattr__(self, "fills", tuple(self.fills))
        if any(not isinstance(fill, Fill) for fill in self.fills):
            raise TypeError("fills must contain Fill values")
        require_unique_ids((fill.fill_id for fill in self.fills), "fill_id")
        require_utc(self.terminal_at, "terminal_at")
        if not (self.order.activate_at < self.terminal_at <= self.order.expires_at):
            raise ValueError("terminal_at must be after activation and no later than expiry")
        object.__setattr__(
            self,
            "unfilled_quantity",
            require_finite_decimal(self.unfilled_quantity, "unfilled_quantity"),
        )
        if self.reason is not None:
            require_non_empty_str(self.reason, "reason")

        for fill in self.fills:
            if (fill.slice_id, fill.instrument) != (self.order.order_id, self.order.instrument):
                raise ValueError("fill provenance must match order")
            if fill.filled_at != self.terminal_at:
                raise ValueError("resting fill timestamp must equal terminal_at")
            if fill.quantity != self.order.quantity:
                raise ValueError("resting fill quantity must equal the complete order quantity")

        if self.status is OrderStatus.FILLED:
            if len(self.fills) != 1 or self.unfilled_quantity != 0:
                raise ValueError("FILLED requires exactly one fill and zero unfilled quantity")
        elif self.fills or self.unfilled_quantity != self.order.quantity:
            raise ValueError(f"{self.status.value} requires no fills and the complete unfilled quantity")


@dataclass(frozen=True, slots=True)
class RestingLimitExecutionResult:
    """Terminal-complete resting-order result using shared accounting DTOs."""

    plan: RestingLimitPlan
    outcomes: tuple[RestingLimitOutcome, ...]
    fills: tuple[Fill, ...]
    holdings: tuple[HoldingPoint, ...]
    account_path: tuple[AccountPoint, ...]
    funding_settlements: tuple[FundingSettlement, ...]
    initial_state: InitialAccountState | None = None
    ambiguous_double_touch_count: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.plan, RestingLimitPlan):
            raise TypeError("plan must be RestingLimitPlan")
        for name, expected_type in (
            ("outcomes", RestingLimitOutcome),
            ("fills", Fill),
            ("holdings", HoldingPoint),
            ("account_path", AccountPoint),
            ("funding_settlements", FundingSettlement),
        ):
            values = tuple(getattr(self, name))
            object.__setattr__(self, name, values)
            if any(not isinstance(value, expected_type) for value in values):
                raise TypeError(f"{name} must contain {expected_type.__name__} values")
        if self.initial_state is not None and not isinstance(self.initial_state, InitialAccountState):
            raise TypeError("initial_state must be InitialAccountState or None")
        if not isinstance(self.ambiguous_double_touch_count, int) or self.ambiguous_double_touch_count < 0:
            raise ValueError("ambiguous_double_touch_count must be a non-negative integer")

        order_by_id = {order.order_id: order for order in self.plan.orders}
        outcome_by_id = {outcome.order.order_id: outcome for outcome in self.outcomes}
        if len(outcome_by_id) != len(self.outcomes) or set(outcome_by_id) != set(order_by_id):
            raise ValueError("outcomes must contain exactly one terminal outcome per order")
        if any(outcome.order != order_by_id[order_id] for order_id, outcome in outcome_by_id.items()):
            raise ValueError("outcome order must match the planned order")

        require_unique_ids((fill.fill_id for fill in self.fills), "fill_id")
        outcome_fills = tuple(fill for outcome in self.outcomes for fill in outcome.fills)
        require_unique_ids((fill.fill_id for fill in outcome_fills), "outcome fill_id")
        if {fill.fill_id: fill for fill in outcome_fills} != {fill.fill_id: fill for fill in self.fills}:
            raise ValueError("top-level fills must exactly match outcome fills")
        if any(fill.target_id != self.plan.plan_id for fill in self.fills):
            raise ValueError("fill target_id must equal plan_id")
        require_unique_ids((item.settlement_id for item in self.funding_settlements), "settlement_id")


# --------------------------------------------------------------------------- #
# Structural validation
# --------------------------------------------------------------------------- #


def _validate_oco_groups(orders: tuple[RestingLimitOrder, ...]) -> None:
    groups: dict[str, list[RestingLimitOrder]] = {}
    for order in orders:
        if order.oco_group_id is not None:
            groups.setdefault(order.oco_group_id, []).append(order)

    for group_id, members in groups.items():
        if len(members) != 2:
            raise ValueError(f"OCO group {group_id!r} must contain exactly two orders")
        left, right = members
        if left.instrument != right.instrument:
            raise ValueError(f"OCO group {group_id!r} orders must share one instrument")
        if (left.activate_at, left.expires_at) != (right.activate_at, right.expires_at):
            raise ValueError(f"OCO group {group_id!r} orders must share one lifecycle window")
        if (left.quantity > 0) == (right.quantity > 0):
            raise ValueError(f"OCO group {group_id!r} orders must have opposite signs")
        buy = left if left.quantity > 0 else right
        sell = right if right.quantity < 0 else left
        if buy.limit_price >= sell.limit_price:
            raise ValueError(f"OCO group {group_id!r} buy limit must be below sell limit")


__all__ = [
    "RestingLimitExecutionResult",
    "RestingLimitOrder",
    "RestingLimitOutcome",
    "RestingLimitPlan",
]
