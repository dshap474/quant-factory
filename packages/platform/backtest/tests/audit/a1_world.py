"""Public-path synthetic world builder and A1 ledger comparator.

Purpose: translate audit facts into public backtest inputs, run the complete
prepared execution path, and compare actual ledgers to already-built oracle
records. This module never calculates expected economic values.

USAGE:
    result = run_world_and_assert(world, expected)
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping

import polars as pl
import pytest
from backtest import (
    BacktestConfig,
    BacktestResult,
    prepare_execution_from_strategy_weights,
    run_backtest_from_strategy_weights,
)

from execution import ImmediateMarketPolicy, InstrumentKey, InstrumentSpec, TimeWeightedTakerPolicy
from strategies import ExecutionTiming, StrategyWeights

from .a1_oracle import ExpectedLedger

# --------------------------------------------------------------------------- #
# Synthetic input facts
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class InstrumentFacts:
    asset: str
    symbol: str
    base_currency: str
    closes: Mapping[datetime, Decimal]
    taker_fee_rate: Decimal = Decimal("0")
    maker_fee_rate: Decimal = Decimal("0")
    multiplier: Decimal = Decimal("1")
    price_increment: Decimal = Decimal("0.01")
    quantity_increment: Decimal = Decimal("0.001")

    @property
    def wire(self) -> str:
        return f"BINANCE:{self.symbol}"

    @property
    def key(self) -> InstrumentKey:
        return InstrumentKey(venue="BINANCE", symbol=self.symbol)

    def spec(self) -> InstrumentSpec:
        return InstrumentSpec(
            key=self.key,
            product="perpetual",
            base_currency=self.base_currency,
            quote_currency="USDT",
            settlement_currency="USDT",
            is_inverse=False,
            multiplier=self.multiplier,
            price_increment=self.price_increment,
            quantity_increment=self.quantity_increment,
            min_quantity=Decimal("0.001"),
            max_quantity=Decimal("1000000"),
            min_notional=Decimal("0"),
            max_notional=Decimal("1000000000"),
            maker_fee_rate=self.maker_fee_rate,
            taker_fee_rate=self.taker_fee_rate,
        )


@dataclass(frozen=True, slots=True)
class DecisionFact:
    decision_at: datetime
    weights: Mapping[str, Decimal]
    cash_weight: Decimal


@dataclass(frozen=True, slots=True)
class FundingFact:
    settlement_id: str
    instrument: str
    settled_at: datetime
    rate: Decimal
    mark_price: Decimal


@dataclass(frozen=True, slots=True)
class SyntheticWorld:
    scenario_id: str
    calendar: tuple[datetime, ...]
    instruments: tuple[InstrumentFacts, ...]
    decisions: tuple[DecisionFact, ...]
    reporting_times: tuple[datetime, ...]
    funding: tuple[FundingFact, ...] = ()
    initial_capital: Decimal = Decimal("100000")
    policy_kind: str = "immediate"
    slice_count: int = 1
    slice_interval: timedelta = timedelta(minutes=1)
    benchmark: str | None = None


# --------------------------------------------------------------------------- #
# Public execution
# --------------------------------------------------------------------------- #


def run_world_and_assert(
    world: SyntheticWorld,
    expected: ExpectedLedger,
) -> BacktestResult:
    """Run one public-path world after the caller has built its oracle."""
    result = _run_public_world(world)
    _assert_ledger(result, expected)
    return result


def _run_public_world(world: SyntheticWorld) -> BacktestResult:
    assets = [instrument.asset for instrument in world.instruments]
    weight_rows = []
    for decision in world.decisions:
        row: dict[str, object] = {"timestamp": decision.decision_at}
        row.update({asset: float(decision.weights[asset]) for asset in assets})
        row["CASH"] = float(decision.cash_weight)
        weight_rows.append(row)
    weights = StrategyWeights(
        weights=pl.DataFrame(weight_rows),
        assets=assets,
        execution=ExecutionTiming.next_bar(),
    )

    bars = pl.DataFrame(
        [
            {
                "instrument": instrument.wire,
                "source_timestamp": timestamp,
                "ts_event": timestamp,
                "ts_init": timestamp,
                "open": float(instrument.closes[timestamp]),
                "high": float(instrument.closes[timestamp]),
                "low": float(instrument.closes[timestamp]),
                "close": float(instrument.closes[timestamp]),
                "volume": 1.0,
            }
            for instrument in world.instruments
            for timestamp in world.calendar
        ]
    )
    references = pl.DataFrame(
        [
            {
                "decision_at": decision.decision_at,
                "instrument": instrument.wire,
                "observed_at": decision.decision_at,
                "price": float(instrument.closes[decision.decision_at]),
            }
            for decision in world.decisions
            for instrument in world.instruments
        ]
    )
    funding = (
        pl.DataFrame(
            [
                {
                    "settlement_id": item.settlement_id,
                    "instrument": item.instrument,
                    "settled_at": item.settled_at,
                    "rate": float(item.rate),
                    "mark_price": float(item.mark_price),
                }
                for item in world.funding
            ]
        )
        if world.funding
        else None
    )
    if world.policy_kind == "immediate":
        policy = ImmediateMarketPolicy()
    elif world.policy_kind == "twap":
        policy = TimeWeightedTakerPolicy(
            slice_count=world.slice_count,
            interval=world.slice_interval,
        )
    else:
        raise ValueError(f"unsupported audit policy: {world.policy_kind}")
    prepared = prepare_execution_from_strategy_weights(
        weights=weights,
        asset_instruments={instrument.asset: instrument.key for instrument in world.instruments},
        reference_prices=references,
        bars=bars,
        instrument_specs=[instrument.spec() for instrument in world.instruments],
        execution_calendar=world.calendar,
        reporting_times=world.reporting_times,
        policy=policy,
        funding_settlements=funding,
    )
    return run_backtest_from_strategy_weights(
        weights=weights,
        data=None,
        config=BacktestConfig(
            initial_capital=float(world.initial_capital),
            trade_cost_bps=999.0,
            include_funding=True,
            frequency="1m",
            benchmark=world.benchmark or world.instruments[0].symbol,
            metrics=[],
        ),
        prepared_execution=prepared,
    )


# --------------------------------------------------------------------------- #
# Exact ledger comparison
# --------------------------------------------------------------------------- #


def _wire(instrument: InstrumentKey) -> str:
    return f"{instrument.venue}:{instrument.symbol}"


def _assert_ledger(result: BacktestResult, expected: ExpectedLedger) -> None:
    assert result.execution is not None
    actual = result.execution

    assert tuple(
        (
            target.target_id,
            target.decision_at,
            target.earliest_execution_at,
            tuple((_wire(weight.instrument), weight.weight) for weight in target.weights),
            target.cash_weight,
            tuple(
                (_wire(reference.instrument), reference.price, reference.observed_at)
                for reference in target.reference_prices
            ),
        )
        for target in actual.targets
    ) == tuple(
        (
            item.target_id,
            item.decision_at,
            item.earliest_execution_at,
            item.weights,
            item.cash_weight,
            item.references,
        )
        for item in expected.targets
    )

    assert tuple(
        (
            item.target_id,
            _wire(item.instrument),
            item.current_quantity,
            item.desired_quantity,
            item.delta_quantity,
            item.reference_price,
            item.decision_at,
            item.earliest_execution_at,
            item.quantity_increment,
        )
        for item in actual.target_quantities
    ) == tuple(
        (
            item.target_id,
            item.instrument,
            item.current,
            item.desired,
            item.delta,
            item.reference_price,
            item.decision_at,
            item.earliest_execution_at,
            item.increment,
        )
        for item in expected.quantities
    )

    assert tuple(
        (
            item.target_id,
            item.slice_id,
            _wire(item.instrument),
            item.quantity,
            item.scheduled_at,
            item.expires_at,
        )
        for item in actual.intents
    ) == tuple(
        (
            item.target_id,
            item.slice_id,
            item.instrument,
            item.quantity,
            item.scheduled_at,
            item.expires_at,
        )
        for item in expected.intents
    )

    assert tuple(
        (
            item.intent.slice_id,
            item.status.value,
            item.unfilled_quantity,
            len(item.fills),
            item.reason,
        )
        for item in actual.outcomes
    ) == tuple((item.slice_id, item.status, item.unfilled, item.fill_count, item.reason) for item in expected.outcomes)
    if any(item.terminal_at is not None for item in expected.outcomes):
        assert tuple(item.terminal_at for item in actual.outcomes) == tuple(
            item.terminal_at for item in expected.outcomes
        )

    fill_ids = [item.fill_id for item in actual.fills]
    assert all(fill_ids)
    assert len(fill_ids) == len(set(fill_ids))
    assert tuple(
        (
            item.target_id,
            item.slice_id,
            _wire(item.instrument),
            item.quantity,
            item.price,
            item.fee,
            item.fee_currency,
            item.filled_at,
        )
        for item in actual.fills
    ) == tuple(
        (
            item.target_id,
            item.slice_id,
            item.instrument,
            item.quantity,
            item.price,
            item.fee,
            item.fee_currency,
            item.filled_at,
        )
        for item in expected.fills
    )
    assert {fill.fill_id for fill in actual.fills} == {
        fill.fill_id for outcome in actual.outcomes for fill in outcome.fills
    }

    assert tuple(
        (
            item.settlement_id,
            _wire(item.instrument),
            item.settled_at,
            item.rate,
            item.mark_price,
        )
        for item in actual.funding_settlements
    ) == tuple(
        (
            item.settlement_id,
            item.instrument,
            item.settled_at,
            item.rate,
            item.mark_price,
        )
        for item in expected.funding
    )

    assert tuple(
        (
            item.timestamp,
            _wire(item.instrument),
            item.quantity,
            item.mark_price,
            item.notional,
        )
        for item in actual.holdings
    ) == tuple(
        (
            item.timestamp,
            item.instrument,
            item.quantity,
            item.mark_price,
            item.notional,
        )
        for item in expected.holdings
    )

    assert tuple(
        (
            item.timestamp,
            item.cash,
            item.equity,
            item.realized_pnl,
            item.unrealized_pnl,
            item.fees,
            item.funding,
        )
        for item in actual.account_path
    ) == tuple(
        (
            item.timestamp,
            item.cash,
            item.equity,
            item.realized_pnl,
            item.unrealized_pnl,
            item.fees,
            item.funding,
        )
        for item in expected.accounts
    )
    assert [float(value) for value in result.equity] == pytest.approx(
        [float(item.equity) for item in expected.accounts],
        rel=0,
        abs=1e-6,
    )
    if expected.shortfalls is not None:
        assert tuple(
            (
                item.target_id,
                _wire(item.instrument),
                item.intended_quantity,
                item.filled_quantity,
                item.decision_price,
                item.arrival_price,
                item.terminal_price,
                item.delay,
                item.trading,
                item.fee,
                item.unfilled,
                item.total,
            )
            for item in actual.shortfalls
        ) == tuple(
            (
                item.target_id,
                item.instrument,
                item.intended,
                item.filled,
                item.decision_price,
                item.arrival_price,
                item.terminal_price,
                item.delay,
                item.trading,
                item.fee,
                item.unfilled,
                item.total,
            )
            for item in expected.shortfalls
        )
    if expected.streams is not None:
        streams = expected.streams
        _assert_float_series(result.equity, streams.equity, tolerance=1e-6)
        _assert_float_series(result.benchmark_equity, streams.benchmark_equity, tolerance=1e-6)
        _assert_float_series(result.price_return, streams.price_return)
        _assert_float_series(result.funding_return, streams.funding_return)
        _assert_float_series(result.cost_return, streams.cost_return)
        _assert_float_series(result.net_return, streams.net_return)
        _assert_float_series(result.turnover, streams.turnover)


def _assert_float_series(
    actual: pl.Series,
    expected: tuple[Decimal, ...],
    *,
    tolerance: float = 1e-12,
) -> None:
    assert actual.to_list() == pytest.approx(
        [float(value) for value in expected],
        rel=0,
        abs=tolerance,
    )


# --------------------------------------------------------------------------- #
# Deterministic trace
# --------------------------------------------------------------------------- #


def input_hash(world: SyntheticWorld) -> str:
    """Hash all synthetic facts plus the fixed public-path configuration."""
    world_facts: dict[str, object] = {
        "scenario_id": world.scenario_id,
        "calendar": world.calendar,
        "instruments": world.instruments,
        "decisions": world.decisions,
        "reporting_times": world.reporting_times,
        "funding": world.funding,
        "initial_capital": world.initial_capital,
    }
    policy: object = "ImmediateMarketPolicy"
    if world.policy_kind != "immediate":
        policy = {
            "kind": world.policy_kind,
            "slice_count": world.slice_count,
            "interval": world.slice_interval,
        }
    config: dict[str, object] = {
        "trade_cost_bps": 999.0,
        "include_funding": True,
        "frequency": "1m",
        "metrics": [],
    }
    if world.benchmark is not None:
        config["benchmark"] = world.benchmark
    return _canonical_hash(
        {
            "world": world_facts,
            "execution": "next_bar",
            "policy": policy,
            "config": config,
        }
    )


def trace_hash(result: BacktestResult) -> str:
    """Hash the complete ordered ledger and public result surface."""
    assert result.execution is not None
    return _canonical_hash(
        {
            "execution": result.execution,
            "equity": result.equity,
            "benchmark_equity": result.benchmark_equity,
            "price_return": result.price_return,
            "funding_return": result.funding_return,
            "cost_return": result.cost_return,
            "net_return": result.net_return,
            "turnover": result.turnover,
            "metrics": result.metrics,
            "engine_used": result.engine_used,
            "engine_meta": result.engine_meta,
        }
    )


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(_canonicalize(value), separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(encoded).hexdigest()


def _canonicalize(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        return value.isoformat(timespec="microseconds")
    if isinstance(value, timedelta):
        return format(Decimal(str(value.total_seconds())), "f")
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, pl.Series):
        return [_canonicalize(item) for item in value.to_list()]
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _canonicalize(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _canonicalize(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (tuple, list)):
        return [_canonicalize(item) for item in value]
    return value
