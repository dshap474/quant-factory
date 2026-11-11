"""Top-of-book quote and the capped marketable limit price.

Purpose: one definition of the price a capped IOC may cross to. A buy may pay
at most ``ask × (1 + cap)``, a sell may receive no less than
``bid × (1 − cap)``; rounding to a venue tick always moves inward (buys down,
sells up) so the bound is never widened. Venue-specific price grammars (for
example significant-figure limits) stay in the venue.

USAGE:
    from execution.pricing import BBO, capped_limit_price

    book = BBO(bid=Decimal("99.9"), ask=Decimal("100.1"))
    price = capped_limit_price(book, is_buy=True, cap_bps=Decimal("25"), tick=Decimal("0.01"))
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

from execution._checks import require_finite_decimal

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

BPS = Decimal("10000")

# --------------------------------------------------------------------------- #
# Quote
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class BBO:
    """Best bid and ask at one instant; both positive and uncrossed."""

    bid: Decimal
    ask: Decimal
    as_of: datetime | None = None

    def __post_init__(self) -> None:
        require_finite_decimal(self.bid, "bid", positive=True)
        require_finite_decimal(self.ask, "ask", positive=True)
        if self.ask < self.bid:
            raise ValueError(f"crossed book: ask {self.ask} < bid {self.bid}")

    @property
    def mid(self) -> Decimal:
        return (self.bid + self.ask) / Decimal("2")

    @property
    def spread_bps(self) -> Decimal:
        return (self.ask - self.bid) / self.mid * BPS


# --------------------------------------------------------------------------- #
# Capped limit price
# --------------------------------------------------------------------------- #


def capped_limit_price(book: BBO, *, is_buy: bool, cap_bps: Decimal, tick: Decimal | None = None) -> Decimal:
    """Return the worst price a capped IOC may accept, rounded inward to ``tick`` when given."""
    fraction = require_finite_decimal(cap_bps, "cap_bps", non_negative=True) / BPS
    raw = book.ask * (Decimal("1") + fraction) if is_buy else book.bid * (Decimal("1") - fraction)
    if tick is None:
        return raw
    step = require_finite_decimal(tick, "tick", positive=True)
    rounding = ROUND_FLOOR if is_buy else ROUND_CEILING
    return (raw / step).to_integral_value(rounding=rounding) * step


__all__ = ["BPS", "BBO", "capped_limit_price"]
