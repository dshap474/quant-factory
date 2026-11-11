"""Independent A8 single-instrument linear-perpetual state oracle.

Purpose: compute fill, funding, mark, account, and sizing state without any
imports from execution, backtest, strategies, Nautilus, Polars, or NumPy.

USAGE:
    state = ModelState(cash=Decimal("1000000"), multiplier=Decimal("1"))
    state.apply_fill(Decimal("2"), Decimal("100"), Decimal("0.08"))
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_FLOOR, Decimal

# --------------------------------------------------------------------------- #
# Independent state model
# --------------------------------------------------------------------------- #


@dataclass
class ModelState:
    """Minimal independent linear-perpetual ledger for generated audit cases."""

    cash: Decimal
    multiplier: Decimal
    quantity: Decimal = Decimal(0)
    average_price: Decimal = Decimal(0)
    realized: Decimal = Decimal(0)
    fees: Decimal = Decimal(0)
    funding: Decimal = Decimal(0)
    mark: Decimal = Decimal(100)

    def apply_fill(self, fill_quantity: Decimal, fill_price: Decimal, fee: Decimal) -> None:
        old_quantity = self.quantity
        if old_quantity == 0 or _same_sign(old_quantity, fill_quantity):
            total = abs(old_quantity) + abs(fill_quantity)
            self.average_price = (abs(old_quantity) * self.average_price + abs(fill_quantity) * fill_price) / total
            self.quantity = old_quantity + fill_quantity
        else:
            closed = min(abs(old_quantity), abs(fill_quantity))
            side = Decimal(1) if old_quantity > 0 else Decimal(-1)
            pnl = side * closed * (fill_price - self.average_price) * self.multiplier
            self.realized += pnl
            self.cash += pnl
            residual = old_quantity + fill_quantity
            if residual == 0:
                self.quantity = Decimal(0)
                self.average_price = Decimal(0)
            elif _same_sign(residual, old_quantity):
                self.quantity = residual
            else:
                self.quantity = residual
                self.average_price = fill_price
        self.cash -= fee
        self.fees += fee

    def apply_funding(self, rate: Decimal, mark: Decimal) -> None:
        cashflow = -self.quantity * mark * self.multiplier * rate
        self.cash += cashflow
        self.funding += cashflow

    def update_mark(self, mark: Decimal) -> None:
        self.mark = mark

    def unrealized(self) -> Decimal:
        return self.quantity * (self.mark - self.average_price) * self.multiplier

    def equity(self) -> Decimal:
        return self.cash + self.unrealized()

    def desired_quantity(self, weight: Decimal, price: Decimal, increment: Decimal) -> Decimal:
        raw = self.equity() * weight / (price * self.multiplier)
        steps = (abs(raw) / increment).to_integral_value(rounding=ROUND_FLOOR)
        return (steps * increment).copy_sign(raw)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _same_sign(left: Decimal, right: Decimal) -> bool:
    return (left > 0) == (right > 0)
