"""Validation and deterministic serialization for prepared initial state.

Purpose: bind an explicit non-flat account state to the first StrategyWeights
decision and derive its exact starting equity using validated instrument specs.

USAGE:
    >>> state = validate_initial_state(state, targets=targets, specs=specs)  # doctest: +SKIP
    >>> equity = initial_state_equity(state, specs=specs)  # doctest: +SKIP
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal

from execution import InitialAccountState, InstrumentKey, InstrumentSpec, PortfolioTarget

from ..errors import BacktestContractError

# --------------------------------------------------------------------------- #
# Contextual validation
# --------------------------------------------------------------------------- #


def validate_initial_state(
    state: InitialAccountState | None,
    *,
    targets: Sequence[PortfolioTarget],
    specs: Sequence[InstrumentSpec],
) -> InitialAccountState | None:
    """Validate one optional state against the first prepared target."""
    if state is None:
        return None
    if not isinstance(state, InitialAccountState):
        raise BacktestContractError("initial_state must be InitialAccountState or None")
    if not targets:
        raise BacktestContractError("initial state requires at least one target")
    first = targets[0]
    if state.as_of != first.decision_at:
        raise BacktestContractError("initial_state.as_of must equal the first target decision_at")

    spec_by_key = {spec.key: spec for spec in specs}
    target_keys = {weight.instrument for weight in first.weights}
    position_keys = {position.instrument for position in state.positions}
    if not position_keys <= target_keys:
        raise BacktestContractError("initial positions must be instruments in the first target")
    if not position_keys <= set(spec_by_key):
        raise BacktestContractError("initial positions lack instrument specifications")

    references = {reference.instrument: reference for reference in first.reference_prices}
    marks = {mark.instrument: mark for mark in state.marks}
    for position in state.positions:
        key = position.instrument
        spec = spec_by_key[key]
        mark = marks[key]
        reference = references[key]
        if mark.price != reference.price or mark.observed_at != reference.observed_at:
            raise BacktestContractError("initial marks must equal first-decision reference prices")
        if position.quantity % spec.quantity_increment != 0:
            raise BacktestContractError(f"initial position for {_key_id(key)} is not aligned to quantity_increment")
        if abs(position.quantity) > spec.max_quantity:
            raise BacktestContractError(f"initial position for {_key_id(key)} exceeds max_quantity")
        if abs(position.quantity * mark.price * spec.multiplier) > spec.max_notional:
            raise BacktestContractError(f"initial position for {_key_id(key)} exceeds max_notional")
    return state


def initial_state_equity(
    state: InitialAccountState,
    *,
    specs: Sequence[InstrumentSpec] | Mapping[InstrumentKey, InstrumentSpec],
) -> Decimal:
    """Return cash plus marked unrealized PnL for an already validated state."""
    spec_by_key = dict(specs) if isinstance(specs, Mapping) else {spec.key: spec for spec in specs}
    marks = {mark.instrument: mark.price for mark in state.marks}
    unrealized = sum(
        (
            position.quantity
            * (marks[position.instrument] - position.average_price)
            * spec_by_key[position.instrument].multiplier
            for position in state.positions
        ),
        Decimal(0),
    )
    equity = state.cash + unrealized
    if not equity.is_finite() or equity <= 0:
        raise BacktestContractError(f"initial state equity must be finite and positive, got {equity}")
    return equity


# --------------------------------------------------------------------------- #
# Stable provenance payload
# --------------------------------------------------------------------------- #


def initial_state_payload(state: InitialAccountState | None) -> dict[str, object] | None:
    """Return a deterministic primitive payload for hashing/publication."""
    if state is None:
        return None
    return {
        "as_of": state.as_of.isoformat(timespec="microseconds"),
        "cash": _decimal(state.cash),
        "positions": [
            {
                "instrument": _key_id(position.instrument),
                "quantity": _decimal(position.quantity),
                "average_price": _decimal(position.average_price),
            }
            for position in sorted(state.positions, key=lambda item: item.instrument.sort_key())
        ],
        "marks": [
            {
                "instrument": _key_id(mark.instrument),
                "price": _decimal(mark.price),
                "observed_at": mark.observed_at.isoformat(timespec="microseconds"),
            }
            for mark in sorted(state.marks, key=lambda item: item.instrument.sort_key())
        ],
    }


def _decimal(value: Decimal) -> str:
    normalized = value.normalize()
    return "0" if normalized == 0 else format(normalized, "f")


def _key_id(key: InstrumentKey) -> str:
    return f"{key.venue}:{key.symbol}"


__all__ = ["initial_state_equity", "initial_state_payload", "validate_initial_state"]
