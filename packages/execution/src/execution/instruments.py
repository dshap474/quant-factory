"""Engine-neutral execution instrument identity and metadata.

Purpose: define provider-neutral execution instrument metadata without importing
provider or engine types.

USAGE:
    >>> from decimal import Decimal
    >>> from execution.instruments import InstrumentKey
    >>> InstrumentKey(venue="EXAMPLE", symbol="BTC-USD")
    InstrumentKey(venue='EXAMPLE', symbol='BTC-USD')
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from execution._checks import require_finite_decimal, require_non_empty_str

# --------------------------------------------------------------------------- #
# Contracts
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class InstrumentKey:
    """Stable engine-neutral instrument identity."""

    venue: str
    symbol: str

    def __post_init__(self) -> None:
        require_non_empty_str(self.venue, "venue")
        require_non_empty_str(self.symbol, "symbol")

    def sort_key(self) -> tuple[str, str]:
        """Return deterministic venue/symbol ordering."""
        return (self.venue, self.symbol)

    def identity(self) -> str:
        """Return the ``venue:symbol`` label used in ids and messages."""
        return f"{self.venue}:{self.symbol}"


@dataclass(frozen=True, slots=True)
class InstrumentSpec:
    """Validated execution-instrument metadata."""

    key: InstrumentKey
    product: str
    base_currency: str
    quote_currency: str
    settlement_currency: str
    is_inverse: bool
    multiplier: Decimal
    price_increment: Decimal
    quantity_increment: Decimal
    min_quantity: Decimal
    max_quantity: Decimal
    min_notional: Decimal
    max_notional: Decimal
    maker_fee_rate: Decimal
    taker_fee_rate: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.key, InstrumentKey):
            raise TypeError("key must be InstrumentKey")
        for name in ("product", "base_currency", "quote_currency", "settlement_currency"):
            require_non_empty_str(getattr(self, name), name)
        if not isinstance(self.is_inverse, bool):
            raise TypeError("is_inverse must be bool")

        for name in ("multiplier", "price_increment", "quantity_increment", "max_quantity", "max_notional"):
            object.__setattr__(
                self,
                name,
                require_finite_decimal(getattr(self, name), name, positive=True),
            )
        for name in ("min_quantity", "min_notional", "taker_fee_rate"):
            object.__setattr__(
                self,
                name,
                require_finite_decimal(getattr(self, name), name, non_negative=True),
            )
        object.__setattr__(self, "maker_fee_rate", require_finite_decimal(self.maker_fee_rate, "maker_fee_rate"))

        if self.min_quantity > self.max_quantity:
            raise ValueError("min_quantity must be <= max_quantity")
        if self.min_notional > self.max_notional:
            raise ValueError("min_notional must be <= max_notional")
        if self.is_inverse:
            raise ValueError("inverse contracts are not supported in the first slice")
