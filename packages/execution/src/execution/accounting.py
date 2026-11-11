"""Pure fee, funding, account, and shortfall identities.

Purpose: provide small replayable accounting helpers that prove the
reconciliation identities without building an OMS or mutable engine.

USAGE:
    >>> from decimal import Decimal
    >>> from execution.accounting import funding_cashflow, equity_from_components
    >>> funding_cashflow(Decimal("2"), Decimal("100"), Decimal("1"), Decimal("0.0001"))
    Decimal('-0.0200')
"""

from __future__ import annotations

from decimal import Decimal
from typing import Iterable, Sequence

from execution._checks import require_finite_decimal, require_unique_ids
from execution.events import (
    Fill,
    Shortfall,
)
from execution.instruments import InstrumentKey

# --------------------------------------------------------------------------- #
# Fees and funding
# --------------------------------------------------------------------------- #


def total_fees(fills: Sequence[Fill]) -> Decimal:
    """Sum fill fees once from accepted fill events."""
    validate_unique_fill_ids(fills)
    return sum((f.fee for f in fills), Decimal(0))


def funding_cashflow(
    signed_position_qty: Decimal,
    settlement_mark: Decimal,
    contract_multiplier: Decimal,
    rate: Decimal,
) -> Decimal:
    """Cashflow for one funding settlement on the carried position.

    Linear contracts: positive rate means longs pay.
        funding_cashflow = -signed_position_qty * mark * multiplier * rate
    """
    qty = require_finite_decimal(signed_position_qty, "signed_position_qty")
    mark = require_finite_decimal(settlement_mark, "settlement_mark", positive=True)
    mult = require_finite_decimal(contract_multiplier, "contract_multiplier", positive=True)
    rate_d = require_finite_decimal(rate, "rate")
    return -qty * mark * mult * rate_d


# --------------------------------------------------------------------------- #
# Account identities
# --------------------------------------------------------------------------- #


def equity_from_components(settlement_cash: Decimal, unrealized_pnl: Decimal) -> Decimal:
    """Authoritative equity identity: cash + unrealized PnL."""
    cash = require_finite_decimal(settlement_cash, "settlement_cash")
    upnl = require_finite_decimal(unrealized_pnl, "unrealized_pnl")
    return cash + upnl


def apply_fee_to_cash(cash: Decimal, fee: Decimal) -> Decimal:
    """Subtract a signed fee once: a negative maker rebate credits cash."""
    cash_d = require_finite_decimal(cash, "cash")
    fee_d = require_finite_decimal(fee, "fee")
    return cash_d - fee_d


def apply_funding_to_cash(cash: Decimal, funding: Decimal) -> Decimal:
    """Apply funding cashflow to settlement cash."""
    cash_d = require_finite_decimal(cash, "cash")
    funding_d = require_finite_decimal(funding, "funding")
    return cash_d + funding_d


# --------------------------------------------------------------------------- #
# Shortfall
# --------------------------------------------------------------------------- #


def compute_shortfall(
    *,
    target_id: str,
    instrument: InstrumentKey,
    intended_quantity: Decimal,
    filled_quantity: Decimal,
    decision_price: Decimal,
    arrival_price: Decimal,
    terminal_price: Decimal,
    fills: Sequence[Fill],
    unfilled_quantity: Decimal,
    contract_multiplier: Decimal = Decimal(1),
) -> Shortfall:
    """Build a Shortfall record under the frozen signed convention.

    Positive shortfall is worse. Multiplier applies to every price×quantity term.
    """
    mult = require_finite_decimal(contract_multiplier, "contract_multiplier", positive=True)
    intended = require_finite_decimal(intended_quantity, "intended_quantity")
    filled = require_finite_decimal(filled_quantity, "filled_quantity")
    decision = require_finite_decimal(decision_price, "decision_price", positive=True)
    arrival = require_finite_decimal(arrival_price, "arrival_price", positive=True)
    terminal = require_finite_decimal(terminal_price, "terminal_price", positive=True)
    unfilled = require_finite_decimal(unfilled_quantity, "unfilled_quantity")

    validate_unique_fill_ids(fills)
    for fill in fills:
        if (fill.target_id, fill.instrument) != (target_id, instrument):
            raise ValueError("shortfall fills must match target_id and instrument")
        if intended != 0 and (fill.quantity > 0) != (intended > 0):
            raise ValueError("shortfall fill quantities must have the same sign as intended_quantity")
    actual_filled = sum((fill.quantity for fill in fills), Decimal(0))
    if actual_filled != filled:
        raise ValueError(f"filled_quantity must equal fill sum ({filled} != {actual_filled})")
    if filled + unfilled != intended:
        raise ValueError("intended_quantity must equal filled_quantity + unfilled_quantity")
    if filled != 0 and intended != 0 and (filled > 0) != (intended > 0):
        raise ValueError("filled_quantity must have the same sign as intended_quantity")
    if unfilled != 0 and intended != 0 and (unfilled > 0) != (intended > 0):
        raise ValueError("unfilled_quantity must have the same sign as intended_quantity")

    delay = filled * (arrival - decision) * mult
    trading = sum(
        (f.quantity * (f.price - arrival) * mult for f in fills),
        Decimal(0),
    )
    fee = sum((f.fee for f in fills), Decimal(0))
    unfilled_effect = unfilled * (terminal - decision) * mult
    total = delay + trading + fee + unfilled_effect

    return Shortfall(
        target_id=target_id,
        instrument=instrument,
        intended_quantity=intended,
        filled_quantity=filled,
        decision_price=decision,
        arrival_price=arrival,
        terminal_price=terminal,
        delay=delay,
        trading=trading,
        fee=fee,
        unfilled=unfilled_effect,
        total=total,
    )


# --------------------------------------------------------------------------- #
# Event identity
# --------------------------------------------------------------------------- #


def validate_unique_fill_ids(fills: Iterable[Fill]) -> None:
    """Reject duplicate fill IDs."""
    require_unique_ids((f.fill_id for f in fills), "fill_id")
