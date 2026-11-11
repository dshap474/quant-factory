"""Independent A2 scenario builders and result-stream equations.

Purpose: keep S21-S37 fixtures compact while constructing every expected
record from audit-local Decimal arithmetic before the public engine runs.

USAGE:
    expected = ledger(targets=..., quantities=..., trades=..., accounts=...)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Mapping, Sequence

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
    ExpectedShortfall,
    ExpectedStreams,
    ExpectedTarget,
    slice_id,
    taker_fee,
    target_id,
)
from .a1_world import DecisionFact, FundingFact, InstrumentFacts, SyntheticWorld

# --------------------------------------------------------------------------- #
# Frozen facts
# --------------------------------------------------------------------------- #

UTC = timezone.utc
T0 = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
CAL = tuple(T0 + timedelta(minutes=index) for index in range(10))
CAPITAL = D("100000")
BTC = "BINANCE:BTCUSDT"
ETH = "BINANCE:ETHUSDT"


# --------------------------------------------------------------------------- #
# Synthetic inputs
# --------------------------------------------------------------------------- #


def prices(*values: str) -> dict[datetime, Decimal]:
    """Map literal closes to the frozen calendar, padding the final value."""
    if not values or len(values) > len(CAL):
        raise ValueError("prices require one to ten values")
    padded = (*values, *((values[-1],) * (len(CAL) - len(values))))
    return dict(zip(CAL, map(D, padded), strict=True))


def instrument(
    asset: str,
    closes: Mapping[datetime, Decimal],
    *,
    fee_rate: str = "0",
    multiplier: str = "1",
    quantity_increment: str = "0.001",
) -> InstrumentFacts:
    return InstrumentFacts(
        asset=asset,
        symbol=f"{asset}USDT",
        base_currency=asset,
        closes=closes,
        taker_fee_rate=D(fee_rate),
        multiplier=D(multiplier),
        quantity_increment=D(quantity_increment),
    )


def decision(index: int, weights: Mapping[str, str]) -> DecisionFact:
    decimal_weights = {asset: D(weight) for asset, weight in weights.items()}
    return DecisionFact(
        decision_at=CAL[index],
        weights=decimal_weights,
        cash_weight=D("1") - sum(decimal_weights.values(), start=D("0")),
    )


def world(
    scenario: str,
    *,
    instruments: tuple[InstrumentFacts, ...],
    decisions: tuple[DecisionFact, ...],
    reports: tuple[int, ...],
    funding: tuple[FundingFact, ...] = (),
    policy_kind: str = "immediate",
    slice_count: int = 1,
    benchmark: str = "BTCUSDT",
    initial_capital: Decimal = CAPITAL,
) -> SyntheticWorld:
    return SyntheticWorld(
        scenario_id=scenario,
        calendar=CAL,
        instruments=instruments,
        decisions=decisions,
        reporting_times=tuple(CAL[index] for index in reports),
        funding=funding,
        initial_capital=initial_capital,
        policy_kind=policy_kind,
        slice_count=slice_count,
        benchmark=benchmark,
    )


# --------------------------------------------------------------------------- #
# Expected ledger records
# --------------------------------------------------------------------------- #


def target(
    target_index: int,
    decision_index: int,
    weights: Sequence[tuple[str, str, str]],
) -> ExpectedTarget:
    decision_at = CAL[decision_index]
    ordered = tuple(sorted(weights, key=lambda item: item[0]))
    decimal_weights = tuple((wire, D(weight)) for wire, weight, _ in ordered)
    return ExpectedTarget(
        target_id=target_id(target_index, decision_at),
        decision_at=decision_at,
        earliest_execution_at=CAL[decision_index + 1],
        weights=decimal_weights,
        cash_weight=D("1") - sum((weight for _, weight in decimal_weights), start=D("0")),
        references=tuple((wire, D(price), decision_at) for wire, _, price in ordered),
    )


def quantity(
    target_index: int,
    decision_index: int,
    instrument_wire: str,
    *,
    current: str,
    desired: str,
    reference: str,
    increment: str = "0.001",
) -> ExpectedQuantity:
    decision_at = CAL[decision_index]
    return ExpectedQuantity(
        target_id=target_id(target_index, decision_at),
        instrument=instrument_wire,
        current=D(current),
        desired=D(desired),
        delta=D(desired) - D(current),
        reference_price=D(reference),
        decision_at=decision_at,
        earliest_execution_at=CAL[decision_index + 1],
        increment=D(increment),
    )


def trade(
    target_index: int,
    decision_index: int,
    instrument_wire: str,
    *,
    quantity_value: str,
    price: str,
    execution_index: int | None = None,
    slice_index: int = 0,
    fee_rate: str = "0",
    multiplier: str = "1",
) -> tuple[ExpectedIntent, ExpectedOutcome, ExpectedFill]:
    target_identity = target_id(target_index, CAL[decision_index])
    execution_at = CAL[execution_index if execution_index is not None else decision_index + 1]
    identity = slice_id(target_identity, instrument_wire, slice_index)
    quantity_decimal = D(quantity_value)
    fee = taker_fee(quantity_decimal, D(price), D(fee_rate)) * D(multiplier)
    return (
        ExpectedIntent(
            target_identity,
            identity,
            instrument_wire,
            quantity_decimal,
            execution_at,
            execution_at,
        ),
        ExpectedOutcome(identity, "FILLED", D("0"), 1, terminal_at=execution_at),
        ExpectedFill(
            target_identity,
            identity,
            instrument_wire,
            quantity_decimal,
            D(price),
            fee,
            "USDT",
            execution_at,
        ),
    )


def holding(
    report_index: int,
    instrument_wire: str,
    quantity_value: str,
    mark: str,
    *,
    multiplier: str = "1",
) -> ExpectedHolding:
    quantity_decimal = D(quantity_value)
    mark_decimal = D(mark)
    return ExpectedHolding(
        CAL[report_index],
        instrument_wire,
        quantity_decimal,
        mark_decimal,
        quantity_decimal * mark_decimal * D(multiplier),
    )


def account(
    report_index: int,
    *,
    cash: Decimal,
    realized: Decimal = D("0"),
    unrealized: Decimal = D("0"),
    fees: Decimal = D("0"),
    funding: Decimal = D("0"),
) -> ExpectedAccount:
    return ExpectedAccount(
        CAL[report_index],
        cash,
        cash + unrealized,
        realized,
        unrealized,
        fees,
        funding,
    )


def funding_record(item: FundingFact) -> ExpectedFunding:
    return ExpectedFunding(item.settlement_id, item.instrument, item.settled_at, item.rate, item.mark_price)


def shortfall(
    target_index: int,
    decision_index: int,
    instrument_wire: str,
    *,
    intended: Decimal,
    fills: Sequence[ExpectedFill],
    decision_price: str,
    arrival_price: str,
    terminal_price: str,
    multiplier: str = "1",
) -> ExpectedShortfall:
    filled = sum((item.quantity for item in fills), start=D("0"))
    unfilled_quantity = intended - filled
    mult = D(multiplier)
    decision_decimal = D(decision_price)
    arrival_decimal = D(arrival_price)
    terminal_decimal = D(terminal_price)
    delay = filled * (arrival_decimal - decision_decimal) * mult
    trading = sum(
        (item.quantity * (item.price - arrival_decimal) * mult for item in fills),
        start=D("0"),
    )
    fee = sum((item.fee for item in fills), start=D("0"))
    unfilled = unfilled_quantity * (terminal_decimal - decision_decimal) * mult
    return ExpectedShortfall(
        target_id(target_index, CAL[decision_index]),
        instrument_wire,
        intended,
        filled,
        decision_decimal,
        arrival_decimal,
        terminal_decimal,
        delay,
        trading,
        fee,
        unfilled,
        delay + trading + fee + unfilled,
    )


def ledger(
    *,
    targets: tuple[ExpectedTarget, ...],
    quantities: tuple[ExpectedQuantity, ...],
    trades: tuple[tuple[ExpectedIntent, ExpectedOutcome, ExpectedFill], ...],
    holdings: tuple[ExpectedHolding, ...],
    accounts: tuple[ExpectedAccount, ...],
    funding: tuple[ExpectedFunding, ...] = (),
    shortfalls: tuple[ExpectedShortfall, ...] = (),
    benchmark_prices: tuple[str, ...],
    multipliers: Mapping[str, Decimal] | None = None,
) -> ExpectedLedger:
    fills = tuple(item[2] for item in trades)
    return ExpectedLedger(
        targets=targets,
        quantities=quantities,
        intents=tuple(item[0] for item in trades),
        outcomes=tuple(item[1] for item in trades),
        fills=fills,
        funding=funding,
        holdings=holdings,
        accounts=accounts,
        shortfalls=shortfalls,
        streams=_streams(
            accounts,
            fills,
            benchmark_prices=tuple(map(D, benchmark_prices)),
            multipliers=multipliers or {},
        ),
    )


# --------------------------------------------------------------------------- #
# Independent public-result equations
# --------------------------------------------------------------------------- #


def _streams(
    accounts: tuple[ExpectedAccount, ...],
    fills: tuple[ExpectedFill, ...],
    *,
    benchmark_prices: tuple[Decimal, ...],
    multipliers: Mapping[str, Decimal],
) -> ExpectedStreams:
    if len(accounts) != len(benchmark_prices):
        raise ValueError("one benchmark price is required per account point")
    price_returns: list[Decimal] = []
    funding_returns: list[Decimal] = []
    cost_returns: list[Decimal] = []
    net_returns: list[Decimal] = []
    turnovers: list[Decimal] = []
    for previous, current in zip(accounts, accounts[1:], strict=False):
        prior_equity = previous.equity
        previous_trade = previous.realized_pnl + previous.unrealized_pnl
        current_trade = current.realized_pnl + current.unrealized_pnl
        price_return = (current_trade - previous_trade) / prior_equity
        funding_return = (current.funding - previous.funding) / prior_equity
        cost_return = (current.fees - previous.fees) / prior_equity
        price_returns.append(price_return)
        funding_returns.append(funding_return)
        cost_returns.append(cost_return)
        net_returns.append(price_return + funding_return - cost_return)
        interval_notional = sum(
            (
                abs(fill.quantity) * fill.price * multipliers.get(fill.instrument, D("1"))
                for fill in fills
                if previous.timestamp < fill.filled_at <= current.timestamp
            ),
            start=D("0"),
        )
        turnovers.append(interval_notional / prior_equity)
    first_benchmark = benchmark_prices[0]
    return ExpectedStreams(
        equity=tuple(item.equity for item in accounts),
        benchmark_equity=tuple(CAPITAL * price / first_benchmark for price in benchmark_prices),
        price_return=tuple(price_returns),
        funding_return=tuple(funding_returns),
        cost_return=tuple(cost_returns),
        net_return=tuple(net_returns),
        turnover=tuple(turnovers),
    )
