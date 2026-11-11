"""Immutable execution intents, terminal outcomes, and result projections.

Purpose: represent the engine-neutral event/result boundary while enforcing
IOC timing, signed quantity conservation, identity uniqueness, and account
reconciliation invariants.

USAGE:
    >>> from execution.events import OrderStatus
    >>> OrderStatus.FILLED.value
    'FILLED'
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Iterable

from execution._checks import require_finite_decimal, require_non_empty_str, require_unique_ids, require_utc
from execution.instruments import InstrumentKey
from execution.targets import InitialAccountState, PortfolioTarget, TargetQuantity

# --------------------------------------------------------------------------- #
# Order lifecycle
# --------------------------------------------------------------------------- #


class OrderStatus(StrEnum):
    """Terminal engine-neutral order lifecycle projection."""

    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    CANCELED = "CANCELED"


@dataclass(frozen=True, slots=True)
class SliceIntent:
    """Market-taker IOC intent for one instrument slice."""

    target_id: str
    slice_id: str
    instrument: InstrumentKey
    quantity: Decimal
    scheduled_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        require_non_empty_str(self.target_id, "target_id")
        require_non_empty_str(self.slice_id, "slice_id")
        if not isinstance(self.instrument, InstrumentKey):
            raise TypeError("instrument must be InstrumentKey")
        object.__setattr__(self, "quantity", require_finite_decimal(self.quantity, "quantity", non_zero=True))
        require_utc(self.scheduled_at, "scheduled_at")
        require_utc(self.expires_at, "expires_at")
        if self.expires_at < self.scheduled_at:
            raise ValueError("expires_at must be at or after scheduled_at")


@dataclass(frozen=True, slots=True)
class Fill:
    """Accepted fill projection; signed fee is positive charge, negative rebate."""

    target_id: str
    slice_id: str
    instrument: InstrumentKey
    fill_id: str
    quantity: Decimal
    price: Decimal
    fee: Decimal
    fee_currency: str
    filled_at: datetime

    def __post_init__(self) -> None:
        for name in ("target_id", "slice_id", "fill_id", "fee_currency"):
            require_non_empty_str(getattr(self, name), name)
        if not isinstance(self.instrument, InstrumentKey):
            raise TypeError("instrument must be InstrumentKey")
        object.__setattr__(self, "quantity", require_finite_decimal(self.quantity, "quantity", non_zero=True))
        object.__setattr__(self, "price", require_finite_decimal(self.price, "price", positive=True))
        object.__setattr__(self, "fee", require_finite_decimal(self.fee, "fee"))
        require_utc(self.filled_at, "filled_at")


@dataclass(frozen=True, slots=True)
class OrderOutcome:
    """Terminal projection of exactly one bounded IOC slice."""

    intent: SliceIntent
    status: OrderStatus
    fills: tuple[Fill, ...]
    terminal_at: datetime
    unfilled_quantity: Decimal
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.intent, SliceIntent):
            raise TypeError("intent must be SliceIntent")
        if not isinstance(self.status, OrderStatus):
            raise TypeError("status must be OrderStatus")
        object.__setattr__(self, "fills", tuple(self.fills))
        if any(not isinstance(fill, Fill) for fill in self.fills):
            raise TypeError("fills must contain Fill values")
        require_unique_ids((fill.fill_id for fill in self.fills), "fill_id")
        require_utc(self.terminal_at, "terminal_at")
        object.__setattr__(
            self,
            "unfilled_quantity",
            require_finite_decimal(self.unfilled_quantity, "unfilled_quantity"),
        )
        if self.reason is not None:
            require_non_empty_str(self.reason, "reason")
        if not (self.intent.scheduled_at <= self.terminal_at <= self.intent.expires_at):
            raise ValueError("terminal_at must be inside the intent window")

        for fill in self.fills:
            if (fill.target_id, fill.slice_id, fill.instrument) != (
                self.intent.target_id,
                self.intent.slice_id,
                self.intent.instrument,
            ):
                raise ValueError("fill provenance must match intent")
            if not (self.intent.scheduled_at <= fill.filled_at <= self.terminal_at):
                raise ValueError("fill timestamp must be inside the intent window and no later than terminal_at")
            if not _same_sign(fill.quantity, self.intent.quantity):
                raise ValueError("fill quantity must have the same sign as intent quantity")
        if self.unfilled_quantity != 0 and not _same_sign(self.unfilled_quantity, self.intent.quantity):
            raise ValueError("unfilled quantity must have the same sign as intent quantity")

        filled = sum((fill.quantity for fill in self.fills), Decimal(0))
        if filled + self.unfilled_quantity != self.intent.quantity:
            raise ValueError("filled + unfilled quantity must equal intent quantity")
        if self.status is OrderStatus.FILLED and (not self.fills or self.unfilled_quantity != 0):
            raise ValueError("FILLED requires fills and zero unfilled quantity")
        if self.status in (OrderStatus.EXPIRED, OrderStatus.REJECTED, OrderStatus.CANCELED) and self.fills:
            raise ValueError(f"{self.status.value} outcomes must have no fills")
        if self.status is OrderStatus.PARTIALLY_FILLED and (not self.fills or self.unfilled_quantity == 0):
            raise ValueError("PARTIALLY_FILLED requires fills and a non-zero terminal remainder")


# --------------------------------------------------------------------------- #
# Accounting events and projections
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class FundingSettlement:
    """Explicit project funding cash event."""

    settlement_id: str
    instrument: InstrumentKey
    settled_at: datetime
    rate: Decimal
    mark_price: Decimal

    def __post_init__(self) -> None:
        require_non_empty_str(self.settlement_id, "settlement_id")
        if not isinstance(self.instrument, InstrumentKey):
            raise TypeError("instrument must be InstrumentKey")
        require_utc(self.settled_at, "settled_at")
        object.__setattr__(self, "rate", require_finite_decimal(self.rate, "rate"))
        object.__setattr__(self, "mark_price", require_finite_decimal(self.mark_price, "mark_price", positive=True))


@dataclass(frozen=True, slots=True)
class HoldingPoint:
    """Realized event-ordered holdings projection."""

    timestamp: datetime
    instrument: InstrumentKey
    quantity: Decimal
    mark_price: Decimal
    notional: Decimal

    def __post_init__(self) -> None:
        require_utc(self.timestamp, "timestamp")
        if not isinstance(self.instrument, InstrumentKey):
            raise TypeError("instrument must be InstrumentKey")
        object.__setattr__(self, "quantity", require_finite_decimal(self.quantity, "quantity"))
        object.__setattr__(self, "mark_price", require_finite_decimal(self.mark_price, "mark_price", positive=True))
        object.__setattr__(self, "notional", require_finite_decimal(self.notional, "notional"))


@dataclass(frozen=True, slots=True)
class AccountPoint:
    """Reporting projection derived from the event ledger."""

    timestamp: datetime
    cash: Decimal
    equity: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    fees: Decimal
    funding: Decimal

    def __post_init__(self) -> None:
        require_utc(self.timestamp, "timestamp")
        for name in ("cash", "realized_pnl", "unrealized_pnl", "funding"):
            object.__setattr__(self, name, require_finite_decimal(getattr(self, name), name))
        equity = require_finite_decimal(self.equity, "equity")
        if equity <= 0:
            raise ValueError(f"equity must remain positive, got {equity}")
        object.__setattr__(self, "equity", equity)
        object.__setattr__(self, "fees", require_finite_decimal(self.fees, "fees"))
        if self.equity != self.cash + self.unrealized_pnl:
            raise ValueError("equity must equal cash + unrealized_pnl")


@dataclass(frozen=True, slots=True)
class Shortfall:
    """Signed implementation shortfall for one target instrument."""

    target_id: str
    instrument: InstrumentKey
    intended_quantity: Decimal
    filled_quantity: Decimal
    decision_price: Decimal
    arrival_price: Decimal
    terminal_price: Decimal
    delay: Decimal
    trading: Decimal
    fee: Decimal
    unfilled: Decimal
    total: Decimal

    def __post_init__(self) -> None:
        require_non_empty_str(self.target_id, "target_id")
        if not isinstance(self.instrument, InstrumentKey):
            raise TypeError("instrument must be InstrumentKey")
        for name in ("intended_quantity", "filled_quantity", "delay", "trading", "unfilled", "total"):
            object.__setattr__(self, name, require_finite_decimal(getattr(self, name), name))
        object.__setattr__(self, "fee", require_finite_decimal(self.fee, "fee"))
        for name in ("decision_price", "arrival_price", "terminal_price"):
            object.__setattr__(self, name, require_finite_decimal(getattr(self, name), name, positive=True))
        if self.delay + self.trading + self.fee + self.unfilled != self.total:
            raise ValueError("shortfall components must reconcile to total")


# --------------------------------------------------------------------------- #
# Aggregate result
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    """Final immutable execution result with cross-ledger reconciliation."""

    targets: tuple[PortfolioTarget, ...]
    target_quantities: tuple[TargetQuantity, ...]
    intents: tuple[SliceIntent, ...]
    outcomes: tuple[OrderOutcome, ...]
    fills: tuple[Fill, ...]
    holdings: tuple[HoldingPoint, ...]
    account_path: tuple[AccountPoint, ...]
    funding_settlements: tuple[FundingSettlement, ...]
    shortfalls: tuple[Shortfall, ...]
    initial_state: InitialAccountState | None = None

    def __post_init__(self) -> None:
        tuple_fields = (
            "targets",
            "target_quantities",
            "intents",
            "outcomes",
            "fills",
            "holdings",
            "account_path",
            "funding_settlements",
            "shortfalls",
        )
        for name in tuple_fields:
            object.__setattr__(self, name, tuple(getattr(self, name)))
        if self.initial_state is not None and not isinstance(self.initial_state, InitialAccountState):
            raise TypeError("initial_state must be InitialAccountState or None")
        require_unique_ids((target.target_id for target in self.targets), "target_id")
        require_unique_ids((intent.slice_id for intent in self.intents), "slice_id")
        require_unique_ids((fill.fill_id for fill in self.fills), "fill_id")
        require_unique_funding(self.funding_settlements)

        target_ids = {target.target_id for target in self.targets}
        if any(quantity.target_id not in target_ids for quantity in self.target_quantities):
            raise ValueError("target quantity references an unknown target")
        if any(intent.target_id not in target_ids for intent in self.intents):
            raise ValueError("intent references an unknown target")
        if any(shortfall.target_id not in target_ids for shortfall in self.shortfalls):
            raise ValueError("shortfall references an unknown target")
        require_unique_ids(
            (
                f"{quantity.target_id}:{quantity.instrument.venue}:{quantity.instrument.symbol}"
                for quantity in self.target_quantities
            ),
            "target quantity",
        )
        expected_quantities = {
            (target.target_id, weight.instrument) for target in self.targets for weight in target.weights
        }
        actual_quantities = {(quantity.target_id, quantity.instrument) for quantity in self.target_quantities}
        if actual_quantities != expected_quantities:
            raise ValueError("target quantities must cover every target instrument exactly once")
        require_unique_ids(
            (
                f"{shortfall.target_id}:{shortfall.instrument.venue}:{shortfall.instrument.symbol}"
                for shortfall in self.shortfalls
            ),
            "shortfall",
        )
        intent_by_id = {intent.slice_id: intent for intent in self.intents}
        if {outcome.intent.slice_id for outcome in self.outcomes} != set(intent_by_id):
            raise ValueError("outcomes must contain exactly one terminal outcome per intent")
        require_unique_ids((outcome.intent.slice_id for outcome in self.outcomes), "outcome slice_id")
        if any(outcome.intent != intent_by_id[outcome.intent.slice_id] for outcome in self.outcomes):
            raise ValueError("outcome intent must match the planned intent")
        outcome_fills = tuple(fill for outcome in self.outcomes for fill in outcome.fills)
        require_unique_ids((fill.fill_id for fill in outcome_fills), "outcome fill_id")
        if {fill.fill_id: fill for fill in outcome_fills} != {fill.fill_id: fill for fill in self.fills}:
            raise ValueError("top-level fills must exactly match outcome fills")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _same_sign(left: Decimal, right: Decimal) -> bool:
    return (left > 0) == (right > 0)


def require_unique_funding(settlements: Iterable[FundingSettlement]) -> None:
    """Reject duplicate funding IDs or instrument/timestamp events."""
    values = tuple(settlements)
    require_unique_ids((settlement.settlement_id for settlement in values), "settlement_id")
    require_unique_ids(
        (f"{settlement.instrument.identity()}:{settlement.settled_at.isoformat()}" for settlement in values),
        "instrument settlement timestamp",
    )
