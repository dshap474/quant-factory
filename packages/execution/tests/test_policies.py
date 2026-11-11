"""Immediate and time-weighted policy slice and overlap tests.

Purpose: prove deterministic signed lot conservation and timing bounds.
USAGE: uv run --project packages/execution pytest packages/execution/tests/test_policies.py -v
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from helpers import DECISION, EARLIEST, make_account, make_key, make_spec, make_target

from execution import (
    DelayedMarketPolicy,
    ImmediateMarketPolicy,
    TargetQuantity,
    TimeWeightedTakerPolicy,
    size_target_quantities,
    validate_non_overlapping_windows,
)

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _quantities_for(
    weights: list[tuple[str, str]],
    *,
    cash: str,
    prices: dict[str, str],
    positions: list[tuple[str, str, str]] | None = None,
    qty_increment: str = "0.001",
    target_id: str = "t1",
    earliest=EARLIEST,
) -> tuple[TargetQuantity, ...]:
    target = make_target(
        target_id=target_id,
        weights=weights,
        cash_weight=cash,
        prices=prices,
        earliest_execution_at=earliest,
    )
    specs = tuple(make_spec(sym, quantity_increment=qty_increment) for sym, _ in weights)
    account = make_account(positions=positions)
    return size_target_quantities(target, account, specs)


# --------------------------------------------------------------------------- #
# Immediate policy
# --------------------------------------------------------------------------- #


def test_immediate_one_slice_per_nonzero_delta() -> None:
    quantities = _quantities_for(
        [("BTCUSDT", "0.5"), ("ETHUSDT", "0.5")],
        cash="0",
        prices={"BTCUSDT": "50000", "ETHUSDT": "3000"},
    )
    intents = ImmediateMarketPolicy().plan(quantities)
    assert len(intents) == 2
    for intent in intents:
        assert intent.scheduled_at == EARLIEST
        assert intent.expires_at == EARLIEST
        assert intent.quantity != 0


def test_immediate_omits_zero_delta() -> None:
    quantities = _quantities_for(
        [("BTCUSDT", "0.5")],
        cash="0.5",
        prices={"BTCUSDT": "50000"},
        positions=[("BTCUSDT", "1.0", "50000")],
    )
    assert quantities[0].delta_quantity == 0
    assert ImmediateMarketPolicy().plan(quantities) == ()


def test_immediate_signed_quantities_long_and_short() -> None:
    quantities = _quantities_for(
        [("BTCUSDT", "0.5"), ("ETHUSDT", "-0.25")],
        cash="0.75",
        prices={"BTCUSDT": "50000", "ETHUSDT": "3000"},
    )
    intents = {i.instrument.symbol: i for i in ImmediateMarketPolicy().plan(quantities)}
    assert intents["BTCUSDT"].quantity > 0
    assert intents["ETHUSDT"].quantity < 0


# --------------------------------------------------------------------------- #
# Delayed policy
# --------------------------------------------------------------------------- #


def test_delayed_market_uses_decision_relative_close_and_full_delta() -> None:
    quantities = _quantities_for(
        [("BTCUSDT", "0.5"), ("ETHUSDT", "-0.25")],
        cash="0.75",
        prices={"BTCUSDT": "50000", "ETHUSDT": "3000"},
    )
    policy = DelayedMarketPolicy(timedelta(minutes=5))
    intents = policy.plan(quantities)

    assert len(intents) == 2
    assert {intent.scheduled_at for intent in intents} == {DECISION + timedelta(minutes=5)}
    assert [intent.quantity for intent in intents] == [quantity.delta_quantity for quantity in quantities]
    assert all(intent.expires_at == intent.scheduled_at for intent in intents)


def test_delayed_market_omits_zero_delta_and_rejects_invalid_timing() -> None:
    quantities = _quantities_for(
        [("BTCUSDT", "0.5")],
        cash="0.5",
        prices={"BTCUSDT": "50000"},
        positions=[("BTCUSDT", "1.0", "50000")],
    )
    assert DelayedMarketPolicy(timedelta(minutes=5)).plan(quantities) == ()
    with pytest.raises(ValueError, match="delay must be positive"):
        DelayedMarketPolicy(timedelta(0))
    with pytest.raises(ValueError, match="earliest_execution_at <= scheduled_at"):
        DelayedMarketPolicy(timedelta(seconds=30)).plan(
            _quantities_for(
                [("BTCUSDT", "0.5")],
                cash="0.5",
                prices={"BTCUSDT": "50000"},
            )
        )


# --------------------------------------------------------------------------- #
# Time-weighted policy
# --------------------------------------------------------------------------- #


def test_twap_equal_slices_and_conservation() -> None:
    # delta BTC = 1.000 with increment 0.001 -> 1000 units; 3 slices -> 334, 333, 333
    quantities = _quantities_for(
        [("BTCUSDT", "0.5")],
        cash="0.5",
        prices={"BTCUSDT": "50000"},
        qty_increment="0.001",
    )
    policy = TimeWeightedTakerPolicy(slice_count=3, interval=timedelta(minutes=1))
    intents = policy.plan(quantities)
    assert len(intents) == 3
    assert [i.quantity for i in intents] == [
        Decimal("0.334"),
        Decimal("0.333"),
        Decimal("0.333"),
    ]
    assert sum((i.quantity for i in intents), Decimal(0)) == quantities[0].delta_quantity
    assert intents[0].scheduled_at == EARLIEST
    assert intents[1].scheduled_at == EARLIEST + timedelta(minutes=1)
    assert intents[2].scheduled_at == EARLIEST + timedelta(minutes=2)
    assert all(i.expires_at == i.scheduled_at for i in intents)


def test_twap_non_divisible_lots_earliest_remainder() -> None:
    # desired notional uses qty increment 1: equity 100000, weight 0.5, price 10000 -> 5 units
    quantities = _quantities_for(
        [("BTCUSDT", "0.5")],
        cash="0.5",
        prices={"BTCUSDT": "10000"},
        qty_increment="1",
    )
    assert quantities[0].delta_quantity == Decimal("5")
    intents = TimeWeightedTakerPolicy(3, timedelta(minutes=1)).plan(quantities)
    assert [i.quantity for i in intents] == [Decimal("2"), Decimal("2"), Decimal("1")]
    assert sum((i.quantity for i in intents), Decimal(0)) == Decimal("5")


def test_twap_short_signed_conservation() -> None:
    quantities = _quantities_for(
        [("BTCUSDT", "-0.5")],
        cash="1.5",
        prices={"BTCUSDT": "10000"},
        qty_increment="1",
    )
    intents = TimeWeightedTakerPolicy(3, timedelta(minutes=1)).plan(quantities)
    assert [i.quantity for i in intents] == [Decimal("-2"), Decimal("-2"), Decimal("-1")]
    assert sum((i.quantity for i in intents), Decimal(0)) == Decimal("-5")


def test_twap_omits_zero_only_parts_when_units_less_than_slices() -> None:
    # 2 units across 3 slices -> slices of 1, 1, and omitted zero
    quantities = _quantities_for(
        [("BTCUSDT", "0.2")],
        cash="0.8",
        prices={"BTCUSDT": "10000"},
        qty_increment="1",
    )
    assert quantities[0].delta_quantity == Decimal("2")
    intents = TimeWeightedTakerPolicy(3, timedelta(minutes=1)).plan(quantities)
    assert [i.quantity for i in intents] == [Decimal("1"), Decimal("1")]
    assert sum((i.quantity for i in intents), Decimal(0)) == Decimal("2")


def test_twap_rejects_invalid_config() -> None:
    with pytest.raises(ValueError, match="slice_count"):
        TimeWeightedTakerPolicy(0, timedelta(minutes=1))
    with pytest.raises(ValueError, match="interval"):
        TimeWeightedTakerPolicy(2, timedelta(0))


def test_policy_schedule_times_share_the_planning_clock() -> None:
    immediate = ImmediateMarketPolicy()
    delayed = DelayedMarketPolicy(timedelta(minutes=5))
    twap = TimeWeightedTakerPolicy(3, timedelta(minutes=1))

    assert immediate.schedule_times(DECISION, EARLIEST) == (EARLIEST,)
    assert delayed.schedule_times(DECISION, EARLIEST) == (DECISION + timedelta(minutes=5),)
    assert twap.schedule_times(DECISION, EARLIEST) == (
        EARLIEST,
        EARLIEST + timedelta(minutes=1),
        EARLIEST + timedelta(minutes=2),
    )


# --------------------------------------------------------------------------- #
# Overlap
# --------------------------------------------------------------------------- #


def test_overlapping_target_windows_rejected() -> None:
    q1 = _quantities_for(
        [("BTCUSDT", "0.5")],
        cash="0.5",
        prices={"BTCUSDT": "50000"},
        target_id="t1",
        earliest=EARLIEST,
    )
    q2 = _quantities_for(
        [("BTCUSDT", "0.6")],
        cash="0.4",
        prices={"BTCUSDT": "50000"},
        target_id="t2",
        earliest=EARLIEST + timedelta(minutes=1),
    )
    policy = TimeWeightedTakerPolicy(3, timedelta(minutes=1))
    intents = policy.plan(q1) + policy.plan(q2)
    # t1 window: t, t+1, t+2; t2 starts at t+1 -> overlap
    with pytest.raises(ValueError, match="overlapping"):
        validate_non_overlapping_windows(intents)


def test_non_overlapping_windows_accepted() -> None:
    q1 = _quantities_for(
        [("BTCUSDT", "0.5")],
        cash="0.5",
        prices={"BTCUSDT": "50000"},
        target_id="t1",
        earliest=EARLIEST,
    )
    q2 = _quantities_for(
        [("BTCUSDT", "0.6")],
        cash="0.4",
        prices={"BTCUSDT": "50000"},
        target_id="t2",
        earliest=EARLIEST + timedelta(minutes=5),
    )
    policy = TimeWeightedTakerPolicy(3, timedelta(minutes=1))
    intents = policy.plan(q1) + policy.plan(q2)
    validate_non_overlapping_windows(intents)


def test_different_instruments_may_overlap_in_time() -> None:
    q_btc = _quantities_for(
        [("BTCUSDT", "0.5")],
        cash="0.5",
        prices={"BTCUSDT": "50000"},
        target_id="t1",
    )
    q_eth = _quantities_for(
        [("ETHUSDT", "0.5")],
        cash="0.5",
        prices={"ETHUSDT": "3000"},
        target_id="t2",
    )
    intents = ImmediateMarketPolicy().plan(q_btc) + ImmediateMarketPolicy().plan(q_eth)
    validate_non_overlapping_windows(intents)


def test_manual_target_quantity_timing_bound() -> None:
    qty = TargetQuantity(
        target_id="t1",
        instrument=make_key("BTCUSDT"),
        current_quantity=Decimal("0"),
        desired_quantity=Decimal("1"),
        delta_quantity=Decimal("1"),
        reference_price=Decimal("50000"),
        decision_at=DECISION,
        earliest_execution_at=EARLIEST,
        quantity_increment=Decimal("0.001"),
    )
    intents = ImmediateMarketPolicy().plan((qty,))
    assert intents[0].scheduled_at == EARLIEST


def test_policy_rejects_mixed_target_provenance() -> None:
    first = _quantities_for(
        [("BTCUSDT", "0.5")],
        cash="0.5",
        prices={"BTCUSDT": "50000"},
        target_id="t1",
    )[0]
    second = _quantities_for(
        [("ETHUSDT", "0.5")],
        cash="0.5",
        prices={"ETHUSDT": "3000"},
        target_id="t2",
    )[0]
    with pytest.raises(ValueError, match="share target and timing provenance"):
        ImmediateMarketPolicy().plan((first, second))
