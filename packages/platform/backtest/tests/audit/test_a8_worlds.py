"""A8 public scale, ordering, horizon, metamorphic, and contract worlds.

Purpose: stress the complete prepared Nautilus path with many instruments and
targets while preserving hand-computable economics and canonical traces.

USAGE:
    uv run --project packages/platform/backtest pytest \
      packages/platform/backtest/tests/audit/test_a8_worlds.py -v
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import polars as pl
import pytest
from backtest.errors import BacktestContractError
from backtest.preparation import strategy_weights_fingerprint

from strategies import StrategyWeights

from .a1_world import DecisionFact, FundingFact, InstrumentFacts, SyntheticWorld, _run_public_world, trace_hash
from .a3_support import capture_rejection

# --------------------------------------------------------------------------- #
# Frozen facts and builders
# --------------------------------------------------------------------------- #

UTC = timezone.utc
T0 = datetime(2024, 8, 3, tzinfo=UTC)
ASSETS = (
    "BTC",
    "ETH",
    "SOL",
    "XRP",
    "ADA",
    "DOGE",
    "AVAX",
    "DOT",
    "LINK",
    "LTC",
    "BCH",
    "ATOM",
    "UNI",
    "AAVE",
    "NEAR",
    "FIL",
)


def _prices(calendar: tuple[datetime, ...], value: str) -> dict[datetime, Decimal]:
    return {timestamp: Decimal(value) for timestamp in calendar}


def _instrument(asset: str, calendar: tuple[datetime, ...], price: str = "100") -> InstrumentFacts:
    return InstrumentFacts(
        asset=asset,
        symbol=f"{asset}USDT",
        base_currency=asset,
        closes=_prices(calendar, price),
        quantity_increment=Decimal("0.001"),
    )


def _decision(timestamp: datetime, weights: dict[str, Decimal]) -> DecisionFact:
    return DecisionFact(timestamp, weights, Decimal(1) - sum(weights.values(), Decimal(0)))


# --------------------------------------------------------------------------- #
# C06: public multi-instrument scale
# --------------------------------------------------------------------------- #


def test_c06_sixteen_instrument_public_world_has_exact_isolated_legs() -> None:
    calendar = tuple(T0 + timedelta(minutes=index) for index in range(3))
    weight = Decimal(1) / Decimal(len(ASSETS))
    world = SyntheticWorld(
        scenario_id="C06-sixteen-instruments",
        calendar=calendar,
        instruments=tuple(_instrument(asset, calendar) for asset in reversed(ASSETS)),
        decisions=(_decision(T0, {asset: weight for asset in ASSETS}),),
        reporting_times=(calendar[1], calendar[2]),
        initial_capital=Decimal("160000"),
        benchmark="BTCUSDT",
    )
    result = _run_public_world(world)
    assert result.execution is not None
    execution = result.execution
    assert len(execution.fills) == len(ASSETS)
    assert [item.instrument.symbol for item in execution.target_quantities] == sorted(
        f"{asset}USDT" for asset in ASSETS
    )
    assert all(item.desired_quantity == Decimal("100.000") for item in execution.target_quantities)
    assert all(fill.quantity == Decimal("100.000") and fill.fee == 0 for fill in execution.fills)
    assert execution.account_path[-1].equity == Decimal("160000")


# --------------------------------------------------------------------------- #
# C07: tied event ordering and input permutation
# --------------------------------------------------------------------------- #


def _tied_world(*, reverse_instruments: bool, reverse_funding: bool) -> SyntheticWorld:
    calendar = tuple(T0 + timedelta(minutes=index) for index in range(6))
    instruments = (
        _instrument("BTC", calendar, "100"),
        _instrument("ETH", calendar, "50"),
    )
    funding = (
        FundingFact("C07-btc", "BINANCE:BTCUSDT", calendar[3], Decimal("0.001"), Decimal("100")),
        FundingFact("C07-eth", "BINANCE:ETHUSDT", calendar[3], Decimal("-0.002"), Decimal("50")),
    )
    return SyntheticWorld(
        scenario_id="C07-tied-order",
        calendar=calendar,
        instruments=tuple(reversed(instruments)) if reverse_instruments else instruments,
        decisions=(
            _decision(T0, {"BTC": Decimal("0.4"), "ETH": Decimal("0.3")}),
            _decision(calendar[2], {"BTC": Decimal("-0.2"), "ETH": Decimal("0.1")}),
        ),
        reporting_times=(calendar[1], calendar[3], calendar[4]),
        funding=tuple(reversed(funding)) if reverse_funding else funding,
        benchmark="BTCUSDT",
    )


def test_c07_tied_multi_instrument_permutations_preserve_complete_trace() -> None:
    results = [
        _run_public_world(_tied_world(reverse_instruments=reverse_instruments, reverse_funding=reverse_funding))
        for reverse_instruments in (False, True)
        for reverse_funding in (False, True)
    ]
    assert len({trace_hash(result) for result in results}) == 1
    execution = results[0].execution
    assert execution is not None
    second_quantities = execution.target_quantities[2:]
    assert [item.desired_quantity for item in second_quantities] == [Decimal("-200.040"), Decimal("200.040")]
    assert execution.account_path[1].funding == Decimal("20.000000")


# --------------------------------------------------------------------------- #
# C08: one hundred targets with periodic explicit funding
# --------------------------------------------------------------------------- #


def test_c08_one_hundred_targets_reconcile_without_identity_or_decimal_drift() -> None:
    calendar = tuple(T0 + timedelta(minutes=index) for index in range(202))
    instrument = _instrument("BTC", calendar, "100")
    weights = (Decimal("0.1"), Decimal("-0.1"), Decimal(0))
    decisions = tuple(_decision(calendar[index * 2], {"BTC": weights[index % 3]}) for index in range(100))
    funding = tuple(
        FundingFact(
            f"C08-funding-{index:03d}",
            "BINANCE:BTCUSDT",
            calendar[index * 2 + 1],
            Decimal(0),
            Decimal("100"),
        )
        for index in range(0, 100, 10)
    )
    result = _run_public_world(
        SyntheticWorld(
            scenario_id="C08-hundred-targets",
            calendar=calendar,
            instruments=(instrument,),
            decisions=decisions,
            reporting_times=tuple(calendar[index * 2 + 1] for index in range(100)),
            funding=funding,
            benchmark="BTCUSDT",
        )
    )
    assert result.execution is not None
    execution = result.execution
    assert len(execution.targets) == len(execution.target_quantities) == len(execution.intents) == 100
    assert len({target.target_id for target in execution.targets}) == 100
    assert len({intent.slice_id for intent in execution.intents}) == 100
    assert execution.holdings[-1].quantity == Decimal("100.000")
    assert execution.account_path[-1].equity == Decimal("100000")
    assert execution.account_path[-1].funding == 0


# --------------------------------------------------------------------------- #
# C09: capital/quantity scaling
# --------------------------------------------------------------------------- #


def _scaled_world(capital: str) -> SyntheticWorld:
    calendar = tuple(T0 + timedelta(minutes=index) for index in range(4))
    closes = {
        calendar[0]: Decimal("100"),
        calendar[1]: Decimal("100"),
        calendar[2]: Decimal("110"),
        calendar[3]: Decimal("110"),
    }
    return SyntheticWorld(
        scenario_id=f"C09-scale-{capital}",
        calendar=calendar,
        instruments=(
            InstrumentFacts(
                asset="BTC",
                symbol="BTCUSDT",
                base_currency="BTC",
                closes=closes,
                taker_fee_rate=Decimal("0.001"),
            ),
        ),
        decisions=(_decision(T0, {"BTC": Decimal("0.5")}),),
        reporting_times=(calendar[1], calendar[2]),
        funding=(FundingFact("C09-funding", "BINANCE:BTCUSDT", calendar[2], Decimal("0.001"), Decimal("110")),),
        initial_capital=Decimal(capital),
        benchmark="BTCUSDT",
    )


def test_c09_capital_scaling_scales_economics_and_preserves_returns() -> None:
    small = _run_public_world(_scaled_world("100000"))
    large = _run_public_world(_scaled_world("1000000"))
    assert small.execution is not None and large.execution is not None
    factor = Decimal(10)
    assert large.execution.fills[0].quantity == small.execution.fills[0].quantity * factor
    for small_point, large_point in zip(small.execution.account_path, large.execution.account_path, strict=True):
        assert large_point.cash == small_point.cash * factor
        assert large_point.equity == small_point.equity * factor
        assert large_point.realized_pnl == small_point.realized_pnl * factor
        assert large_point.unrealized_pnl == small_point.unrealized_pnl * factor
        assert large_point.fees == small_point.fees * factor
        assert large_point.funding == small_point.funding * factor
    for name in ("price_return", "funding_return", "cost_return", "net_return", "turnover"):
        assert getattr(large, name).to_list() == pytest.approx(getattr(small, name).to_list(), rel=0, abs=1e-12)


# --------------------------------------------------------------------------- #
# C10-C11: fingerprint fuzzing and malformed-but-typed inputs
# --------------------------------------------------------------------------- #


def test_c10_one_hundred_equivalent_weight_representations_share_fingerprint() -> None:
    baseline = StrategyWeights(
        pl.DataFrame({"timestamp": [T0], "BTC": [0.4], "ETH": [-0.2], "CASH": [0.8]}),
        ["BTC", "ETH"],
    )
    expected = strategy_weights_fingerprint(baseline)
    for case in range(100):
        rng = random.Random(8_100 + case)
        assets = ["BTC", "ETH"]
        rng.shuffle(assets)
        columns: list[tuple[str, object]] = [
            ("timestamp", [T0]),
            ("BTC", [Decimal("0.4000")]),
            ("ETH", [Decimal("-0.200")]),
            ("CASH", [Decimal("0.800")]),
        ]
        rng.shuffle(columns)
        if columns[0][0] != "timestamp":
            timestamp_item = next(item for item in columns if item[0] == "timestamp")
            columns.remove(timestamp_item)
            columns.insert(0, timestamp_item)
        variant = StrategyWeights(pl.DataFrame(dict(columns)), assets, metadata={"case": case})
        assert strategy_weights_fingerprint(variant) == expected


def test_c10_semantic_row_changes_never_share_fingerprint() -> None:
    base = StrategyWeights(pl.DataFrame({"timestamp": [T0], "BTC": [0.5], "CASH": [0.5]}), ["BTC"])
    baseline = strategy_weights_fingerprint(base)
    for case in range(1, 101):
        weight = Decimal("0.5") + Decimal(case) / Decimal("1000")
        variant = StrategyWeights(
            pl.DataFrame({"timestamp": [T0], "BTC": [weight], "CASH": [Decimal(1) - weight]}),
            ["BTC"],
        )
        assert strategy_weights_fingerprint(variant) != baseline


@pytest.mark.parametrize(
    ("frame", "assets"),
    [
        (pl.DataFrame({"timestamp": [T0], "BTC": [0.0], "CASH": [1.0]}), ["BTC", "BTC"]),
        (pl.DataFrame({"timestamp": [T0], "CASH": [0.5]}), ["CASH"]),
        (pl.DataFrame({"timestamp": [T0], "": [0.5], "CASH": [0.5]}), [""]),
    ],
    ids=["duplicate-assets", "cash-is-asset", "empty-asset"],
)
def test_c11_malformed_asset_identities_fail_before_engine(frame: pl.DataFrame, assets: list[str]) -> None:
    capture_rejection(
        "C11",
        "public strategy weights identity",
        lambda: strategy_weights_fingerprint(StrategyWeights(frame, assets)),
        (BacktestContractError, ValueError),
        "weights.assets",
    )


def test_c11_signed_zero_normalizes_and_empty_metadata_is_irrelevant() -> None:
    positive = StrategyWeights(
        pl.DataFrame({"timestamp": [T0], "BTC": [Decimal("0")], "CASH": [Decimal("1")]}),
        ["BTC"],
        metadata={"": ""},
    )
    negative = StrategyWeights(
        pl.DataFrame({"timestamp": [T0], "BTC": [Decimal("-0")], "CASH": [Decimal("1.0")]}),
        ["BTC"],
    )
    assert strategy_weights_fingerprint(positive) == strategy_weights_fingerprint(negative)


# --------------------------------------------------------------------------- #
# C12: public schema at scale and long horizon
# --------------------------------------------------------------------------- #


def test_c12_long_horizon_keeps_detailed_ledger_and_frozen_public_schema() -> None:
    calendar = tuple(T0 + timedelta(minutes=index) for index in range(42))
    decisions = tuple(
        _decision(calendar[index * 2], {"BTC": Decimal("0.1") if index % 2 == 0 else Decimal("-0.1")})
        for index in range(20)
    )
    result = _run_public_world(
        SyntheticWorld(
            scenario_id="C12-long-compatibility",
            calendar=calendar,
            instruments=(_instrument("BTC", calendar),),
            decisions=decisions,
            reporting_times=tuple(calendar[index * 2 + 1] for index in range(20)),
            benchmark="BTCUSDT",
        )
    )
    assert result.execution is not None
    assert len(result.execution.targets) == len(result.execution.outcomes) == 20
    assert result.to_dataframe().columns == [
        "equity",
        "benchmark_equity",
        "price_return",
        "funding_return",
        "cost_return",
        "net_return",
        "turnover",
    ]
