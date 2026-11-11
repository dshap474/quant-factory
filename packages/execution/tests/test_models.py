"""DTO validation for UTC, Decimals, identities, CASH, and outcomes.

Purpose: prove immutable public-contract validation and reconciliation.
USAGE: uv run --project packages/execution pytest packages/execution/tests/test_models.py -v
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import cast

import pytest
from helpers import DECISION, EARLIEST, make_key, make_target

from execution import (
    AccountPoint,
    AccountSnapshot,
    ExecutionResult,
    Fill,
    FundingSettlement,
    InitialAccountState,
    InstrumentKey,
    InstrumentSpec,
    OrderOutcome,
    OrderStatus,
    PortfolioTarget,
    PositionSnapshot,
    ReferencePrice,
    Shortfall,
    SliceIntent,
    TargetWeight,
)

UTC = timezone.utc


# --------------------------------------------------------------------------- #
# Instrument metadata
# --------------------------------------------------------------------------- #


def test_instrument_key_rejects_empty_symbol() -> None:
    with pytest.raises(ValueError, match="symbol"):
        InstrumentKey(venue="EXAMPLE", symbol="")


def test_instrument_spec_rejects_inverse() -> None:
    with pytest.raises(ValueError, match="inverse"):
        InstrumentSpec(
            key=make_key("BTCUSD"),
            product="perpetual",
            base_currency="BTC",
            quote_currency="USDT",
            settlement_currency="USDT",
            is_inverse=True,
            multiplier=Decimal("1"),
            price_increment=Decimal("0.01"),
            quantity_increment=Decimal("0.001"),
            min_quantity=Decimal("0.001"),
            max_quantity=Decimal("1000"),
            min_notional=Decimal("5"),
            max_notional=Decimal("1e9"),
            maker_fee_rate=Decimal("0"),
            taker_fee_rate=Decimal("0"),
        )


def test_instrument_spec_accepts_arbitrary_non_empty_provider_identity() -> None:
    spec = InstrumentSpec(
        key=InstrumentKey(venue="EXAMPLE", symbol="asset.contract"),
        product="custom",
        base_currency="ASSET",
        quote_currency="QUOTE",
        settlement_currency="SETTLEMENT",
        is_inverse=False,
        multiplier=Decimal("2"),
        price_increment=Decimal("0.01"),
        quantity_increment=Decimal("0.001"),
        min_quantity=Decimal("0.001"),
        max_quantity=Decimal("1000"),
        min_notional=Decimal("1"),
        max_notional=Decimal("1000000"),
        maker_fee_rate=Decimal("0"),
        taker_fee_rate=Decimal("0"),
    )
    assert spec.key.venue == "EXAMPLE"
    assert spec.product == "custom"


# --------------------------------------------------------------------------- #
# Portfolio target / CASH residual
# --------------------------------------------------------------------------- #


def test_portfolio_target_requires_utc() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        PortfolioTarget(
            target_id="t1",
            decision_at=datetime(2024, 1, 1),
            earliest_execution_at=datetime(2024, 1, 1, 1),
            weights=(TargetWeight(make_key("BTCUSDT"), Decimal("1")),),
            cash_weight=Decimal("0"),
            reference_prices=(ReferencePrice(make_key("BTCUSDT"), Decimal("1"), datetime(2024, 1, 1)),),
        )


def test_decision_must_precede_earliest_execution() -> None:
    with pytest.raises(ValueError, match="strictly before"):
        make_target(decision_at=EARLIEST, earliest_execution_at=EARLIEST)


def test_cash_residual_must_complete_to_one() -> None:
    with pytest.raises(ValueError, match="cash_weight"):
        make_target(weights=[("BTCUSDT", "0.4"), ("ETHUSDT", "0.4")], cash_weight="0.1")


def test_cash_residual_valid_with_partial_investment() -> None:
    target = make_target(
        weights=[("BTCUSDT", "0.3"), ("ETHUSDT", "0.2")],
        cash_weight="0.5",
        prices={"BTCUSDT": "50000", "ETHUSDT": "3000"},
    )
    assert target.cash_weight == Decimal("0.5")


def test_duplicate_weight_instruments_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        PortfolioTarget(
            target_id="t1",
            decision_at=DECISION,
            earliest_execution_at=EARLIEST,
            weights=(
                TargetWeight(make_key("BTCUSDT"), Decimal("0.5")),
                TargetWeight(make_key("BTCUSDT"), Decimal("0.5")),
            ),
            cash_weight=Decimal("0"),
            reference_prices=(ReferencePrice(make_key("BTCUSDT"), Decimal("50000"), DECISION),),
        )


def test_missing_reference_price_rejected() -> None:
    with pytest.raises(ValueError, match="missing reference"):
        PortfolioTarget(
            target_id="t1",
            decision_at=DECISION,
            earliest_execution_at=EARLIEST,
            weights=(
                TargetWeight(make_key("BTCUSDT"), Decimal("0.5")),
                TargetWeight(make_key("ETHUSDT"), Decimal("0.5")),
            ),
            cash_weight=Decimal("0"),
            reference_prices=(ReferencePrice(make_key("BTCUSDT"), Decimal("50000"), DECISION),),
        )


def test_reference_after_decision_rejected() -> None:
    with pytest.raises(ValueError, match="observed_at"):
        PortfolioTarget(
            target_id="t1",
            decision_at=DECISION,
            earliest_execution_at=EARLIEST,
            weights=(TargetWeight(make_key("BTCUSDT"), Decimal("1")),),
            cash_weight=Decimal("0"),
            reference_prices=(
                ReferencePrice(
                    make_key("BTCUSDT"),
                    Decimal("50000"),
                    DECISION + timedelta(seconds=1),
                ),
            ),
        )


def test_reference_prices_must_share_observation_time() -> None:
    with pytest.raises(ValueError, match="share one observed_at"):
        PortfolioTarget(
            target_id="t1",
            decision_at=DECISION,
            earliest_execution_at=EARLIEST,
            weights=(
                TargetWeight(make_key("BTCUSDT"), Decimal("0.5")),
                TargetWeight(make_key("ETHUSDT"), Decimal("0.5")),
            ),
            cash_weight=Decimal("0"),
            reference_prices=(
                ReferencePrice(make_key("BTCUSDT"), Decimal("50000"), DECISION),
                ReferencePrice(
                    make_key("ETHUSDT"),
                    Decimal("3000"),
                    DECISION - timedelta(seconds=1),
                ),
            ),
        )


def test_non_finite_price_rejected() -> None:
    with pytest.raises(ValueError, match="finite"):
        ReferencePrice(make_key("BTCUSDT"), Decimal("NaN"), DECISION)


def test_float_price_rejected() -> None:
    # cast hides the deliberate runtime type error from the static checker.
    with pytest.raises(TypeError, match="Decimal"):
        ReferencePrice(make_key("BTCUSDT"), cast(Decimal, 50000.0), DECISION)


# --------------------------------------------------------------------------- #
# Outcomes and shortfall conservation
# --------------------------------------------------------------------------- #


def _intent(qty: str = "1") -> SliceIntent:
    return SliceIntent(
        target_id="t1",
        slice_id="t1:EXAMPLE:BTCUSDT:0000",
        instrument=make_key("BTCUSDT"),
        quantity=Decimal(qty),
        scheduled_at=EARLIEST,
        expires_at=EARLIEST,
    )


def test_outcome_conservation_filled() -> None:
    intent = _intent("2")
    fill = Fill(
        target_id="t1",
        slice_id=intent.slice_id,
        instrument=intent.instrument,
        fill_id="f1",
        quantity=Decimal("2"),
        price=Decimal("50000"),
        fee=Decimal("1"),
        fee_currency="USDT",
        filled_at=EARLIEST,
    )
    outcome = OrderOutcome(
        intent=intent,
        status=OrderStatus.FILLED,
        fills=(fill,),
        terminal_at=EARLIEST,
        unfilled_quantity=Decimal("0"),
    )
    assert outcome.status is OrderStatus.FILLED


def test_outcome_conservation_partial() -> None:
    intent = _intent("2")
    fill = Fill(
        target_id="t1",
        slice_id=intent.slice_id,
        instrument=intent.instrument,
        fill_id="f1",
        quantity=Decimal("1.5"),
        price=Decimal("50000"),
        fee=Decimal("1"),
        fee_currency="USDT",
        filled_at=EARLIEST,
    )
    outcome = OrderOutcome(
        intent=intent,
        status=OrderStatus.PARTIALLY_FILLED,
        fills=(fill,),
        terminal_at=EARLIEST,
        unfilled_quantity=Decimal("0.5"),
    )
    assert outcome.unfilled_quantity == Decimal("0.5")


def test_outcome_rejects_quantity_mismatch() -> None:
    intent = _intent("2")
    fill = Fill(
        target_id="t1",
        slice_id=intent.slice_id,
        instrument=intent.instrument,
        fill_id="f1",
        quantity=Decimal("1"),
        price=Decimal("50000"),
        fee=Decimal("1"),
        fee_currency="USDT",
        filled_at=EARLIEST,
    )
    with pytest.raises(ValueError, match="filled \\+ unfilled"):
        OrderOutcome(
            intent=intent,
            status=OrderStatus.PARTIALLY_FILLED,
            fills=(fill,),
            terminal_at=EARLIEST,
            unfilled_quantity=Decimal("0.5"),
        )


def test_outcome_rejects_opposite_direction_fill() -> None:
    intent = _intent("2")
    fill = Fill(
        target_id="t1",
        slice_id=intent.slice_id,
        instrument=intent.instrument,
        fill_id="f1",
        quantity=Decimal("-1"),
        price=Decimal("50000"),
        fee=Decimal("1"),
        fee_currency="USDT",
        filled_at=EARLIEST,
    )
    with pytest.raises(ValueError, match="same sign"):
        OrderOutcome(
            intent=intent,
            status=OrderStatus.PARTIALLY_FILLED,
            fills=(fill,),
            terminal_at=EARLIEST,
            unfilled_quantity=Decimal("3"),
        )


def test_outcome_rejects_terminal_after_expiry() -> None:
    intent = _intent("2")
    with pytest.raises(ValueError, match="inside the intent window"):
        OrderOutcome(
            intent=intent,
            status=OrderStatus.EXPIRED,
            fills=(),
            terminal_at=EARLIEST + timedelta(seconds=1),
            unfilled_quantity=Decimal("2"),
        )


def test_account_point_reconciles_equity() -> None:
    with pytest.raises(ValueError, match=r"cash \+ unrealized_pnl"):
        AccountPoint(
            timestamp=EARLIEST,
            cash=Decimal("100"),
            equity=Decimal("999"),
            realized_pnl=Decimal("0"),
            unrealized_pnl=Decimal("5"),
            fees=Decimal("0"),
            funding=Decimal("0"),
        )


def test_account_snapshot_requires_mark_for_open_position() -> None:
    with pytest.raises(ValueError, match="missing mark"):
        AccountSnapshot(
            as_of=DECISION,
            cash=Decimal("100"),
            equity=Decimal("100"),
            positions=(PositionSnapshot(make_key("BTCUSDT"), Decimal("1"), Decimal("50000")),),
            marks=(),
            cumulative_fees=Decimal("0"),
            cumulative_funding=Decimal("0"),
        )


def test_initial_account_state_requires_exact_nonzero_position_marks() -> None:
    state = InitialAccountState(
        as_of=DECISION,
        cash=Decimal("100000"),
        positions=(PositionSnapshot(make_key("BTCUSDT"), Decimal("1"), Decimal("50000")),),
        marks=(ReferencePrice(make_key("BTCUSDT"), Decimal("50000"), DECISION),),
    )
    assert state.cash == Decimal("100000")

    with pytest.raises(ValueError, match="omit zero"):
        InitialAccountState(
            as_of=DECISION,
            cash=Decimal("100000"),
            positions=(PositionSnapshot(make_key("BTCUSDT"), Decimal("0"), Decimal("0")),),
            marks=(ReferencePrice(make_key("BTCUSDT"), Decimal("50000"), DECISION),),
        )
    with pytest.raises(ValueError, match="cover initial positions exactly"):
        InitialAccountState(
            as_of=DECISION,
            cash=Decimal("100000"),
            positions=(PositionSnapshot(make_key("BTCUSDT"), Decimal("1"), Decimal("50000")),),
            marks=(ReferencePrice(make_key("ETHUSDT"), Decimal("3000"), DECISION),),
        )


def test_execution_result_requires_sized_quantity_for_every_target_instrument() -> None:
    target = make_target(
        weights=[("BTCUSDT", "1")],
        cash_weight="0",
        prices={"BTCUSDT": "50000"},
    )
    with pytest.raises(ValueError, match="cover every target instrument"):
        ExecutionResult(
            targets=(target,),
            target_quantities=(),
            intents=(),
            outcomes=(),
            fills=(),
            holdings=(),
            account_path=(),
            funding_settlements=(),
            shortfalls=(),
        )


def test_shortfall_component_identity() -> None:
    sf = Shortfall(
        target_id="t1",
        instrument=make_key("BTCUSDT"),
        intended_quantity=Decimal("1"),
        filled_quantity=Decimal("1"),
        decision_price=Decimal("100"),
        arrival_price=Decimal("101"),
        terminal_price=Decimal("102"),
        delay=Decimal("1"),
        trading=Decimal("2"),
        fee=Decimal("0.5"),
        unfilled=Decimal("0"),
        total=Decimal("3.5"),
    )
    assert sf.total == Decimal("3.5")


def test_shortfall_rejects_broken_identity() -> None:
    with pytest.raises(ValueError, match="reconcile"):
        Shortfall(
            target_id="t1",
            instrument=make_key("BTCUSDT"),
            intended_quantity=Decimal("1"),
            filled_quantity=Decimal("1"),
            decision_price=Decimal("100"),
            arrival_price=Decimal("101"),
            terminal_price=Decimal("102"),
            delay=Decimal("1"),
            trading=Decimal("2"),
            fee=Decimal("0.5"),
            unfilled=Decimal("0"),
            total=Decimal("9"),
        )


def test_funding_settlement_requires_id_and_utc() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        FundingSettlement(
            settlement_id="s1",
            instrument=make_key("BTCUSDT"),
            settled_at=datetime(2024, 1, 1),
            rate=Decimal("0.0001"),
            mark_price=Decimal("50000"),
        )
