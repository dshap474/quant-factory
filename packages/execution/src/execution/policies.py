"""Deterministic market-taker planning policies.

Purpose: convert already-sized TargetQuantity records into market IOC slice
intents without inspecting market data or mutating account state.

USAGE:
    >>> from datetime import timedelta
    >>> from execution.policies import ImmediateMarketPolicy, TimeWeightedTakerPolicy
    >>> ImmediateMarketPolicy().plan(quantities)  # doctest: +SKIP
    >>> TimeWeightedTakerPolicy(slice_count=3, interval=timedelta(minutes=1)).plan(quantities)  # doctest: +SKIP

Parent-order policies (``ParentOrderPolicy``) describe how one parent order is worked over time
(market now, or a post-only maker schedule with a deadline). Their per-minute decisions
(``maker_child_lots``, ``maker_price``) are the one copy shared by the backtest simulator and live
executors; only fills differ (simulated from bars versus reported by the venue).

    >>> from execution.policies import ParentOrderPolicy, maker_child_lots, maker_price
    >>> policy = ParentOrderPolicy(name="maker_30m", style="maker", horizon=timedelta(minutes=30))
    >>> maker_child_lots(minute=0, horizon_minutes=30, child_minutes=1, remaining_lots=60, min_lots=1)
    2
    >>> maker_price(side=1, bid=100.4, ask=101.0, tick=0.5, price_rule="join")
    100.0
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Literal, Sequence

from execution._checks import require_utc
from execution.events import SliceIntent
from execution.instruments import InstrumentKey
from execution.targets import TargetQuantity

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _slice_id(target_id: str, instrument: InstrumentKey, index: int) -> str:
    return f"{target_id}:{instrument.identity()}:{index:04d}"


def _intent(qty: TargetQuantity, index: int, quantity: Decimal, scheduled_at: datetime) -> SliceIntent:
    return SliceIntent(
        target_id=qty.target_id,
        slice_id=_slice_id(qty.target_id, qty.instrument, index),
        instrument=qty.instrument,
        quantity=quantity,
        scheduled_at=scheduled_at,
        expires_at=scheduled_at,
    )


def _split_lot_slices(
    delta: Decimal,
    increment: Decimal,
    slice_count: int,
) -> tuple[Decimal, ...]:
    """Partition signed delta into ``slice_count`` integer-increment slices.

    Absolute lot units are divided by quotient/remainder. The earliest
    ``remainder`` slices each receive one extra unit. Zero slices are omitted
    by the caller. Signed sum equals the already-rounded delta exactly.
    """
    if slice_count < 1:
        raise ValueError(f"slice_count must be >= 1, got {slice_count}")
    if increment <= 0:
        raise ValueError(f"increment must be positive, got {increment}")
    if delta == 0:
        return ()

    if delta % increment != 0:
        raise ValueError(f"delta {delta} is not an integer multiple of increment {increment}")

    sign = Decimal(1) if delta > 0 else Decimal(-1)
    total_units = int(abs(delta) / increment)
    base, remainder = divmod(total_units, slice_count)
    parts: list[Decimal] = []
    for i in range(slice_count):
        units = base + (1 if i < remainder else 0)
        if units == 0:
            continue
        parts.append(sign * Decimal(units) * increment)
    return tuple(parts)


def _validate_schedule_bounds(
    decision_at: datetime,
    earliest_execution_at: datetime,
    scheduled_at: datetime,
) -> None:
    require_utc(decision_at, "decision_at")
    require_utc(earliest_execution_at, "earliest_execution_at")
    require_utc(scheduled_at, "scheduled_at")
    if not (decision_at < earliest_execution_at <= scheduled_at):
        raise ValueError(
            "require decision_at < earliest_execution_at <= scheduled_at; "
            f"got decision_at={decision_at}, "
            f"earliest_execution_at={earliest_execution_at}, "
            f"scheduled_at={scheduled_at}"
        )


def _validated_quantities(
    target_quantities: Sequence[TargetQuantity],
) -> tuple[TargetQuantity, ...]:
    quantities = tuple(target_quantities)
    if any(not isinstance(quantity, TargetQuantity) for quantity in quantities):
        raise TypeError("target_quantities must contain TargetQuantity values")
    if not quantities:
        return ()
    first = quantities[0]
    provenance = (first.target_id, first.decision_at, first.earliest_execution_at)
    if any(
        (quantity.target_id, quantity.decision_at, quantity.earliest_execution_at) != provenance
        for quantity in quantities
    ):
        raise ValueError("all target quantities in one plan must share target and timing provenance")
    identities = [(quantity.target_id, quantity.instrument) for quantity in quantities]
    if len(set(identities)) != len(identities):
        raise ValueError("target quantities must be unique per target and instrument")
    return tuple(sorted(quantities, key=lambda quantity: quantity.instrument.sort_key()))


# --------------------------------------------------------------------------- #
# Overlap validation
# --------------------------------------------------------------------------- #


def validate_non_overlapping_windows(
    intents: Sequence[SliceIntent],
) -> None:
    """Reject instrument windows that overlap across portfolio targets.

    For each instrument, targets ordered by earliest scheduled time must satisfy:
    next target's first scheduled_at > previous target's last scheduled_at.
    Same-target slices are allowed to form a contiguous TWAP window.
    """
    by_instrument: dict[InstrumentKey, list[SliceIntent]] = {}
    for intent in intents:
        by_instrument.setdefault(intent.instrument, []).append(intent)

    for instrument, group in by_instrument.items():
        by_target: dict[str, list[SliceIntent]] = {}
        for intent in group:
            by_target.setdefault(intent.target_id, []).append(intent)

        windows: list[tuple[datetime, datetime, str]] = []
        for target_id, slices in by_target.items():
            starts = [s.scheduled_at for s in slices]
            windows.append((min(starts), max(starts), target_id))
        windows.sort(key=lambda w: (w[0], w[2]))

        for i in range(1, len(windows)):
            prev_start, prev_end, prev_id = windows[i - 1]
            next_start, next_end, next_id = windows[i]
            if next_start <= prev_end:
                raise ValueError(
                    "overlapping target windows for "
                    f"{instrument.identity()}: "
                    f"target {prev_id!r} ends at {prev_end}, "
                    f"target {next_id!r} starts at {next_start}"
                )


# --------------------------------------------------------------------------- #
# Policies
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class ImmediateMarketPolicy:
    """One full-delta IOC market slice per non-zero instrument at earliest time."""

    def schedule_times(
        self,
        decision_at: datetime,
        earliest_execution_at: datetime,
    ) -> tuple[datetime, ...]:
        """Return the one earliest permissible execution close."""
        _validate_schedule_bounds(decision_at, earliest_execution_at, earliest_execution_at)
        return (earliest_execution_at,)

    def plan(self, target_quantities: Sequence[TargetQuantity]) -> tuple[SliceIntent, ...]:
        ordered = _validated_quantities(target_quantities)
        if not ordered:
            return ()
        scheduled_at = self.schedule_times(ordered[0].decision_at, ordered[0].earliest_execution_at)[0]
        return tuple(_intent(qty, 0, qty.delta_quantity, scheduled_at) for qty in ordered if qty.delta_quantity != 0)


@dataclass(frozen=True, slots=True)
class TimeWeightedTakerPolicy:
    """Equal-time deterministic slices with exact signed lot conservation."""

    slice_count: int
    interval: timedelta

    def __post_init__(self) -> None:
        if not isinstance(self.slice_count, int) or isinstance(self.slice_count, bool):
            raise TypeError("slice_count must be int")
        if self.slice_count < 1:
            raise ValueError(f"slice_count must be >= 1, got {self.slice_count}")
        if not isinstance(self.interval, timedelta):
            raise TypeError("interval must be timedelta")
        if self.interval <= timedelta(0):
            raise ValueError(f"interval must be positive, got {self.interval}")

    def schedule_times(
        self,
        decision_at: datetime,
        earliest_execution_at: datetime,
    ) -> tuple[datetime, ...]:
        """Return every configured one-shot slice close."""
        times = tuple(earliest_execution_at + index * self.interval for index in range(self.slice_count))
        for scheduled_at in times:
            _validate_schedule_bounds(decision_at, earliest_execution_at, scheduled_at)
        return times

    def plan(self, target_quantities: Sequence[TargetQuantity]) -> tuple[SliceIntent, ...]:
        ordered = _validated_quantities(target_quantities)
        if not ordered:
            return ()
        scheduled = self.schedule_times(ordered[0].decision_at, ordered[0].earliest_execution_at)
        intents: list[SliceIntent] = []
        for qty in ordered:
            if qty.delta_quantity == 0:
                continue
            parts = _split_lot_slices(
                qty.delta_quantity,
                qty.quantity_increment,
                self.slice_count,
            )
            if sum(parts, Decimal(0)) != qty.delta_quantity:
                raise ValueError(f"slice conservation failed for {qty.instrument.identity()}")
            intents.extend(_intent(qty, index, part, scheduled[index]) for index, part in enumerate(parts))

        intents.sort(key=lambda intent: (intent.scheduled_at, intent.instrument.sort_key(), intent.slice_id))
        return tuple(intents)


@dataclass(frozen=True, slots=True)
class DelayedMarketPolicy:
    """One full-delta market IOC at a fixed delay after the decision."""

    delay: timedelta

    def __post_init__(self) -> None:
        if not isinstance(self.delay, timedelta):
            raise TypeError("delay must be timedelta")
        if self.delay <= timedelta(0):
            raise ValueError(f"delay must be positive, got {self.delay}")

    def schedule_times(
        self,
        decision_at: datetime,
        earliest_execution_at: datetime,
    ) -> tuple[datetime, ...]:
        """Return the decision-relative delayed execution close."""
        scheduled_at = decision_at + self.delay
        _validate_schedule_bounds(decision_at, earliest_execution_at, scheduled_at)
        return (scheduled_at,)

    def plan(self, target_quantities: Sequence[TargetQuantity]) -> tuple[SliceIntent, ...]:
        """Plan one delayed full-delta slice per non-zero instrument."""
        ordered = _validated_quantities(target_quantities)
        intents: list[SliceIntent] = []
        for qty in ordered:
            if qty.delta_quantity == 0:
                continue
            scheduled_at = self.schedule_times(qty.decision_at, qty.earliest_execution_at)[0]
            intents.append(_intent(qty, 0, qty.delta_quantity, scheduled_at))
        return tuple(intents)


# --------------------------------------------------------------------------- #
# Parent-order policies
# --------------------------------------------------------------------------- #

# Float slack, in ticks, so grid prices compare as exact grid values.
_TICK_EPS = 1e-9


def _whole_minutes(value: timedelta, name: str) -> int:
    if not isinstance(value, timedelta):
        raise TypeError(f"{name} must be a timedelta")
    if value < timedelta(0) or value % timedelta(minutes=1) != timedelta(0):
        raise ValueError(f"{name} must be a non-negative whole number of minutes")
    return value // timedelta(minutes=1)


@dataclass(frozen=True, slots=True)
class ParentOrderPolicy:
    """How one parent order is worked: market now, or a post-only maker schedule.

    A maker policy starts a child order every ``child_interval`` over ``horizon``, prices it with
    ``maker_price`` (re-pegged every ``repeg_interval``, or never when that is ``None``), sizes it
    with ``maker_child_lots``, and at the deadline markets any remainder (``at_deadline="market"``)
    or leaves it unfilled (``"leave"``).
    """

    name: str
    style: Literal["market", "maker"]
    horizon: timedelta = timedelta(0)
    child_interval: timedelta = timedelta(minutes=1)
    price_rule: Literal["join", "improve"] = "join"
    repeg_interval: timedelta | None = timedelta(minutes=1)
    at_deadline: Literal["market", "leave"] = "market"

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("policy name must be a non-empty string")
        if self.style not in ("market", "maker"):
            raise ValueError(f"policy {self.name!r} style must be 'market' or 'maker'")
        if self.price_rule not in ("join", "improve"):
            raise ValueError(f"policy {self.name!r} price_rule must be 'join' or 'improve'")
        if self.at_deadline not in ("market", "leave"):
            raise ValueError(f"policy {self.name!r} at_deadline must be 'market' or 'leave'")
        if (
            self.repeg_interval is not None
            and _whole_minutes(self.repeg_interval, f"policy {self.name!r} repeg_interval") <= 0
        ):
            raise ValueError(f"policy {self.name!r} repeg_interval must be positive or None")
        horizon = _whole_minutes(self.horizon, f"policy {self.name!r} horizon")
        child = _whole_minutes(self.child_interval, f"policy {self.name!r} child_interval")
        if child <= 0:
            raise ValueError(f"policy {self.name!r} child_interval must be positive")
        if self.style == "maker" and horizon <= 0:
            raise ValueError(f"maker policy {self.name!r} requires horizon > 0")
        if self.style == "market" and horizon != 0:
            raise ValueError(f"market policy {self.name!r} requires horizon == 0")
        if horizon % child != 0:
            raise ValueError(f"policy {self.name!r} horizon must be a multiple of child_interval")

    @property
    def horizon_minutes(self) -> int:
        """Window length in minutes (0 for market)."""
        return self.horizon // timedelta(minutes=1)

    @property
    def child_minutes(self) -> int:
        """Minutes between child-order starts."""
        return self.child_interval // timedelta(minutes=1)

    @property
    def repeg_minutes(self) -> int | None:
        """Minutes between re-pegs (``None`` for never)."""
        return None if self.repeg_interval is None else self.repeg_interval // timedelta(minutes=1)


def maker_child_lots(
    *,
    minute: int,
    horizon_minutes: int,
    child_minutes: int,
    remaining_lots: int,
    min_lots: int,
) -> int | None:
    """Lots for the child starting at ``minute`` of the window; ``None`` between child starts.

    The remainder is spread evenly over the children left (``remaining // children_left``), never
    below the venue minimum and never above the remainder. Returns 0 (post nothing) once the
    remainder is exhausted or below the venue minimum; that dust is left to the deadline.
    """
    if minute % child_minutes:
        return None
    if remaining_lots <= 0 or remaining_lots < min_lots:
        return 0
    children_left = (horizon_minutes - minute) // child_minutes
    return min(max(remaining_lots // children_left, min_lots, 1), remaining_lots)


def maker_price(*, side: int, bid: float, ask: float, tick: float, price_rule: str) -> float:
    """Post-only limit price: join the near touch, or improve it by one tick without crossing.

    ``side`` is +1 (buy) or -1 (sell). Buys round the bid down to the tick grid and sells round the
    ask up; ``"improve"`` steps one tick inside only when that stays more than half a tick from the
    far touch. Floats in, float out; live callers round the result to their Decimal tick.
    """
    if side > 0:
        ticks = math.floor(bid / tick + _TICK_EPS)
        if price_rule == "improve" and (ticks + 1) * tick < ask - tick / 2:
            ticks += 1
    else:
        ticks = math.ceil(ask / tick - _TICK_EPS)
        if price_rule == "improve" and (ticks - 1) * tick > bid + tick / 2:
            ticks -= 1
    return ticks * tick
