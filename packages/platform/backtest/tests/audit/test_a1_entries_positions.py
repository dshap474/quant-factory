"""A1 synthetic-oracle scenarios S01-S14.

Purpose: prove entry timing/fees, deterministic replay, zero deltas, and every
linear-perpetual long/short/add/reduce/close/reversal transition against
expected ledgers constructed before the public engine runs.

USAGE:
    uv run --project packages/platform/backtest pytest \
      packages/platform/backtest/tests/audit/test_a1_entries_positions.py -v
"""

from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from .a1_oracle import (
    D,
    ExpectedAccount,
    ExpectedFill,
    ExpectedHolding,
    ExpectedIntent,
    ExpectedLedger,
    ExpectedOutcome,
    ExpectedQuantity,
    ExpectedTarget,
    realized_on_close,
    slice_id,
    taker_fee,
    target_id,
    unrealized,
    weighted_average,
)
from .a1_world import (
    DecisionFact,
    InstrumentFacts,
    SyntheticWorld,
    input_hash,
    run_world_and_assert,
    trace_hash,
)

# --------------------------------------------------------------------------- #
# Frozen facts
# --------------------------------------------------------------------------- #

UTC = timezone.utc
T0 = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
CAL = tuple(T0 + timedelta(minutes=index) for index in range(8))
BTC = "BINANCE:BTCUSDT"
CAPITAL = D("100000")
LOT = D("0.001")


def _prices(*values: str) -> dict[datetime, Decimal]:
    if len(values) > len(CAL):
        raise ValueError("too many prices")
    padded = (*values, *((values[-1],) * (len(CAL) - len(values))))
    return dict(zip(CAL, map(D, padded), strict=True))


def _world(
    scenario_id: str,
    *,
    closes: dict[datetime, Decimal],
    decisions: tuple[tuple[int, str], ...],
    reports: tuple[int, ...],
    fee_rate: str = "0",
) -> SyntheticWorld:
    return SyntheticWorld(
        scenario_id=scenario_id,
        calendar=CAL,
        instruments=(
            InstrumentFacts(
                asset="BTC",
                symbol="BTCUSDT",
                base_currency="BTC",
                closes=closes,
                taker_fee_rate=D(fee_rate),
            ),
        ),
        decisions=tuple(
            DecisionFact(
                decision_at=CAL[index],
                weights={"BTC": D(weight)},
                cash_weight=D("1") - D(weight),
            )
            for index, weight in decisions
        ),
        reporting_times=tuple(CAL[index] for index in reports),
    )


def _target(index: int, decision_index: int, weight: str, price: str) -> ExpectedTarget:
    decision = CAL[decision_index]
    return ExpectedTarget(
        target_id=target_id(index, decision),
        decision_at=decision,
        earliest_execution_at=CAL[decision_index + 1],
        weights=((BTC, D(weight)),),
        cash_weight=D("1") - D(weight),
        references=((BTC, D(price), decision),),
    )


def _quantity(
    target_index: int,
    decision_index: int,
    *,
    current: str,
    desired: str,
    reference: str,
) -> ExpectedQuantity:
    decision = CAL[decision_index]
    return ExpectedQuantity(
        target_id=target_id(target_index, decision),
        instrument=BTC,
        current=D(current),
        desired=D(desired),
        delta=D(desired) - D(current),
        reference_price=D(reference),
        decision_at=decision,
        earliest_execution_at=CAL[decision_index + 1],
        increment=LOT,
    )


def _trade(
    target_index: int,
    decision_index: int,
    quantity: Decimal,
    price: Decimal,
    fee_rate: Decimal = D("0"),
) -> tuple[ExpectedIntent, ExpectedOutcome, ExpectedFill]:
    target = target_id(target_index, CAL[decision_index])
    execution = CAL[decision_index + 1]
    slice_identity = slice_id(target, BTC)
    fill = ExpectedFill(
        target_id=target,
        slice_id=slice_identity,
        instrument=BTC,
        quantity=quantity,
        price=price,
        fee=taker_fee(quantity, price, fee_rate),
        fee_currency="USDT",
        filled_at=execution,
    )
    return (
        ExpectedIntent(
            target_id=target,
            slice_id=slice_identity,
            instrument=BTC,
            quantity=quantity,
            scheduled_at=execution,
            expires_at=execution,
        ),
        ExpectedOutcome(
            slice_id=slice_identity,
            status="FILLED",
            unfilled=D("0"),
            fill_count=1,
        ),
        fill,
    )


def _holding(timestamp_index: int, quantity: str, mark: str) -> ExpectedHolding:
    return ExpectedHolding(
        timestamp=CAL[timestamp_index],
        instrument=BTC,
        quantity=D(quantity),
        mark_price=D(mark),
        notional=D(quantity) * D(mark),
    )


def _account(
    timestamp_index: int,
    *,
    cash: Decimal,
    realized: Decimal = D("0"),
    unrealized_pnl: Decimal = D("0"),
    fees: Decimal = D("0"),
) -> ExpectedAccount:
    return ExpectedAccount(
        timestamp=CAL[timestamp_index],
        cash=cash,
        equity=cash + unrealized_pnl,
        realized_pnl=realized,
        unrealized_pnl=unrealized_pnl,
        fees=fees,
        funding=D("0"),
    )


def _ledger(
    *,
    targets: tuple[ExpectedTarget, ...],
    quantities: tuple[ExpectedQuantity, ...],
    trades: tuple[tuple[ExpectedIntent, ExpectedOutcome, ExpectedFill], ...],
    holdings: tuple[ExpectedHolding, ...],
    accounts: tuple[ExpectedAccount, ...],
) -> ExpectedLedger:
    return ExpectedLedger(
        targets=targets,
        quantities=quantities,
        intents=tuple(item[0] for item in trades),
        outcomes=tuple(item[1] for item in trades),
        fills=tuple(item[2] for item in trades),
        funding=(),
        holdings=holdings,
        accounts=accounts,
    )


# --------------------------------------------------------------------------- #
# Oracle independence
# --------------------------------------------------------------------------- #


def test_a1_oracle_is_standard_library_only() -> None:
    oracle_path = Path(__file__).with_name("a1_oracle.py")
    tree = ast.parse(oracle_path.read_text(encoding="utf-8"), filename=str(oracle_path))
    imported = {
        node.module.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    imported.update(
        alias.name.split(".", 1)[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names
    )
    assert imported <= {"__future__", "dataclasses", "datetime", "decimal"}


# --------------------------------------------------------------------------- #
# S01-S05: entry, timing, determinism, zero delta
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("scenario_id", "weight", "quantity"),
    [
        pytest.param("S01", "0.5", D("500"), id="S01-flat-long-fee"),
        pytest.param("S02", "-0.5", D("-500"), id="S02-flat-short-fee"),
    ],
)
def test_flat_entry_fee_oracle(
    scenario_id: str,
    weight: str,
    quantity: Decimal,
) -> None:
    fee_rate = D("0.0004")
    fill_fee = taker_fee(quantity, D("100"), fee_rate)
    world = _world(
        scenario_id,
        closes=_prices("100"),
        decisions=((0, weight),),
        reports=(1,),
        fee_rate=str(fee_rate),
    )
    trade = _trade(0, 0, quantity, D("100"), fee_rate)
    expected = _ledger(
        targets=(_target(0, 0, weight, "100"),),
        quantities=(_quantity(0, 0, current="0", desired=str(quantity), reference="100"),),
        trades=(trade,),
        holdings=(_holding(1, str(quantity), "100"),),
        accounts=(_account(1, cash=CAPITAL - fill_fee, fees=fill_fee),),
    )
    run_world_and_assert(world, expected)


def test_s03_next_bar_uses_decision_reference_and_execution_close() -> None:
    fee_rate = D("0.0004")
    quantity = D("500")
    fill_fee = taker_fee(quantity, D("110"), fee_rate)
    world = _world(
        "S03",
        closes=_prices("100", "110"),
        decisions=((0, "0.5"),),
        reports=(1,),
        fee_rate=str(fee_rate),
    )
    expected = _ledger(
        targets=(_target(0, 0, "0.5", "100"),),
        quantities=(_quantity(0, 0, current="0", desired="500", reference="100"),),
        trades=(_trade(0, 0, quantity, D("110"), fee_rate),),
        holdings=(_holding(1, "500", "110"),),
        accounts=(_account(1, cash=CAPITAL - fill_fee, fees=fill_fee),),
    )
    run_world_and_assert(world, expected)


def test_s04_identical_public_runs_have_one_trace_hash() -> None:
    world = _world(
        "S04",
        closes=_prices("100"),
        decisions=((0, "0.5"),),
        reports=(1,),
        fee_rate="0.0004",
    )
    fee = D("20")
    expected = _ledger(
        targets=(_target(0, 0, "0.5", "100"),),
        quantities=(_quantity(0, 0, current="0", desired="500", reference="100"),),
        trades=(_trade(0, 0, D("500"), D("100"), D("0.0004")),),
        holdings=(_holding(1, "500", "100"),),
        accounts=(_account(1, cash=CAPITAL - fee, fees=fee),),
    )
    first = run_world_and_assert(world, expected)
    second = run_world_and_assert(world, expected)
    assert input_hash(world) == "fa85ea55da15d2a49d3a52993a04944bbdb694485585c9d48100a83619ebbb9a"
    assert trace_hash(first) == trace_hash(second)


def test_s05_zero_delta_has_no_order_fill_fee_or_turnover() -> None:
    world = _world(
        "S05",
        closes=_prices("100"),
        decisions=((0, "0"),),
        reports=(1,),
        fee_rate="0.0004",
    )
    expected = _ledger(
        targets=(_target(0, 0, "0", "100"),),
        quantities=(_quantity(0, 0, current="0", desired="0", reference="100"),),
        trades=(),
        holdings=(_holding(1, "0", "100"),),
        accounts=(_account(1, cash=CAPITAL),),
    )
    result = run_world_and_assert(world, expected)
    assert len(result.turnover) == 0


# --------------------------------------------------------------------------- #
# S06-S07: marked long and short
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("scenario_id", "weight", "quantity", "expected_unrealized"),
    [
        pytest.param("S06", "1", "1000", D("10000"), id="S06-long-rise"),
        pytest.param("S07", "-1", "-1000", D("-10000"), id="S07-short-rise"),
    ],
)
def test_marked_long_short_oracle(
    scenario_id: str,
    weight: str,
    quantity: str,
    expected_unrealized: Decimal,
) -> None:
    assert expected_unrealized == unrealized(D(quantity), D("100"), D("110"))
    world = _world(
        scenario_id,
        closes=_prices("100", "100", "110"),
        decisions=((0, weight),),
        reports=(1, 2),
    )
    expected = _ledger(
        targets=(_target(0, 0, weight, "100"),),
        quantities=(_quantity(0, 0, current="0", desired=quantity, reference="100"),),
        trades=(_trade(0, 0, D(quantity), D("100")),),
        holdings=(
            _holding(1, quantity, "100"),
            _holding(2, quantity, "110"),
        ),
        accounts=(
            _account(1, cash=CAPITAL),
            _account(2, cash=CAPITAL, unrealized_pnl=expected_unrealized),
        ),
    )
    run_world_and_assert(world, expected)


# --------------------------------------------------------------------------- #
# S08-S14: add, reduce, close, reverse
# --------------------------------------------------------------------------- #


def test_s08_add_long_preserves_exact_weighted_average_economics() -> None:
    average = weighted_average(D("1000"), D("100"), D("500"), D("120"))
    assert average == D("106.6666666666666666666666667")
    world = _world(
        "S08",
        closes=_prices("100", "100", "120", "120", "130"),
        decisions=((0, "1"), (2, "1.5")),
        reports=(1, 3, 4),
    )
    expected = _ledger(
        targets=(
            _target(0, 0, "1", "100"),
            _target(1, 2, "1.5", "120"),
        ),
        quantities=(
            _quantity(0, 0, current="0", desired="1000", reference="100"),
            _quantity(1, 2, current="1000", desired="1500", reference="120"),
        ),
        trades=(
            _trade(0, 0, D("1000"), D("100")),
            _trade(1, 2, D("500"), D("120")),
        ),
        holdings=(
            _holding(1, "1000", "100"),
            _holding(3, "1500", "120"),
            _holding(4, "1500", "130"),
        ),
        accounts=(
            _account(1, cash=CAPITAL),
            _account(3, cash=CAPITAL, unrealized_pnl=unrealized(D("1500"), average, D("120"))),
            _account(4, cash=CAPITAL, unrealized_pnl=unrealized(D("1500"), average, D("130"))),
        ),
    )
    run_world_and_assert(world, expected)


def test_s09_add_short_preserves_exact_weighted_average_economics() -> None:
    average = weighted_average(D("-1000"), D("100"), D("-500"), D("80"))
    assert average == D("93.33333333333333333333333333")
    world = _world(
        "S09",
        closes=_prices("100", "100", "80", "80", "70"),
        decisions=((0, "-1"), (2, "-1")),
        reports=(1, 3, 4),
    )
    expected = _ledger(
        targets=(
            _target(0, 0, "-1", "100"),
            _target(1, 2, "-1", "80"),
        ),
        quantities=(
            _quantity(0, 0, current="0", desired="-1000", reference="100"),
            _quantity(1, 2, current="-1000", desired="-1500", reference="80"),
        ),
        trades=(
            _trade(0, 0, D("-1000"), D("100")),
            _trade(1, 2, D("-500"), D("80")),
        ),
        holdings=(
            _holding(1, "-1000", "100"),
            _holding(3, "-1500", "80"),
            _holding(4, "-1500", "70"),
        ),
        accounts=(
            _account(1, cash=CAPITAL),
            _account(3, cash=CAPITAL, unrealized_pnl=D("20000")),
            _account(4, cash=CAPITAL, unrealized_pnl=unrealized(D("-1500"), average, D("70"))),
        ),
    )
    run_world_and_assert(world, expected)


def test_s10_partial_long_reduction_realizes_only_closed_quantity() -> None:
    realized = realized_on_close(D("1000"), D("500"), D("100"), D("110"))
    assert realized == D("5000")
    world = _world(
        "S10",
        closes=_prices("100", "100", "110", "110"),
        decisions=((0, "1"), (2, "0.5")),
        reports=(1, 3),
    )
    expected = _ledger(
        targets=(_target(0, 0, "1", "100"), _target(1, 2, "0.5", "110")),
        quantities=(
            _quantity(0, 0, current="0", desired="1000", reference="100"),
            _quantity(1, 2, current="1000", desired="500", reference="110"),
        ),
        trades=(
            _trade(0, 0, D("1000"), D("100")),
            _trade(1, 2, D("-500"), D("110")),
        ),
        holdings=(_holding(1, "1000", "100"), _holding(3, "500", "110")),
        accounts=(
            _account(1, cash=CAPITAL),
            _account(
                3,
                cash=CAPITAL + realized,
                realized=realized,
                unrealized_pnl=D("5000"),
            ),
        ),
    )
    run_world_and_assert(world, expected)


def test_s11_partial_short_reduction_realizes_only_closed_quantity() -> None:
    realized = realized_on_close(D("-1000"), D("250"), D("100"), D("80"))
    assert realized == D("5000")
    world = _world(
        "S11",
        closes=_prices("100", "100", "80", "80"),
        decisions=((0, "-1"), (2, "-0.5")),
        reports=(1, 3),
    )
    expected = _ledger(
        targets=(_target(0, 0, "-1", "100"), _target(1, 2, "-0.5", "80")),
        quantities=(
            _quantity(0, 0, current="0", desired="-1000", reference="100"),
            _quantity(1, 2, current="-1000", desired="-750", reference="80"),
        ),
        trades=(
            _trade(0, 0, D("-1000"), D("100")),
            _trade(1, 2, D("250"), D("80")),
        ),
        holdings=(_holding(1, "-1000", "100"), _holding(3, "-750", "80")),
        accounts=(
            _account(1, cash=CAPITAL),
            _account(
                3,
                cash=CAPITAL + realized,
                realized=realized,
                unrealized_pnl=D("15000"),
            ),
        ),
    )
    run_world_and_assert(world, expected)


@pytest.mark.parametrize(
    ("case", "first_weight", "exit_price", "first_qty", "exit_qty"),
    [
        pytest.param("long", "1", "110", "1000", "-1000", id="S12-close-long"),
        pytest.param("short", "-1", "90", "-1000", "1000", id="S12-close-short"),
    ],
)
def test_s12_full_close_flattens_position(
    case: str,
    first_weight: str,
    exit_price: str,
    first_qty: str,
    exit_qty: str,
) -> None:
    del case
    realized = D("10000")
    world = _world(
        "S12",
        closes=_prices("100", "100", exit_price, exit_price),
        decisions=((0, first_weight), (2, "0")),
        reports=(1, 3),
    )
    expected = _ledger(
        targets=(
            _target(0, 0, first_weight, "100"),
            _target(1, 2, "0", exit_price),
        ),
        quantities=(
            _quantity(0, 0, current="0", desired=first_qty, reference="100"),
            _quantity(1, 2, current=first_qty, desired="0", reference=exit_price),
        ),
        trades=(
            _trade(0, 0, D(first_qty), D("100")),
            _trade(1, 2, D(exit_qty), D(exit_price)),
        ),
        holdings=(
            _holding(1, first_qty, "100"),
            _holding(3, "0", exit_price),
        ),
        accounts=(
            _account(1, cash=CAPITAL),
            _account(3, cash=CAPITAL + realized, realized=realized),
        ),
    )
    run_world_and_assert(world, expected)


def test_s13_long_to_short_reversal() -> None:
    realized = D("20000")
    world = _world(
        "S13",
        closes=_prices("100", "100", "120", "120"),
        decisions=((0, "1"), (2, "-1")),
        reports=(1, 3),
    )
    expected = _ledger(
        targets=(_target(0, 0, "1", "100"), _target(1, 2, "-1", "120")),
        quantities=(
            _quantity(0, 0, current="0", desired="1000", reference="100"),
            _quantity(1, 2, current="1000", desired="-1000", reference="120"),
        ),
        trades=(
            _trade(0, 0, D("1000"), D("100")),
            _trade(1, 2, D("-2000"), D("120")),
        ),
        holdings=(_holding(1, "1000", "100"), _holding(3, "-1000", "120")),
        accounts=(
            _account(1, cash=CAPITAL),
            _account(3, cash=CAPITAL + realized, realized=realized),
        ),
    )
    run_world_and_assert(world, expected)


def test_s14_short_to_long_reversal() -> None:
    realized = D("20000")
    world = _world(
        "S14",
        closes=_prices("100", "100", "80", "80"),
        decisions=((0, "-1"), (2, "1")),
        reports=(1, 3),
    )
    expected = _ledger(
        targets=(_target(0, 0, "-1", "100"), _target(1, 2, "1", "80")),
        quantities=(
            _quantity(0, 0, current="0", desired="-1000", reference="100"),
            _quantity(1, 2, current="-1000", desired="1500", reference="80"),
        ),
        trades=(
            _trade(0, 0, D("-1000"), D("100")),
            _trade(1, 2, D("2500"), D("80")),
        ),
        holdings=(_holding(1, "-1000", "100"), _holding(3, "1500", "80")),
        accounts=(
            _account(1, cash=CAPITAL),
            _account(3, cash=CAPITAL + realized, realized=realized),
        ),
    )
    run_world_and_assert(world, expected)
