"""A2 synthetic-oracle reporting and compatibility scenarios S32-S37.

Purpose: prove report event order, interval turnover, return decomposition,
shortfall, benchmark sampling, and the frozen legacy/prepared result surface.

USAGE:
    uv run pytest -q packages/platform/backtest/tests/audit/test_a2_reporting.py
"""

from __future__ import annotations

import polars as pl
import pytest
from backtest import BacktestConfig, run_backtest

from .a1_oracle import D, unrealized, weighted_average
from .a1_world import run_world_and_assert
from .a2_support import (
    BTC,
    CAL,
    CAPITAL,
    account,
    decision,
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

SEVEN_COLUMNS = (
    "equity",
    "benchmark_equity",
    "price_return",
    "funding_return",
    "cost_return",
    "net_return",
    "turnover",
)

# --------------------------------------------------------------------------- #
# S32-S34: report order, turnover interval, and return decomposition
# --------------------------------------------------------------------------- #


def test_s32_reports_before_at_and_after_fill_follow_event_order() -> None:
    fill = trade(0, 0, BTC, quantity_value="500", price="110", fee_rate="0.0004")
    expected = ledger(
        targets=(target(0, 0, ((BTC, "0.5", "100"),)),),
        quantities=(quantity(0, 0, BTC, current="0", desired="500", reference="100"),),
        trades=(fill,),
        holdings=(
            holding(0, BTC, "0", "100"),
            holding(1, BTC, "500", "110"),
            holding(2, BTC, "500", "120"),
        ),
        accounts=(
            account(0, cash=CAPITAL),
            account(1, cash=D("99978"), fees=D("22")),
            account(2, cash=D("99978"), unrealized=D("5000"), fees=D("22")),
        ),
        shortfalls=(
            shortfall(
                0,
                0,
                BTC,
                intended=D("500"),
                fills=(fill[2],),
                decision_price="100",
                arrival_price="110",
                terminal_price="110",
            ),
        ),
        benchmark_prices=("100", "110", "120"),
    )
    synthetic = world(
        "S32",
        instruments=(instrument("BTC", prices("100", "110", "120"), fee_rate="0.0004"),),
        decisions=(decision(0, {"BTC": "0.5"}),),
        reports=(0, 1, 2),
    )
    run_world_and_assert(synthetic, expected)


def test_s33_fill_notional_appears_in_only_its_report_interval() -> None:
    fill = trade(0, 0, BTC, quantity_value="500", price="110")
    expected = ledger(
        targets=(target(0, 0, ((BTC, "0.5", "100"),)),),
        quantities=(quantity(0, 0, BTC, current="0", desired="500", reference="100"),),
        trades=(fill,),
        holdings=(holding(0, BTC, "0", "100"), holding(2, BTC, "500", "110")),
        accounts=(account(0, cash=CAPITAL), account(2, cash=CAPITAL)),
        shortfalls=(
            shortfall(
                0,
                0,
                BTC,
                intended=D("500"),
                fills=(fill[2],),
                decision_price="100",
                arrival_price="110",
                terminal_price="110",
            ),
        ),
        benchmark_prices=("100", "110"),
    )
    synthetic = world(
        "S33",
        instruments=(instrument("BTC", prices("100", "110", "110")),),
        decisions=(decision(0, {"BTC": "0.5"}),),
        reports=(0, 2),
    )
    result = run_world_and_assert(synthetic, expected)
    assert result.turnover.to_list() == pytest.approx([0.55], rel=0, abs=1e-12)


def test_s34_flat_entry_decomposes_exact_cost_and_net_return() -> None:
    fill = trade(0, 0, BTC, quantity_value="500", price="100", fee_rate="0.0004")
    expected = ledger(
        targets=(target(0, 0, ((BTC, "0.5", "100"),)),),
        quantities=(quantity(0, 0, BTC, current="0", desired="500", reference="100"),),
        trades=(fill,),
        holdings=(holding(0, BTC, "0", "100"), holding(1, BTC, "500", "100")),
        accounts=(account(0, cash=CAPITAL), account(1, cash=D("99980"), fees=D("20"))),
        shortfalls=(
            shortfall(
                0,
                0,
                BTC,
                intended=D("500"),
                fills=(fill[2],),
                decision_price="100",
                arrival_price="100",
                terminal_price="100",
            ),
        ),
        benchmark_prices=("100", "100"),
    )
    synthetic = world(
        "S34",
        instruments=(instrument("BTC", prices("100"), fee_rate="0.0004"),),
        decisions=(decision(0, {"BTC": "0.5"}),),
        reports=(0, 1),
    )
    result = run_world_and_assert(synthetic, expected)
    assert result.price_return.to_list() == pytest.approx([0], rel=0, abs=1e-12)
    assert result.funding_return.to_list() == pytest.approx([0], rel=0, abs=1e-12)
    assert result.cost_return.to_list() == pytest.approx([0.0002], rel=0, abs=1e-12)
    assert result.net_return.to_list() == pytest.approx([-0.0002], rel=0, abs=1e-12)


# --------------------------------------------------------------------------- #
# S35-S36: implementation shortfall and benchmark
# --------------------------------------------------------------------------- #


def test_s35_known_twap_shortfall_components_reconcile_exactly() -> None:
    slices = (
        trade(
            0,
            0,
            BTC,
            quantity_value="2",
            price="110",
            execution_index=1,
            slice_index=0,
            fee_rate="0.001",
        ),
        trade(
            0,
            0,
            BTC,
            quantity_value="2",
            price="120",
            execution_index=2,
            slice_index=1,
            fee_rate="0.001",
        ),
        trade(
            0,
            0,
            BTC,
            quantity_value="2",
            price="130",
            execution_index=3,
            slice_index=2,
            fee_rate="0.001",
        ),
    )
    average_two = weighted_average(D("2"), D("110"), D("2"), D("120"))
    average_three = weighted_average(D("4"), average_two, D("2"), D("130"))
    expected_shortfall = shortfall(
        0,
        0,
        BTC,
        intended=D("6"),
        fills=tuple(item[2] for item in slices),
        decision_price="100",
        arrival_price="110",
        terminal_price="130",
    )
    assert expected_shortfall.delay == D("60")
    assert expected_shortfall.trading == D("60")
    assert expected_shortfall.fee == D("0.72")
    assert expected_shortfall.unfilled == D("0")
    assert expected_shortfall.total == D("120.72")
    expected = ledger(
        targets=(target(0, 0, ((BTC, "0.006", "100"),)),),
        quantities=(quantity(0, 0, BTC, current="0", desired="6", reference="100", increment="1"),),
        trades=slices,
        holdings=(
            holding(0, BTC, "0", "100"),
            holding(1, BTC, "2", "110"),
            holding(2, BTC, "4", "120"),
            holding(3, BTC, "6", "130"),
        ),
        accounts=(
            account(0, cash=CAPITAL),
            account(1, cash=D("99999.78"), fees=D("0.22")),
            account(
                2,
                cash=D("99999.54"),
                unrealized=unrealized(D("4"), average_two, D("120")),
                fees=D("0.46"),
            ),
            account(
                3,
                cash=D("99999.28"),
                unrealized=unrealized(D("6"), average_three, D("130")),
                fees=D("0.72"),
            ),
        ),
        shortfalls=(expected_shortfall,),
        benchmark_prices=("100", "110", "120", "130"),
    )
    synthetic = world(
        "S35",
        instruments=(
            instrument(
                "BTC",
                prices("100", "110", "120", "130"),
                fee_rate="0.001",
                quantity_increment="1",
            ),
        ),
        decisions=(decision(0, {"BTC": "0.006"}),),
        reports=(0, 1, 2, 3),
        policy_kind="twap",
        slice_count=3,
    )
    run_world_and_assert(synthetic, expected)


def test_s36_benchmark_uses_completed_close_at_each_report() -> None:
    expected = ledger(
        targets=(target(0, 0, ((BTC, "0", "100"),)),),
        quantities=(quantity(0, 0, BTC, current="0", desired="0", reference="100"),),
        trades=(),
        holdings=(
            holding(0, BTC, "0", "100"),
            holding(2, BTC, "0", "120"),
            holding(4, BTC, "0", "90"),
        ),
        accounts=tuple(account(index, cash=CAPITAL) for index in (0, 2, 4)),
        shortfalls=(
            shortfall(
                0,
                0,
                BTC,
                intended=D("0"),
                fills=(),
                decision_price="100",
                arrival_price="110",
                terminal_price="110",
            ),
        ),
        benchmark_prices=("100", "120", "90"),
    )
    synthetic = world(
        "S36",
        instruments=(instrument("BTC", prices("100", "110", "120", "105", "90")),),
        decisions=(decision(0, {"BTC": "0"}),),
        reports=(0, 2, 4),
    )
    result = run_world_and_assert(synthetic, expected)
    assert result.benchmark_equity.to_list() == pytest.approx([100000, 120000, 90000], rel=0, abs=1e-6)


# --------------------------------------------------------------------------- #
# S37: legacy/prepared additive compatibility
# --------------------------------------------------------------------------- #


def test_s37_legacy_and_prepared_keep_seven_columns_and_same_economics() -> None:
    fill = trade(0, 0, BTC, quantity_value="500", price="100", fee_rate="0.0004")
    expected = ledger(
        targets=(target(0, 0, ((BTC, "0.5", "100"),)),),
        quantities=(quantity(0, 0, BTC, current="0", desired="500", reference="100"),),
        trades=(fill,),
        holdings=(
            holding(0, BTC, "0", "100"),
            holding(1, BTC, "500", "100"),
            holding(2, BTC, "500", "100"),
        ),
        accounts=(
            account(0, cash=CAPITAL),
            account(1, cash=D("99980"), fees=D("20")),
            account(2, cash=D("99980"), fees=D("20")),
        ),
        shortfalls=(
            shortfall(
                0,
                0,
                BTC,
                intended=D("500"),
                fills=(fill[2],),
                decision_price="100",
                arrival_price="100",
                terminal_price="100",
            ),
        ),
        benchmark_prices=("100", "100", "100"),
    )
    prepared_world = world(
        "S37",
        instruments=(instrument("BTC", prices("100"), fee_rate="0.0004"),),
        decisions=(decision(0, {"BTC": "0.5"}),),
        reports=(0, 1, 2),
    )
    prepared = run_world_and_assert(prepared_world, expected)

    legacy = run_backtest(
        prices=pl.DataFrame(
            {
                "timestamp": CAL[:3],
                "BTC": [100.0, 100.0, 100.0],
                "CASH": [1.0, 1.0, 1.0],
            }
        ),
        weights=pl.DataFrame(
            {
                "timestamp": CAL[:3],
                "BTC": [0.0, 0.5, 0.5],
                "CASH": [1.0, 0.5, 0.5],
            }
        ),
        config=BacktestConfig(
            initial_capital=100000,
            trade_cost_bps=4,
            include_funding=False,
            frequency="1m",
            benchmark="BTC",
            metrics=[],
        ),
    )

    assert tuple(legacy.to_dataframe().columns) == SEVEN_COLUMNS
    assert tuple(prepared.to_dataframe().columns) == SEVEN_COLUMNS
    assert legacy.execution is None
    assert prepared.execution is not None
    for column in SEVEN_COLUMNS:
        assert legacy.to_dataframe()[column].to_list() == pytest.approx(
            prepared.to_dataframe()[column].to_list(),
            rel=0,
            abs=1e-6 if "equity" in column else 1e-12,
        )
