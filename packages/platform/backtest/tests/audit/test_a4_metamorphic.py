"""A4 literal metamorphic relations for execution economics.

Purpose: transform known synthetic worlds in ways with known invariant
outcomes and prove the public engine preserves those outcomes.

USAGE:
    uv run pytest -q packages/platform/backtest/tests/audit/test_a4_metamorphic.py
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from backtest.projection import LinearPerpetualProjection

from execution import Fill

from .a1_world import FundingFact, trace_hash
from .a2_support import BTC, CAL, ETH, decision, instrument, prices, world
from .a3_support import KEY, valid_spec
from .a4_support import (
    A4_ORIGIN,
    account_economics,
    core_world,
    instrument_economics,
    public_series,
    relative_event_times,
    run_public_world,
    shift_world,
)

# --------------------------------------------------------------------------- #
# Ordering and event-partition relations
# --------------------------------------------------------------------------- #


def test_a4_reordering_assets_preserves_complete_trace() -> None:
    btc = instrument("BTC", prices("100", "100", "110"), fee_rate="0.001")
    eth = instrument("ETH", prices("50", "50", "45"), fee_rate="0.002")
    first = world(
        "A4-reorder",
        instruments=(btc, eth),
        decisions=(decision(0, {"BTC": "0.4", "ETH": "-0.2"}),),
        reports=(0, 1, 2),
        benchmark="BTCUSDT",
    )
    second = world(
        "A4-reorder",
        instruments=(eth, btc),
        decisions=(decision(0, {"ETH": "-0.2", "BTC": "0.4"}),),
        reports=(0, 1, 2),
        benchmark="BTCUSDT",
    )
    assert trace_hash(run_public_world(first)) == trace_hash(run_public_world(second))


def test_a4_splitting_same_price_fill_preserves_account_but_records_both_fills() -> None:
    single = LinearPerpetualProjection(initial_cash=Decimal("100000"), instruments={KEY: valid_spec()})
    split = LinearPerpetualProjection(initial_cash=Decimal("100000"), instruments={KEY: valid_spec()})
    single.apply_fill(Fill("t1", "s1", KEY, "single", Decimal("1"), Decimal("100"), Decimal("1"), "USDT", CAL[1]))
    split_fills = (
        Fill("t1", "s1", KEY, "split-1", Decimal("0.4"), Decimal("100"), Decimal("0.4"), "USDT", CAL[1]),
        Fill("t1", "s1", KEY, "split-2", Decimal("0.6"), Decimal("100"), Decimal("0.6"), "USDT", CAL[1]),
    )
    for fill in split_fills:
        split.apply_fill(fill)
    for projection in (single, split):
        projection.update_marks({KEY: Decimal("110")}, observed_at=CAL[2])

    assert split.snapshot(CAL[2]) == single.snapshot(CAL[2])
    assert split.signed_quantity(KEY) == single.signed_quantity(KEY) == Decimal("1")
    assert split.average_price(KEY) == single.average_price(KEY) == Decimal("100")
    assert len(split_fills) == 2
    assert {item.fill_id for item in split_fills} == {"split-1", "split-2"}


# --------------------------------------------------------------------------- #
# Time, scale, and symmetry relations
# --------------------------------------------------------------------------- #


def test_a4_constant_timestamp_shift_preserves_values_and_relative_times() -> None:
    base_world = core_world("twap")
    delta = timedelta(days=37, hours=5)
    shifted_world = shift_world(base_world, delta)
    base = run_public_world(base_world)
    shifted = run_public_world(shifted_world)

    assert account_economics(shifted) == account_economics(base)
    assert public_series(shifted) == public_series(base)
    assert relative_event_times(shifted, A4_ORIGIN + delta) == relative_event_times(base, A4_ORIGIN)


def test_a4_price_scale_and_inverse_quantity_preserve_notional_economics() -> None:
    base = world(
        "A4-scale-base",
        instruments=(instrument("BTC", prices("100", "100", "110"), fee_rate="0.001"),),
        decisions=(decision(0, {"BTC": "0.5"}),),
        reports=(0, 1, 2),
        benchmark="BTCUSDT",
    )
    scaled = world(
        "A4-scale-scaled",
        instruments=(instrument("BTC", prices("200", "200", "220"), fee_rate="0.001"),),
        decisions=(decision(0, {"BTC": "0.5"}),),
        reports=(0, 1, 2),
        benchmark="BTCUSDT",
    )
    base_result = run_public_world(base)
    scaled_result = run_public_world(scaled)

    assert account_economics(scaled_result) == account_economics(base_result)
    assert public_series(scaled_result) == public_series(base_result)
    assert base_result.execution is not None and scaled_result.execution is not None
    assert base_result.execution.fills[0].quantity == Decimal("500")
    assert scaled_result.execution.fills[0].quantity == Decimal("250")


def test_a4_mirrored_long_rise_and_short_fall_have_symmetric_pnl_before_fees() -> None:
    long_world = world(
        "A4-mirror-long",
        instruments=(instrument("BTC", prices("100", "100", "110")),),
        decisions=(decision(0, {"BTC": "0.5"}),),
        reports=(0, 1, 2),
        benchmark="BTCUSDT",
    )
    short_world = world(
        "A4-mirror-short",
        instruments=(instrument("BTC", prices("100", "100", "90")),),
        decisions=(decision(0, {"BTC": "-0.5"}),),
        reports=(0, 1, 2),
        benchmark="BTCUSDT",
    )
    long_result = run_public_world(long_world)
    short_result = run_public_world(short_world)

    assert account_economics(long_result)[-1][-3:] == account_economics(short_result)[-1][-3:]
    assert long_result.execution is not None and short_result.execution is not None
    assert long_result.execution.account_path[-1].unrealized_pnl == Decimal("5000")
    assert short_result.execution.account_path[-1].unrealized_pnl == Decimal("5000")


# --------------------------------------------------------------------------- #
# Zero-leg and funding-order relations
# --------------------------------------------------------------------------- #


def test_a4_zero_weight_instrument_does_not_change_existing_leg_economics() -> None:
    base = core_world("immediate")
    augmented = world(
        "A4-zero-leg",
        instruments=(
            instrument("BTC", prices("100", "100", "110"), fee_rate="0.001"),
            instrument("ETH", prices("50", "55", "40"), fee_rate="0.009"),
        ),
        decisions=(decision(0, {"BTC": "0.5", "ETH": "0"}),),
        reports=(0, 1, 2),
        benchmark="BTCUSDT",
    )
    base_result = run_public_world(base)
    augmented_result = run_public_world(augmented)

    assert account_economics(augmented_result) == account_economics(base_result)
    assert public_series(augmented_result) == public_series(base_result)
    assert instrument_economics(augmented_result, BTC) == instrument_economics(base_result, BTC)
    assert augmented_result.execution is not None
    assert not [fill for fill in augmented_result.execution.fills if fill.instrument.symbol == "ETHUSDT"]


def test_a4_funding_row_permutation_preserves_canonical_complete_trace() -> None:
    btc_funding = FundingFact("A4-funding-btc", BTC, CAL[2], Decimal("0.001"), Decimal("110"))
    eth_funding = FundingFact("A4-funding-eth", ETH, CAL[2], Decimal("-0.002"), Decimal("45"))
    instruments = (
        instrument("BTC", prices("100", "100", "110")),
        instrument("ETH", prices("50", "50", "45")),
    )
    decisions = (decision(0, {"BTC": "0.4", "ETH": "0.3"}),)
    first = world(
        "A4-funding-order",
        instruments=instruments,
        decisions=decisions,
        reports=(0, 1, 2),
        funding=(btc_funding, eth_funding),
        benchmark="BTCUSDT",
    )
    second = world(
        "A4-funding-order",
        instruments=instruments,
        decisions=decisions,
        reports=(0, 1, 2),
        funding=(eth_funding, btc_funding),
        benchmark="BTCUSDT",
    )

    assert trace_hash(run_public_world(first)) == trace_hash(run_public_world(second))
