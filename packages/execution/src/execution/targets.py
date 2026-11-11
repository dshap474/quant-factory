"""Immutable portfolio targets, account snapshots, and sized quantities.

Purpose: retain decision provenance and validate the complete atomic inputs used
by engine-neutral sizing and order planning.

USAGE:
    >>> from execution.targets import PortfolioTarget, TargetQuantity
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from execution._checks import (
    WEIGHT_SUM_TOLERANCE,
    require_finite_decimal,
    require_non_empty_str,
    require_unique_ids,
    require_utc,
)
from execution.instruments import InstrumentKey

# --------------------------------------------------------------------------- #
# Target inputs
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class TargetWeight:
    """One non-CASH desired portfolio weight."""

    instrument: InstrumentKey
    weight: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.instrument, InstrumentKey):
            raise TypeError("instrument must be InstrumentKey")
        object.__setattr__(self, "weight", require_finite_decimal(self.weight, "weight"))


@dataclass(frozen=True, slots=True)
class ReferencePrice:
    """Fully observed reference or mark price for one instrument."""

    instrument: InstrumentKey
    price: Decimal
    observed_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.instrument, InstrumentKey):
            raise TypeError("instrument must be InstrumentKey")
        object.__setattr__(self, "price", require_finite_decimal(self.price, "price", positive=True))
        require_utc(self.observed_at, "observed_at")


@dataclass(frozen=True, slots=True)
class PortfolioTarget:
    """Atomic translation of one original StrategyWeights decision row."""

    target_id: str
    decision_at: datetime
    earliest_execution_at: datetime
    weights: tuple[TargetWeight, ...]
    cash_weight: Decimal
    reference_prices: tuple[ReferencePrice, ...]

    def __post_init__(self) -> None:
        require_non_empty_str(self.target_id, "target_id")
        require_utc(self.decision_at, "decision_at")
        require_utc(self.earliest_execution_at, "earliest_execution_at")
        if self.decision_at >= self.earliest_execution_at:
            raise ValueError("decision_at must be strictly before earliest_execution_at")
        object.__setattr__(self, "weights", tuple(self.weights))
        object.__setattr__(self, "reference_prices", tuple(self.reference_prices))
        object.__setattr__(self, "cash_weight", require_finite_decimal(self.cash_weight, "cash_weight"))
        if not self.weights:
            raise ValueError("weights must contain at least one instrument")
        if any(not isinstance(weight, TargetWeight) for weight in self.weights):
            raise TypeError("weights must contain TargetWeight values")
        if any(not isinstance(price, ReferencePrice) for price in self.reference_prices):
            raise TypeError("reference_prices must contain ReferencePrice values")

        weight_keys = [weight.instrument for weight in self.weights]
        require_unique_ids((key.identity() for key in weight_keys), "weight instrument")
        total = self.cash_weight + sum((weight.weight for weight in self.weights), Decimal(0))
        if abs(total - Decimal(1)) > WEIGHT_SUM_TOLERANCE:
            raise ValueError(f"weights plus cash_weight must equal 1 within {WEIGHT_SUM_TOLERANCE}; got {total}")

        references = {price.instrument: price for price in self.reference_prices}
        if len(references) != len(self.reference_prices):
            raise ValueError("reference_prices must be unique per instrument")
        if set(references) != set(weight_keys):
            missing = set(weight_keys) - set(references)
            extra = set(references) - set(weight_keys)
            if missing:
                raise ValueError(f"missing reference price for {_sorted_key_names(missing)}")
            raise ValueError(f"reference_prices contain instruments absent from weights: {_sorted_key_names(extra)}")
        observed_times = {price.observed_at for price in self.reference_prices}
        if len(observed_times) != 1:
            raise ValueError("reference_prices must share one observed_at timestamp")
        if next(iter(observed_times)) > self.decision_at:
            raise ValueError("reference price observed_at must be at or before decision_at")


# --------------------------------------------------------------------------- #
# Account snapshot
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class PositionSnapshot:
    """Realized position carried into target planning."""

    instrument: InstrumentKey
    quantity: Decimal
    average_price: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.instrument, InstrumentKey):
            raise TypeError("instrument must be InstrumentKey")
        object.__setattr__(self, "quantity", require_finite_decimal(self.quantity, "quantity"))
        object.__setattr__(
            self,
            "average_price",
            require_finite_decimal(self.average_price, "average_price", non_negative=True),
        )
        if self.quantity != 0 and self.average_price == 0:
            raise ValueError("non-zero positions require a positive average_price")


@dataclass(frozen=True, slots=True)
class AccountSnapshot:
    """Immutable pre-target account view used by every asset in a target."""

    as_of: datetime
    cash: Decimal
    equity: Decimal
    positions: tuple[PositionSnapshot, ...]
    marks: tuple[ReferencePrice, ...]
    cumulative_fees: Decimal
    cumulative_funding: Decimal

    def __post_init__(self) -> None:
        require_utc(self.as_of, "as_of")
        object.__setattr__(self, "cash", require_finite_decimal(self.cash, "cash"))
        object.__setattr__(self, "equity", require_finite_decimal(self.equity, "equity", positive=True))
        object.__setattr__(
            self,
            "cumulative_fees",
            require_finite_decimal(self.cumulative_fees, "cumulative_fees"),
        )
        object.__setattr__(
            self,
            "cumulative_funding",
            require_finite_decimal(self.cumulative_funding, "cumulative_funding"),
        )
        object.__setattr__(self, "positions", tuple(self.positions))
        object.__setattr__(self, "marks", tuple(self.marks))
        if any(not isinstance(position, PositionSnapshot) for position in self.positions):
            raise TypeError("positions must contain PositionSnapshot values")
        if any(not isinstance(mark, ReferencePrice) for mark in self.marks):
            raise TypeError("marks must contain ReferencePrice values")
        require_unique_ids((position.instrument.identity() for position in self.positions), "position instrument")
        require_unique_ids((mark.instrument.identity() for mark in self.marks), "mark instrument")
        mark_keys = {mark.instrument for mark in self.marks}
        missing_marks = {position.instrument for position in self.positions if position.quantity != 0} - mark_keys
        if missing_marks:
            raise ValueError(f"missing mark for open position: {_sorted_key_names(missing_marks)}")
        if any(mark.observed_at > self.as_of for mark in self.marks):
            raise ValueError("mark observed_at must be at or before account as_of")


# --------------------------------------------------------------------------- #
# Initial account state
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class InitialAccountState:
    """Explicit non-flat state carried into the first portfolio target."""

    as_of: datetime
    cash: Decimal
    positions: tuple[PositionSnapshot, ...]
    marks: tuple[ReferencePrice, ...]

    def __post_init__(self) -> None:
        require_utc(self.as_of, "as_of")
        object.__setattr__(self, "cash", require_finite_decimal(self.cash, "cash", positive=True))
        object.__setattr__(self, "positions", tuple(self.positions))
        object.__setattr__(self, "marks", tuple(self.marks))
        if not self.positions:
            raise ValueError("initial positions must be non-empty; use None for a flat start")
        if any(not isinstance(position, PositionSnapshot) for position in self.positions):
            raise TypeError("initial positions must contain PositionSnapshot values")
        if any(not isinstance(mark, ReferencePrice) for mark in self.marks):
            raise TypeError("initial marks must contain ReferencePrice values")
        if any(position.quantity == 0 for position in self.positions):
            raise ValueError("initial positions must omit zero quantities")
        require_unique_ids(
            (position.instrument.identity() for position in self.positions), "initial position instrument"
        )
        require_unique_ids((mark.instrument.identity() for mark in self.marks), "initial mark instrument")
        position_keys = {position.instrument for position in self.positions}
        mark_keys = {mark.instrument for mark in self.marks}
        if mark_keys != position_keys:
            raise ValueError("initial marks must cover initial positions exactly")
        if any(mark.observed_at != self.as_of for mark in self.marks):
            raise ValueError("initial marks must be observed exactly at initial as_of")


# --------------------------------------------------------------------------- #
# Sized targets
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class TargetQuantity:
    """Per-instrument target result with schedule and lot provenance."""

    target_id: str
    instrument: InstrumentKey
    current_quantity: Decimal
    desired_quantity: Decimal
    delta_quantity: Decimal
    reference_price: Decimal
    decision_at: datetime
    earliest_execution_at: datetime
    quantity_increment: Decimal

    def __post_init__(self) -> None:
        require_non_empty_str(self.target_id, "target_id")
        if not isinstance(self.instrument, InstrumentKey):
            raise TypeError("instrument must be InstrumentKey")
        for name in ("current_quantity", "desired_quantity", "delta_quantity"):
            object.__setattr__(self, name, require_finite_decimal(getattr(self, name), name))
        object.__setattr__(
            self,
            "reference_price",
            require_finite_decimal(self.reference_price, "reference_price", positive=True),
        )
        object.__setattr__(
            self,
            "quantity_increment",
            require_finite_decimal(self.quantity_increment, "quantity_increment", positive=True),
        )
        require_utc(self.decision_at, "decision_at")
        require_utc(self.earliest_execution_at, "earliest_execution_at")
        if self.decision_at >= self.earliest_execution_at:
            raise ValueError("decision_at must be strictly before earliest_execution_at")
        if self.desired_quantity - self.current_quantity != self.delta_quantity:
            raise ValueError("delta_quantity must equal desired_quantity - current_quantity")
        for name in ("current_quantity", "desired_quantity", "delta_quantity"):
            if getattr(self, name) % self.quantity_increment != 0:
                raise ValueError(f"{name} must be an integer multiple of quantity_increment")


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _sorted_key_names(keys: set[InstrumentKey]) -> str:
    return ", ".join(key.identity() for key in sorted(keys, key=lambda item: item.sort_key()))
