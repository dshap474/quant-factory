"""Work one transition leg with a single resting post-only order.

Purpose: the venue-neutral live loop behind a maker ``ParentOrderPolicy``. It
posts at the near touch, re-pegs every ``repeg_interval`` only when the touch has
moved away (an unchanged price keeps its queue place), and at the deadline markets
what is left. A venue plugs in through ``MakerPort``; ``run_transition`` still
owns close, prove-flat and open, and a venue calls this from ``submit``.

Safety model: at most one live child. No new child until the previous one is
proven terminal and the account position equals the start position plus our
own fills, so an outside trade stops the run. Every exit tries to cancel the
live child, including a post whose outcome is unknown. A child that ends
unfilled without our cancel stops the run. Once anything may have traded, a
failure raises ``Unresolved``.

USAGE:
    from execution.maker import work_maker_leg

    result = work_maker_leg(port, order=order_leg, policy=policy, clock=clock, sleep=time.sleep)
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol, TypeVar

from execution.policies import ParentOrderPolicy, maker_price
from execution.transition import LegResult, OrderLeg, Unresolved

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

POLL_SECONDS = 2.0
MAX_READ_FAILURES = 5
SETTLE_ATTEMPTS = 6
SETTLE_WAIT_SECONDS = 0.5
_ZERO = Decimal("0")

T = TypeVar("T")
logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Contracts
# --------------------------------------------------------------------------- #


class ReadFailed(RuntimeError):
    """A venue read failed transiently; the loop may retry it a few times."""


@dataclass(frozen=True, slots=True)
class MakerQuote:
    """Current top of book and the price grid at that level."""

    bid: Decimal
    ask: Decimal
    tick: Decimal


class MakerPort(Protocol):
    """What one venue supplies for one leg. Transient read failures raise ``ReadFailed``."""

    min_notional: Decimal
    leg_id: str

    def position(self) -> Decimal:
        """Return the account's signed position in this instrument."""

    def quote(self, live_cloid: str | None) -> MakerQuote:
        """Re-validate the account (only ``live_cloid`` may be open) and return the book."""

    def cloid(self, index: int) -> str:
        """Return the deterministic id of child ``index``."""

    def post(self, *, quantity: Decimal, price: Decimal, index: int) -> str | None:
        """Post one post-only child; return its id, or ``None`` if it would have crossed."""

    def open_size(self, cloid: str) -> Decimal | None:
        """Return the child's unfilled size while it rests, or ``None`` once terminal."""

    def cancel(self, cloid: str) -> None:
        """Ask the venue to cancel; ``open_size`` proves the outcome."""

    def child_result(self, cloid: str) -> LegResult:
        """Return fills and fees for one terminal child."""

    def take(self, *, quantity: Decimal, index: int) -> LegResult | None:
        """Cross the spread for ``quantity``; ``None`` when the venue cannot trade that size."""


@dataclass(frozen=True, slots=True)
class _Child:
    cloid: str
    price: Decimal
    quantity: Decimal


# --------------------------------------------------------------------------- #
# Loop
# --------------------------------------------------------------------------- #


class _Worker:
    """State for working one leg; position only ever advances by proven fills."""

    def __init__(
        self,
        port: MakerPort,
        order: OrderLeg,
        policy: ParentOrderPolicy,
        clock: Callable[[], datetime],
        sleep: Callable[[float], None],
    ) -> None:
        self.port = port
        self.order = order
        self.policy = policy
        self.clock = clock
        self.sleep = sleep
        self.side = 1 if order.quantity > 0 else -1
        self.start = _ZERO
        self.target = _ZERO
        self.position = _ZERO
        self.child: _Child | None = None
        self.pending: str | None = None
        self.done: list[LegResult] = []
        self.taker_filled = _ZERO
        self.index = 0

    def run(self) -> LegResult:
        self.start = self.position = self._retrying(self.port.position)
        self.target = self.start + self.order.quantity
        try:
            self._work_until(self.clock() + self.policy.horizon)
            if self.child is not None:
                self._retrying(self._cancel_and_settle)
            self._at_deadline()
        except Unresolved:
            raise
        except Exception as exc:
            if self.child is None and self._filled() == 0:
                raise
            raise Unresolved(
                f"maker leg stopped after orders were live; check for a resting order: {exc}",
                client_order_id=self._last_id(),
            ) from exc
        finally:
            self._cancel_quietly()
        return self._result()

    def _work_until(self, deadline: datetime) -> None:
        # Never re-pegging is an interval as long as the leg, so the deadline always comes first.
        interval = self.policy.repeg_interval or self.policy.horizon
        next_repeg = self.clock() + interval
        failures = 0
        while self.clock() < deadline:
            now = self.clock()
            due = now >= next_repeg
            try:
                if self._step(repeg_due=due):
                    return
                if due:
                    next_repeg = now + interval
                failures = 0
            except ReadFailed:
                failures += 1
                if failures >= MAX_READ_FAILURES:
                    raise
            self.sleep(POLL_SECONDS)

    def _step(self, *, repeg_due: bool) -> bool:
        """Advance one pass; return True when the leg can post nothing further."""
        if self.child is not None:
            left = self.port.open_size(self.child.cloid)
            if left is not None:
                return self._repeg(left) if repeg_due else False
            child = self.child
            self._settle_child()
            if self.done[-1].filled_quantity != child.quantity:
                raise Unresolved(
                    f"child ended {self.done[-1].status} without our cancel; run stopped", client_order_id=child.cloid
                )
        return self._post()

    def _repeg(self, left: Decimal) -> bool:
        child = self.child
        assert child is not None
        price = self._price(self.port.quote(child.cloid), resting=child.price)
        if price == child.price or left * price < self.port.min_notional:
            return False  # A remainder under the venue minimum could not be re-posted; leave it working.
        self._cancel_and_settle()
        return self._post()

    def _post(self) -> bool:
        remaining = self.target - self.position
        if remaining == 0:
            return True
        price = self._price(self.port.quote(None), resting=None)
        if abs(remaining) * price < self.port.min_notional:
            return True
        index = self.index
        self.index += 1
        self.pending = self.port.cloid(index)
        cloid = self.port.post(quantity=remaining, price=price, index=index)
        self.pending = None
        if cloid is not None:
            self.child = _Child(cloid, price, remaining)
        return False

    def _price(self, quote: MakerQuote, *, resting: Decimal | None) -> Decimal:
        raw = maker_price(
            side=self.side,
            bid=float(quote.bid),
            ask=float(quote.ask),
            tick=float(quote.tick),
            price_rule=self.policy.price_rule,
        )
        price = Decimal(round(raw / float(quote.tick))) * quote.tick
        if resting is None:
            return price
        return max(price, resting) if self.side > 0 else min(price, resting)

    def _cancel_and_settle(self) -> None:
        child = self.child
        assert child is not None
        self.port.cancel(child.cloid)
        for _ in range(SETTLE_ATTEMPTS):
            if self.port.open_size(child.cloid) is None:
                self._settle_child()
                return
            self.sleep(SETTLE_WAIT_SECONDS)
        raise Unresolved("child is still open after cancel", client_order_id=child.cloid)

    def _settle_child(self) -> None:
        child = self.child
        assert child is not None
        self._prove(lambda: self.port.child_result(child.cloid), cloid=child.cloid)
        self.child = None

    def _at_deadline(self) -> None:
        remaining = self.target - self.position
        if remaining == 0 or self.policy.at_deadline == "leave":
            return
        self._retrying(lambda: self.port.quote(None))
        index = self.index
        self.index += 1
        taken = self._retrying(lambda: self.port.take(quantity=remaining, index=index))
        if taken is None:
            return
        self.done.append(taken)
        self.taker_filled = taken.filled_quantity
        self._prove(None, cloid=taken.client_order_id)

    def _prove(self, fetch: Callable[[], LegResult] | None, *, cloid: str) -> None:
        """Wait for the position to equal the start plus own fills, then record it."""
        result = None
        expected = position = _ZERO
        for _ in range(SETTLE_ATTEMPTS):
            result = fetch() if fetch is not None else None
            position = self.port.position()
            expected = self.start + self._filled() + (result.filled_quantity if result is not None else _ZERO)
            if position == expected:
                break
            self.sleep(SETTLE_WAIT_SECONDS)
        else:
            raise Unresolved(f"position {position} does not equal own fills {expected}", client_order_id=cloid)
        if (self.target - position) * self.side < 0:
            raise Unresolved(f"position {position} overshot target {self.target}", client_order_id=cloid)
        if result is not None:
            self.done.append(result)
        self.position = position

    def _retrying(self, fn: Callable[[], T]) -> T:
        for _ in range(MAX_READ_FAILURES - 1):
            try:
                return fn()
            except ReadFailed:
                self.sleep(POLL_SECONDS)
        return fn()

    def _cancel_quietly(self) -> None:
        for cloid in (self.child.cloid if self.child is not None else None, self.pending):
            if cloid is None:
                continue
            try:
                self.port.cancel(cloid)
            except Exception as exc:  # noqa: BLE001 - never mask the error that ended the run
                logger.error("cancel failed for order %s; check the venue for a resting order: %s", cloid, exc)

    def _filled(self) -> Decimal:
        return sum((row.filled_quantity for row in self.done), _ZERO)

    def _last_id(self) -> str:
        if self.child is not None:
            return self.child.cloid
        return self.done[-1].client_order_id if self.done else self.port.leg_id

    def _result(self) -> LegResult:
        filled = self._filled()
        notional = sum((abs(row.filled_quantity) * row.average_price for row in self.done), _ZERO)
        complete = filled == self.order.quantity
        return LegResult(
            leg=self.order.leg,
            client_order_id=self._last_id(),
            venue_order_id=self.done[-1].venue_order_id if self.done else None,
            status="filled" if complete else "partial",
            requested_quantity=self.order.quantity,
            filled_quantity=filled,
            average_price=notional / abs(filled) if filled else _ZERO,
            fee=sum((row.fee for row in self.done), _ZERO),
            fee_currency=self.done[0].fee_currency if self.done else "USDC",
            trustworthy=complete,
            detail={
                "policy": self.policy.name,
                "orders": str(self.index),
                "maker_filled": str(filled - self.taker_filled),
                "taker_filled": str(self.taker_filled),
            },
        )


# --------------------------------------------------------------------------- #
# Public entry
# --------------------------------------------------------------------------- #


def work_maker_leg(
    port: MakerPort,
    *,
    order: OrderLeg,
    policy: ParentOrderPolicy,
    clock: Callable[[], datetime],
    sleep: Callable[[float], None],
) -> LegResult:
    """Work one leg to completion or its deadline; only one child rests at a time."""
    if policy.style != "maker":
        raise ValueError(f"policy {policy.name!r} is not a maker policy")
    if policy.child_interval != policy.horizon:
        raise ValueError(f"policy {policy.name!r} slices the order; live maker execution posts one order")
    if order.quantity == 0:
        raise ValueError("maker leg quantity must be nonzero")
    return _Worker(port, order, policy, clock, sleep).run()


__all__ = ["MakerPort", "MakerQuote", "ReadFailed", "work_maker_leg"]
