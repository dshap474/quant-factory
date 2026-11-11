"""Atomic target sizing tests across position transitions.

Purpose: prove order-independent long, short, reduction, reversal, and zero sizing.
USAGE: uv run --project packages/execution pytest packages/execution/tests/test_sizing.py -v
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest
from helpers import make_account, make_key, make_target

from execution import (
    round_toward_zero_to_increment,
    size_target_quantities,
)

# --------------------------------------------------------------------------- #
# Rounding
# --------------------------------------------------------------------------- #


def test_round_toward_zero_positive_and_negative() -> None:
    assert round_toward_zero_to_increment(Decimal("1.25"), Decimal("0.1")) == Decimal("1.2")
    assert round_toward_zero_to_increment(Decimal("-1.25"), Decimal("0.1")) == Decimal("-1.2")
    assert round_toward_zero_to_increment(Decimal("0"), Decimal("0.1")) == Decimal("0")


# --------------------------------------------------------------------------- #
# Atomic two-asset sizing
# --------------------------------------------------------------------------- #


def test_two_asset_sizing_independent_of_weight_order(
    btc_spec,
    eth_spec,
    flat_account,
) -> None:
    target_ab = make_target(weights=[("BTCUSDT", "0.5"), ("ETHUSDT", "0.5")])
    target_ba = make_target(weights=[("ETHUSDT", "0.5"), ("BTCUSDT", "0.5")])

    qty_ab = size_target_quantities(target_ab, flat_account, (btc_spec, eth_spec))
    qty_ba = size_target_quantities(target_ba, flat_account, (eth_spec, btc_spec))

    by_ab = {q.instrument: q for q in qty_ab}
    by_ba = {q.instrument: q for q in qty_ba}
    assert by_ab.keys() == by_ba.keys()
    for key in by_ab:
        assert by_ab[key].desired_quantity == by_ba[key].desired_quantity
        assert by_ab[key].delta_quantity == by_ba[key].delta_quantity

    # Equity 100_000; BTC 50% / 50000 = 1.0; ETH 50% / 3000 = 16.666 -> 16.666
    btc = by_ab[make_key("BTCUSDT")]
    eth = by_ab[make_key("ETHUSDT")]
    assert btc.desired_quantity == Decimal("1.000")
    assert eth.desired_quantity == Decimal("16.666")
    assert btc.delta_quantity == btc.desired_quantity
    assert eth.delta_quantity == eth.desired_quantity


def test_long_short_and_cash_residual(btc_spec, eth_spec, flat_account) -> None:
    target = make_target(
        weights=[("BTCUSDT", "0.6"), ("ETHUSDT", "-0.2")],
        cash_weight="0.6",
        prices={"BTCUSDT": "50000", "ETHUSDT": "3000"},
    )
    quantities = size_target_quantities(target, flat_account, (btc_spec, eth_spec))
    by_key = {q.instrument.symbol: q for q in quantities}
    # 0.6 * 100000 / 50000 = 1.2
    assert by_key["BTCUSDT"].desired_quantity == Decimal("1.200")
    # -0.2 * 100000 / 3000 = -6.666... -> -6.666
    assert by_key["ETHUSDT"].desired_quantity == Decimal("-6.666")


def test_reduction_and_reversal(btc_spec) -> None:
    target = make_target(
        weights=[("BTCUSDT", "0.1")],
        cash_weight="0.9",
        prices={"BTCUSDT": "50000"},
    )
    account = make_account(
        equity="100000",
        positions=[("BTCUSDT", "1.0", "48000")],
    )
    quantities = size_target_quantities(target, account, (btc_spec,))
    q = quantities[0]
    # desired = 0.1 * 100000 / 50000 = 0.2; current 1.0; delta -0.8
    assert q.desired_quantity == Decimal("0.200")
    assert q.current_quantity == Decimal("1.0")
    assert q.delta_quantity == Decimal("-0.800")

    reverse_target = make_target(
        target_id="rev",
        weights=[("BTCUSDT", "-0.2")],
        cash_weight="1.2",
        prices={"BTCUSDT": "50000"},
    )
    reverse_qty = size_target_quantities(reverse_target, account, (btc_spec,))[0]
    # desired = -0.4; current 1.0; delta -1.4
    assert reverse_qty.desired_quantity == Decimal("-0.400")
    assert reverse_qty.delta_quantity == Decimal("-1.400")


def test_zero_delta_when_already_at_target(btc_spec) -> None:
    target = make_target(
        weights=[("BTCUSDT", "0.5")],
        cash_weight="0.5",
        prices={"BTCUSDT": "50000"},
    )
    account = make_account(
        equity="100000",
        positions=[("BTCUSDT", "1.0", "50000")],
    )
    q = size_target_quantities(target, account, (btc_spec,))[0]
    assert q.desired_quantity == Decimal("1.000")
    assert q.delta_quantity == Decimal("0.000")


def test_non_unit_multiplier_converts_target_notional_to_contracts(btc_spec, flat_account) -> None:
    target = make_target(
        weights=[("BTCUSDT", "0.5")],
        cash_weight="0.5",
        prices={"BTCUSDT": "100"},
    )
    multiplier_spec = replace(btc_spec, multiplier=Decimal("10"), quantity_increment=Decimal("1"))

    quantity = size_target_quantities(target, flat_account, (multiplier_spec,))[0]

    # 100000 * 0.5 / (100 * 10) = 50 contracts, not 500 units.
    assert quantity.desired_quantity == Decimal("50")
    assert quantity.delta_quantity == Decimal("50")


@pytest.mark.parametrize(
    ("spec_changes", "weight", "message"),
    [
        ({"min_quantity": Decimal("501")}, "0.5", "below min_quantity"),
        ({"max_quantity": Decimal("499")}, "0.5", "exceeds max_quantity"),
        ({"min_notional": Decimal("50001")}, "0.5", "below min_notional"),
        ({"max_notional": Decimal("49999")}, "0.5", "exceeds max_notional"),
    ],
)
def test_order_limits_fail_before_planning(
    btc_spec,
    flat_account,
    spec_changes: dict[str, Decimal],
    weight: str,
    message: str,
) -> None:
    target = make_target(
        weights=[("BTCUSDT", weight)],
        cash_weight=str(Decimal("1") - Decimal(weight)),
        prices={"BTCUSDT": "100"},
    )
    limited_spec = replace(btc_spec, **spec_changes)

    with pytest.raises(ValueError, match=message):
        size_target_quantities(target, flat_account, (limited_spec,))


def test_missing_instrument_metadata_rejected(flat_account, btc_spec) -> None:
    target = make_target()
    with pytest.raises(ValueError, match="missing instrument metadata"):
        size_target_quantities(target, flat_account, (btc_spec,))


def test_account_as_of_after_earliest_rejected(btc_spec, eth_spec, two_asset_target) -> None:
    from datetime import timedelta

    from helpers import EARLIEST

    account = make_account(as_of=EARLIEST + timedelta(seconds=1))
    with pytest.raises(ValueError, match="as_of"):
        size_target_quantities(two_asset_target, account, (btc_spec, eth_spec))
