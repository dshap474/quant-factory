"""A8 deterministic state-model and mirrored-sequence stress tests.

Purpose: compare thousands of generated intermediate execution states against
an audit-owned standard-library oracle, not only terminal equity.

USAGE:
    uv run --project packages/platform/backtest pytest \
      packages/platform/backtest/tests/audit/test_a8_state_model.py -v
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from backtest.projection import LinearPerpetualProjection

from execution import (
    Fill,
    FundingSettlement,
    InstrumentKey,
    InstrumentSpec,
    PortfolioTarget,
    ReferencePrice,
    TargetWeight,
    size_target_quantities,
)

from .a8_model import ModelState

# --------------------------------------------------------------------------- #
# Frozen generated-case registry
# --------------------------------------------------------------------------- #

SEED = 7_150_826
SEQUENCE_COUNT = 500
STEPS_PER_SEQUENCE = 50
UTC = timezone.utc
T0 = datetime(2024, 8, 2, tzinfo=UTC)
KEY = InstrumentKey("BINANCE", "BTCUSDT")


def _spec(multiplier: Decimal) -> InstrumentSpec:
    return InstrumentSpec(
        key=KEY,
        product="perpetual",
        base_currency="BTC",
        quote_currency="USDT",
        settlement_currency="USDT",
        is_inverse=False,
        multiplier=multiplier,
        price_increment=Decimal("0.01"),
        quantity_increment=Decimal("0.001"),
        min_quantity=Decimal(0),
        max_quantity=Decimal("1000000000"),
        min_notional=Decimal(0),
        max_notional=Decimal("1000000000000"),
        maker_fee_rate=Decimal(0),
        taker_fee_rate=Decimal("0.0004"),
    )


def _assert_state(projection: LinearPerpetualProjection, model: ModelState, timestamp: datetime) -> None:
    snapshot = projection.snapshot(as_of=timestamp)
    assert projection.signed_quantity(KEY) == model.quantity
    assert projection.average_price(KEY) == model.average_price
    assert projection.realized_pnl() == model.realized
    assert projection.cumulative_fees() == model.fees
    assert projection.cumulative_funding() == model.funding
    assert projection.cash() == model.cash
    assert projection.unrealized_pnl() == model.unrealized()
    assert snapshot.equity == model.equity()


# --------------------------------------------------------------------------- #
# C04-C05: generated state and mirrored economics
# --------------------------------------------------------------------------- #


def test_c04_five_hundred_generated_sequences_match_every_intermediate_state() -> None:
    for sequence in range(SEQUENCE_COUNT):
        rng = random.Random(SEED + sequence)
        multiplier = Decimal(rng.choice((1, 10)))
        spec = _spec(multiplier)
        model = ModelState(cash=Decimal("1000000"), multiplier=multiplier)
        projection = LinearPerpetualProjection(initial_cash=model.cash, instruments={KEY: spec})
        projection.update_marks({KEY: model.mark}, observed_at=T0)

        for step in range(STEPS_PER_SEQUENCE):
            timestamp = T0 + timedelta(seconds=step + 1)
            action = step % 5
            if action == 0:
                desired = Decimal(rng.randint(-20, 20))
                delta = desired - model.quantity
                if delta != 0:
                    price = Decimal(rng.randint(80, 120))
                    fee = abs(delta * price * multiplier) * spec.taker_fee_rate
                    fill = Fill(
                        target_id=f"g{sequence:04d}-t{step:02d}",
                        slice_id=f"g{sequence:04d}-s{step:02d}",
                        instrument=KEY,
                        fill_id=f"g{sequence:04d}-f{step:02d}",
                        quantity=delta,
                        price=price,
                        fee=fee,
                        fee_currency="USDT",
                        filled_at=timestamp,
                    )
                    model.apply_fill(delta, price, fee)
                    projection.apply_fill(fill)
            elif action == 1:
                mark = Decimal(rng.randint(70, 130))
                model.update_mark(mark)
                projection.update_marks({KEY: mark}, observed_at=timestamp)
            elif action == 2:
                rate = Decimal(rng.randint(-10, 10)) / Decimal("10000")
                settlement = FundingSettlement(
                    settlement_id=f"g{sequence:04d}-u{step:02d}",
                    instrument=KEY,
                    settled_at=timestamp,
                    rate=rate,
                    mark_price=model.mark,
                )
                model.apply_funding(rate, model.mark)
                projection.apply_funding(settlement)
            elif action == 3:
                weight = Decimal(rng.randint(-10, 10)) / Decimal(10)
                snapshot = projection.snapshot(as_of=timestamp)
                target = PortfolioTarget(
                    target_id=f"g{sequence:04d}-q{step:02d}",
                    decision_at=timestamp - timedelta(microseconds=1),
                    earliest_execution_at=timestamp,
                    weights=(TargetWeight(KEY, weight),),
                    cash_weight=Decimal(1) - weight,
                    reference_prices=(ReferencePrice(KEY, model.mark, timestamp - timedelta(microseconds=1)),),
                )
                quantity = size_target_quantities(target, snapshot, (spec,))[0]
                assert quantity.desired_quantity == model.desired_quantity(weight, model.mark, Decimal("0.001"))
            else:
                projection.update_marks({KEY: model.mark}, observed_at=timestamp)
            _assert_state(projection, model, timestamp)


def test_c05_five_hundred_long_short_mirrors_have_equal_realized_pnl() -> None:
    for sequence in range(SEQUENCE_COUNT):
        rng = random.Random(SEED + 100_000 + sequence)
        quantity = Decimal(rng.randint(1, 100))
        exit_price = Decimal(rng.randint(50, 150))
        mirrored_exit = Decimal(200) - exit_price
        long = ModelState(cash=Decimal("1000000"), multiplier=Decimal(1))
        short = ModelState(cash=Decimal("1000000"), multiplier=Decimal(1))
        long.apply_fill(quantity, Decimal(100), Decimal(0))
        long.apply_fill(-quantity, exit_price, Decimal(0))
        short.apply_fill(-quantity, Decimal(100), Decimal(0))
        short.apply_fill(quantity, mirrored_exit, Decimal(0))
        assert long.quantity == short.quantity == 0
        assert long.realized == short.realized == quantity * (exit_price - Decimal(100))
