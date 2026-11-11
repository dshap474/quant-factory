"""Independent expected-ledger types and elementary A1 oracle equations.

Purpose: calculate known synthetic outcomes without importing production
execution, strategy, backtest, or Nautilus logic. These functions are the A1
oracle and must remain standard-library-only.

USAGE:
    from .a1_oracle import D, funding_cashflow, target_id
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_FLOOR, Decimal

# --------------------------------------------------------------------------- #
# Scalar helpers
# --------------------------------------------------------------------------- #

D = Decimal
ZERO = D("0")


def target_id(index: int, decision_at: datetime) -> str:
    """Return the frozen input-derived target identity."""
    return f"t{index:04d}:{decision_at.strftime('%Y%m%dT%H%M%S.%fZ')}"


def slice_id(target: str, instrument: str, index: int = 0) -> str:
    """Return the frozen input-derived slice identity."""
    venue, symbol = instrument.split(":", 1)
    return f"{target}:{venue}:{symbol}:{index:04d}"


def floor_lots(value: Decimal, increment: Decimal = D("0.001")) -> Decimal:
    """Round a signed quantity toward zero using elementary Decimal math."""
    steps = (abs(value) / increment).to_integral_value(rounding=ROUND_FLOOR)
    return (steps * increment).copy_sign(value)


def desired_quantity(
    equity: Decimal,
    weight: Decimal,
    price: Decimal,
    multiplier: Decimal = D("1"),
    increment: Decimal = D("0.001"),
) -> Decimal:
    """Return independently sized linear-contract quantity."""
    return floor_lots(equity * weight / (price * multiplier), increment)


def taker_fee(quantity: Decimal, price: Decimal, rate: Decimal) -> Decimal:
    """Return absolute filled notional times the known taker rate."""
    return abs(quantity) * price * rate


def funding_cashflow(
    quantity: Decimal,
    mark: Decimal,
    rate: Decimal,
    multiplier: Decimal = D("1"),
) -> Decimal:
    """Positive rates charge longs and credit shorts."""
    return -quantity * mark * multiplier * rate


def realized_on_close(
    carried_quantity: Decimal,
    closed_quantity: Decimal,
    average_price: Decimal,
    fill_price: Decimal,
    multiplier: Decimal = D("1"),
) -> Decimal:
    """Return signed linear PnL for a reduction of the carried side."""
    side = D("1") if carried_quantity > 0 else D("-1")
    return side * abs(closed_quantity) * (fill_price - average_price) * multiplier


def unrealized(
    quantity: Decimal,
    average_price: Decimal,
    mark: Decimal,
    multiplier: Decimal = D("1"),
) -> Decimal:
    """Return signed linear unrealized PnL."""
    return quantity * (mark - average_price) * multiplier


def weighted_average(
    carried_quantity: Decimal,
    carried_average: Decimal,
    added_quantity: Decimal,
    fill_price: Decimal,
) -> Decimal:
    """Return the average entry after adding on the same side."""
    return (abs(carried_quantity) * carried_average + abs(added_quantity) * fill_price) / (
        abs(carried_quantity) + abs(added_quantity)
    )


# --------------------------------------------------------------------------- #
# Expected ledger records
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class ExpectedTarget:
    target_id: str
    decision_at: datetime
    earliest_execution_at: datetime
    weights: tuple[tuple[str, Decimal], ...]
    cash_weight: Decimal
    references: tuple[tuple[str, Decimal, datetime], ...]


@dataclass(frozen=True, slots=True)
class ExpectedQuantity:
    target_id: str
    instrument: str
    current: Decimal
    desired: Decimal
    delta: Decimal
    reference_price: Decimal
    decision_at: datetime
    earliest_execution_at: datetime
    increment: Decimal = D("0.001")


@dataclass(frozen=True, slots=True)
class ExpectedIntent:
    target_id: str
    slice_id: str
    instrument: str
    quantity: Decimal
    scheduled_at: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class ExpectedFill:
    target_id: str
    slice_id: str
    instrument: str
    quantity: Decimal
    price: Decimal
    fee: Decimal
    fee_currency: str
    filled_at: datetime


@dataclass(frozen=True, slots=True)
class ExpectedOutcome:
    slice_id: str
    status: str
    unfilled: Decimal
    fill_count: int
    reason: str | None = None
    terminal_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ExpectedFunding:
    settlement_id: str
    instrument: str
    settled_at: datetime
    rate: Decimal
    mark_price: Decimal


@dataclass(frozen=True, slots=True)
class ExpectedHolding:
    timestamp: datetime
    instrument: str
    quantity: Decimal
    mark_price: Decimal
    notional: Decimal


@dataclass(frozen=True, slots=True)
class ExpectedAccount:
    timestamp: datetime
    cash: Decimal
    equity: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    fees: Decimal
    funding: Decimal


@dataclass(frozen=True, slots=True)
class ExpectedShortfall:
    target_id: str
    instrument: str
    intended: Decimal
    filled: Decimal
    decision_price: Decimal
    arrival_price: Decimal
    terminal_price: Decimal
    delay: Decimal
    trading: Decimal
    fee: Decimal
    unfilled: Decimal
    total: Decimal


@dataclass(frozen=True, slots=True)
class ExpectedStreams:
    equity: tuple[Decimal, ...]
    benchmark_equity: tuple[Decimal, ...]
    price_return: tuple[Decimal, ...]
    funding_return: tuple[Decimal, ...]
    cost_return: tuple[Decimal, ...]
    net_return: tuple[Decimal, ...]
    turnover: tuple[Decimal, ...]


@dataclass(frozen=True, slots=True)
class ExpectedLedger:
    targets: tuple[ExpectedTarget, ...]
    quantities: tuple[ExpectedQuantity, ...]
    intents: tuple[ExpectedIntent, ...]
    outcomes: tuple[ExpectedOutcome, ...]
    fills: tuple[ExpectedFill, ...]
    funding: tuple[ExpectedFunding, ...]
    holdings: tuple[ExpectedHolding, ...]
    accounts: tuple[ExpectedAccount, ...]
    shortfalls: tuple[ExpectedShortfall, ...] | None = None
    streams: ExpectedStreams | None = None
