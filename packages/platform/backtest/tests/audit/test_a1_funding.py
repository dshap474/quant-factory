"""A1 synthetic-oracle funding scenarios S15-S20.

Purpose: prove funding sign, zero-position behavior, funding-before-sizing order,
and deterministic multi-instrument settlement order against independent ledgers.

USAGE:
    uv run --project packages/platform/backtest pytest \
      packages/platform/backtest/tests/audit/test_a1_funding.py -v
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from .a1_oracle import (
    D,
    ExpectedAccount,
    ExpectedFill,
    ExpectedFunding,
    ExpectedHolding,
    ExpectedIntent,
    ExpectedLedger,
    ExpectedOutcome,
    ExpectedQuantity,
    ExpectedTarget,
    funding_cashflow,
    slice_id,
    target_id,
    unrealized,
)
from .a1_world import DecisionFact, FundingFact, InstrumentFacts, SyntheticWorld, run_world_and_assert

# --------------------------------------------------------------------------- #
# Frozen facts and builders
# --------------------------------------------------------------------------- #

UTC = timezone.utc
T0 = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
CAL = tuple(T0 + timedelta(minutes=index) for index in range(6))
BTC = "BINANCE:BTCUSDT"
ETH = "BINANCE:ETHUSDT"
CAPITAL = D("100000")
LOT = D("0.001")


def _prices(value: str) -> dict[datetime, Decimal]:
    return {timestamp: D(value) for timestamp in CAL}


def _instrument(asset: str, price: str) -> InstrumentFacts:
    return InstrumentFacts(
        asset=asset,
        symbol=f"{asset}USDT",
        base_currency=asset,
        closes=_prices(price),
    )


def _decision(index: int, weights: dict[str, str]) -> DecisionFact:
    decimal_weights = {asset: D(weight) for asset, weight in weights.items()}
    return DecisionFact(
        decision_at=CAL[index],
        weights=decimal_weights,
        cash_weight=D("1") - sum(decimal_weights.values(), start=D("0")),
    )


def _funding(
    scenario: str,
    index: int,
    rate: str,
    *,
    instrument: str = BTC,
    mark: str = "100",
) -> FundingFact:
    return FundingFact(
        settlement_id=f"{scenario}-funding-{instrument.split(':')[1]}",
        instrument=instrument,
        settled_at=CAL[index],
        rate=D(rate),
        mark_price=D(mark),
    )


def _target(
    target_index: int,
    decision_index: int,
    weights: tuple[tuple[str, str, str], ...],
) -> ExpectedTarget:
    decision_at = CAL[decision_index]
    decimal_weights = tuple((instrument, D(weight)) for instrument, weight, _ in weights)
    return ExpectedTarget(
        target_id=target_id(target_index, decision_at),
        decision_at=decision_at,
        earliest_execution_at=CAL[decision_index + 1],
        weights=decimal_weights,
        cash_weight=D("1") - sum((weight for _, weight in decimal_weights), start=D("0")),
        references=tuple((instrument, D(price), decision_at) for instrument, _, price in weights),
    )


def _quantity(
    target_index: int,
    decision_index: int,
    instrument: str,
    current: str,
    desired: str,
    reference: str,
) -> ExpectedQuantity:
    decision_at = CAL[decision_index]
    return ExpectedQuantity(
        target_id=target_id(target_index, decision_at),
        instrument=instrument,
        current=D(current),
        desired=D(desired),
        delta=D(desired) - D(current),
        reference_price=D(reference),
        decision_at=decision_at,
        earliest_execution_at=CAL[decision_index + 1],
        increment=LOT,
    )


def _trade(
    target_index: int,
    decision_index: int,
    instrument: str,
    quantity: str,
    price: str,
) -> tuple[ExpectedIntent, ExpectedOutcome, ExpectedFill]:
    target = target_id(target_index, CAL[decision_index])
    execution_at = CAL[decision_index + 1]
    identity = slice_id(target, instrument)
    return (
        ExpectedIntent(target, identity, instrument, D(quantity), execution_at, execution_at),
        ExpectedOutcome(identity, "FILLED", D("0"), 1),
        ExpectedFill(target, identity, instrument, D(quantity), D(price), D("0"), "USDT", execution_at),
    )


def _holding(index: int, instrument: str, quantity: str, mark: str) -> ExpectedHolding:
    return ExpectedHolding(CAL[index], instrument, D(quantity), D(mark), D(quantity) * D(mark))


def _account(
    index: int,
    *,
    cash: Decimal,
    realized: Decimal = D("0"),
    unrealized_pnl: Decimal = D("0"),
    funding: Decimal = D("0"),
) -> ExpectedAccount:
    return ExpectedAccount(
        CAL[index],
        cash,
        cash + unrealized_pnl,
        realized,
        unrealized_pnl,
        D("0"),
        funding,
    )


def _expected_funding(item: FundingFact) -> ExpectedFunding:
    return ExpectedFunding(item.settlement_id, item.instrument, item.settled_at, item.rate, item.mark_price)


def _ledger(
    *,
    targets: tuple[ExpectedTarget, ...],
    quantities: tuple[ExpectedQuantity, ...],
    trades: tuple[tuple[ExpectedIntent, ExpectedOutcome, ExpectedFill], ...],
    funding: tuple[ExpectedFunding, ...],
    holdings: tuple[ExpectedHolding, ...],
    accounts: tuple[ExpectedAccount, ...],
) -> ExpectedLedger:
    return ExpectedLedger(
        targets=targets,
        quantities=quantities,
        intents=tuple(trade[0] for trade in trades),
        outcomes=tuple(trade[1] for trade in trades),
        fills=tuple(trade[2] for trade in trades),
        funding=funding,
        holdings=holdings,
        accounts=accounts,
    )


# --------------------------------------------------------------------------- #
# S15-S18: sign and position timing
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("scenario", "weight", "quantity", "rate", "cashflow"),
    [
        pytest.param("S15", "1", "1000", "0.001", "-100", id="S15-positive-long-pays"),
        pytest.param("S16", "-1", "-1000", "0.001", "100", id="S16-positive-short-receives"),
        pytest.param("S17L", "1", "1000", "-0.001", "100", id="S17-negative-long-receives"),
        pytest.param("S17S", "-1", "-1000", "-0.001", "-100", id="S17-negative-short-pays"),
    ],
)
def test_s15_s17_funding_sign_oracle(
    scenario: str,
    weight: str,
    quantity: str,
    rate: str,
    cashflow: str,
) -> None:
    settlement = _funding(scenario, 2, rate)
    expected_cashflow = funding_cashflow(D(quantity), D("100"), D(rate))
    assert expected_cashflow == D(cashflow)
    world = SyntheticWorld(
        scenario,
        CAL,
        (_instrument("BTC", "100"),),
        (_decision(0, {"BTC": weight}),),
        (CAL[1], CAL[2]),
        (settlement,),
    )
    trade = _trade(0, 0, BTC, quantity, "100")
    expected = _ledger(
        targets=(_target(0, 0, ((BTC, weight, "100"),)),),
        quantities=(_quantity(0, 0, BTC, "0", quantity, "100"),),
        trades=(trade,),
        funding=(_expected_funding(settlement),),
        holdings=(_holding(1, BTC, quantity, "100"), _holding(2, BTC, quantity, "100")),
        accounts=(
            _account(1, cash=CAPITAL),
            _account(2, cash=CAPITAL + expected_cashflow, funding=expected_cashflow),
        ),
    )
    run_world_and_assert(world, expected)


def test_s18_funding_before_entry_has_zero_cashflow() -> None:
    settlement = _funding("S18", 1, "0.001")
    world = SyntheticWorld(
        "S18",
        CAL,
        (_instrument("BTC", "100"),),
        (_decision(0, {"BTC": "1"}),),
        (CAL[1],),
        (settlement,),
    )
    expected = _ledger(
        targets=(_target(0, 0, ((BTC, "1", "100"),)),),
        quantities=(_quantity(0, 0, BTC, "0", "1000", "100"),),
        trades=(_trade(0, 0, BTC, "1000", "100"),),
        funding=(_expected_funding(settlement),),
        holdings=(_holding(1, BTC, "1000", "100"),),
        accounts=(_account(1, cash=CAPITAL),),
    )
    run_world_and_assert(world, expected)


# --------------------------------------------------------------------------- #
# S19: funding before target sizing and execution
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("case", "second_weight", "desired", "delta", "realized", "final_quantity", "final_average"),
    [
        pytest.param("reduce", "0.5", "499.500", "-500.500", "5005", "499.500", "100", id="reduce"),
        pytest.param("reverse", "-1", "-999.000", "-1999.000", "10000", "-999.000", "110", id="reverse"),
    ],
)
def test_s19_funding_precedes_same_bar_sizing_and_fill(
    case: str,
    second_weight: str,
    desired: str,
    delta: str,
    realized: str,
    final_quantity: str,
    final_average: str,
) -> None:
    prices = {timestamp: D("100") if index < 2 else D("110") for index, timestamp in enumerate(CAL)}
    settlement = _funding(f"S19-{case}", 3, "0.001", mark="110")
    funding_pnl = funding_cashflow(D("1000"), D("110"), D("0.001"))
    realized_pnl = D(realized)
    world = SyntheticWorld(
        f"S19-{case}",
        CAL,
        (InstrumentFacts("BTC", "BTCUSDT", "BTC", prices),),
        (_decision(0, {"BTC": "1"}), _decision(2, {"BTC": second_weight})),
        (CAL[1], CAL[3]),
        (settlement,),
    )
    expected = _ledger(
        targets=(
            _target(0, 0, ((BTC, "1", "100"),)),
            _target(1, 2, ((BTC, second_weight, "110"),)),
        ),
        quantities=(
            _quantity(0, 0, BTC, "0", "1000", "100"),
            _quantity(1, 2, BTC, "1000", desired, "110"),
        ),
        trades=(
            _trade(0, 0, BTC, "1000", "100"),
            _trade(1, 2, BTC, delta, "110"),
        ),
        funding=(_expected_funding(settlement),),
        holdings=(
            _holding(1, BTC, "1000", "100"),
            _holding(3, BTC, final_quantity, "110"),
        ),
        accounts=(
            _account(1, cash=CAPITAL),
            _account(
                3,
                cash=CAPITAL + funding_pnl + realized_pnl,
                realized=realized_pnl,
                unrealized_pnl=unrealized(D(final_quantity), D(final_average), D("110")),
                funding=funding_pnl,
            ),
        ),
    )
    run_world_and_assert(world, expected)


# --------------------------------------------------------------------------- #
# S20: deterministic multi-instrument order and aggregation
# --------------------------------------------------------------------------- #


def test_s20_multi_instrument_same_timestamp_is_sorted_and_aggregated() -> None:
    btc_funding = _funding("S20-z", 2, "0.001", instrument=BTC, mark="100")
    eth_funding = _funding("S20-a", 2, "0.002", instrument=ETH, mark="50")
    total_funding = funding_cashflow(D("500"), D("100"), D("0.001")) + funding_cashflow(D("500"), D("50"), D("0.002"))
    assert total_funding == D("-100")
    world = SyntheticWorld(
        "S20",
        CAL,
        (_instrument("ETH", "50"), _instrument("BTC", "100")),
        (_decision(0, {"ETH": "0.25", "BTC": "0.5"}),),
        (CAL[1], CAL[2]),
        (eth_funding, btc_funding),
    )
    btc_trade = _trade(0, 0, BTC, "500", "100")
    eth_trade = _trade(0, 0, ETH, "500", "50")
    expected = _ledger(
        targets=(_target(0, 0, ((BTC, "0.5", "100"), (ETH, "0.25", "50"))),),
        quantities=(
            _quantity(0, 0, BTC, "0", "500", "100"),
            _quantity(0, 0, ETH, "0", "500", "50"),
        ),
        trades=(btc_trade, eth_trade),
        funding=(_expected_funding(btc_funding), _expected_funding(eth_funding)),
        holdings=(
            _holding(1, BTC, "500", "100"),
            _holding(1, ETH, "500", "50"),
            _holding(2, BTC, "500", "100"),
            _holding(2, ETH, "500", "50"),
        ),
        accounts=(
            _account(1, cash=CAPITAL),
            _account(2, cash=CAPITAL + total_funding, funding=total_funding),
        ),
    )
    run_world_and_assert(world, expected)
