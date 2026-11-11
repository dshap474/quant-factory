"""Independent signed-fee accounting examples, including maker rebates.

Purpose: preserve provider fee signs through fills, cash, snapshots and shortfall.
USAGE: uv run pytest packages/execution/tests/test_signed_fees.py -q
"""

from dataclasses import replace
from decimal import Decimal

import pytest
from helpers import EARLIEST, make_account, make_key, make_spec

from execution import AccountPoint, Fill, apply_fee_to_cash, compute_shortfall, total_fees

# --------------------------------------------------------------------------- #
# Independently calculated cash and implementation shortfall
# --------------------------------------------------------------------------- #


def test_rebate_is_a_cash_credit_and_reduces_shortfall() -> None:
    # Buy two units at 101 versus a 100 decision: price cost 2, rebate 0.25,
    # total cost 1.75. The rebate credits 0.25 to cash, never debits it.
    fill = Fill("t", "s", make_key("ASSET"), "f", Decimal("2"), Decimal("101"), Decimal("-0.25"), "USDC", EARLIEST)
    assert total_fees((fill,)) == Decimal("-0.25")
    assert apply_fee_to_cash(Decimal("1000"), fill.fee) == Decimal("1000.25")
    result = compute_shortfall(
        target_id="t",
        instrument=fill.instrument,
        intended_quantity=Decimal("2"),
        filled_quantity=Decimal("2"),
        decision_price=Decimal("100"),
        arrival_price=Decimal("100.5"),
        terminal_price=Decimal("101"),
        fills=(fill,),
        unfilled_quantity=Decimal("0"),
    )
    assert (result.delay, result.trading, result.fee, result.total) == (
        Decimal("1"),
        Decimal("1"),
        Decimal("-0.25"),
        Decimal("1.75"),
    )
    # A taker charge of 0.40 nets with the rebate to a charge of 0.15.
    charge = replace(fill, fill_id="g", fee=Decimal("0.40"))
    assert total_fees((fill, charge)) == Decimal("0.15")


def test_signed_fee_survives_account_projections_and_metadata() -> None:
    account = replace(make_account(), cumulative_fees=Decimal("-0.25"))
    assert account.cumulative_fees == Decimal("-0.25")
    point = AccountPoint(
        EARLIEST, Decimal("1000.25"), Decimal("1000.25"), Decimal("0.25"), Decimal("0"), Decimal("-0.25"), Decimal("0")
    )
    assert point.fees == Decimal("-0.25")
    spec = replace(make_spec("ASSET"), maker_fee_rate=Decimal("-0.00005"))
    assert spec.maker_fee_rate == Decimal("-0.00005")


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity"])
def test_signed_does_not_mean_nonfinite(bad: str) -> None:
    with pytest.raises(ValueError):
        apply_fee_to_cash(Decimal("1"), Decimal(bad))
    with pytest.raises(ValueError):
        replace(make_account(), cumulative_fees=Decimal(bad))
    with pytest.raises(ValueError):
        replace(make_spec("ASSET"), maker_fee_rate=Decimal(bad))
