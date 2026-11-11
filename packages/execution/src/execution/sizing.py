"""Atomic portfolio target sizing independent of asset order.

Purpose: translate one PortfolioTarget and one AccountSnapshot into per-
instrument TargetQuantity records using a single equity and reference vector.

USAGE:
    >>> from execution.sizing import round_toward_zero_to_increment, size_target_quantities
    >>> from decimal import Decimal
    >>> round_toward_zero_to_increment(Decimal("1.25"), Decimal("0.1"))
    Decimal('1.2')
"""

from __future__ import annotations

from decimal import ROUND_FLOOR, Decimal

from execution._checks import require_finite_decimal
from execution.instruments import InstrumentKey, InstrumentSpec
from execution.targets import (
    AccountSnapshot,
    PortfolioTarget,
    TargetQuantity,
)

# --------------------------------------------------------------------------- #
# Rounding
# --------------------------------------------------------------------------- #


def round_toward_zero_to_increment(value: Decimal, increment: Decimal) -> Decimal:
    """Round ``value`` toward zero to an integer multiple of ``increment``."""
    value = require_finite_decimal(value, "value")
    increment = require_finite_decimal(increment, "increment", positive=True)
    if value == 0:
        return Decimal(0)
    steps = (abs(value) / increment).to_integral_value(rounding=ROUND_FLOOR)
    return (steps * increment).copy_sign(value)


# --------------------------------------------------------------------------- #
# Atomic sizing
# --------------------------------------------------------------------------- #


def size_target_quantities(
    target: PortfolioTarget,
    account: AccountSnapshot,
    instruments: tuple[InstrumentSpec, ...] | list[InstrumentSpec],
) -> tuple[TargetQuantity, ...]:
    """Size every non-CASH instrument from one snapshot and reference vector.

    For each instrument:
        desired_notional = equity * weight
        raw_desired_qty  = desired_notional / (reference_price * multiplier)
        desired_qty      = round_toward_zero_to_increment(raw, qty_increment)
        delta_qty        = desired_qty - current_qty

    Instrument iteration order cannot affect any individual result. Output is
    sorted by instrument identity for deterministic boundary ordering.
    """
    if not isinstance(target, PortfolioTarget):
        raise TypeError("target must be PortfolioTarget")
    if not isinstance(account, AccountSnapshot):
        raise TypeError("account must be AccountSnapshot")
    if account.as_of > target.earliest_execution_at:
        raise ValueError(
            "account.as_of must be at or before target.earliest_execution_at "
            f"({account.as_of} > {target.earliest_execution_at})"
        )

    specs = tuple(instruments)
    if not specs:
        raise ValueError("instruments must not be empty")

    spec_by_key: dict[InstrumentKey, InstrumentSpec] = {}
    for spec in specs:
        if not isinstance(spec, InstrumentSpec):
            raise TypeError("instruments must contain InstrumentSpec values")
        if spec.key in spec_by_key:
            raise ValueError(f"duplicate instrument spec for {spec.key.identity()}")
        spec_by_key[spec.key] = spec

    weight_keys = {w.instrument for w in target.weights}
    missing_specs = weight_keys - set(spec_by_key)
    if missing_specs:
        names = ", ".join(k.identity() for k in sorted(missing_specs, key=lambda x: x.sort_key()))
        raise ValueError(f"missing instrument metadata for: {names}")

    ref_by_key = {r.instrument: r for r in target.reference_prices}
    mark_by_key = {mark.instrument: mark for mark in account.marks}
    position_by_key = {position.instrument: position.quantity for position in account.positions}
    equity = account.equity

    results: list[TargetQuantity] = []
    for weight in target.weights:
        instrument = weight.instrument
        spec = spec_by_key[instrument]
        reference = ref_by_key[instrument]
        desired_notional = equity * weight.weight
        raw_desired_qty = desired_notional / (reference.price * spec.multiplier)
        desired_qty = round_toward_zero_to_increment(raw_desired_qty, spec.quantity_increment)
        current_qty = position_by_key.get(instrument, Decimal(0))
        if current_qty % spec.quantity_increment != 0:
            raise ValueError(
                f"current position for {instrument.identity()} is not aligned "
                f"to quantity_increment {spec.quantity_increment}"
            )
        delta_qty = desired_qty - current_qty
        if delta_qty != 0:
            limit_price = mark_by_key.get(instrument, reference).price
            validate_order_limits(
                order_quantity=delta_qty,
                price=limit_price,
                spec=spec,
            )
        results.append(
            TargetQuantity(
                target_id=target.target_id,
                instrument=instrument,
                current_quantity=current_qty,
                desired_quantity=desired_qty,
                delta_quantity=delta_qty,
                reference_price=reference.price,
                decision_at=target.decision_at,
                earliest_execution_at=target.earliest_execution_at,
                quantity_increment=spec.quantity_increment,
            )
        )

    results.sort(key=lambda q: q.instrument.sort_key())
    return tuple(results)


def validate_order_limits(
    *,
    order_quantity: Decimal,
    price: Decimal,
    spec: InstrumentSpec,
) -> None:
    """Reject one concrete order outside its quantity or notional limits."""
    absolute_quantity = abs(order_quantity)
    instrument = spec.key.identity()
    if absolute_quantity < spec.min_quantity:
        raise ValueError(
            f"order quantity for {instrument} is below min_quantity: {absolute_quantity} < {spec.min_quantity}"
        )
    if absolute_quantity > spec.max_quantity:
        raise ValueError(
            f"order quantity for {instrument} exceeds max_quantity: {absolute_quantity} > {spec.max_quantity}"
        )
    notional = absolute_quantity * price * spec.multiplier
    if notional < spec.min_notional:
        raise ValueError(f"order notional for {instrument} is below min_notional: {notional} < {spec.min_notional}")
    if notional > spec.max_notional:
        raise ValueError(f"order notional for {instrument} exceeds max_notional: {notional} > {spec.max_notional}")
