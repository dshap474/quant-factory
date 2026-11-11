"""Unit tests for linear-perpetual account projection (no Nautilus).

Purpose: cover long/short add, reduction, close, reversal, realized/unrealized
PnL, average price, fee once/duplicate rejection, funding-before-fill order,
snapshot, reporting event order, missing marks, and equity identity.

USAGE:
    uv run --project packages/platform/backtest pytest \\
      packages/platform/backtest/tests/unit/test_projection.py -v
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from backtest.projection import LinearPerpetualProjection, ProjectionError, replay_reporting

from execution import Fill, FundingSettlement, InstrumentKey, InstrumentSpec

# --------------------------------------------------------------------------- #
# Fixtures / builders
# --------------------------------------------------------------------------- #

UTC = timezone.utc
T0 = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)


def _key(symbol: str = "BTCUSDT") -> InstrumentKey:
    return InstrumentKey(venue="BINANCE", symbol=symbol)


def _spec(symbol: str = "BTCUSDT", *, multiplier: str = "1") -> InstrumentSpec:
    return InstrumentSpec(
        key=_key(symbol),
        product="perpetual",
        base_currency=symbol.replace("USDT", ""),
        quote_currency="USDT",
        settlement_currency="USDT",
        is_inverse=False,
        multiplier=Decimal(multiplier),
        price_increment=Decimal("0.01"),
        quantity_increment=Decimal("0.001"),
        min_quantity=Decimal("0.001"),
        max_quantity=Decimal("1000000"),
        min_notional=Decimal("5"),
        max_notional=Decimal("100000000"),
        maker_fee_rate=Decimal("0.0002"),
        taker_fee_rate=Decimal("0.0004"),
    )


def _projection(
    *,
    cash: str = "100000",
    symbols: tuple[str, ...] = ("BTCUSDT",),
    multiplier: str = "1",
) -> LinearPerpetualProjection:
    instruments = {_key(sym): _spec(sym, multiplier=multiplier) for sym in symbols}
    return LinearPerpetualProjection(
        initial_cash=Decimal(cash),
        instruments=instruments,
    )


def _fill(
    *,
    fill_id: str = "f1",
    symbol: str = "BTCUSDT",
    qty: str = "1",
    price: str = "100",
    fee: str = "0.04",
    fee_currency: str = "USDT",
    filled_at: datetime = T0,
    target_id: str = "t1",
    slice_id: str = "s1",
) -> Fill:
    return Fill(
        target_id=target_id,
        slice_id=slice_id,
        instrument=_key(symbol),
        fill_id=fill_id,
        quantity=Decimal(qty),
        price=Decimal(price),
        fee=Decimal(fee),
        fee_currency=fee_currency,
        filled_at=filled_at,
    )


def _funding(
    *,
    settlement_id: str = "fund1",
    symbol: str = "BTCUSDT",
    rate: str = "0.0001",
    mark: str = "100",
    settled_at: datetime = T0,
) -> FundingSettlement:
    return FundingSettlement(
        settlement_id=settlement_id,
        instrument=_key(symbol),
        settled_at=settled_at,
        rate=Decimal(rate),
        mark_price=Decimal(mark),
    )


# --------------------------------------------------------------------------- #
# Position mutations: long add, short add, reduction, close, reversal
# --------------------------------------------------------------------------- #


def test_long_add_updates_quantity_and_average_price() -> None:
    proj = _projection()
    proj.apply_fill(_fill(fill_id="f1", qty="2", price="100", fee="0.08"))
    proj.apply_fill(_fill(fill_id="f2", qty="1", price="110", fee="0.044", slice_id="s2"))

    assert proj.signed_quantity(_key()) == Decimal("3")
    # (2*100 + 1*110) / 3
    assert proj.average_price(_key()) == Decimal("103.3333333333333333333333333")
    assert proj.realized_pnl() == Decimal("0")
    assert proj.cumulative_fees() == Decimal("0.124")
    assert proj.cash() == Decimal("100000") - Decimal("0.124")


def test_short_add_updates_quantity_and_average_price() -> None:
    proj = _projection()
    proj.apply_fill(_fill(fill_id="f1", qty="-2", price="100", fee="0.08"))
    proj.apply_fill(_fill(fill_id="f2", qty="-1", price="90", fee="0.036", slice_id="s2"))

    assert proj.signed_quantity(_key()) == Decimal("-3")
    # (2*100 + 1*90) / 3
    assert proj.average_price(_key()) == Decimal("96.66666666666666666666666667")
    assert proj.realized_pnl() == Decimal("0")


def test_reduction_realizes_linear_pnl_and_keeps_average() -> None:
    proj = _projection()
    proj.apply_fill(_fill(fill_id="f1", qty="3", price="100", fee="0"))
    # Sell 1 @ 110: realize +10, qty 2, avg still 100
    proj.apply_fill(_fill(fill_id="f2", qty="-1", price="110", fee="0", slice_id="s2"))

    assert proj.signed_quantity(_key()) == Decimal("2")
    assert proj.average_price(_key()) == Decimal("100")
    assert proj.realized_pnl() == Decimal("10")
    assert proj.cash() == Decimal("100010")


def test_close_realizes_full_pnl_and_flattens() -> None:
    proj = _projection()
    proj.apply_fill(_fill(fill_id="f1", qty="-2", price="100", fee="0"))
    # Cover 2 @ 90: short profit +20
    proj.apply_fill(_fill(fill_id="f2", qty="2", price="90", fee="0", slice_id="s2"))

    assert proj.signed_quantity(_key()) == Decimal("0")
    assert proj.average_price(_key()) == Decimal("0")
    assert proj.realized_pnl() == Decimal("20")
    assert proj.cash() == Decimal("100020")


def test_reversal_realizes_closed_side_and_opens_residual() -> None:
    proj = _projection()
    proj.apply_fill(_fill(fill_id="f1", qty="2", price="100", fee="0"))
    # Sell 5 @ 110: close 2 for +20, open short 3 @ 110
    proj.apply_fill(_fill(fill_id="f2", qty="-5", price="110", fee="0", slice_id="s2"))

    assert proj.signed_quantity(_key()) == Decimal("-3")
    assert proj.average_price(_key()) == Decimal("110")
    assert proj.realized_pnl() == Decimal("20")
    assert proj.cash() == Decimal("100020")


# --------------------------------------------------------------------------- #
# Unrealized PnL, snapshot, equity identity, missing marks
# --------------------------------------------------------------------------- #


def test_unrealized_pnl_and_equity_identity() -> None:
    proj = _projection()
    proj.apply_fill(_fill(fill_id="f1", qty="2", price="100", fee="1"))
    proj.update_marks({_key(): Decimal("105")}, observed_at=T0)

    # cash = 100000 - 1; upnl = 2*(105-100)=10; equity=100009
    snap = proj.snapshot(T0)
    assert snap.cash == Decimal("99999")
    assert snap.equity == Decimal("100009")
    assert snap.equity == snap.cash + Decimal("10")
    assert snap.positions[0].quantity == Decimal("2")
    assert snap.positions[0].average_price == Decimal("100")
    assert snap.marks[0].price == Decimal("105")
    assert snap.cumulative_fees == Decimal("1")


def test_snapshot_requires_marks_for_open_positions() -> None:
    proj = _projection()
    proj.apply_fill(_fill(fill_id="f1", qty="1", price="100", fee="0"))
    with pytest.raises(ProjectionError, match="missing mark"):
        proj.snapshot(T0)


def test_update_marks_rejects_unknown_and_non_positive() -> None:
    proj = _projection()
    with pytest.raises(ProjectionError, match="unknown instrument"):
        proj.update_marks({_key("ETHUSDT"): Decimal("1")}, observed_at=T0)
    with pytest.raises(ProjectionError, match="positive"):
        proj.update_marks({_key(): Decimal("0")}, observed_at=T0)


# --------------------------------------------------------------------------- #
# Fee once, duplicates, unknown instrument, fee currency
# --------------------------------------------------------------------------- #


def test_fee_debited_once_and_duplicate_fill_rejected() -> None:
    proj = _projection()
    fill = _fill(fill_id="f1", qty="1", price="100", fee="4")
    proj.apply_fill(fill)
    assert proj.cash() == Decimal("99996")
    assert proj.cumulative_fees() == Decimal("4")
    with pytest.raises(ProjectionError, match="duplicate fill_id"):
        proj.apply_fill(fill)


def test_apply_fill_rejects_unknown_instrument_and_fee_currency() -> None:
    proj = _projection(symbols=("BTCUSDT",))
    with pytest.raises(ProjectionError, match="unknown instrument"):
        proj.apply_fill(_fill(fill_id="f1", symbol="ETHUSDT", qty="1", price="100", fee="0"))
    with pytest.raises(ProjectionError, match="fee currency mismatch"):
        proj.apply_fill(_fill(fill_id="f2", qty="1", price="100", fee="0.1", fee_currency="BTC"))


def test_apply_funding_rejects_duplicate_and_unknown() -> None:
    proj = _projection()
    settlement = _funding()
    proj.apply_funding(settlement)
    with pytest.raises(ProjectionError, match="duplicate settlement_id"):
        proj.apply_funding(settlement)
    with pytest.raises(ProjectionError, match="unknown instrument"):
        proj.apply_funding(_funding(settlement_id="fund2", symbol="ETHUSDT"))


# --------------------------------------------------------------------------- #
# Funding on carried position before same-time fill
# --------------------------------------------------------------------------- #


def test_funding_uses_carried_position_before_same_time_fill() -> None:
    """Equal-time order: mark -> funding -> fill; funding ignores the new fill."""
    proj = _projection()
    # Pre-open a long 2 so funding has a carried position.
    t_open = T0 - timedelta(hours=1)
    proj.apply_fill(_fill(fill_id="f0", qty="2", price="100", fee="0", filled_at=t_open))

    t = T0
    marks = ((t, {_key(): Decimal("100")}),)
    funding = (_funding(settlement_id="fund1", rate="0.0001", mark="100", settled_at=t),)
    # Same-time fill would grow the position to 5; funding must still use qty=2.
    fills = (_fill(fill_id="f1", qty="3", price="100", fee="0", filled_at=t),)
    reporting = (t,)

    holdings, account_path = replay_reporting(
        proj,
        marks=marks,
        funding=funding,
        fills=fills,
        reporting_times=reporting,
    )

    # funding = -2 * 100 * 1 * 0.0001 = -0.02
    assert proj.cumulative_funding() == Decimal("-0.0200")
    assert proj.signed_quantity(_key()) == Decimal("5")
    assert account_path[0].funding == Decimal("-0.0200")
    assert account_path[0].fees == Decimal("0")
    assert holdings[0].quantity == Decimal("5")
    assert holdings[0].mark_price == Decimal("100")
    assert holdings[0].notional == Decimal("500")


def test_funding_zero_when_flat_before_open_at_same_timestamp() -> None:
    proj = _projection()
    t = T0
    _, account_path = replay_reporting(
        proj,
        marks=((t, {_key(): Decimal("100")}),),
        funding=(_funding(rate="0.001", mark="100", settled_at=t),),
        fills=(_fill(fill_id="f1", qty="2", price="100", fee="0", filled_at=t),),
        reporting_times=(t,),
    )
    assert account_path[0].funding == Decimal("0")
    assert proj.signed_quantity(_key()) == Decimal("2")


# --------------------------------------------------------------------------- #
# Reporting event order and multi-step path
# --------------------------------------------------------------------------- #


def test_reporting_event_order_mark_funding_fills_then_report() -> None:
    proj = _projection(symbols=("BTCUSDT", "ETHUSDT"))
    btc = _key("BTCUSDT")
    eth = _key("ETHUSDT")
    t1 = T0
    t2 = T0 + timedelta(hours=8)

    # t1: open long BTC 1 @ 100 fee 0.04
    # t2: mark both, fund BTC (rate positive long pays), reduce BTC, open ETH short
    marks = (
        (t1, {btc: Decimal("100")}),
        (t2, {btc: Decimal("110"), eth: Decimal("3000")}),
    )
    funding = (
        _funding(
            settlement_id="fund-btc",
            symbol="BTCUSDT",
            rate="0.0001",
            mark="110",
            settled_at=t2,
        ),
    )
    fills = (
        _fill(fill_id="f1", symbol="BTCUSDT", qty="1", price="100", fee="0.04", filled_at=t1),
        _fill(
            fill_id="f2",
            symbol="BTCUSDT",
            qty="-1",
            price="110",
            fee="0.044",
            filled_at=t2,
            slice_id="s2",
        ),
        _fill(
            fill_id="f3",
            symbol="ETHUSDT",
            qty="-0.5",
            price="3000",
            fee="0.6",
            filled_at=t2,
            slice_id="s3",
        ),
    )
    holdings, account_path = replay_reporting(
        proj,
        marks=marks,
        funding=funding,
        fills=fills,
        reporting_times=(t1, t2),
    )

    assert len(account_path) == 2
    # After t1: cash 100000 - 0.04; upnl 0 (mark=avg)
    assert account_path[0].cash == Decimal("99999.96")
    assert account_path[0].unrealized_pnl == Decimal("0")
    assert account_path[0].equity == Decimal("99999.96")
    assert account_path[0].fees == Decimal("0.04")
    assert account_path[0].realized_pnl == Decimal("0")

    # Funding on carried BTC qty=1 before close: -1*110*1*0.0001 = -0.011
    # Realize close BTC: +10; fees total 0.04+0.044+0.6=0.684
    # cash = 100000 - 0.684 + 10 - 0.011 = 100009.305
    assert proj.cumulative_funding() == Decimal("-0.0110")
    assert proj.realized_pnl() == Decimal("10")
    assert proj.cumulative_fees() == Decimal("0.684")
    assert account_path[1].cash == Decimal("100009.305")
    assert account_path[1].funding == Decimal("-0.0110")
    assert account_path[1].realized_pnl == Decimal("10")
    # ETH short 0.5 @ 3000 mark 3000 => upnl 0
    assert account_path[1].unrealized_pnl == Decimal("0")
    assert account_path[1].equity == account_path[1].cash + account_path[1].unrealized_pnl

    # Holdings: t1 one BTC, t2 flat BTC omitted? We emit instruments with marks.
    # At t2 both btc (flat qty 0) and eth short have marks.
    t1_holdings = [h for h in holdings if h.timestamp == t1]
    t2_holdings = [h for h in holdings if h.timestamp == t2]
    assert len(t1_holdings) == 1
    assert t1_holdings[0].instrument == btc
    assert t1_holdings[0].quantity == Decimal("1")
    assert {h.instrument for h in t2_holdings} == {btc, eth}
    eth_h = next(h for h in t2_holdings if h.instrument == eth)
    assert eth_h.quantity == Decimal("-0.5")
    assert eth_h.notional == Decimal("-1500.0")


def test_multiplier_applies_to_realized_unrealized_and_funding() -> None:
    proj = _projection(multiplier="10")
    proj.apply_fill(_fill(fill_id="f1", qty="1", price="100", fee="0"))
    # Reduce 1 @ 101: realized = 1*(101-100)*10 = 10
    proj.apply_fill(_fill(fill_id="f2", qty="-1", price="101", fee="0", slice_id="s2"))
    assert proj.realized_pnl() == Decimal("10")

    proj.apply_fill(_fill(fill_id="f3", qty="2", price="100", fee="0", slice_id="s3"))
    proj.update_marks({_key(): Decimal("102")}, observed_at=T0)
    # upnl = 2*(102-100)*10 = 40
    assert proj.unrealized_pnl() == Decimal("40")
    proj.apply_funding(_funding(rate="0.001", mark="102"))
    # funding = -2*102*10*0.001 = -2.04
    assert proj.cumulative_funding() == Decimal("-2.040")


def test_snapshot_includes_prior_fees_funding_and_realized() -> None:
    proj = _projection()
    t1 = T0
    t2 = T0 + timedelta(hours=1)
    proj.apply_fill(_fill(fill_id="f1", qty="1", price="100", fee="0.5", filled_at=t1))
    proj.update_marks({_key(): Decimal("100")}, observed_at=t1)
    proj.apply_funding(_funding(rate="0.001", mark="100", settled_at=t1))
    # funding on 1: -0.1; cash = 100000 - 0.5 - 0.1 = 99999.4
    proj.apply_fill(_fill(fill_id="f2", qty="-1", price="105", fee="0.2", filled_at=t2, slice_id="s2"))
    # realize +5; cash = 99999.4 + 5 - 0.2 = 100004.2
    snap = proj.snapshot(t2)
    assert snap.cash == Decimal("100004.2")
    assert snap.equity == Decimal("100004.2")
    assert snap.cumulative_fees == Decimal("0.7")
    assert snap.cumulative_funding == Decimal("-0.1000")
    assert snap.positions == ()
