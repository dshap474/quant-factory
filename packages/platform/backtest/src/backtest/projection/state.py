"""Private mutable runtime state for linear-perpetual account projection.

Purpose: hold cash, signed positions, marks, and applied event IDs for the
backtest-owned projection fold. Public outputs remain execution DTOs.

USAGE:
    >>> from decimal import Decimal
    >>> from backtest.projection.state import PositionState
    >>> PositionState(quantity=Decimal("1"), average_price=Decimal("100"))
    PositionState(quantity=Decimal('1'), average_price=Decimal('100'))
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from execution import InstrumentKey, InstrumentSpec

# --------------------------------------------------------------------------- #
# Position and mark state
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class PositionState:
    """Mutable signed quantity and average entry price for one instrument."""

    quantity: Decimal = Decimal(0)
    average_price: Decimal = Decimal(0)


@dataclass(slots=True)
class MarkState:
    """Latest positive mark and its observation time."""

    price: Decimal
    observed_at: datetime


# --------------------------------------------------------------------------- #
# Projection ledger
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class ProjectionLedger:
    """Mutable cash/position ledger consumed by the projection core."""

    specs: dict[InstrumentKey, InstrumentSpec]
    cash: Decimal
    positions: dict[InstrumentKey, PositionState] = field(default_factory=dict)
    marks: dict[InstrumentKey, MarkState] = field(default_factory=dict)
    realized_pnl: Decimal = Decimal(0)
    cumulative_fees: Decimal = Decimal(0)
    cumulative_funding: Decimal = Decimal(0)
    applied_fill_ids: set[str] = field(default_factory=set)
    applied_settlement_ids: set[str] = field(default_factory=set)

    def position(self, key: InstrumentKey) -> PositionState:
        """Return existing position state or a flat zero-cost placeholder."""
        state = self.positions.get(key)
        if state is None:
            state = PositionState()
            self.positions[key] = state
        return state

    def open_positions(self) -> list[tuple[InstrumentKey, PositionState]]:
        """Open (non-zero) positions in deterministic instrument order."""
        items = [(key, pos) for key, pos in self.positions.items() if pos.quantity != 0]
        items.sort(key=lambda item: item[0].sort_key())
        return items
