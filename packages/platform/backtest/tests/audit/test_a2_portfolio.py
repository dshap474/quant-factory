"""A2 synthetic-oracle portfolio scenarios S21-S25.

Purpose: prove sequential equity-aware sizing and atomic multi-instrument
accounting against complete expected ledgers and result streams.

USAGE:
    uv run pytest -q packages/platform/backtest/tests/audit/test_a2_portfolio.py
"""

from __future__ import annotations

import pytest

from .a1_oracle import D, funding_cashflow, realized_on_close, unrealized
from .a1_world import FundingFact, run_world_and_assert, trace_hash
from .a2_support import (
    BTC,
    CAL,
    CAPITAL,
    ETH,
    account,
    decision,
    funding_record,
    holding,
    instrument,
    ledger,
    prices,
    quantity,
    shortfall,
    target,
    trade,
    world,
)

# --------------------------------------------------------------------------- #
# S21-S22: sequential equity snapshots
# --------------------------------------------------------------------------- #


def test_s21_second_target_sizes_from_equity_after_first_fee() -> None:
    first = trade(0, 0, BTC, quantity_value="500", price="100", fee_rate="0.001")
    second = trade(1, 2, BTC, quantity_value="499.5", price="100", fee_rate="0.001")
    expected = ledger(
        targets=(target(0, 0, ((BTC, "0.5", "100"),)), target(1, 2, ((BTC, "1", "100"),))),
        quantities=(
            quantity(0, 0, BTC, current="0", desired="500", reference="100"),
            quantity(1, 2, BTC, current="500", desired="999.5", reference="100"),
        ),
        trades=(first, second),
        holdings=(
            holding(0, BTC, "0", "100"),
            holding(1, BTC, "500", "100"),
            holding(3, BTC, "999.5", "100"),
        ),
        accounts=(
            account(0, cash=CAPITAL),
            account(1, cash=D("99950"), fees=D("50")),
            account(3, cash=D("99900.05"), fees=D("99.95")),
        ),
        shortfalls=(
            shortfall(
                0,
                0,
                BTC,
                intended=D("500"),
                fills=(first[2],),
                decision_price="100",
                arrival_price="100",
                terminal_price="100",
            ),
            shortfall(
                1,
                2,
                BTC,
                intended=D("499.5"),
                fills=(second[2],),
                decision_price="100",
                arrival_price="100",
                terminal_price="100",
            ),
        ),
        benchmark_prices=("100", "100", "100"),
    )
    synthetic = world(
        "S21",
        instruments=(instrument("BTC", prices("100"), fee_rate="0.001"),),
        decisions=(decision(0, {"BTC": "0.5"}), decision(2, {"BTC": "1"})),
        reports=(0, 1, 3),
    )
    run_world_and_assert(synthetic, expected)


@pytest.mark.parametrize(
    ("scenario", "mark", "realized", "unrealized_pnl", "equity"),
    [
        pytest.param("S22-gain", "110", "5000", "5000", "110000", id="realized-gain"),
        pytest.param("S22-loss", "90", "-5000", "-5000", "90000", id="realized-loss"),
    ],
)
def test_s22_second_target_sizes_from_current_marked_equity(
    scenario: str,
    mark: str,
    realized: str,
    unrealized_pnl: str,
    equity: str,
) -> None:
    first = trade(0, 0, BTC, quantity_value="1000", price="100")
    second = trade(1, 2, BTC, quantity_value="-500", price=mark)
    realized_decimal = realized_on_close(D("1000"), D("500"), D("100"), D(mark))
    assert realized_decimal == D(realized)
    expected = ledger(
        targets=(target(0, 0, ((BTC, "1", "100"),)), target(1, 2, ((BTC, "0.5", mark),))),
        quantities=(
            quantity(0, 0, BTC, current="0", desired="1000", reference="100"),
            quantity(1, 2, BTC, current="1000", desired="500", reference=mark),
        ),
        trades=(first, second),
        holdings=(holding(1, BTC, "1000", "100"), holding(3, BTC, "500", mark)),
        accounts=(
            account(1, cash=CAPITAL),
            account(
                3,
                cash=CAPITAL + realized_decimal,
                realized=realized_decimal,
                unrealized=D(unrealized_pnl),
            ),
        ),
        shortfalls=(
            shortfall(
                0,
                0,
                BTC,
                intended=D("1000"),
                fills=(first[2],),
                decision_price="100",
                arrival_price="100",
                terminal_price="100",
            ),
            shortfall(
                1,
                2,
                BTC,
                intended=D("-500"),
                fills=(second[2],),
                decision_price=mark,
                arrival_price=mark,
                terminal_price=mark,
            ),
        ),
        benchmark_prices=("100", mark),
    )
    assert expected.accounts[-1].equity == D(equity)
    synthetic = world(
        scenario,
        instruments=(instrument("BTC", prices("100", "100", mark, mark)),),
        decisions=(decision(0, {"BTC": "1"}), decision(2, {"BTC": "0.5"})),
        reports=(1, 3),
    )
    run_world_and_assert(synthetic, expected)


# --------------------------------------------------------------------------- #
# S23-S25: portfolio atomicity and isolation
# --------------------------------------------------------------------------- #


def test_s23_reordered_assets_produce_identical_atomic_trace() -> None:
    btc_trade = trade(0, 0, BTC, quantity_value="400", price="100")
    eth_trade = trade(0, 0, ETH, quantity_value="600", price="50")
    expected = ledger(
        targets=(target(0, 0, ((BTC, "0.4", "100"), (ETH, "0.3", "50"))),),
        quantities=(
            quantity(0, 0, BTC, current="0", desired="400", reference="100"),
            quantity(0, 0, ETH, current="0", desired="600", reference="50"),
        ),
        trades=(btc_trade, eth_trade),
        holdings=(
            holding(0, BTC, "0", "100"),
            holding(0, ETH, "0", "50"),
            holding(1, BTC, "400", "100"),
            holding(1, ETH, "600", "50"),
        ),
        accounts=(account(0, cash=CAPITAL), account(1, cash=CAPITAL)),
        shortfalls=(
            shortfall(
                0,
                0,
                BTC,
                intended=D("400"),
                fills=(btc_trade[2],),
                decision_price="100",
                arrival_price="100",
                terminal_price="100",
            ),
            shortfall(
                0,
                0,
                ETH,
                intended=D("600"),
                fills=(eth_trade[2],),
                decision_price="50",
                arrival_price="50",
                terminal_price="50",
            ),
        ),
        benchmark_prices=("100", "100"),
    )
    btc = instrument("BTC", prices("100"))
    eth = instrument("ETH", prices("50"))
    first_world = world(
        "S23",
        instruments=(btc, eth),
        decisions=(decision(0, {"BTC": "0.4", "ETH": "0.3"}),),
        reports=(0, 1),
    )
    second_world = world(
        "S23",
        instruments=(eth, btc),
        decisions=(decision(0, {"ETH": "0.3", "BTC": "0.4"}),),
        reports=(0, 1),
    )
    first = run_world_and_assert(first_world, expected)
    second = run_world_and_assert(second_world, expected)
    assert trace_hash(first) == trace_hash(second)


def test_s24_two_asset_pnl_fees_and_funding_sum_without_leakage() -> None:
    btc_fill = trade(0, 0, BTC, quantity_value="500", price="100", fee_rate="0.001")
    eth_fill = trade(0, 0, ETH, quantity_value="-500", price="50", fee_rate="0.002")
    btc_funding = FundingFact("S24-btc", BTC, CAL[2], D("0.001"), D("110"))
    eth_funding = FundingFact("S24-eth", ETH, CAL[2], D("0.002"), D("40"))
    funding_total = funding_cashflow(D("500"), D("110"), D("0.001")) + funding_cashflow(D("-500"), D("40"), D("0.002"))
    assert funding_total == D("-15")
    expected = ledger(
        targets=(target(0, 0, ((BTC, "0.5", "100"), (ETH, "-0.25", "50"))),),
        quantities=(
            quantity(0, 0, BTC, current="0", desired="500", reference="100"),
            quantity(0, 0, ETH, current="0", desired="-500", reference="50"),
        ),
        trades=(btc_fill, eth_fill),
        funding=(funding_record(btc_funding), funding_record(eth_funding)),
        holdings=(
            holding(0, BTC, "0", "100"),
            holding(0, ETH, "0", "50"),
            holding(1, BTC, "500", "100"),
            holding(1, ETH, "-500", "50"),
            holding(2, BTC, "500", "110"),
            holding(2, ETH, "-500", "40"),
        ),
        accounts=(
            account(0, cash=CAPITAL),
            account(1, cash=D("99900"), fees=D("100")),
            account(2, cash=D("99885"), unrealized=D("10000"), fees=D("100"), funding=D("-15")),
        ),
        shortfalls=(
            shortfall(
                0,
                0,
                BTC,
                intended=D("500"),
                fills=(btc_fill[2],),
                decision_price="100",
                arrival_price="100",
                terminal_price="100",
            ),
            shortfall(
                0,
                0,
                ETH,
                intended=D("-500"),
                fills=(eth_fill[2],),
                decision_price="50",
                arrival_price="50",
                terminal_price="50",
            ),
        ),
        benchmark_prices=("100", "100", "110"),
    )
    synthetic = world(
        "S24",
        instruments=(
            instrument("BTC", prices("100", "100", "110"), fee_rate="0.001"),
            instrument("ETH", prices("50", "50", "40"), fee_rate="0.002"),
        ),
        decisions=(decision(0, {"BTC": "0.5", "ETH": "-0.25"}),),
        reports=(0, 1, 2),
        funding=(eth_funding, btc_funding),
    )
    run_world_and_assert(synthetic, expected)


def test_s25_close_one_instrument_while_opening_another_is_isolated() -> None:
    first_btc = trade(0, 0, BTC, quantity_value="1000", price="100", fee_rate="0.001")
    close_btc = trade(1, 2, BTC, quantity_value="-1000", price="110", fee_rate="0.001")
    open_eth = trade(1, 2, ETH, quantity_value="1099", price="50", fee_rate="0.002")
    realized = realized_on_close(D("1000"), D("1000"), D("100"), D("110"))
    expected = ledger(
        targets=(
            target(0, 0, ((BTC, "1", "100"), (ETH, "0", "50"))),
            target(1, 2, ((BTC, "0", "110"), (ETH, "0.5", "50"))),
        ),
        quantities=(
            quantity(0, 0, BTC, current="0", desired="1000", reference="100"),
            quantity(0, 0, ETH, current="0", desired="0", reference="50"),
            quantity(1, 2, BTC, current="1000", desired="0", reference="110"),
            quantity(1, 2, ETH, current="0", desired="1099", reference="50"),
        ),
        trades=(first_btc, close_btc, open_eth),
        holdings=(
            holding(0, BTC, "0", "100"),
            holding(0, ETH, "0", "50"),
            holding(1, BTC, "1000", "100"),
            holding(1, ETH, "0", "50"),
            holding(3, BTC, "0", "110"),
            holding(3, ETH, "1099", "50"),
        ),
        accounts=(
            account(0, cash=CAPITAL),
            account(1, cash=D("99900"), fees=D("100")),
            account(3, cash=D("109680.1"), realized=realized, fees=D("319.9")),
        ),
        shortfalls=(
            shortfall(
                0,
                0,
                BTC,
                intended=D("1000"),
                fills=(first_btc[2],),
                decision_price="100",
                arrival_price="100",
                terminal_price="100",
            ),
            shortfall(
                0,
                0,
                ETH,
                intended=D("0"),
                fills=(),
                decision_price="50",
                arrival_price="50",
                terminal_price="50",
            ),
            shortfall(
                1,
                2,
                BTC,
                intended=D("-1000"),
                fills=(close_btc[2],),
                decision_price="110",
                arrival_price="110",
                terminal_price="110",
            ),
            shortfall(
                1,
                2,
                ETH,
                intended=D("1099"),
                fills=(open_eth[2],),
                decision_price="50",
                arrival_price="50",
                terminal_price="50",
            ),
        ),
        benchmark_prices=("100", "100", "110"),
    )
    synthetic = world(
        "S25",
        instruments=(
            instrument("BTC", prices("100", "100", "110", "110"), fee_rate="0.001"),
            instrument("ETH", prices("50"), fee_rate="0.002"),
        ),
        decisions=(decision(0, {"BTC": "1", "ETH": "0"}), decision(2, {"BTC": "0", "ETH": "0.5"})),
        reports=(0, 1, 3),
    )
    result = run_world_and_assert(synthetic, expected)
    assert result.execution is not None
    assert unrealized(result.execution.holdings[-1].quantity, D("50"), D("50")) == 0
