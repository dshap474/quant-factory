"""A2 synthetic-oracle policy and contract scenarios S26-S31.

Purpose: prove immediate/TWAP lifecycle, lot rounding, non-unit contract
multiplier economics, and exact terminal outcome coverage.

USAGE:
    uv run pytest -q \
      packages/platform/backtest/tests/audit/test_a2_policy_multiplier.py
"""

from __future__ import annotations

import pytest

from .a1_oracle import D, desired_quantity, funding_cashflow, unrealized, weighted_average
from .a1_world import FundingFact, run_world_and_assert
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
# S26-S28: immediate and TWAP policy lifecycle
# --------------------------------------------------------------------------- #


def test_s26_immediate_emits_one_due_ioc_per_nonzero_leg() -> None:
    btc_fill = trade(0, 0, BTC, quantity_value="400", price="100")
    eth_fill = trade(0, 0, ETH, quantity_value="600", price="50")
    expected = ledger(
        targets=(target(0, 0, ((BTC, "0.4", "100"), (ETH, "0.3", "50"))),),
        quantities=(
            quantity(0, 0, BTC, current="0", desired="400", reference="100"),
            quantity(0, 0, ETH, current="0", desired="600", reference="50"),
        ),
        trades=(btc_fill, eth_fill),
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
                fills=(btc_fill[2],),
                decision_price="100",
                arrival_price="100",
                terminal_price="100",
            ),
            shortfall(
                0,
                0,
                ETH,
                intended=D("600"),
                fills=(eth_fill[2],),
                decision_price="50",
                arrival_price="50",
                terminal_price="50",
            ),
        ),
        benchmark_prices=("100", "100"),
    )
    synthetic = world(
        "S26",
        instruments=(instrument("BTC", prices("100")), instrument("ETH", prices("50"))),
        decisions=(decision(0, {"BTC": "0.4", "ETH": "0.3"}),),
        reports=(0, 1),
    )
    result = run_world_and_assert(synthetic, expected)
    assert result.execution is not None
    assert len(result.execution.intents) == 2
    assert all(item.scheduled_at == CAL[1] == item.expires_at for item in result.execution.intents)


def test_s27_three_slice_twap_conserves_quantity_and_marks_incrementally() -> None:
    slices = (
        trade(0, 0, BTC, quantity_value="2", price="100", execution_index=1, slice_index=0),
        trade(0, 0, BTC, quantity_value="2", price="110", execution_index=2, slice_index=1),
        trade(0, 0, BTC, quantity_value="2", price="120", execution_index=3, slice_index=2),
    )
    average_at_two = weighted_average(D("2"), D("100"), D("2"), D("110"))
    average_at_three = weighted_average(D("4"), average_at_two, D("2"), D("120"))
    assert average_at_two == D("105")
    assert average_at_three == D("110")
    expected = ledger(
        targets=(target(0, 0, ((BTC, "0.006", "100"),)),),
        quantities=(quantity(0, 0, BTC, current="0", desired="6", reference="100", increment="1"),),
        trades=slices,
        holdings=(
            holding(0, BTC, "0", "100"),
            holding(1, BTC, "2", "100"),
            holding(2, BTC, "4", "110"),
            holding(3, BTC, "6", "120"),
        ),
        accounts=(
            account(0, cash=CAPITAL),
            account(1, cash=CAPITAL),
            account(2, cash=CAPITAL, unrealized=unrealized(D("4"), average_at_two, D("110"))),
            account(3, cash=CAPITAL, unrealized=unrealized(D("6"), average_at_three, D("120"))),
        ),
        shortfalls=(
            shortfall(
                0,
                0,
                BTC,
                intended=D("6"),
                fills=tuple(item[2] for item in slices),
                decision_price="100",
                arrival_price="100",
                terminal_price="120",
            ),
        ),
        benchmark_prices=("100", "100", "110", "120"),
    )
    synthetic = world(
        "S27",
        instruments=(instrument("BTC", prices("100", "100", "110", "120"), quantity_increment="1"),),
        decisions=(decision(0, {"BTC": "0.006"}),),
        reports=(0, 1, 2, 3),
        policy_kind="twap",
        slice_count=3,
    )
    result = run_world_and_assert(synthetic, expected)
    assert result.execution is not None
    assert sum((item.quantity for item in result.execution.intents), start=D("0")) == D("6")


def test_s28_twap_omits_zero_slices_but_conserves_two_lots() -> None:
    slices = (
        trade(0, 0, BTC, quantity_value="1", price="100", execution_index=1, slice_index=0),
        trade(0, 0, BTC, quantity_value="1", price="100", execution_index=2, slice_index=1),
    )
    expected = ledger(
        targets=(target(0, 0, ((BTC, "0.002", "100"),)),),
        quantities=(quantity(0, 0, BTC, current="0", desired="2", reference="100", increment="1"),),
        trades=slices,
        holdings=(
            holding(0, BTC, "0", "100"),
            holding(1, BTC, "1", "100"),
            holding(2, BTC, "2", "100"),
            holding(3, BTC, "2", "100"),
        ),
        accounts=tuple(account(index, cash=CAPITAL) for index in (0, 1, 2, 3)),
        shortfalls=(
            shortfall(
                0,
                0,
                BTC,
                intended=D("2"),
                fills=tuple(item[2] for item in slices),
                decision_price="100",
                arrival_price="100",
                terminal_price="100",
            ),
        ),
        benchmark_prices=("100", "100", "100", "100"),
    )
    synthetic = world(
        "S28",
        instruments=(instrument("BTC", prices("100"), quantity_increment="1"),),
        decisions=(decision(0, {"BTC": "0.002"}),),
        reports=(0, 1, 2, 3),
        policy_kind="twap",
        slice_count=3,
    )
    result = run_world_and_assert(synthetic, expected)
    assert result.execution is not None
    assert len(result.execution.intents) == 2
    assert all(item.quantity != 0 for item in result.execution.intents)


# --------------------------------------------------------------------------- #
# S29-S30: lot rounding and contract multiplier
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("scenario", "weight", "expected_quantity"),
    [
        pytest.param("S29-long", "0.0015", "1", id="positive-half-lot"),
        pytest.param("S29-short", "-0.0015", "-1", id="negative-half-lot"),
    ],
)
def test_s29_half_lot_rounds_toward_zero(
    scenario: str,
    weight: str,
    expected_quantity: str,
) -> None:
    fill = trade(0, 0, BTC, quantity_value=expected_quantity, price="100")
    expected = ledger(
        targets=(target(0, 0, ((BTC, weight, "100"),)),),
        quantities=(
            quantity(
                0,
                0,
                BTC,
                current="0",
                desired=expected_quantity,
                reference="100",
                increment="1",
            ),
        ),
        trades=(fill,),
        holdings=(holding(0, BTC, "0", "100"), holding(1, BTC, expected_quantity, "100")),
        accounts=(account(0, cash=CAPITAL), account(1, cash=CAPITAL)),
        shortfalls=(
            shortfall(
                0,
                0,
                BTC,
                intended=D(expected_quantity),
                fills=(fill[2],),
                decision_price="100",
                arrival_price="100",
                terminal_price="100",
            ),
        ),
        benchmark_prices=("100", "100"),
    )
    synthetic = world(
        scenario,
        instruments=(instrument("BTC", prices("100"), quantity_increment="1"),),
        decisions=(decision(0, {"BTC": weight}),),
        reports=(0, 1),
    )
    run_world_and_assert(synthetic, expected)


def test_s30_multiplier_applies_once_to_every_economic_field() -> None:
    desired = desired_quantity(CAPITAL, D("0.5"), D("100"), multiplier=D("10"), increment=D("1"))
    assert desired == D("50")
    fill = trade(0, 0, BTC, quantity_value="50", price="100", multiplier="10")
    settlement = FundingFact("S30-funding", BTC, CAL[2], D("0.001"), D("110"))
    funding_pnl = funding_cashflow(D("50"), D("110"), D("0.001"), multiplier=D("10"))
    assert funding_pnl == D("-55")
    expected = ledger(
        targets=(target(0, 0, ((BTC, "0.5", "100"),)),),
        quantities=(quantity(0, 0, BTC, current="0", desired="50", reference="100", increment="1"),),
        trades=(fill,),
        funding=(funding_record(settlement),),
        holdings=(
            holding(0, BTC, "0", "100", multiplier="10"),
            holding(1, BTC, "50", "100", multiplier="10"),
            holding(2, BTC, "50", "110", multiplier="10"),
        ),
        accounts=(
            account(0, cash=CAPITAL),
            account(1, cash=CAPITAL),
            account(
                2,
                cash=CAPITAL + funding_pnl,
                unrealized=unrealized(D("50"), D("100"), D("110"), multiplier=D("10")),
                funding=funding_pnl,
            ),
        ),
        shortfalls=(
            shortfall(
                0,
                0,
                BTC,
                intended=D("50"),
                fills=(fill[2],),
                decision_price="100",
                arrival_price="100",
                terminal_price="100",
                multiplier="10",
            ),
        ),
        benchmark_prices=("100", "100", "110"),
        multipliers={BTC: D("10")},
    )
    synthetic = world(
        "S30",
        instruments=(
            instrument(
                "BTC",
                prices("100", "100", "110"),
                multiplier="10",
                quantity_increment="1",
            ),
        ),
        decisions=(decision(0, {"BTC": "0.5"}),),
        reports=(0, 1, 2),
        funding=(settlement,),
    )
    run_world_and_assert(synthetic, expected)


# --------------------------------------------------------------------------- #
# S31: terminal outcome and fill coverage
# --------------------------------------------------------------------------- #


def test_s31_buy_and_sell_iocs_have_exact_terminal_fill_coverage() -> None:
    buy = trade(0, 0, BTC, quantity_value="500", price="100")
    sell = trade(1, 2, BTC, quantity_value="-1000", price="100")
    expected = ledger(
        targets=(target(0, 0, ((BTC, "0.5", "100"),)), target(1, 2, ((BTC, "-0.5", "100"),))),
        quantities=(
            quantity(0, 0, BTC, current="0", desired="500", reference="100"),
            quantity(1, 2, BTC, current="500", desired="-500", reference="100"),
        ),
        trades=(buy, sell),
        holdings=(
            holding(0, BTC, "0", "100"),
            holding(1, BTC, "500", "100"),
            holding(3, BTC, "-500", "100"),
        ),
        accounts=(account(0, cash=CAPITAL), account(1, cash=CAPITAL), account(3, cash=CAPITAL)),
        shortfalls=(
            shortfall(
                0,
                0,
                BTC,
                intended=D("500"),
                fills=(buy[2],),
                decision_price="100",
                arrival_price="100",
                terminal_price="100",
            ),
            shortfall(
                1,
                2,
                BTC,
                intended=D("-1000"),
                fills=(sell[2],),
                decision_price="100",
                arrival_price="100",
                terminal_price="100",
            ),
        ),
        benchmark_prices=("100", "100", "100"),
    )
    synthetic = world(
        "S31",
        instruments=(instrument("BTC", prices("100")),),
        decisions=(decision(0, {"BTC": "0.5"}), decision(2, {"BTC": "-0.5"})),
        reports=(0, 1, 3),
    )
    result = run_world_and_assert(synthetic, expected)
    assert result.execution is not None
    execution = result.execution
    assert len(execution.intents) == len(execution.outcomes) == len(execution.fills) == 2
    assert {item.fill_id for item in execution.fills} == {
        fill.fill_id for outcome in execution.outcomes for fill in outcome.fills
    }
