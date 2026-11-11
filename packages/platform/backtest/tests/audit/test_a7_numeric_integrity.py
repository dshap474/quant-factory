"""A7 numeric-boundary and prepared-integrity audit regressions.

Purpose: prove configuration and execution inputs fail closed at numeric,
insolvency, provenance, identity, reuse, and timestamp boundaries.

USAGE:
    uv run --project packages/platform/backtest pytest \
      packages/platform/backtest/tests/audit/test_a7_numeric_integrity.py -v
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from math import inf, nan

import polars as pl
import pytest
from backtest import BacktestConfig, prepare_execution_from_strategy_weights, run_backtest_from_strategy_weights
from backtest.errors import BacktestContractError, BacktestEngineExecutionError
from backtest.preparation import prepared_execution_fingerprint, strategy_weights_fingerprint

from execution import (
    AccountSnapshot,
    FundingSettlement,
    InstrumentKey,
    PortfolioTarget,
    ReferencePrice,
    TargetWeight,
    TimeWeightedTakerPolicy,
    size_target_quantities,
    validate_order_limits,
)
from strategies import ExecutionTiming, StrategyWeights

from .a1_world import DecisionFact, FundingFact, InstrumentFacts, SyntheticWorld, _run_public_world, trace_hash
from .a3_support import capture_rejection, prepare, valid_packet, valid_spec

# --------------------------------------------------------------------------- #
# Frozen A7 facts
# --------------------------------------------------------------------------- #

UTC = timezone.utc
T0 = datetime(2024, 7, 1, tzinfo=UTC)
CAL = tuple(T0 + timedelta(minutes=index) for index in range(6))
KEY = InstrumentKey("BINANCE", "BTCUSDT")
WIRE = "BINANCE:BTCUSDT"

# --------------------------------------------------------------------------- #
# B01-B02: public configuration boundaries
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("initial_capital", [0, -1, nan, inf, -inf])
def test_b01_invalid_initial_capital_rejects_at_configuration(initial_capital: float) -> None:
    with pytest.raises(ValueError, match="initial_capital must be finite and positive"):
        BacktestConfig(initial_capital=initial_capital)


def test_b01_finite_positive_initial_capital_is_accepted() -> None:
    assert BacktestConfig(initial_capital=1).initial_capital == 1


@pytest.mark.parametrize("trade_cost_bps", [-1, nan, inf, -inf])
def test_b02_invalid_trade_cost_rejects_at_configuration(trade_cost_bps: float) -> None:
    with pytest.raises(ValueError, match="trade_cost_bps must be finite and non-negative"):
        BacktestConfig(trade_cost_bps=trade_cost_bps)


def test_b02_zero_trade_cost_is_accepted() -> None:
    assert BacktestConfig(trade_cost_bps=0).trade_cost_bps == 0


# --------------------------------------------------------------------------- #
# B03-B04: insolvency boundaries
# --------------------------------------------------------------------------- #


def _decision(index: int, weight: str) -> DecisionFact:
    value = Decimal(weight)
    return DecisionFact(CAL[index], {"BTC": value}, Decimal(1) - value)


def _instrument(*closes: str) -> InstrumentFacts:
    padded = (*closes, *((closes[-1],) * (len(CAL) - len(closes))))
    return InstrumentFacts(
        asset="BTC",
        symbol="BTCUSDT",
        base_currency="BTC",
        closes=dict(zip(CAL, map(Decimal, padded), strict=True)),
        quantity_increment=Decimal("1"),
    )


def test_b03_funding_to_zero_equity_fails_before_second_target() -> None:
    synthetic = SyntheticWorld(
        scenario_id="B03-funding-zero-equity",
        calendar=CAL,
        instruments=(_instrument("100"),),
        decisions=(_decision(0, "1"), _decision(1, "1")),
        reporting_times=(CAL[1], CAL[2]),
        funding=(FundingFact("B03-funding", WIRE, CAL[2], Decimal("1"), Decimal("100")),),
        initial_capital=Decimal("1000"),
        benchmark="BTCUSDT",
    )
    evidence = capture_rejection(
        "B03",
        "public second-target account snapshot",
        lambda: _run_public_world(synthetic),
        BacktestEngineExecutionError,
        "equity must be positive, got 0",
    )
    assert evidence.exception == "BacktestEngineExecutionError"


def test_b04_mark_to_negative_equity_fails_before_second_target() -> None:
    synthetic = SyntheticWorld(
        scenario_id="B04-mark-negative-equity",
        calendar=CAL,
        instruments=(_instrument("100", "100", "49"),),
        decisions=(_decision(0, "2"), _decision(1, "2")),
        reporting_times=(CAL[1], CAL[2]),
        initial_capital=Decimal("1000"),
        benchmark="BTCUSDT",
    )
    evidence = capture_rejection(
        "B04",
        "public second-target account snapshot",
        lambda: _run_public_world(synthetic),
        BacktestEngineExecutionError,
        "equity must be positive, got -20",
    )
    assert evidence.exception == "BacktestEngineExecutionError"


def test_b04_terminal_negative_equity_cannot_return_usable_result() -> None:
    synthetic = SyntheticWorld(
        scenario_id="B04-terminal-negative-equity",
        calendar=CAL,
        instruments=(_instrument("100", "100", "49"),),
        decisions=(_decision(0, "2"),),
        reporting_times=(CAL[1], CAL[2]),
        initial_capital=Decimal("1000"),
        benchmark="BTCUSDT",
    )
    capture_rejection(
        "B04-terminal",
        "public terminal account report",
        lambda: _run_public_world(synthetic),
        BacktestEngineExecutionError,
        "equity must remain positive",
    )


# --------------------------------------------------------------------------- #
# B05-B06: Decimal, multiplier, and exact limit boundaries
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("price", "multiplier", "expected"),
    [
        ("0.00000001", "0.01", "500000000000000"),
        ("1", "1", "50000"),
        ("100000000", "100", "0.000005"),
    ],
)
def test_b05_decimal_magnitude_and_multiplier_size_exactly(
    price: str,
    multiplier: str,
    expected: str,
) -> None:
    reference = ReferencePrice(KEY, Decimal(price), T0)
    target = PortfolioTarget(
        target_id=f"B05-{price}-{multiplier}",
        decision_at=T0,
        earliest_execution_at=CAL[1],
        weights=(TargetWeight(KEY, Decimal("0.5")),),
        cash_weight=Decimal("0.5"),
        reference_prices=(reference,),
    )
    account = AccountSnapshot(
        as_of=CAL[1],
        cash=Decimal("100000"),
        equity=Decimal("100000"),
        positions=(),
        marks=(ReferencePrice(KEY, Decimal(price), CAL[1]),),
        cumulative_fees=Decimal(0),
        cumulative_funding=Decimal(0),
    )
    spec = valid_spec(
        multiplier=Decimal(multiplier),
        price_increment=Decimal("0.00000001"),
        quantity_increment=Decimal("0.000001"),
        min_quantity=Decimal(0),
        max_quantity=Decimal("1e30"),
        max_notional=Decimal("1e30"),
    )
    sized = size_target_quantities(target, account, (spec,))
    assert sized[0].desired_quantity == Decimal(expected)


@pytest.mark.parametrize(
    ("price", "multiplier", "capital", "expected"),
    [
        ("0.00000001", "0.01", "0.000001", "5000.000000"),
        ("1", "1", "100000", "50000.000000"),
        ("100000000", "100", "100000", "0.000005"),
    ],
)
def test_b05_decimal_extremes_cross_public_nautilus_path(
    price: str,
    multiplier: str,
    capital: str,
    expected: str,
) -> None:
    packet = valid_packet()
    price_float = float(Decimal(price))
    packet["reference_prices"] = packet["reference_prices"].with_columns(pl.lit(price_float).alias("price"))
    packet["bars"] = packet["bars"].with_columns(
        pl.lit(price_float).alias("open"),
        pl.lit(price_float).alias("high"),
        pl.lit(price_float).alias("low"),
        pl.lit(price_float).alias("close"),
    )
    packet["instrument_specs"] = (
        valid_spec(
            multiplier=Decimal(multiplier),
            price_increment=Decimal("0.00000001"),
            quantity_increment=Decimal("0.000001"),
            min_quantity=Decimal("0.000001"),
            max_quantity=Decimal("1000000"),
            max_notional=Decimal("1000000000000"),
        ),
    )
    prepared = prepare(packet)
    result = run_backtest_from_strategy_weights(
        weights=packet["weights"],
        data=None,
        config=BacktestConfig(initial_capital=float(Decimal(capital)), metrics=[]),
        prepared_execution=prepared,
    )
    assert result.execution is not None
    assert result.execution.target_quantities[0].desired_quantity == Decimal(expected)
    assert result.execution.fills[0].quantity == Decimal(expected)


@pytest.mark.parametrize("quantity", [Decimal("2"), Decimal("4"), Decimal("-2"), Decimal("-4")])
def test_b06_quantity_limits_accept_exact_boundaries(quantity: Decimal) -> None:
    validate_order_limits(
        order_quantity=quantity,
        price=Decimal("100"),
        spec=valid_spec(
            quantity_increment=Decimal("1"),
            min_quantity=Decimal("2"),
            max_quantity=Decimal("4"),
            min_notional=Decimal(0),
            max_notional=Decimal("1e30"),
        ),
    )


@pytest.mark.parametrize(
    ("quantity", "fragment"),
    [
        (Decimal("1"), "below min_quantity"),
        (Decimal("5"), "exceeds max_quantity"),
        (Decimal("-1"), "below min_quantity"),
        (Decimal("-5"), "exceeds max_quantity"),
    ],
)
def test_b06_quantity_limits_reject_one_increment_outside(quantity: Decimal, fragment: str) -> None:
    with pytest.raises(ValueError, match=fragment):
        validate_order_limits(
            order_quantity=quantity,
            price=Decimal("100"),
            spec=valid_spec(
                quantity_increment=Decimal("1"),
                min_quantity=Decimal("2"),
                max_quantity=Decimal("4"),
                min_notional=Decimal(0),
                max_notional=Decimal("1e30"),
            ),
        )


@pytest.mark.parametrize("quantity", [Decimal("2"), Decimal("4"), Decimal("-2"), Decimal("-4")])
def test_b06_notional_limits_accept_exact_boundaries(quantity: Decimal) -> None:
    validate_order_limits(
        order_quantity=quantity,
        price=Decimal("100"),
        spec=valid_spec(
            quantity_increment=Decimal("1"),
            min_quantity=Decimal(0),
            max_quantity=Decimal("100"),
            min_notional=Decimal("200"),
            max_notional=Decimal("400"),
        ),
    )


@pytest.mark.parametrize(
    ("quantity", "fragment"),
    [
        (Decimal("1.99"), "below min_notional"),
        (Decimal("4.01"), "exceeds max_notional"),
        (Decimal("-1.99"), "below min_notional"),
        (Decimal("-4.01"), "exceeds max_notional"),
    ],
)
def test_b06_notional_limits_reject_one_unit_outside(quantity: Decimal, fragment: str) -> None:
    with pytest.raises(ValueError, match=fragment):
        validate_order_limits(
            order_quantity=quantity,
            price=Decimal("100"),
            spec=valid_spec(
                quantity_increment=Decimal("0.01"),
                min_quantity=Decimal(0),
                max_quantity=Decimal("100"),
                min_notional=Decimal("200"),
                max_notional=Decimal("400"),
            ),
        )


# --------------------------------------------------------------------------- #
# B07: prepared target integrity
# --------------------------------------------------------------------------- #


def test_b07_copied_weights_fingerprint_cannot_authorize_opposite_targets() -> None:
    packet = valid_packet()
    prepared = prepare(packet)
    original = prepared.targets[0]
    forged_target = replace(
        original,
        weights=(TargetWeight(KEY, Decimal("-0.5")),),
        cash_weight=Decimal("1.5"),
    )
    forged = replace(prepared, targets=(forged_target,))
    capture_rejection(
        "B07",
        "public prepared execution integrity",
        lambda: run_backtest_from_strategy_weights(
            weights=packet["weights"],
            data=None,
            config=BacktestConfig(metrics=[]),
            prepared_execution=forged,
        ),
        BacktestContractError,
        "prepared execution integrity",
    )


# --------------------------------------------------------------------------- #
# B08-B09: complete prepared payload and identity boundaries
# --------------------------------------------------------------------------- #


def test_b08_every_material_prepared_field_is_integrity_bound() -> None:
    packet = valid_packet()
    prepared = prepare(packet)
    altered_bar = prepared.bars.with_columns(pl.lit(101.0).alias("close"))
    mutations = {
        "bars": replace(prepared, bars=altered_bar),
        "instrument_specs": replace(
            prepared,
            instrument_specs=(replace(prepared.instrument_specs[0], taker_fee_rate=Decimal("0.001")),),
        ),
        "funding": replace(
            prepared,
            funding_settlements=(FundingSettlement("B08-funding", KEY, CAL[1], Decimal("0.001"), Decimal("100")),),
        ),
        "reporting_times": replace(prepared, reporting_times=prepared.reporting_times[:-1]),
        "execution_calendar": replace(prepared, execution_calendar=prepared.execution_calendar[:-1]),
        "policy": replace(prepared, policy=TimeWeightedTakerPolicy(2, timedelta(minutes=1))),
    }
    for name, forged in mutations.items():
        with pytest.raises(BacktestContractError, match="prepared execution integrity"):
            run_backtest_from_strategy_weights(
                weights=packet["weights"],
                data=None,
                config=BacktestConfig(metrics=[]),
                prepared_execution=forged,
            )
        assert prepared_execution_fingerprint(forged) != prepared.prepared_payload_sha256, name


def test_b09_direct_prepared_input_rejects_duplicate_target_identity() -> None:
    prepared = prepare(valid_packet())
    with pytest.raises(ValueError, match="duplicate target_id"):
        replace(prepared, targets=(prepared.targets[0], prepared.targets[0]))


def test_b09_execution_result_rejects_every_identity_collision() -> None:
    packet = valid_packet()
    result = run_backtest_from_strategy_weights(
        weights=packet["weights"],
        data=None,
        config=BacktestConfig(metrics=[]),
        prepared_execution=prepare(packet),
    )
    assert result.execution is not None
    execution = result.execution
    with pytest.raises(ValueError, match="duplicate target quantity"):
        replace(execution, target_quantities=(*execution.target_quantities, execution.target_quantities[0]))
    with pytest.raises(ValueError, match="duplicate slice_id"):
        replace(execution, intents=(*execution.intents, execution.intents[0]))
    with pytest.raises(ValueError, match="duplicate fill_id"):
        replace(execution, fills=(*execution.fills, execution.fills[0]))
    with pytest.raises(ValueError, match="duplicate outcome slice_id"):
        replace(execution, outcomes=(*execution.outcomes, execution.outcomes[0]))
    with pytest.raises(ValueError, match="duplicate shortfall"):
        replace(execution, shortfalls=(*execution.shortfalls, execution.shortfalls[0]))
    settlement = FundingSettlement("B09-funding", KEY, CAL[1], Decimal("0.001"), Decimal("100"))
    with pytest.raises(ValueError, match="duplicate settlement_id"):
        replace(execution, funding_settlements=(settlement, settlement))


# --------------------------------------------------------------------------- #
# B10-B11: immutable reuse and exhaustive weights fingerprint facts
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("kind", ["immediate", "twap"])
def test_b10_exact_prepared_object_reuse_has_one_trace_and_no_mutation(kind: str) -> None:
    packet = valid_packet()
    if kind == "twap":
        packet["weights"] = StrategyWeights(
            weights=pl.DataFrame(
                {"timestamp": [packet["weights"].weights["timestamp"][0]], "BTC": [0.006], "CASH": [0.994]}
            ),
            assets=["BTC"],
            execution=ExecutionTiming.next_bar(),
        )
        packet["instrument_specs"] = (valid_spec(quantity_increment=Decimal("1"), min_quantity=Decimal("1")),)
        packet["policy"] = TimeWeightedTakerPolicy(3, timedelta(minutes=1))
    prepared = prepare(packet)
    before = prepared_execution_fingerprint(prepared)
    traces = {
        trace_hash(
            run_backtest_from_strategy_weights(
                weights=packet["weights"],
                data=None,
                config=BacktestConfig(metrics=[]),
                prepared_execution=prepared,
            )
        )
        for _ in range(25)
    }
    assert len(traces) == 1
    assert prepared_execution_fingerprint(prepared) == before == prepared.prepared_payload_sha256


def test_b11_weights_fingerprint_covers_all_economic_and_timing_facts() -> None:
    base = StrategyWeights(
        weights=pl.DataFrame({"timestamp": [T0], "BTC": [0.5], "CASH": [0.5]}),
        assets=["BTC"],
        execution=ExecutionTiming.next_bar(),
    )
    variants = (
        StrategyWeights(pl.DataFrame({"timestamp": [T0], "BTC": [-0.5], "CASH": [1.5]}), ["BTC"]),
        StrategyWeights(pl.DataFrame({"timestamp": [T0], "BTC": [0.6], "CASH": [0.4]}), ["BTC"]),
        StrategyWeights(
            pl.DataFrame({"timestamp": [T0 + timedelta(microseconds=1)], "BTC": [0.5], "CASH": [0.5]}),
            ["BTC"],
        ),
        StrategyWeights(pl.DataFrame({"timestamp": [T0], "ETH": [0.5], "CASH": [0.5]}), ["ETH"]),
        StrategyWeights(
            pl.DataFrame({"timestamp": [T0], "BTC": [0.5], "RESERVE": [0.5]}),
            ["BTC"],
            cash_col="RESERVE",
        ),
        StrategyWeights(
            pl.DataFrame({"timestamp": [T0], "BTC": [0.5], "CASH": [0.5]}),
            ["BTC"],
            execution=ExecutionTiming.lagged(2),
        ),
    )
    baseline = strategy_weights_fingerprint(base)
    assert all(strategy_weights_fingerprint(variant) != baseline for variant in variants)


def test_b11_weights_fingerprint_ignores_only_declared_representation_and_metadata() -> None:
    first = StrategyWeights(
        pl.DataFrame({"timestamp": [T0], "BTC": [0.5], "ETH": [-0.25], "CASH": [0.75]}),
        ["BTC", "ETH"],
        metadata={"source": "first"},
    )
    second = StrategyWeights(
        pl.DataFrame(
            {
                "timestamp": [T0],
                "CASH": [Decimal("0.7500")],
                "ETH": [Decimal("-0.250")],
                "BTC": [Decimal("0.500")],
            }
        ),
        ["ETH", "BTC"],
        metadata={"source": "second", "ignored": True},
    )
    assert strategy_weights_fingerprint(first) == strategy_weights_fingerprint(second)


# --------------------------------------------------------------------------- #
# B12: epoch, 2038, microsecond decisions, and completed-time authority
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "origin",
    [datetime(1970, 1, 1, tzinfo=UTC), datetime(2038, 1, 19, 3, 13, tzinfo=UTC)],
)
def test_b12_timestamp_boundaries_preserve_microseconds_and_completed_order(origin: datetime) -> None:
    calendar = tuple(origin + timedelta(minutes=index) for index in range(5))
    decisions = (origin, origin + timedelta(minutes=1, microseconds=1))
    weights = StrategyWeights(
        pl.DataFrame(
            {
                "timestamp": list(decisions),
                "BTC": [0.5, -0.5],
                "CASH": [0.5, 1.5],
            }
        ),
        ["BTC"],
    )
    bars = pl.DataFrame(
        [
            {
                "instrument": WIRE,
                "source_timestamp": origin,
                "ts_event": origin,
                "ts_init": close,
                "open": 100.0,
                "high": 100.0,
                "low": 100.0,
                "close": 100.0,
                "volume": 1.0,
            }
            for close in calendar
        ]
    )
    references = pl.DataFrame(
        {
            "decision_at": list(decisions),
            "instrument": [WIRE, WIRE],
            "observed_at": [calendar[0], calendar[1]],
            "price": [100.0, 100.0],
        }
    )
    prepared = prepare_execution_from_strategy_weights(
        weights=weights,
        asset_instruments={"BTC": KEY},
        reference_prices=references,
        bars=bars,
        instrument_specs=(valid_spec(),),
        execution_calendar=calendar,
        reporting_times=calendar[:4],
        policy=valid_packet()["policy"],
    )
    result = run_backtest_from_strategy_weights(
        weights=weights,
        data=None,
        config=BacktestConfig(metrics=[]),
        prepared_execution=prepared,
    )
    assert result.execution is not None
    assert tuple(target.decision_at for target in result.execution.targets) == decisions
    assert tuple(fill.filled_at for fill in result.execution.fills) == (calendar[1], calendar[2])
    assert [fill.quantity for fill in result.execution.fills] == [Decimal("500.000"), Decimal("-1000.000")]
