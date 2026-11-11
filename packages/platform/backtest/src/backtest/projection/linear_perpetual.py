"""Backtest-owned linear-perpetual fill/funding/mark projection core.

Purpose: fold validated InstrumentSpec, Fill, and FundingSettlement events into
authoritative cash/position state for next-target sizing. No Nautilus imports.

USAGE:
    >>> from decimal import Decimal
    >>> from datetime import datetime, timezone
    >>> from backtest.projection import LinearPerpetualProjection  # doctest: +SKIP
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Mapping

from execution import (
    AccountSnapshot,
    Fill,
    FundingSettlement,
    InitialAccountState,
    InstrumentKey,
    InstrumentSpec,
    PositionSnapshot,
    ReferencePrice,
    apply_fee_to_cash,
    apply_funding_to_cash,
    equity_from_components,
    funding_cashflow,
)

from .state import MarkState, PositionState, ProjectionLedger

# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #


class ProjectionError(ValueError):
    """Raised when a projection event is invalid or non-deterministic."""


# --------------------------------------------------------------------------- #
# Core
# --------------------------------------------------------------------------- #


class LinearPerpetualProjection:
    """Mutable linear-perpetual account projection for execution accounting.

    Public methods consume engine-neutral execution DTOs and emit immutable
    AccountSnapshot values. Internal quantity/average-price state is private.
    """

    def __init__(
        self,
        *,
        initial_cash: Decimal,
        instruments: Mapping[InstrumentKey, InstrumentSpec],
        initial_state: InitialAccountState | None = None,
    ) -> None:
        if not instruments:
            raise ProjectionError("instruments must be non-empty")
        if initial_cash <= 0:
            raise ProjectionError("initial_cash must be positive")
        specs: dict[InstrumentKey, InstrumentSpec] = {}
        for key, spec in instruments.items():
            if not isinstance(spec, InstrumentSpec):
                raise TypeError("instruments values must be InstrumentSpec")
            if spec.key != key:
                raise ProjectionError(f"instrument map key {key!r} does not match spec.key {spec.key!r}")
            if key in specs:
                raise ProjectionError(f"duplicate instrument: {key!r}")
            specs[key] = spec
        self._ledger = ProjectionLedger(specs=specs, cash=initial_cash)
        if initial_state is not None:
            self._seed_initial_state(initial_state)

    # ------------------------------------------------------------------ #
    # Event application
    # ------------------------------------------------------------------ #

    def apply_fill(self, fill: Fill) -> None:
        """Apply one accepted fill: position, realized PnL, and fee once."""
        if not isinstance(fill, Fill):
            raise TypeError("fill must be Fill")
        if fill.fill_id in self._ledger.applied_fill_ids:
            raise ProjectionError(f"duplicate fill_id: {fill.fill_id!r}")
        spec = self._require_spec(fill.instrument)
        if fill.fee_currency != spec.settlement_currency:
            raise ProjectionError(f"fee currency mismatch: {fill.fee_currency!r} != {spec.settlement_currency!r}")

        position = self._ledger.position(fill.instrument)
        realized = _realize_linear_fill(
            position=position,
            fill_qty=fill.quantity,
            fill_price=fill.price,
            multiplier=spec.multiplier,
        )
        self._ledger.realized_pnl += realized
        self._ledger.cash += realized
        self._ledger.cash = apply_fee_to_cash(self._ledger.cash, fill.fee)
        self._ledger.cumulative_fees += fill.fee
        self._ledger.applied_fill_ids.add(fill.fill_id)

    def _seed_initial_state(self, state: InitialAccountState) -> None:
        """Load validated carried positions without manufacturing fills."""
        if not isinstance(state, InitialAccountState):
            raise TypeError("initial_state must be InitialAccountState")
        if state.cash != self._ledger.cash:
            raise ProjectionError(f"initial_state cash {state.cash} does not match initial_cash {self._ledger.cash}")
        marks = {mark.instrument: mark for mark in state.marks}
        for position in state.positions:
            self._require_spec(position.instrument)
            self._ledger.positions[position.instrument] = PositionState(
                quantity=position.quantity,
                average_price=position.average_price,
            )
            mark = marks[position.instrument]
            self._ledger.marks[position.instrument] = MarkState(
                price=mark.price,
                observed_at=mark.observed_at,
            )

    def apply_funding(self, settlement: FundingSettlement) -> None:
        """Apply funding to the position carried before later same-time fills."""
        if not isinstance(settlement, FundingSettlement):
            raise TypeError("settlement must be FundingSettlement")
        if settlement.settlement_id in self._ledger.applied_settlement_ids:
            raise ProjectionError(f"duplicate settlement_id: {settlement.settlement_id!r}")
        spec = self._require_spec(settlement.instrument)
        position = self._ledger.positions.get(settlement.instrument)
        qty = position.quantity if position is not None else Decimal(0)
        cashflow = funding_cashflow(
            qty,
            settlement.mark_price,
            spec.multiplier,
            settlement.rate,
        )
        self._ledger.cash = apply_funding_to_cash(self._ledger.cash, cashflow)
        self._ledger.cumulative_funding += cashflow
        self._ledger.applied_settlement_ids.add(settlement.settlement_id)

    def update_marks(
        self,
        marks: Mapping[InstrumentKey, Decimal],
        *,
        observed_at: datetime,
    ) -> None:
        """Store positive marks for known instruments at one observation time."""
        if not marks:
            raise ProjectionError("marks must be non-empty")
        for key, price in marks.items():
            self._require_spec(key)
            if price <= 0:
                raise ProjectionError(f"mark price must be positive for {key!r}, got {price}")
            self._ledger.marks[key] = MarkState(price=price, observed_at=observed_at)

    # ------------------------------------------------------------------ #
    # Snapshots
    # ------------------------------------------------------------------ #

    def snapshot(self, as_of: datetime) -> AccountSnapshot:
        """Build the immutable pre-target view for next-target sizing."""
        positions, mark_refs, unrealized = self._position_views(as_of=as_of)
        equity = equity_from_components(self._ledger.cash, unrealized)
        return AccountSnapshot(
            as_of=as_of,
            cash=self._ledger.cash,
            equity=equity,
            positions=positions,
            marks=mark_refs,
            cumulative_fees=self._ledger.cumulative_fees,
            cumulative_funding=self._ledger.cumulative_funding,
        )

    def unrealized_pnl(self) -> Decimal:
        """Sum signed unrealized PnL using latest marks for open positions."""
        total = Decimal(0)
        for key, position in self._ledger.open_positions():
            mark = self._ledger.marks.get(key)
            if mark is None:
                raise ProjectionError(f"missing mark for open position: {_key_id(key)}")
            mult = self._ledger.specs[key].multiplier
            total += position.quantity * (mark.price - position.average_price) * mult
        return total

    def realized_pnl(self) -> Decimal:
        """Cumulative trading realized PnL (excludes funding)."""
        return self._ledger.realized_pnl

    def cumulative_fees(self) -> Decimal:
        return self._ledger.cumulative_fees

    def cumulative_funding(self) -> Decimal:
        return self._ledger.cumulative_funding

    def cash(self) -> Decimal:
        return self._ledger.cash

    def signed_quantity(self, instrument: InstrumentKey) -> Decimal:
        position = self._ledger.positions.get(instrument)
        return position.quantity if position is not None else Decimal(0)

    def average_price(self, instrument: InstrumentKey) -> Decimal:
        position = self._ledger.positions.get(instrument)
        return position.average_price if position is not None else Decimal(0)

    def mark_price(self, instrument: InstrumentKey) -> Decimal | None:
        mark = self._ledger.marks.get(instrument)
        return mark.price if mark is not None else None

    def instrument_keys(self) -> tuple[InstrumentKey, ...]:
        return tuple(sorted(self._ledger.specs, key=lambda key: key.sort_key()))

    def multiplier(self, instrument: InstrumentKey) -> Decimal:
        return self._require_spec(instrument).multiplier

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    def _require_spec(self, key: InstrumentKey) -> InstrumentSpec:
        spec = self._ledger.specs.get(key)
        if spec is None:
            raise ProjectionError(f"unknown instrument: {_key_id(key)}")
        return spec

    def _position_views(
        self,
        *,
        as_of: datetime,
    ) -> tuple[tuple[PositionSnapshot, ...], tuple[ReferencePrice, ...], Decimal]:
        open_items = self._ledger.open_positions()
        positions: list[PositionSnapshot] = []
        mark_refs: list[ReferencePrice] = []
        unrealized = Decimal(0)
        for key, position in open_items:
            mark = self._ledger.marks.get(key)
            if mark is None:
                raise ProjectionError(f"missing mark for open position: {_key_id(key)}")
            if mark.observed_at > as_of:
                raise ProjectionError(
                    f"mark for {_key_id(key)} observed after as_of "
                    f"({mark.observed_at.isoformat()} > {as_of.isoformat()})"
                )
            mult = self._ledger.specs[key].multiplier
            unrealized += position.quantity * (mark.price - position.average_price) * mult
            positions.append(
                PositionSnapshot(
                    instrument=key,
                    quantity=position.quantity,
                    average_price=position.average_price,
                )
            )
            mark_refs.append(ReferencePrice(instrument=key, price=mark.price, observed_at=mark.observed_at))
        return tuple(positions), tuple(mark_refs), unrealized


# --------------------------------------------------------------------------- #
# Linear fill realization
# --------------------------------------------------------------------------- #


def _realize_linear_fill(
    *,
    position: PositionState,
    fill_qty: Decimal,
    fill_price: Decimal,
    multiplier: Decimal,
) -> Decimal:
    """Update position state and return realized PnL for one linear fill.

    Adds average into an existing side. Reductions, closes, and reversals realize
    ``sign(old_qty) * closed_qty * (fill_price - avg) * multiplier``.
    """
    old_qty = position.quantity
    avg = position.average_price
    new_qty = old_qty + fill_qty

    if old_qty == 0:
        position.quantity = fill_qty
        position.average_price = fill_price
        return Decimal(0)

    same_side = (old_qty > 0) == (fill_qty > 0)
    if same_side:
        # Weighted average of absolute quantities on the carried side.
        abs_old = abs(old_qty)
        abs_fill = abs(fill_qty)
        position.average_price = (abs_old * avg + abs_fill * fill_price) / (abs_old + abs_fill)
        position.quantity = new_qty
        return Decimal(0)

    closed = min(abs(old_qty), abs(fill_qty))
    sign = Decimal(1) if old_qty > 0 else Decimal(-1)
    realized = sign * closed * (fill_price - avg) * multiplier

    if new_qty == 0:
        position.quantity = Decimal(0)
        position.average_price = Decimal(0)
    elif abs(fill_qty) < abs(old_qty):
        # Partial reduction: keep average entry.
        position.quantity = new_qty
    else:
        # Reversal: residual opens at the fill price.
        position.quantity = new_qty
        position.average_price = fill_price
    return realized


def _key_id(key: InstrumentKey) -> str:
    return f"{key.venue}:{key.symbol}"
