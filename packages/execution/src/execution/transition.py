"""Venue-neutral flat-then-target transition engine.

Purpose: own the one execution sequence every live venue shares — authorize,
lock, read venue truth, close the existing position, prove it flat, re-size
from fresh truth, open the target, prove the result — plus the at-most-once
submit protocol. A venue plugs in through the small ``Venue`` protocol and
keeps its own gates, caps, wire formats and recovery evidence private. A venue
that sets ``net_resize`` has a same-side resize traded as one difference order.

Failure model: before the first mutation any exception is an ordinary refusal.
After a mutation, anything the engine cannot prove raises ``Unresolved``: the
original client order id must be reconciled, never retried or re-minted.

USAGE:
    from execution.transition import run_transition

    result = run_transition(venue, target_weight=Decimal("1"), dry_run=True)
    print(result.summary())
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal, Protocol, TypeVar, cast

from execution._checks import require_finite_decimal, require_non_empty_str

# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #


class Unresolved(RuntimeError):
    """Venue truth is ambiguous after a possible mutation; never resubmit."""

    def __init__(self, message: str, *, client_order_id: str | None = None) -> None:
        super().__init__(message)
        self.client_order_id = client_order_id


class Rejected(RuntimeError):
    """The venue definitively refused one order; nothing was created."""


# --------------------------------------------------------------------------- #
# Contracts
# --------------------------------------------------------------------------- #

Leg = Literal["close", "open"]


@dataclass(frozen=True, slots=True)
class TransitionPlan:
    """Signed current and target position derived from one venue truth."""

    current_quantity: Decimal
    target_quantity: Decimal
    mark_price: Decimal

    def __post_init__(self) -> None:
        for name in ("current_quantity", "target_quantity"):
            object.__setattr__(self, name, require_finite_decimal(getattr(self, name), name))
        object.__setattr__(self, "mark_price", require_finite_decimal(self.mark_price, "mark_price", positive=True))


@dataclass(frozen=True, slots=True)
class OrderLeg:
    """One order the engine asks a venue to realize: close to flat, or open the target."""

    leg: Leg
    quantity: Decimal

    @property
    def reduce_only(self) -> bool:
        return self.leg == "close"


@dataclass(frozen=True, slots=True)
class LegResult:
    """Terminal venue truth for one realized leg; quantities are signed."""

    leg: Leg
    client_order_id: str
    venue_order_id: str | None
    status: str
    requested_quantity: Decimal
    filled_quantity: Decimal
    average_price: Decimal
    fee: Decimal
    fee_currency: str
    trustworthy: bool
    detail: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_non_empty_str(self.client_order_id, "client_order_id")
        require_non_empty_str(self.status, "status")
        for name in ("requested_quantity", "filled_quantity", "fee"):
            object.__setattr__(self, name, require_finite_decimal(getattr(self, name), name))
        object.__setattr__(
            self, "average_price", require_finite_decimal(self.average_price, "average_price", non_negative=True)
        )
        if abs(self.filled_quantity) > abs(self.requested_quantity):
            raise ValueError("filled_quantity cannot exceed requested_quantity")
        if self.filled_quantity and (self.filled_quantity > 0) != (self.requested_quantity > 0):
            raise ValueError("filled_quantity must have the requested sign")

    @property
    def complete(self) -> bool:
        """True when venue truth proves the whole requested quantity filled."""
        return self.trustworthy and self.filled_quantity == self.requested_quantity


@dataclass(frozen=True, slots=True)
class TransitionResult:
    """Complete dry-run or terminal result of one flat-then-target transition."""

    venue: str
    symbol: str
    run_id: str
    target_id: str
    target_weight: Decimal
    dry_run: bool
    plan: TransitionPlan
    legs: tuple[LegResult, ...]
    funding: Decimal
    trustworthy: bool
    note: str | None = None
    detail: Mapping[str, object] = field(default_factory=dict)

    def leg(self, name: Leg) -> LegResult | None:
        return next((leg for leg in self.legs if leg.leg == name), None)

    def summary(self) -> dict[str, object]:
        """Return JSON-ready, log-safe facts (no credentials or account identifiers)."""
        return {
            "venue": self.venue,
            "symbol": self.symbol,
            "dry_run": self.dry_run,
            "target_weight": str(self.target_weight),
            "current_quantity": str(self.plan.current_quantity),
            "target_quantity": str(self.plan.target_quantity),
            "mark_price": str(self.plan.mark_price),
            "legs": [
                {
                    "leg": leg.leg,
                    "status": leg.status,
                    "venue_order_id": leg.venue_order_id,
                    "requested_quantity": str(leg.requested_quantity),
                    "filled_quantity": str(leg.filled_quantity),
                    "average_price": str(leg.average_price),
                    "fee": str(leg.fee),
                    "fee_currency": leg.fee_currency,
                    "trustworthy": leg.trustworthy,
                    "detail": dict(leg.detail),
                }
                for leg in self.legs
            ],
            "fees": str(sum((leg.fee for leg in self.legs), Decimal("0"))),
            "funding": str(self.funding),
            "trustworthy": self.trustworthy,
            "note": self.note,
            "ruleset": self.detail.get("ruleset"),
        }


class Venue(Protocol):
    """One account on one venue for one run; everything venue-specific lives behind it.

    The engine calls, in order: ``authorize`` → ``session`` → ``load``/``plan``
    → (dry run: ``preview``) or (live: ``submit``/``load``/``plan``/``confirm``)
    → ``settle``. Each method raises to refuse; ``submit`` and ``confirm`` raise
    ``Unresolved`` when venue truth cannot be proven.
    """

    name: str
    symbol: str
    run_id: str
    target_id: str

    def authorize(self, *, dry_run: bool, target_weight: Decimal) -> None:
        """Enforce gates, arming, credential binding and target shape before any venue read."""

    def session(self) -> AbstractContextManager[object]:
        """Hold the account lock and any durable run state for the whole transition."""

    def load(self) -> Any:
        """Read one consistent venue truth (account, position, book, rules)."""

    def plan(self, truth: Any, target_weight: Decimal) -> TransitionPlan:
        """Validate truth and caps, then size the target position; refuse by raising."""

    def preview(self, truth: Any, plan: TransitionPlan) -> tuple[Mapping[str, object], str | None]:
        """Dry run only: return venue preview facts and an optional note; never mutate."""

    def submit(self, truth: Any, order: OrderLeg) -> LegResult:
        """Realize one leg at most once, including its own submit-boundary checks."""

    def confirm(self, opened: LegResult) -> None:
        """Prove realized account state after the open leg; raise ``Unresolved`` otherwise."""

    def settle(self, *, dry_run: bool) -> tuple[Decimal, Mapping[str, object]]:
        """Return realized funding and any venue facts to attach to the result."""


class NetResizeVenue(Venue, Protocol):
    """A venue that opted in (``net_resize`` true) to trading only the difference on a resize."""

    net_resize: bool

    def confirm_position(self, expected: Decimal, *, client_order_id: str) -> None:
        """Prove the realized position equals ``expected``; raise ``Unresolved`` otherwise."""


# --------------------------------------------------------------------------- #
# At-most-once submit
# --------------------------------------------------------------------------- #

T = TypeVar("T")


def submit_at_most_once(
    *,
    client_order_id: str,
    lookup: Callable[[], T | None],
    create: Callable[[], T],
    lookup_first: bool = True,
) -> T:
    """Create one order identity at most once.

    An existing order under ``client_order_id`` is adopted instead of created.
    ``Rejected`` passes through. Any other create failure is resolved only by
    finding the order; if it cannot be found the outcome is ``Unresolved``.
    """
    if lookup_first:
        existing = lookup()
        if existing is not None:
            return existing
    try:
        return create()
    except Rejected:
        raise
    except Exception as exc:
        try:
            recovered = lookup()
        except Exception as lookup_exc:
            raise Unresolved(
                f"ambiguous create for {client_order_id} and lookup failed; never resubmit",
                client_order_id=client_order_id,
            ) from lookup_exc
        if recovered is None:
            raise Unresolved(
                f"ambiguous create for {client_order_id}; reconcile by client order id and never resubmit",
                client_order_id=client_order_id,
            ) from exc
        return recovered


def reconcile_or_unresolved(client_order_id: str, reconcile: Callable[[], T]) -> T:
    """Run post-submit work; once an order may exist, any failure leaves its outcome unknown.

    ``Rejected`` passes through; ``Unresolved`` passes through tagged with ``client_order_id``;
    every other error becomes ``Unresolved`` so the operator reconciles by client order id
    instead of the engine retrying.
    """
    try:
        return reconcile()
    except Unresolved as exc:
        if exc.client_order_id is None:
            exc.client_order_id = client_order_id
        raise
    except Rejected:
        raise
    except Exception as exc:
        raise Unresolved(
            f"order reconciliation is unresolved for {client_order_id}; never resubmit: {exc}",
            client_order_id=client_order_id,
        ) from exc


# --------------------------------------------------------------------------- #
# Transition
# --------------------------------------------------------------------------- #


def run_transition(venue: Venue, *, target_weight: Decimal, dry_run: bool) -> TransitionResult:
    """Close any position, prove flat, then open the freshly sized target."""
    weight = require_finite_decimal(target_weight, "target_weight")
    if not isinstance(dry_run, bool):
        raise TypeError("dry_run must be bool")
    venue.authorize(dry_run=dry_run, target_weight=weight)
    with venue.session():
        truth = venue.load()
        plan = venue.plan(truth, weight)
        if dry_run:
            detail, note = venue.preview(truth, plan)
            funding, extra = venue.settle(dry_run=True)
            return _result(venue, weight, True, plan, (), funding, True, note, {**detail, **extra})

        if getattr(venue, "net_resize", False) and plan.current_quantity * plan.target_quantity > 0:
            return _run_resize(cast(NetResizeVenue, venue), weight, truth, plan)

        legs: list[LegResult] = []
        starting_quantity = plan.current_quantity
        closed = starting_quantity != 0
        if closed:
            close = venue.submit(truth, OrderLeg("close", -plan.current_quantity))
            legs.append(close)
            if not close.complete or close.requested_quantity != -plan.current_quantity:
                raise Unresolved("close did not fill exactly; open is blocked", client_order_id=close.client_order_id)

        if closed or weight != 0:
            truth, plan = _fresh_flat_plan(venue, weight, closed_by=legs[0] if closed else None)

        if weight != 0 and plan.target_quantity != 0:
            opened = venue.submit(truth, OrderLeg("open", plan.target_quantity))
            legs.append(opened)
            reconcile_or_unresolved(opened.client_order_id, lambda: venue.confirm(opened))

        funding, extra = venue.settle(dry_run=False)
        trustworthy = all(leg.trustworthy for leg in legs)
        note = None if legs else "already at target"
        # Report the position the run started from, not the proven-flat re-read after a close.
        reported = TransitionPlan(starting_quantity, plan.target_quantity, plan.mark_price)
        return _result(venue, weight, False, reported, tuple(legs), funding, trustworthy, note, extra)


def _run_resize(venue: NetResizeVenue, weight: Decimal, truth: Any, plan: TransitionPlan) -> TransitionResult:
    """Trade one order for the difference: reduce-only when shrinking, never through flat."""
    delta = plan.target_quantity - plan.current_quantity
    legs: tuple[LegResult, ...] = ()
    if delta != 0:
        leg: Leg = "open" if abs(plan.target_quantity) > abs(plan.current_quantity) else "close"
        result = venue.submit(truth, OrderLeg(leg, delta))
        legs = (result,)
        expected = plan.current_quantity + result.filled_quantity
        cid = result.client_order_id
        reconcile_or_unresolved(cid, lambda: venue.confirm_position(expected, client_order_id=cid))
    funding, extra = venue.settle(dry_run=False)
    trustworthy = all(row.trustworthy for row in legs)
    note = None if legs else "no trade needed: at target, or the difference is below the venue minimum"
    return _result(venue, weight, False, plan, legs, funding, trustworthy, note, extra)


def _fresh_flat_plan(venue: Venue, weight: Decimal, *, closed_by: LegResult | None) -> tuple[Any, TransitionPlan]:
    """Re-read venue truth and re-size; the account must be exactly flat."""
    cid = closed_by.client_order_id if closed_by is not None else None
    try:
        truth = venue.load()
        plan = venue.plan(truth, weight)
    except Unresolved:
        raise
    except Exception as exc:
        if closed_by is None:
            raise
        raise Unresolved("close is terminal but fresh venue truth could not be proven", client_order_id=cid) from exc
    if plan.current_quantity != 0:
        reason = "close is terminal but account is not flat" if closed_by else "account changed before open"
        raise Unresolved(reason, client_order_id=cid)
    return truth, plan


def _result(
    venue: Venue,
    weight: Decimal,
    dry_run: bool,
    plan: TransitionPlan,
    legs: tuple[LegResult, ...],
    funding: Decimal,
    trustworthy: bool,
    note: str | None,
    detail: Mapping[str, object],
) -> TransitionResult:
    return TransitionResult(
        venue=venue.name,
        symbol=venue.symbol,
        run_id=venue.run_id,
        target_id=venue.target_id,
        target_weight=weight,
        dry_run=dry_run,
        plan=plan,
        legs=legs,
        funding=require_finite_decimal(funding, "funding"),
        trustworthy=trustworthy,
        note=note,
        detail=dict(detail),
    )


__all__ = [
    "LegResult",
    "NetResizeVenue",
    "OrderLeg",
    "Rejected",
    "TransitionPlan",
    "TransitionResult",
    "Unresolved",
    "Venue",
    "reconcile_or_unresolved",
    "run_transition",
    "submit_at_most_once",
]
