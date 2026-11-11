"""A3 labeled white-box fault-injection scenarios F13-F22.

Purpose: inject impossible or corrupted runtime/accounting states at the
narrowest engine seam and prove each fails before a result can be assembled.

USAGE:
    uv run pytest -q \
      packages/platform/backtest/tests/audit/test_a3_fault_injection.py
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from typing import cast

import pytest
from backtest.engines.nautilus.construction import require_nautilus_version
from backtest.engines.nautilus.runtime import _reconcile_end
from backtest.engines.nautilus.strategy import (
    ExecutionRuntimeState,
    build_execution_strategy,
    final_reconcile,
    terminalize_outcomes,
)
from backtest.errors import BacktestEngineExecutionError, BacktestEngineUnavailableError
from backtest.projection import LinearPerpetualProjection, ProjectionError, replay_reporting

from execution import (
    AccountPoint,
    ExecutionResult,
    Fill,
    FundingSettlement,
    OrderOutcome,
    OrderStatus,
    Shortfall,
    SliceIntent,
)

from .a3_support import CAL, KEY, capture_rejection, valid_spec

# --------------------------------------------------------------------------- #
# Fault builders
# --------------------------------------------------------------------------- #


def _intent(*, quantity: str = "1") -> SliceIntent:
    return SliceIntent("t1", "s1", KEY, Decimal(quantity), CAL[1], CAL[1])


def _fill(
    *,
    fill_id: str = "f1",
    quantity: str = "1",
    fee_currency: str = "USDT",
    instrument=KEY,
    slice_id: str = "s1",
) -> Fill:
    return Fill(
        target_id="t1",
        slice_id=slice_id,
        instrument=instrument,
        fill_id=fill_id,
        quantity=Decimal(quantity),
        price=Decimal("100"),
        fee=Decimal("1"),
        fee_currency=fee_currency,
        filled_at=CAL[1],
    )


def _projection() -> LinearPerpetualProjection:
    return LinearPerpetualProjection(initial_cash=Decimal("100000"), instruments={KEY: valid_spec()})


class _FakeConfig:
    def __init_subclass__(cls, **kwargs) -> None:
        del kwargs


class _FakeStrategy:
    def __init__(self, config) -> None:
        del config
        self.cache = SimpleNamespace(positions_open=lambda: [], positions=lambda: [])


class _Side:
    BUY = "BUY"
    SELL = "SELL"


class _Commission:
    currency = "USDT"

    def __str__(self) -> str:
        return "0 USDT"


def _runtime_strategy(intent: SliceIntent | None = None):
    projection = _projection()
    state = SimpleNamespace(
        client_to_slice={} if intent is None else {"c1": intent},
        id_to_key={"BTC-ID": KEY},
        fills_by_slice={} if intent is None else {intent.slice_id: []},
        projection=projection,
        fills=[],
        expected_keys=(KEY,),
        instrument_ids={KEY: SimpleNamespace(id="BTC-ID")},
    )
    nt = {
        "Strategy": _FakeStrategy,
        "StrategyConfig": _FakeConfig,
        "OrderSide": _Side,
        "TimeInForce": SimpleNamespace(IOC="IOC"),
        "ExecAlgorithmId": lambda value: value,
    }
    state.nt = nt
    return build_execution_strategy(state=cast(ExecutionRuntimeState, state), nt=nt), state


def _event(
    *,
    client_id: str = "c1",
    instrument_id: str = "BTC-ID",
    side: str = _Side.BUY,
    quantity: str = "1",
    timestamp=CAL[1],
):
    return SimpleNamespace(
        client_order_id=client_id,
        instrument_id=instrument_id,
        order_side=side,
        last_qty=quantity,
        last_px="100",
        commission=_Commission(),
        trade_id="trade-1",
        ts_event=int(timestamp.timestamp() * 1_000_000_000),
    )


# --------------------------------------------------------------------------- #
# F13-F16: duplicate, provenance, fill, and fee faults
# --------------------------------------------------------------------------- #


def test_f13_duplicate_fill_and_funding_ids_fail_once_only_projection() -> None:
    projection = _projection()
    fill = _fill()
    projection.apply_fill(fill)
    fill_evidence = capture_rejection(
        "F13-fill",
        "white-box projection event fold",
        lambda: projection.apply_fill(fill),
        ProjectionError,
        "duplicate fill_id",
        white_box=True,
    )
    assert fill_evidence.white_box

    settlement = FundingSettlement("funding-1", KEY, CAL[2], Decimal("0.001"), Decimal("100"))
    projection.apply_funding(settlement)
    capture_rejection(
        "F13-funding",
        "white-box projection event fold",
        lambda: projection.apply_funding(settlement),
        ProjectionError,
        "duplicate settlement_id",
        white_box=True,
    )


def test_f14_unknown_client_instrument_target_and_slice_fail_provenance() -> None:
    strategy, _ = _runtime_strategy()
    capture_rejection(
        "F14-client",
        "white-box Nautilus fill callback",
        lambda: strategy._handle_fill(_event(client_id="unknown")),
        BacktestEngineExecutionError,
        "unknown client_order_id",
        white_box=True,
    )

    strategy, _ = _runtime_strategy(_intent())
    capture_rejection(
        "F14-instrument",
        "white-box Nautilus fill callback",
        lambda: strategy._handle_fill(_event(instrument_id="UNKNOWN")),
        BacktestEngineExecutionError,
        "fill instrument mismatch",
        white_box=True,
    )

    capture_rejection(
        "F14-target",
        "white-box immutable result construction",
        lambda: ExecutionResult(
            targets=(),
            target_quantities=(),
            intents=(_intent(),),
            outcomes=(),
            fills=(),
            holdings=(),
            account_path=(),
            funding_settlements=(),
            shortfalls=(),
        ),
        ValueError,
        "intent references an unknown target",
        white_box=True,
    )

    capture_rejection(
        "F14-slice",
        "white-box terminal outcome construction",
        lambda: OrderOutcome(
            intent=_intent(),
            status=OrderStatus.FILLED,
            fills=(_fill(slice_id="unknown"),),
            terminal_at=CAL[1],
            unfilled_quantity=Decimal("0"),
        ),
        ValueError,
        "fill provenance",
        white_box=True,
    )


@pytest.mark.parametrize(
    ("case", "event", "fragment"),
    [
        pytest.param("side", _event(side=_Side.SELL), "fill side mismatch", id="side"),
        pytest.param("late", _event(timestamp=CAL[2]), "outside IOC window", id="late"),
        pytest.param("zero", _event(quantity="0"), "must be positive", id="zero"),
        pytest.param("negative", _event(quantity="-1"), "must be positive", id="negative"),
        pytest.param("overfill", _event(quantity="2"), "overfill", id="overfill"),
    ],
)
def test_f15_invalid_engine_fill_facts_fail_before_projection(case: str, event, fragment: str) -> None:
    strategy, state = _runtime_strategy(_intent())
    capture_rejection(
        f"F15-{case}",
        "white-box Nautilus fill callback",
        lambda: strategy._handle_fill(event),
        BacktestEngineExecutionError,
        fragment,
        white_box=True,
    )
    assert state.fills == []
    assert state.projection.signed_quantity(KEY) == 0


def test_f16_fee_currency_mismatch_and_double_application_fail() -> None:
    wrong_currency = _projection()
    capture_rejection(
        "F16-currency",
        "white-box projection event fold",
        lambda: wrong_currency.apply_fill(_fill(fee_currency="USD")),
        ProjectionError,
        "fee currency mismatch",
        white_box=True,
    )
    assert wrong_currency.cumulative_fees() == 0

    duplicate = _projection()
    fill = _fill()
    duplicate.apply_fill(fill)
    capture_rejection(
        "F16-double",
        "white-box projection event fold",
        lambda: duplicate.apply_fill(fill),
        ProjectionError,
        "duplicate fill_id",
        white_box=True,
    )
    assert duplicate.cumulative_fees() == Decimal("1")


# --------------------------------------------------------------------------- #
# F17-F20: terminalization, reconciliation, reporting, completion
# --------------------------------------------------------------------------- #


def test_f17_pending_and_nonterminal_iocs_fail_terminalization() -> None:
    intent = _intent()
    pending_state = SimpleNamespace(pending_by_time={CAL[1]: [intent]})
    capture_rejection(
        "F17-pending",
        "white-box terminalization",
        lambda: terminalize_outcomes(cast(ExecutionRuntimeState, pending_state), nt={}),
        BacktestEngineExecutionError,
        "unsubmitted slices remain",
        white_box=True,
    )

    from nautilus_trader.model.enums import OrderStatus as NautilusOrderStatus

    nonterminal_state = SimpleNamespace(
        pending_by_time={},
        intents=[intent],
        submitted_slices={intent.slice_id},
        orders_by_slice={intent.slice_id: SimpleNamespace(status=NautilusOrderStatus.ACCEPTED, ts_last=0)},
        fills_by_slice={intent.slice_id: []},
        outcomes=[],
    )
    capture_rejection(
        "F17-nonterminal",
        "white-box terminalization",
        lambda: terminalize_outcomes(cast(ExecutionRuntimeState, nonterminal_state), nt={}),
        BacktestEngineExecutionError,
        "nonterminal or inconsistent",
        white_box=True,
    )


def test_f18_target_boundary_and_end_position_mismatch_are_fatal() -> None:
    strategy, state = _runtime_strategy(_intent())
    state.projection.update_marks({KEY: Decimal("100")}, observed_at=CAL[1])
    fake_position = SimpleNamespace(instrument_id="BTC-ID", signed_qty=Decimal("1"))
    strategy.cache = SimpleNamespace(
        positions_open=lambda: [fake_position],
        positions=lambda: [fake_position],
    )
    capture_rejection(
        "F18-boundary",
        "white-box target-boundary reconciliation",
        lambda: strategy._reconcile_positions(CAL[1]),
        BacktestEngineExecutionError,
        "position reconcile failed",
        white_box=True,
    )

    engine = SimpleNamespace(cache=strategy.cache)
    capture_rejection(
        "F18-end",
        "white-box end-of-run reconciliation",
        lambda: _reconcile_end(state, engine=engine),
        BacktestEngineExecutionError,
        "end-of-run position reconcile failed",
        white_box=True,
    )


def test_f19_open_position_without_report_mark_is_fatal() -> None:
    projection = _projection()
    capture_rejection(
        "F19",
        "white-box reporting replay",
        lambda: replay_reporting(
            projection,
            marks=(),
            funding=(),
            fills=(_fill(),),
            reporting_times=(CAL[2],),
        ),
        ProjectionError,
        "missing mark for open position",
        white_box=True,
    )


def test_f20_unplanned_target_and_unsubmitted_slice_are_fatal() -> None:
    target = SimpleNamespace(target_id="t1")
    unplanned = SimpleNamespace(
        error=None,
        prepared=SimpleNamespace(targets=(target,)),
        planned_target_ids=set(),
    )
    capture_rejection(
        "F20-target",
        "white-box final reconciliation",
        lambda: final_reconcile(cast(ExecutionRuntimeState, unplanned)),
        BacktestEngineExecutionError,
        "targets never planned",
        white_box=True,
    )

    intent = _intent()
    unsubmitted = SimpleNamespace(
        pending_by_time={},
        intents=[intent],
        submitted_slices=set(),
        orders_by_slice={},
        fills_by_slice={},
        outcomes=[],
    )
    capture_rejection(
        "F20-slice",
        "white-box terminalization",
        lambda: terminalize_outcomes(cast(ExecutionRuntimeState, unsubmitted), nt={}),
        BacktestEngineExecutionError,
        "intent never submitted",
        white_box=True,
    )


# --------------------------------------------------------------------------- #
# F21-F22: immutable identities and runtime version
# --------------------------------------------------------------------------- #


def test_f21_corrupted_shortfall_and_equity_identities_reject() -> None:
    capture_rejection(
        "F21-shortfall",
        "white-box immutable shortfall construction",
        lambda: Shortfall(
            target_id="t1",
            instrument=KEY,
            intended_quantity=Decimal("1"),
            filled_quantity=Decimal("1"),
            decision_price=Decimal("100"),
            arrival_price=Decimal("101"),
            terminal_price=Decimal("102"),
            delay=Decimal("1"),
            trading=Decimal("2"),
            fee=Decimal("0.5"),
            unfilled=Decimal("0"),
            total=Decimal("99"),
        ),
        ValueError,
        "reconcile",
        white_box=True,
    )
    capture_rejection(
        "F21-equity",
        "white-box immutable account construction",
        lambda: AccountPoint(
            timestamp=CAL[1],
            cash=Decimal("100"),
            equity=Decimal("999"),
            realized_pnl=Decimal("0"),
            unrealized_pnl=Decimal("5"),
            fees=Decimal("0"),
            funding=Decimal("0"),
        ),
        ValueError,
        "cash + unrealized_pnl",
        white_box=True,
    )


def test_f22_any_unpinned_nautilus_version_is_rejected() -> None:
    evidence = capture_rejection(
        "F22",
        "white-box runtime dependency gate",
        lambda: require_nautilus_version("1.225.0"),
        BacktestEngineUnavailableError,
        "nautilus_trader==1.224.0 required",
        "1.225.0",
        white_box=True,
    )
    assert evidence.message == "nautilus_trader==1.224.0 required, got '1.225.0'"
