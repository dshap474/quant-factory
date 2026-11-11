"""Real-Nautilus integration tests for the prepared execution path.

Purpose: prove same-close IOC fill/outcome/fee/result schema, TWAP incremental
fills, funding-before-fill, sequential multi-target sizing, deterministic
repeat, oversized volume not capped, and legacy execution is None.

USAGE:
    uv run --project packages/platform/backtest pytest \\
      packages/platform/backtest/tests/unit/test_nautilus_execution_runtime.py -v
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Mapping, Sequence

import polars as pl
import pytest
from backtest import (
    BacktestConfig,
    BacktestResult,
    prepare_execution_from_strategy_weights,
    run_backtest_from_strategy_weights,
)
from backtest.engines.nautilus.construction import REQUIRED_NAUTILUS_VERSION
from backtest.errors import BacktestContractError

from execution import (
    DelayedMarketPolicy,
    ExecutionResult,
    ImmediateMarketPolicy,
    InitialAccountState,
    InstrumentKey,
    InstrumentSpec,
    OrderStatus,
    PositionSnapshot,
    ReferencePrice,
    TimeWeightedTakerPolicy,
)
from strategies import ExecutionTiming, StrategyWeights

# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

UTC = timezone.utc
T0 = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
CAL = tuple(T0 + timedelta(minutes=i) for i in range(0, 8))


@pytest.fixture(scope="module")
def _nautilus_ready() -> None:
    pytest.importorskip("nautilus_trader")
    import nautilus_trader

    assert nautilus_trader.__version__ == REQUIRED_NAUTILUS_VERSION


def _key(symbol: str = "BTCUSDT") -> InstrumentKey:
    return InstrumentKey(venue="BINANCE", symbol=symbol)


def _wire(symbol: str = "BTCUSDT") -> str:
    return f"BINANCE:{symbol}"


def _spec(symbol: str = "BTCUSDT") -> InstrumentSpec:
    return InstrumentSpec(
        key=_key(symbol),
        product="perpetual",
        base_currency=symbol.replace("USDT", ""),
        quote_currency="USDT",
        settlement_currency="USDT",
        is_inverse=False,
        multiplier=Decimal("1"),
        price_increment=Decimal("0.01"),
        quantity_increment=Decimal("0.001"),
        min_quantity=Decimal("0.001"),
        max_quantity=Decimal("1000000"),
        min_notional=Decimal("5"),
        max_notional=Decimal("100000000"),
        maker_fee_rate=Decimal("0.0002"),
        taker_fee_rate=Decimal("0.0004"),
    )


def _weights_single(
    *,
    decision: datetime = T0,
    btc: float = 0.5,
    cash: float = 0.5,
) -> StrategyWeights:
    return StrategyWeights(
        weights=pl.DataFrame(
            {
                "timestamp": [decision],
                "BTC": [btc],
                "CASH": [cash],
            }
        ),
        assets=["BTC"],
        execution=ExecutionTiming.next_bar(),
    )


def _bar_rows(
    times: Sequence[datetime],
    *,
    symbol: str = "BTCUSDT",
    closes: Mapping[datetime, float] | None = None,
    volume: float = 1.0,
    event_lag: timedelta = timedelta(0),
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for ts in times:
        close = float(closes[ts]) if closes is not None and ts in closes else 100.0
        rows.append(
            {
                "instrument": _wire(symbol),
                "source_timestamp": ts - event_lag,
                "ts_event": ts - event_lag,
                "ts_init": ts,
                "open": close,
                "high": close + 1.0,
                "low": close - 1.0,
                "close": close,
                "volume": volume,
            }
        )
    return rows


def _prepare_and_run(
    *,
    policy: DelayedMarketPolicy | ImmediateMarketPolicy | TimeWeightedTakerPolicy | None = None,
    closes: Mapping[datetime, float] | None = None,
    volume: float = 1.0,
    funding_rate: str | None = None,
    funding_at: datetime | None = None,
    second_target: tuple[datetime, float, float] | None = None,
    calendar: Sequence[datetime] | None = None,
    reporting: Sequence[datetime] | None = None,
    initial_capital: float = 100_000.0,
    trade_cost_bps: float = 5.0,
    btc_weight: float = 0.5,
    event_lag: timedelta = timedelta(0),
    initial_state: InitialAccountState | None = None,
) -> BacktestResult:
    cal = tuple(calendar) if calendar is not None else CAL
    decision = cal[0]
    earliest = cal[1]
    pol = policy if policy is not None else ImmediateMarketPolicy()

    rows: list[tuple[datetime, dict[str, float]]] = [
        (decision, {"BTC": btc_weight, "CASH": 1.0 - btc_weight}),
    ]
    if second_target is not None:
        d2, w2, _c2 = second_target
        rows.append((d2, {"BTC": w2, "CASH": 1.0 - w2}))

    weights = StrategyWeights(
        weights=pl.DataFrame([{"timestamp": ts, **vals} for ts, vals in rows]),
        assets=["BTC"],
        execution=ExecutionTiming.next_bar(),
    )

    price_map = closes or {ts: 100.0 + i for i, ts in enumerate(cal)}
    bars = pl.DataFrame(_bar_rows(cal, closes=price_map, volume=volume, event_lag=event_lag))
    ref_price = float(price_map.get(decision, 100.0))
    refs = pl.DataFrame(
        {
            "decision_at": [decision],
            "instrument": [_wire()],
            "observed_at": [decision],
            "price": [ref_price],
        }
    )
    if second_target is not None:
        d2, _w2, _c2 = second_target
        refs = pl.concat(
            [
                refs,
                pl.DataFrame(
                    {
                        "decision_at": [d2],
                        "instrument": [_wire()],
                        "observed_at": [d2],
                        "price": [float(price_map.get(d2, 100.0))],
                    }
                ),
            ]
        )

    funding = None
    if funding_rate is not None:
        settled = funding_at if funding_at is not None else earliest
        funding = pl.DataFrame(
            {
                "settlement_id": ["fund-1"],
                "instrument": [_wire()],
                "settled_at": [settled],
                "rate": [float(Decimal(funding_rate))],
                "mark_price": [float(price_map.get(settled, 100.0))],
            }
        )

    report_times = tuple(reporting) if reporting is not None else (earliest, cal[2], cal[4])
    prepared = prepare_execution_from_strategy_weights(
        weights=weights,
        asset_instruments={"BTC": _key()},
        reference_prices=refs,
        bars=bars,
        instrument_specs=[_spec()],
        execution_calendar=cal,
        reporting_times=report_times,
        policy=pol,
        funding_settlements=funding,
        initial_state=initial_state,
    )
    cfg = BacktestConfig(
        initial_capital=initial_capital,
        trade_cost_bps=trade_cost_bps,
        include_funding=True,
        frequency="1m",
        benchmark="BTCUSDT",
    )
    return run_backtest_from_strategy_weights(
        weights=weights,
        data=None,
        config=cfg,
        prepared_execution=prepared,
    )


def _execution(result: BacktestResult) -> ExecutionResult:
    """Return the opt-in ledger while narrowing its public optional type."""
    assert result.execution is not None
    return result.execution


# --------------------------------------------------------------------------- #
# Core path
# --------------------------------------------------------------------------- #


def test_same_close_ioc_fill_outcome_fee_and_result_schema(_nautilus_ready: None) -> None:
    result = _prepare_and_run(volume=1.0, closes={ts: 100.0 for ts in CAL})
    assert result.execution is not None
    ex = _execution(result)
    assert len(ex.fills) == 1
    fill = ex.fills[0]
    # equity 100k * 0.5 / 100 = 500 BTC desired, already rounded.
    assert fill.quantity == Decimal("500.000")
    assert fill.price == Decimal("100.00")
    expected_fee = Decimal("500.000") * Decimal("100.00") * Decimal("0.0004")
    assert fill.fee == expected_fee
    assert fill.fee_currency == "USDT"
    assert len(ex.outcomes) == 1
    assert ex.outcomes[0].status is OrderStatus.FILLED
    assert ex.outcomes[0].unfilled_quantity == 0
    assert len(ex.intents) == 1
    assert {f.fill_id for f in ex.fills} == {f.fill_id for o in ex.outcomes for f in o.fills}
    assert len(ex.shortfalls) == 1
    df = result.to_dataframe()
    assert df.columns == [
        "equity",
        "benchmark_equity",
        "price_return",
        "funding_return",
        "cost_return",
        "net_return",
        "turnover",
    ]
    assert len(result.equity) == 3
    # Fee debited once; equity below initial after fill at flat price.
    assert float(result.equity[0]) < 100_000.0
    assert float(result.equity[0]) == pytest.approx(100_000.0 - float(expected_fee), rel=0, abs=1e-6)


def test_initial_long_exits_without_public_setup_trade(_nautilus_ready: None) -> None:
    state = InitialAccountState(
        as_of=T0,
        cash=Decimal("100000"),
        positions=(PositionSnapshot(_key(), Decimal("1000"), Decimal("100")),),
        marks=(ReferencePrice(_key(), Decimal("100"), T0),),
    )
    result = _prepare_and_run(
        closes={ts: 100.0 for ts in CAL},
        btc_weight=0.0,
        initial_state=state,
        reporting=(T0, CAL[1], CAL[2]),
    )
    execution = _execution(result)

    assert execution.initial_state == state
    assert len(execution.targets) == len(execution.intents) == len(execution.fills) == 1
    assert execution.target_quantities[0].current_quantity == Decimal("1000")
    assert execution.target_quantities[0].delta_quantity == Decimal("-1000")
    assert execution.fills[0].quantity == Decimal("-1000")
    assert execution.fills[0].fee == Decimal("40")
    assert execution.account_path[0].fees == 0
    assert execution.account_path[-1].fees == Decimal("40")
    assert execution.holdings[-1].quantity == 0


@pytest.mark.parametrize(
    ("name", "current_weight", "target_weight"),
    [
        ("flat_to_long", Decimal("0"), Decimal("1")),
        ("flat_to_short", Decimal("0"), Decimal("-1")),
        ("long_add", Decimal("0.5"), Decimal("1")),
        ("short_add", Decimal("-0.5"), Decimal("-1")),
        ("long_reduce", Decimal("1"), Decimal("0.5")),
        ("short_reduce", Decimal("-1"), Decimal("-0.5")),
        ("long_exit", Decimal("1"), Decimal("0")),
        ("short_exit", Decimal("-1"), Decimal("0")),
        ("long_to_short", Decimal("1"), Decimal("-1")),
        ("short_to_long", Decimal("-1"), Decimal("1")),
    ],
)
@pytest.mark.parametrize(
    "policy",
    [
        ImmediateMarketPolicy(),
        DelayedMarketPolicy(timedelta(minutes=5)),
        TimeWeightedTakerPolicy(3, timedelta(minutes=1)),
    ],
    ids=["immediate", "delayed", "twap"],
)
def test_initial_state_transition_oracles(
    _nautilus_ready: None,
    name: str,
    current_weight: Decimal,
    target_weight: Decimal,
    policy: DelayedMarketPolicy | ImmediateMarketPolicy | TimeWeightedTakerPolicy,
) -> None:
    del name
    current_quantity = current_weight * Decimal("1000")
    target_quantity = target_weight * Decimal("1000")
    delta = target_quantity - current_quantity
    state = (
        None
        if current_quantity == 0
        else InitialAccountState(
            as_of=T0,
            cash=Decimal("100000"),
            positions=(PositionSnapshot(_key(), current_quantity, Decimal("100")),),
            marks=(ReferencePrice(_key(), Decimal("100"), T0),),
        )
    )
    result = _prepare_and_run(
        policy=policy,
        closes={timestamp: 100.0 for timestamp in CAL},
        btc_weight=float(target_weight),
        initial_state=state,
        reporting=(T0, CAL[1], CAL[3], CAL[5], CAL[6]),
    )
    execution = _execution(result)
    quantity = execution.target_quantities[0]

    assert execution.initial_state == state
    assert quantity.current_quantity == current_quantity
    assert quantity.desired_quantity == target_quantity
    assert quantity.delta_quantity == delta
    assert sum((fill.quantity for fill in execution.fills), Decimal(0)) == delta
    assert sum((fill.fee for fill in execution.fills), Decimal(0)) == abs(delta) * Decimal("0.04")
    assert execution.holdings[-1].quantity == target_quantity
    assert execution.account_path[-1].realized_pnl == 0
    assert execution.account_path[-1].unrealized_pnl == 0


def test_initial_state_equity_mismatch_fails_before_nautilus(_nautilus_ready: None) -> None:
    state = InitialAccountState(
        as_of=T0,
        cash=Decimal("100000"),
        positions=(PositionSnapshot(_key(), Decimal("1000"), Decimal("100")),),
        marks=(ReferencePrice(_key(), Decimal("100"), T0),),
    )
    with pytest.raises(BacktestContractError, match="initial state equity"):
        _prepare_and_run(
            closes={timestamp: 100.0 for timestamp in CAL},
            initial_state=state,
            initial_capital=99_999,
        )


def test_initial_unrealized_pnl_realizes_only_after_exit(_nautilus_ready: None) -> None:
    state = InitialAccountState(
        as_of=T0,
        cash=Decimal("90000"),
        positions=(PositionSnapshot(_key(), Decimal("1000"), Decimal("90")),),
        marks=(ReferencePrice(_key(), Decimal("100"), T0),),
    )
    closes = {timestamp: 110.0 for timestamp in CAL}
    closes[T0] = 100.0
    result = _prepare_and_run(
        closes=closes,
        btc_weight=0,
        initial_state=state,
        reporting=(T0, CAL[1], CAL[2]),
    )
    execution = _execution(result)

    assert execution.account_path[0].unrealized_pnl == Decimal("10000")
    assert execution.account_path[0].realized_pnl == 0
    assert execution.account_path[-1].unrealized_pnl == 0
    assert execution.account_path[-1].realized_pnl == Decimal("20000")
    assert execution.account_path[-1].equity == Decimal("109956")


def test_funding_uses_initial_position_before_first_exit(_nautilus_ready: None) -> None:
    state = InitialAccountState(
        as_of=T0,
        cash=Decimal("100000"),
        positions=(PositionSnapshot(_key(), Decimal("1000"), Decimal("100")),),
        marks=(ReferencePrice(_key(), Decimal("100"), T0),),
    )
    result = _prepare_and_run(
        closes={timestamp: 100.0 for timestamp in CAL},
        btc_weight=0,
        initial_state=state,
        funding_rate="0.001",
        funding_at=CAL[1],
        reporting=(T0, CAL[1], CAL[2]),
    )
    execution = _execution(result)

    assert execution.account_path[0].funding == 0
    assert execution.account_path[1].funding == Decimal("-100")
    assert execution.account_path[1].fees == Decimal("40")
    assert execution.account_path[1].equity == Decimal("99860")


def test_oversized_volume_not_capped(_nautilus_ready: None) -> None:
    result = _prepare_and_run(volume=1.0, closes={ts: 100.0 for ts in CAL}, btc_weight=0.5)
    fill = _execution(result).fills[0]
    assert abs(fill.quantity) > Decimal("1")
    assert fill.quantity == Decimal("500.000")


def test_execution_uses_completed_close_ts_init_not_source_event_time(
    _nautilus_ready: None,
) -> None:
    result = _prepare_and_run(
        closes={ts: 100.0 for ts in CAL},
        event_lag=timedelta(seconds=30),
    )
    execution = _execution(result)
    assert execution.fills[0].filled_at == CAL[1]
    assert execution.intents[0].scheduled_at == CAL[1]


def test_deterministic_repeat_trace(_nautilus_ready: None) -> None:
    a = _prepare_and_run(closes={ts: 100.0 + (i % 3) for i, ts in enumerate(CAL)})
    b = _prepare_and_run(closes={ts: 100.0 + (i % 3) for i, ts in enumerate(CAL)})
    a_execution = _execution(a)
    b_execution = _execution(b)
    assert [f.fill_id for f in a_execution.fills] == [f.fill_id for f in b_execution.fills]
    assert [float(x) for x in a.equity] == [float(x) for x in b.equity]
    assert [(f.quantity, f.price, f.fee) for f in a_execution.fills] == [
        (f.quantity, f.price, f.fee) for f in b_execution.fills
    ]


def test_funding_applies_to_carried_position_before_same_time_fill(_nautilus_ready: None) -> None:
    # First bar after decision is earliest; open long at cal[1], then at cal[2]
    # apply funding then a second target that reduces. Simpler: one target fills
    # at cal[1]; funding also at cal[1] must apply to pre-fill (flat) position.
    earliest = CAL[1]
    result = _prepare_and_run(
        closes={ts: 100.0 for ts in CAL},
        funding_rate="0.001",
        funding_at=earliest,
        reporting=(earliest, CAL[2]),
    )
    ex = _execution(result)
    assert len(ex.funding_settlements) == 1
    # Flat pre-fill => funding cashflow 0; fee still charged on fill.
    ap0 = ex.account_path[0]
    assert ap0.funding == Decimal("0")
    assert ap0.fees > 0


def test_funding_applies_to_carried_position_before_same_time_close(
    _nautilus_ready: None,
) -> None:
    result = _prepare_and_run(
        closes={ts: 100.0 for ts in CAL},
        funding_rate="0.001",
        funding_at=CAL[3],
        second_target=(CAL[2], 0.0, 1.0),
        reporting=(CAL[1], CAL[3], CAL[4]),
    )
    ex = _execution(result)
    at_second_close = next(point for point in ex.account_path if point.timestamp == CAL[3])
    assert at_second_close.funding == Decimal("-50.0000000")
    assert next(q for q in ex.target_quantities if q.target_id == ex.targets[1].target_id).current_quantity == Decimal(
        "500.000"
    )


def test_twap_incremental_scheduled_fills(_nautilus_ready: None) -> None:
    policy = TimeWeightedTakerPolicy(slice_count=3, interval=timedelta(minutes=1))
    result = _prepare_and_run(
        policy=policy,
        closes={ts: 100.0 for ts in CAL},
        reporting=(CAL[1], CAL[2], CAL[3], CAL[4]),
    )
    ex = _execution(result)
    assert len(ex.intents) == 3
    assert len(ex.fills) == 3
    assert sum((f.quantity for f in ex.fills), Decimal(0)) == Decimal("500.000")
    # Holdings should step up across scheduled closes.
    btc_holdings = [h for h in ex.holdings if h.instrument == _key()]
    by_ts = {h.timestamp: h.quantity for h in btc_holdings}
    assert by_ts[CAL[1]] < by_ts[CAL[2]] < by_ts[CAL[3]]
    assert by_ts[CAL[3]] == Decimal("500.000")


def test_delayed_market_fills_at_decision_relative_close_and_uses_it_as_arrival(
    _nautilus_ready: None,
) -> None:
    closes = {timestamp: 100.0 + index for index, timestamp in enumerate(CAL)}
    result = _prepare_and_run(
        policy=DelayedMarketPolicy(timedelta(minutes=5)),
        closes=closes,
        reporting=(CAL[1], CAL[5], CAL[6]),
    )
    execution = _execution(result)
    shortfall = execution.shortfalls[0]

    assert len(execution.intents) == len(execution.fills) == 1
    assert execution.intents[0].scheduled_at == CAL[5]
    assert execution.fills[0].filled_at == CAL[5]
    assert shortfall.arrival_price == Decimal("105.0")
    assert shortfall.terminal_price == Decimal("105.0")
    assert shortfall.trading == Decimal(0)
    assert shortfall.delay > 0


def test_second_target_sizes_from_post_fill_equity(_nautilus_ready: None) -> None:
    # Target1 at cal[1]: 50% BTC. Target2 uses post-fee equity at cal[3].
    d2 = CAL[2]
    result = _prepare_and_run(
        closes={ts: 100.0 for ts in CAL},
        second_target=(d2, 0.25, 0.75),
        reporting=(CAL[1], CAL[3], CAL[5]),
        calendar=CAL,
    )
    ex = _execution(result)
    assert len(ex.targets) == 2
    assert len(ex.intents) == 2
    # First intent long, second reduces using equity after the first taker fee.
    q1 = next(q for q in ex.target_quantities if q.target_id == ex.targets[0].target_id)
    q2 = next(q for q in ex.target_quantities if q.target_id == ex.targets[1].target_id)
    assert q1.delta_quantity > 0
    assert q2.current_quantity == q1.desired_quantity
    assert q2.desired_quantity == Decimal("249.950")
    assert q2.delta_quantity == Decimal("-250.050")
    assert q2.current_quantity == Decimal("500.000")


def test_reject_include_funding_false(_nautilus_ready: None) -> None:
    weights = _weights_single()
    cal = CAL
    bars = pl.DataFrame(_bar_rows(cal, closes={ts: 100.0 for ts in cal}))
    refs = pl.DataFrame(
        {
            "decision_at": [cal[0]],
            "instrument": [_wire()],
            "observed_at": [cal[0]],
            "price": [100.0],
        }
    )
    prepared = prepare_execution_from_strategy_weights(
        weights=weights,
        asset_instruments={"BTC": _key()},
        reference_prices=refs,
        bars=bars,
        instrument_specs=[_spec()],
        execution_calendar=cal,
        reporting_times=(cal[1], cal[2]),
        policy=ImmediateMarketPolicy(),
    )
    with pytest.raises(BacktestContractError, match="include_funding"):
        run_backtest_from_strategy_weights(
            weights=weights,
            data=None,
            config=BacktestConfig(include_funding=False),
            prepared_execution=prepared,
        )


def test_legacy_execution_is_none(_nautilus_ready: None) -> None:
    data = pl.DataFrame(
        {
            "timestamp": [datetime(2024, 1, 1), datetime(2024, 1, 2)],
            "BTC": [100.0, 105.0],
            "CASH": [1.0, 1.0],
        }
    )
    weights = StrategyWeights(
        weights=pl.DataFrame(
            {
                "timestamp": [datetime(2024, 1, 1), datetime(2024, 1, 2)],
                "BTC": [0.5, 0.5],
                "CASH": [0.5, 0.5],
            }
        ),
        assets=["BTC"],
        execution=ExecutionTiming.same_bar(),
    )
    result = run_backtest_from_strategy_weights(
        weights=weights,
        data=data,
        config=BacktestConfig(include_funding=False),
    )
    assert result.execution is None
    df = result.to_dataframe()
    assert list(df.columns) == [
        "equity",
        "benchmark_equity",
        "price_return",
        "funding_return",
        "cost_return",
        "net_return",
        "turnover",
    ]
