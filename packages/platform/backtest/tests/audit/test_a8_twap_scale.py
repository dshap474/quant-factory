"""A8 long-TWAP and scale stress regressions.

Purpose: prove exact signed lot conservation across long schedules, later-slice
limit failure, and deterministic behavior as instrument/target counts grow.

USAGE:
    uv run --project packages/platform/backtest pytest \
      packages/platform/backtest/tests/audit/test_a8_twap_scale.py -v
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import polars as pl
import pytest
from backtest import BacktestConfig, prepare_execution_from_strategy_weights, run_backtest_from_strategy_weights
from backtest.errors import BacktestEngineExecutionError

from execution import (
    AccountSnapshot,
    InstrumentKey,
    InstrumentSpec,
    PortfolioTarget,
    ReferencePrice,
    TargetQuantity,
    TargetWeight,
    TimeWeightedTakerPolicy,
    size_target_quantities,
)
from strategies import ExecutionTiming, StrategyWeights

from .a3_support import capture_rejection, valid_spec
from .a4_support import replay_fingerprint

# --------------------------------------------------------------------------- #
# Frozen facts and builders
# --------------------------------------------------------------------------- #

UTC = timezone.utc
T0 = datetime(2024, 8, 1, tzinfo=UTC)
KEY = InstrumentKey("BINANCE", "BTCUSDT")
WIRE = "BINANCE:BTCUSDT"


def _quantity(*, units: int, slice_count: int, multiplier: str = "1") -> tuple[TargetQuantity, TimeWeightedTakerPolicy]:
    increment = Decimal("0.001")
    decision_at = T0
    earliest = T0 + timedelta(minutes=1)
    quantity = TargetQuantity(
        target_id=f"C01-{units}-{slice_count}-{multiplier}",
        instrument=KEY,
        current_quantity=Decimal(0),
        desired_quantity=Decimal(units) * increment,
        delta_quantity=Decimal(units) * increment,
        reference_price=Decimal("100"),
        decision_at=decision_at,
        earliest_execution_at=earliest,
        quantity_increment=increment,
    )
    return quantity, TimeWeightedTakerPolicy(slice_count, timedelta(minutes=1))


def _spec(key: InstrumentKey, *, multiplier: str = "1") -> InstrumentSpec:
    base = key.symbol.removesuffix("USDT")
    return InstrumentSpec(
        key=key,
        product="perpetual",
        base_currency=base,
        quote_currency="USDT",
        settlement_currency="USDT",
        is_inverse=False,
        multiplier=Decimal(multiplier),
        price_increment=Decimal("0.01"),
        quantity_increment=Decimal("0.001"),
        min_quantity=Decimal(0),
        max_quantity=Decimal("1000000000"),
        min_notional=Decimal(0),
        max_notional=Decimal("1000000000000"),
        maker_fee_rate=Decimal(0),
        taker_fee_rate=Decimal(0),
    )


# --------------------------------------------------------------------------- #
# C01-C02: long schedule conservation and residue policy
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("slice_count", [7, 11, 24, 257])
@pytest.mark.parametrize("units", [1001, -1001, 7, -7])
def test_c01_long_twap_exact_signed_lot_conservation(slice_count: int, units: int) -> None:
    quantity, policy = _quantity(units=units, slice_count=slice_count)
    intents = policy.plan((quantity,))
    expected_count = min(abs(units), slice_count)
    assert len(intents) == expected_count
    assert sum((intent.quantity for intent in intents), Decimal(0)) == Decimal(units) * Decimal("0.001")
    assert len({intent.slice_id for intent in intents}) == expected_count
    absolute_units = [int(abs(intent.quantity) / Decimal("0.001")) for intent in intents]
    quotient, remainder = divmod(abs(units), slice_count)
    assert absolute_units == [quotient + (index < remainder) for index in range(expected_count)]


@pytest.mark.parametrize("slice_count", [7, 11, 24])
@pytest.mark.parametrize("relative_units", [-1, 0, 1])
@pytest.mark.parametrize("sign", [-1, 1])
@pytest.mark.parametrize("multiplier", ["1", "10"])
def test_c02_units_around_slice_count_conserve_and_scale(
    slice_count: int,
    relative_units: int,
    sign: int,
    multiplier: str,
) -> None:
    units = sign * (slice_count + relative_units)
    quantity, policy = _quantity(units=units, slice_count=slice_count, multiplier=multiplier)
    intents = policy.plan((quantity,))
    assert len(intents) == min(abs(units), slice_count)
    assert all(intent.quantity != 0 for intent in intents)
    assert sum((intent.quantity for intent in intents), Decimal(0)) == quantity.delta_quantity
    executed_notional = sum(abs(intent.quantity * Decimal("100") * Decimal(multiplier)) for intent in intents)
    assert executed_notional == abs(quantity.delta_quantity * Decimal("100") * Decimal(multiplier))


# --------------------------------------------------------------------------- #
# C03: later child crosses a price-dependent limit
# --------------------------------------------------------------------------- #


def test_c03_later_twap_child_below_min_notional_fails_without_result() -> None:
    calendar = tuple(T0 + timedelta(minutes=index) for index in range(6))
    closes = [100.0, 100.0, 100.0, 50.0, 100.0, 100.0]
    weights = StrategyWeights(
        pl.DataFrame({"timestamp": [T0], "BTC": [0.006], "CASH": [0.994]}),
        ["BTC"],
        execution=ExecutionTiming.next_bar(),
    )
    bars = pl.DataFrame(
        [
            {
                "instrument": WIRE,
                "source_timestamp": timestamp,
                "ts_event": timestamp,
                "ts_init": timestamp,
                "open": close,
                "high": close,
                "low": close,
                "close": close,
                "volume": 1.0,
            }
            for timestamp, close in zip(calendar, closes, strict=True)
        ]
    )
    prepared = prepare_execution_from_strategy_weights(
        weights=weights,
        asset_instruments={"BTC": KEY},
        reference_prices=pl.DataFrame(
            {
                "decision_at": [T0],
                "instrument": [WIRE],
                "observed_at": [T0],
                "price": [100.0],
            }
        ),
        bars=bars,
        instrument_specs=(
            valid_spec(
                quantity_increment=Decimal("1"),
                min_quantity=Decimal("1"),
                min_notional=Decimal("150"),
            ),
        ),
        execution_calendar=calendar,
        reporting_times=calendar[:5],
        policy=TimeWeightedTakerPolicy(3, timedelta(minutes=1)),
    )
    capture_rejection(
        "C03",
        "third public TWAP child",
        lambda: run_backtest_from_strategy_weights(
            weights=weights,
            data=None,
            config=BacktestConfig(metrics=[]),
            prepared_execution=prepared,
        ),
        BacktestEngineExecutionError,
        "below min_notional",
    )
    assert replay_fingerprint("immediate")[1] == "1745c8d15ac6cb09a83b237757b46b729740ce3dde0ea3d23d7c42638b59e5cd"


# --------------------------------------------------------------------------- #
# C06: engine-neutral scale
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("count", [1, 2, 16, 64, 128])
def test_c06_atomic_sizing_is_exact_and_canonical_at_scale(count: int) -> None:
    keys = tuple(InstrumentKey("BINANCE", f"A{index:03d}USDT") for index in range(count))
    decision_at = T0
    earliest = T0 + timedelta(minutes=1)
    weight = Decimal(1) / Decimal(count)
    target = PortfolioTarget(
        target_id=f"C06-{count}",
        decision_at=decision_at,
        earliest_execution_at=earliest,
        weights=tuple(TargetWeight(key, weight) for key in reversed(keys)),
        cash_weight=Decimal(0),
        reference_prices=tuple(ReferencePrice(key, Decimal("100"), decision_at) for key in reversed(keys)),
    )
    account = AccountSnapshot(
        as_of=earliest,
        cash=Decimal("128000"),
        equity=Decimal("128000"),
        positions=(),
        marks=tuple(ReferencePrice(key, Decimal("100"), earliest) for key in keys),
        cumulative_fees=Decimal(0),
        cumulative_funding=Decimal(0),
    )
    quantities = size_target_quantities(target, account, tuple(_spec(key) for key in keys))
    expected = (Decimal("128000") * weight / Decimal("100")).quantize(Decimal("0.001"))
    assert [item.instrument for item in quantities] == list(keys)
    assert all(item.desired_quantity == expected for item in quantities)
