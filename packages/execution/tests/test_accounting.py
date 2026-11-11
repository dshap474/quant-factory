"""Fee, funding, turnover, account, shortfall, and event reconciliation.

Purpose: prove pure accounting identities and rejection paths.
USAGE: uv run --project packages/execution pytest packages/execution/tests/test_accounting.py -v
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from execution.events import require_unique_funding
from helpers import EARLIEST, make_key

from execution import (
    Fill,
    FundingSettlement,
    apply_fee_to_cash,
    apply_funding_to_cash,
    compute_shortfall,
    equity_from_components,
    funding_cashflow,
    total_fees,
    validate_unique_fill_ids,
)

UTC = timezone.utc


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _fill(
    *,
    fill_id: str = "f1",
    qty: str = "1",
    price: str = "100",
    fee: str = "0.04",
    slice_id: str = "s1",
) -> Fill:
    return Fill(
        target_id="t1",
        slice_id=slice_id,
        instrument=make_key("BTCUSDT"),
        fill_id=fill_id,
        quantity=Decimal(qty),
        price=Decimal(price),
        fee=Decimal(fee),
        fee_currency="USDT",
        filled_at=EARLIEST,
    )


# --------------------------------------------------------------------------- #
# Fee / funding / equity
# --------------------------------------------------------------------------- #


def test_total_fees_once() -> None:
    fills = (_fill(fill_id="f1", fee="1.5"), _fill(fill_id="f2", fee="0.5"))
    assert total_fees(fills) == Decimal("2.0")


def test_funding_long_pays_when_rate_positive() -> None:
    # long 2 @ mark 100, mult 1, rate 0.0001 -> -0.02
    cf = funding_cashflow(
        Decimal("2"),
        Decimal("100"),
        Decimal("1"),
        Decimal("0.0001"),
    )
    assert cf == Decimal("-0.0200")


def test_funding_short_receives_when_rate_positive() -> None:
    cf = funding_cashflow(
        Decimal("-2"),
        Decimal("100"),
        Decimal("1"),
        Decimal("0.0001"),
    )
    assert cf == Decimal("0.0200")


def test_equity_and_cash_updates() -> None:
    assert equity_from_components(Decimal("1000"), Decimal("50")) == Decimal("1050")
    assert apply_fee_to_cash(Decimal("1000"), Decimal("4")) == Decimal("996")
    assert apply_funding_to_cash(Decimal("1000"), Decimal("-2")) == Decimal("998")


# --------------------------------------------------------------------------- #
# Shortfall
# --------------------------------------------------------------------------- #


def test_shortfall_reconciles_components() -> None:
    fills = (_fill(fill_id="f1", qty="1", price="102", fee="0.5"),)
    # decision 100, arrival 101, terminal 103
    # delay = 1*(101-100)=1
    # trading = 1*(102-101)=1
    # fee = 0.5
    # unfilled = 0
    sf = compute_shortfall(
        target_id="t1",
        instrument=make_key("BTCUSDT"),
        intended_quantity=Decimal("1"),
        filled_quantity=Decimal("1"),
        decision_price=Decimal("100"),
        arrival_price=Decimal("101"),
        terminal_price=Decimal("103"),
        fills=fills,
        unfilled_quantity=Decimal("0"),
    )
    assert sf.delay == Decimal("1")
    assert sf.trading == Decimal("1")
    assert sf.fee == Decimal("0.5")
    assert sf.unfilled == Decimal("0")
    assert sf.total == Decimal("2.5")


def test_shortfall_unfilled_component() -> None:
    fills = (_fill(fill_id="f1", qty="0.5", price="101", fee="0.1"),)
    sf = compute_shortfall(
        target_id="t1",
        instrument=make_key("BTCUSDT"),
        intended_quantity=Decimal("1"),
        filled_quantity=Decimal("0.5"),
        decision_price=Decimal("100"),
        arrival_price=Decimal("101"),
        terminal_price=Decimal("104"),
        fills=fills,
        unfilled_quantity=Decimal("0.5"),
    )
    # delay=0.5*(101-100)=0.5; trading=0.5*(101-101)=0; fee=0.1; unfilled=0.5*(104-100)=2
    assert sf.delay == Decimal("0.5")
    assert sf.trading == Decimal("0.0")
    assert sf.fee == Decimal("0.1")
    assert sf.unfilled == Decimal("2.0")
    assert sf.total == Decimal("2.6")


# --------------------------------------------------------------------------- #
# Duplicate events / outcome conservation helpers
# --------------------------------------------------------------------------- #


def test_duplicate_fill_ids_rejected() -> None:
    fills = (_fill(fill_id="dup"), _fill(fill_id="dup", slice_id="s2"))
    with pytest.raises(ValueError, match="duplicate fill_id"):
        validate_unique_fill_ids(fills)


def test_duplicate_settlement_ids_rejected() -> None:
    s = FundingSettlement(
        settlement_id="fund1",
        instrument=make_key("BTCUSDT"),
        settled_at=datetime(2024, 6, 1, 12, 0, tzinfo=UTC),
        rate=Decimal("0.0001"),
        mark_price=Decimal("50000"),
    )
    with pytest.raises(ValueError, match="duplicate settlement_id"):
        require_unique_funding((s, s))


def test_duplicate_instrument_settlement_timestamp_rejected() -> None:
    first = FundingSettlement(
        settlement_id="fund1",
        instrument=make_key("BTCUSDT"),
        settled_at=datetime(2024, 6, 1, 12, 0, tzinfo=UTC),
        rate=Decimal("0.0001"),
        mark_price=Decimal("50000"),
    )
    second = FundingSettlement(
        settlement_id="fund2",
        instrument=make_key("BTCUSDT"),
        settled_at=first.settled_at,
        rate=Decimal("0.0002"),
        mark_price=Decimal("50000"),
    )
    with pytest.raises(ValueError, match="instrument settlement timestamp"):
        require_unique_funding((first, second))


def test_shortfall_rejects_unrelated_fill() -> None:
    fill = Fill(
        target_id="other",
        slice_id="other-slice",
        instrument=make_key("ETHUSDT"),
        fill_id="wrong",
        quantity=Decimal("1"),
        price=Decimal("100"),
        fee=Decimal("1"),
        fee_currency="USDT",
        filled_at=EARLIEST,
    )
    with pytest.raises(ValueError, match="match target_id and instrument"):
        compute_shortfall(
            target_id="t1",
            instrument=make_key("BTCUSDT"),
            intended_quantity=Decimal("1"),
            filled_quantity=Decimal("1"),
            decision_price=Decimal("100"),
            arrival_price=Decimal("101"),
            terminal_price=Decimal("102"),
            fills=(fill,),
            unfilled_quantity=Decimal("0"),
        )


def test_shortfall_rejects_declared_fill_mismatch() -> None:
    with pytest.raises(ValueError, match="fill sum"):
        compute_shortfall(
            target_id="t1",
            instrument=make_key("BTCUSDT"),
            intended_quantity=Decimal("2"),
            filled_quantity=Decimal("2"),
            decision_price=Decimal("100"),
            arrival_price=Decimal("101"),
            terminal_price=Decimal("102"),
            fills=(_fill(qty="1"),),
            unfilled_quantity=Decimal("0"),
        )
