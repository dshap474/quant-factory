"""Unit tests for opt-in StrategyWeights execution preparation.

Purpose: cover atomic translation, calendar timing, reference/bar validation,
policy-window preflight, and legacy connector non-regression through the public
backtest import surface.

USAGE:
    uv run --project packages/platform/backtest pytest \\
      packages/platform/backtest/tests/unit/test_preparation.py -v
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Mapping, Sequence, TypedDict
from zoneinfo import ZoneInfo

import polars as pl
import pytest
from backtest import (
    BacktestConfig,
    PreparedExecutionInput,
    instrument_key_wire,
    materialize_effective_weights,
    prepare_execution_from_strategy_weights,
    run_backtest_from_strategy_weights,
)
from backtest.errors import BacktestContractError
from backtest.preparation import strategy_weights_fingerprint

from execution import (
    DelayedMarketPolicy,
    ImmediateMarketPolicy,
    InitialAccountState,
    InstrumentKey,
    InstrumentSpec,
    PositionSnapshot,
    ReferencePrice,
    TimeWeightedTakerPolicy,
)
from strategies import ExecutionTiming, StrategyWeights

# --------------------------------------------------------------------------- #
# Constants / builders
# --------------------------------------------------------------------------- #

UTC = timezone.utc
T0 = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
CAL = tuple(T0 + timedelta(minutes=i) for i in range(0, 12))


class _PrepareKwargs(TypedDict):
    """Typed keyword packet for the public preparation boundary."""

    weights: StrategyWeights
    asset_instruments: Mapping[str, InstrumentKey]
    reference_prices: pl.DataFrame
    bars: pl.DataFrame
    instrument_specs: Sequence[InstrumentSpec]
    execution_calendar: Sequence[datetime]
    reporting_times: Sequence[datetime]
    policy: DelayedMarketPolicy | ImmediateMarketPolicy | TimeWeightedTakerPolicy
    funding_settlements: pl.DataFrame | None


def _key(symbol: str) -> InstrumentKey:
    return InstrumentKey(venue="BINANCE", symbol=symbol)


def _wire(symbol: str) -> str:
    return instrument_key_wire(_key(symbol))


def _spec(symbol: str) -> InstrumentSpec:
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


def _weights(
    *,
    rows: Sequence[tuple[datetime, Mapping[str, float]]],
    assets: Sequence[str] = ("BTC", "ETH"),
    execution: ExecutionTiming | None = None,
    column_order: Sequence[str] | None = None,
) -> StrategyWeights:
    records: list[dict[str, object]] = []
    for ts, values in rows:
        row: dict[str, object] = {"timestamp": ts}
        row.update(values)
        records.append(row)
    frame = pl.DataFrame(records)
    if column_order is not None:
        frame = frame.select(["timestamp", *column_order])
    return StrategyWeights(
        weights=frame,
        assets=list(assets),
        execution=execution or ExecutionTiming.next_bar(),
    )


def _refs(
    decision_at: datetime,
    prices: Mapping[str, str],
    *,
    observed_at: datetime | None = None,
    instruments: Mapping[str, str] | None = None,
) -> pl.DataFrame:
    obs = observed_at if observed_at is not None else decision_at
    inst = instruments or {asset: _wire(f"{asset}USDT") for asset in prices}
    return pl.DataFrame(
        {
            "decision_at": [decision_at] * len(prices),
            "instrument": [inst[asset] for asset in prices],
            "observed_at": [obs] * len(prices),
            "price": [float(prices[asset]) for asset in prices],
        }
    )


def _bar(
    symbol: str,
    ts: datetime,
    *,
    open_: float = 100.0,
    high: float = 101.0,
    low: float = 99.0,
    close: float = 100.5,
    volume: float = 10.0,
) -> dict[str, object]:
    return {
        "instrument": _wire(symbol),
        "source_timestamp": ts,
        "ts_event": ts,
        "ts_init": ts,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


def _bars_for(
    symbols: Sequence[str],
    times: Sequence[datetime],
) -> pl.DataFrame:
    rows = [_bar(sym, ts) for ts in times for sym in symbols]
    return pl.DataFrame(rows)


def _prepare_kwargs(
    *,
    decision: datetime = T0,
    execution: ExecutionTiming | None = None,
    policy: DelayedMarketPolicy | ImmediateMarketPolicy | TimeWeightedTakerPolicy | None = None,
    assets: Sequence[str] = ("BTC", "ETH"),
    weight_values: Mapping[str, float] | None = None,
    second_row: tuple[datetime, Mapping[str, float]] | None = None,
    column_order: Sequence[str] | None = None,
    calendar: Sequence[datetime] | None = None,
    reporting_times: Sequence[datetime] | None = None,
    bars: pl.DataFrame | None = None,
    reference_prices: pl.DataFrame | None = None,
    instrument_specs: Sequence[InstrumentSpec] | None = None,
    funding_settlements: pl.DataFrame | None = None,
    asset_instruments: Mapping[str, InstrumentKey] | None = None,
) -> _PrepareKwargs:
    values = dict(weight_values or {"BTC": 0.4, "ETH": 0.4, "CASH": 0.2})
    rows: list[tuple[datetime, Mapping[str, float]]] = [(decision, values)]
    if second_row is not None:
        rows.append(second_row)

    weights = _weights(
        rows=rows,
        assets=assets,
        execution=execution,
        column_order=column_order,
    )
    symbols = [f"{asset}USDT" for asset in assets]
    cal = tuple(calendar) if calendar is not None else CAL
    pol = policy if policy is not None else ImmediateMarketPolicy()

    if bars is None:
        # Cover earliest closes for both rows if present.
        needed = list(cal)
        bars = _bars_for(symbols, needed)

    if reference_prices is None:
        frames = [_refs(decision, {asset: "100.5" for asset in assets})]
        if second_row is not None:
            frames.append(_refs(second_row[0], {asset: "100.5" for asset in assets}))
        reference_prices = pl.concat(frames)

    if instrument_specs is None:
        instrument_specs = tuple(_spec(sym) for sym in symbols)

    if asset_instruments is None:
        asset_instruments = {asset: _key(f"{asset}USDT") for asset in assets}

    if reporting_times is None:
        reporting_times = (cal[1], cal[2], cal[3])

    return _PrepareKwargs(
        weights=weights,
        asset_instruments=asset_instruments,
        reference_prices=reference_prices,
        bars=bars,
        instrument_specs=instrument_specs,
        execution_calendar=cal,
        reporting_times=reporting_times,
        policy=pol,
        funding_settlements=funding_settlements,
    )


# --------------------------------------------------------------------------- #
# Happy-path translation
# --------------------------------------------------------------------------- #


def test_atomic_translation_reordered_columns_and_deterministic_instruments() -> None:
    # Column order ETH, CASH, BTC — result must sort instruments by key.
    prepared = prepare_execution_from_strategy_weights(
        **_prepare_kwargs(  # type: ignore[arg-type]
            column_order=["ETH", "CASH", "BTC"],
            weight_values={"BTC": 0.0, "ETH": 0.5, "CASH": 0.5},
        )
    )
    assert isinstance(prepared, PreparedExecutionInput)
    assert len(prepared.targets) == 1
    target = prepared.targets[0]
    assert target.target_id == f"t0000:{T0.strftime('%Y%m%dT%H%M%S.%fZ')}"
    assert [w.instrument.symbol for w in target.weights] == ["BTCUSDT", "ETHUSDT"]
    assert target.weights[0].weight == Decimal("0.0")
    assert target.weights[1].weight == Decimal("0.5")
    assert target.cash_weight == Decimal("0.5")
    assert target.decision_at == T0
    assert target.earliest_execution_at == CAL[1]  # next_bar
    assert prepared.policy == ImmediateMarketPolicy()
    assert prepared.reporting_times == (CAL[1], CAL[2], CAL[3])
    assert prepared.execution_calendar == CAL
    assert [spec.key.symbol for spec in prepared.instrument_specs] == ["BTCUSDT", "ETHUSDT"]


def test_next_bar_and_lag_bars_use_explicit_calendar() -> None:
    next_prepared = prepare_execution_from_strategy_weights(
        **_prepare_kwargs(execution=ExecutionTiming.next_bar())  # type: ignore[arg-type]
    )
    assert next_prepared.targets[0].earliest_execution_at == CAL[1]

    lag_prepared = prepare_execution_from_strategy_weights(
        **_prepare_kwargs(execution=ExecutionTiming.lagged(3))  # type: ignore[arg-type]
    )
    assert lag_prepared.targets[0].earliest_execution_at == CAL[3]


def test_strategy_weights_fingerprint_preserves_canonical_known_answer() -> None:
    weights = StrategyWeights(
        weights=pl.DataFrame(
            {
                "timestamp": [datetime(2026, 7, 21, 12, 0, tzinfo=UTC)],
                "CASH": [Decimal("0.10")],
                "BTC": [Decimal("0.90")],
            }
        ),
        assets=["BTC"],
        execution=ExecutionTiming.next_bar(),
    )

    assert strategy_weights_fingerprint(weights) == "69d8d7d5ce35c0845d012915154f3c17ae6b4f8ec2b98e61a508427f6ce508ba"


# --------------------------------------------------------------------------- #
# Initial account state
# --------------------------------------------------------------------------- #


def _initial_state(
    *,
    as_of: datetime = T0,
    symbol: str = "BTCUSDT",
    quantity: str = "10",
    average_price: str = "100.5",
    mark_price: str = "100.5",
) -> InitialAccountState:
    key = _key(symbol)
    return InitialAccountState(
        as_of=as_of,
        cash=Decimal("100000"),
        positions=(PositionSnapshot(key, Decimal(quantity), Decimal(average_price)),),
        marks=(ReferencePrice(key, Decimal(mark_price), as_of),),
    )


def test_initial_state_is_validated_and_changes_prepared_fingerprint() -> None:
    kwargs = _prepare_kwargs()
    flat = prepare_execution_from_strategy_weights(**kwargs)  # type: ignore[arg-type]
    carried = prepare_execution_from_strategy_weights(  # type: ignore[arg-type]
        **kwargs,
        initial_state=_initial_state(),
    )

    assert flat.initial_state is None
    assert carried.initial_state == _initial_state()
    assert carried.prepared_payload_sha256 != flat.prepared_payload_sha256


@pytest.mark.parametrize(
    ("state", "message"),
    [
        (_initial_state(as_of=T0 - timedelta(minutes=1)), "as_of"),
        (_initial_state(mark_price="100"), "reference"),
        (_initial_state(quantity="10.0005"), "quantity_increment"),
        (_initial_state(symbol="SOLUSDT"), "first target"),
    ],
)
def test_invalid_initial_state_fails_preparation(
    state: InitialAccountState,
    message: str,
) -> None:
    with pytest.raises(BacktestContractError, match=message):
        prepare_execution_from_strategy_weights(  # type: ignore[arg-type]
            **_prepare_kwargs(),
            initial_state=state,
        )


# --------------------------------------------------------------------------- #
# Timing failures
# --------------------------------------------------------------------------- #


def test_same_bar_rejected() -> None:
    with pytest.raises(BacktestContractError, match="SAME_BAR|same_bar"):
        prepare_execution_from_strategy_weights(
            **_prepare_kwargs(execution=ExecutionTiming.same_bar())  # type: ignore[arg-type]
        )


def test_missing_calendar_point_rejected() -> None:
    short_cal = (T0, T0 + timedelta(minutes=1))
    with pytest.raises(BacktestContractError, match="calendar lacks|lag="):
        prepare_execution_from_strategy_weights(
            **_prepare_kwargs(  # type: ignore[arg-type]
                execution=ExecutionTiming.lagged(3),
                calendar=short_cal,
                bars=_bars_for(("BTCUSDT", "ETHUSDT"), short_cal),
                reporting_times=(short_cal[0], short_cal[1]),
            )
        )


@pytest.mark.parametrize(
    "bad_ts",
    [
        datetime(2024, 6, 1, 12, 0, 0),  # naive
        datetime(2024, 6, 1, 12, 0, 0, tzinfo=ZoneInfo("America/New_York")),  # non-UTC
    ],
)
def test_naive_or_non_utc_decision_timestamp_fails(bad_ts: datetime) -> None:
    kwargs = _prepare_kwargs()
    weights = kwargs["weights"]
    assert isinstance(weights, StrategyWeights)
    bad = StrategyWeights(
        weights=weights.weights.with_columns(pl.lit(bad_ts).alias("timestamp")),
        assets=list(weights.assets),
        execution=weights.execution,
    )
    kwargs["weights"] = bad
    # Also fix reference decision_at to match if needed — preparation fails on weights first.
    with pytest.raises(BacktestContractError, match="UTC|timezone"):
        prepare_execution_from_strategy_weights(**kwargs)  # type: ignore[arg-type]


def test_duplicate_decision_timestamps_fail() -> None:
    # StrategyWeights itself rejects duplicate timestamps at construction.
    with pytest.raises(ValueError, match="duplicate timestamps"):
        _weights(
            rows=[
                (T0, {"BTC": 0.5, "ETH": 0.3, "CASH": 0.2}),
                (T0, {"BTC": 0.4, "ETH": 0.4, "CASH": 0.2}),
            ]
        )


def test_non_increasing_decision_timestamps_fail() -> None:
    kwargs = _prepare_kwargs(
        second_row=(T0 - timedelta(minutes=1), {"BTC": 0.4, "ETH": 0.4, "CASH": 0.2}),
    )
    with pytest.raises(BacktestContractError, match="strictly increasing"):
        prepare_execution_from_strategy_weights(**kwargs)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# Reference prices
# --------------------------------------------------------------------------- #


def test_reference_missing_instrument_fails() -> None:
    refs = _refs(T0, {"BTC": "100"})  # missing ETH
    with pytest.raises(BacktestContractError, match="missing instruments|reference"):
        prepare_execution_from_strategy_weights(
            **_prepare_kwargs(reference_prices=refs)  # type: ignore[arg-type]
        )


def test_reference_extra_instrument_fails() -> None:
    refs = pl.concat(
        [
            _refs(T0, {"BTC": "100", "ETH": "100"}),
            pl.DataFrame(
                {
                    "decision_at": [T0],
                    "instrument": [_wire("SOLUSDT")],
                    "observed_at": [T0],
                    "price": [50.0],
                }
            ),
        ]
    )
    with pytest.raises(BacktestContractError, match="unknown instrument|extra"):
        prepare_execution_from_strategy_weights(
            **_prepare_kwargs(reference_prices=refs)  # type: ignore[arg-type]
        )


def test_reference_extra_decision_vector_fails() -> None:
    refs = pl.concat(
        [
            _refs(T0, {"BTC": "100.5", "ETH": "100.5"}),
            _refs(CAL[1], {"BTC": "100.5", "ETH": "100.5"}),
        ]
    )
    with pytest.raises(BacktestContractError, match="extra decision vectors"):
        prepare_execution_from_strategy_weights(
            **_prepare_kwargs(reference_prices=refs)  # type: ignore[arg-type]
        )


def test_reference_duplicate_instrument_fails() -> None:
    refs = pl.concat([_refs(T0, {"BTC": "100", "ETH": "100"}), _refs(T0, {"BTC": "101"})])
    with pytest.raises(BacktestContractError, match="duplicate reference"):
        prepare_execution_from_strategy_weights(
            **_prepare_kwargs(reference_prices=refs)  # type: ignore[arg-type]
        )


def test_reference_mixed_observation_time_fails() -> None:
    refs = pl.DataFrame(
        {
            "decision_at": [T0, T0],
            "instrument": [_wire("BTCUSDT"), _wire("ETHUSDT")],
            "observed_at": [T0, T0 - timedelta(minutes=1)],
            "price": [100.0, 100.0],
        }
    )
    with pytest.raises(BacktestContractError, match="share one observed_at"):
        prepare_execution_from_strategy_weights(
            **_prepare_kwargs(reference_prices=refs)  # type: ignore[arg-type]
        )


def test_reference_future_observation_fails() -> None:
    refs = _refs(T0, {"BTC": "100", "ETH": "100"}, observed_at=T0 + timedelta(minutes=1))
    with pytest.raises(BacktestContractError, match="observed_at must be"):
        prepare_execution_from_strategy_weights(
            **_prepare_kwargs(reference_prices=refs)  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("price", [0.0, -1.0, float("nan"), float("inf")])
def test_reference_invalid_price_fails(price: float) -> None:
    refs = pl.DataFrame(
        {
            "decision_at": [T0, T0],
            "instrument": [_wire("BTCUSDT"), _wire("ETHUSDT")],
            "observed_at": [T0, T0],
            "price": [price, 100.0],
        }
    )
    with pytest.raises(BacktestContractError):
        prepare_execution_from_strategy_weights(
            **_prepare_kwargs(reference_prices=refs)  # type: ignore[arg-type]
        )


# --------------------------------------------------------------------------- #
# Bars
# --------------------------------------------------------------------------- #


def test_bar_schema_and_ohlcv_validation() -> None:
    # Happy path retains required columns.
    prepared = prepare_execution_from_strategy_weights(**_prepare_kwargs())  # type: ignore[arg-type]
    assert set(prepared.bars.columns) >= {
        "instrument",
        "source_timestamp",
        "ts_event",
        "ts_init",
        "open",
        "high",
        "low",
        "close",
        "volume",
    }
    assert prepared.bars.schema["close"].is_numeric()
    assert prepared.bars.schema["volume"].is_numeric()
    assert prepared.bars.schema["ts_init"] == pl.Datetime("ns", "UTC")

    bad_high = _bars_for(("BTCUSDT", "ETHUSDT"), CAL).with_columns(
        pl.when(pl.col("instrument") == _wire("BTCUSDT")).then(pl.lit(50.0)).otherwise(pl.col("high")).alias("high")
    )
    with pytest.raises(BacktestContractError, match="high"):
        prepare_execution_from_strategy_weights(
            **_prepare_kwargs(bars=bad_high)  # type: ignore[arg-type]
        )

    string_close = _bars_for(("BTCUSDT", "ETHUSDT"), CAL).with_columns(pl.col("close").cast(pl.String))
    with pytest.raises(BacktestContractError, match="non-numeric dtypes"):
        prepare_execution_from_strategy_weights(
            **_prepare_kwargs(bars=string_close)  # type: ignore[arg-type]
        )


def test_reference_must_match_completed_normalized_bar_close() -> None:
    mismatched = _refs(T0, {"BTC": "100.0", "ETH": "100.5"})
    with pytest.raises(BacktestContractError, match="must equal completed bar close"):
        prepare_execution_from_strategy_weights(
            **_prepare_kwargs(reference_prices=mismatched)  # type: ignore[arg-type]
        )

    no_decision_bars = _bars_for(("BTCUSDT", "ETHUSDT"), CAL[1:])
    with pytest.raises(BacktestContractError, match="completed normalized bar close"):
        prepare_execution_from_strategy_weights(
            **_prepare_kwargs(bars=no_decision_bars)  # type: ignore[arg-type]
        )


def test_bar_ts_event_after_ts_init_fails() -> None:
    rows = _bars_for(("BTCUSDT", "ETHUSDT"), CAL)
    rows = rows.with_columns(
        pl.when(pl.col("instrument") == _wire("BTCUSDT"))
        .then(pl.col("ts_init") + timedelta(minutes=1))
        .otherwise(pl.col("ts_event"))
        .alias("ts_event")
    )
    with pytest.raises(BacktestContractError, match="ts_event"):
        prepare_execution_from_strategy_weights(
            **_prepare_kwargs(bars=rows)  # type: ignore[arg-type]
        )


def test_bar_duplicate_instrument_ts_init_fails() -> None:
    bars = pl.concat(
        [
            _bars_for(("BTCUSDT", "ETHUSDT"), CAL),
            pl.DataFrame([_bar("BTCUSDT", CAL[1])]),
        ]
    )
    with pytest.raises(BacktestContractError, match="unique"):
        prepare_execution_from_strategy_weights(
            **_prepare_kwargs(bars=bars)  # type: ignore[arg-type]
        )


# --------------------------------------------------------------------------- #
# Policy-window preflight
# --------------------------------------------------------------------------- #


def test_missing_leg_at_one_twap_close_rejects_whole_call() -> None:
    policy = TimeWeightedTakerPolicy(slice_count=3, interval=timedelta(minutes=1))
    # Earliest is CAL[1]; schedule CAL[1], CAL[2], CAL[3]. Drop ETH at CAL[2].
    bars = _bars_for(("BTCUSDT", "ETHUSDT"), CAL).filter(
        ~((pl.col("instrument") == _wire("ETHUSDT")) & (pl.col("ts_init") == CAL[2]))
    )
    with pytest.raises(BacktestContractError, match="missing bar"):
        prepare_execution_from_strategy_weights(
            **_prepare_kwargs(policy=policy, bars=bars)  # type: ignore[arg-type]
        )


def test_twap_off_calendar_scheduled_time_fails() -> None:
    # Interval that lands off calendar: 90 seconds not on minute grid.
    policy = TimeWeightedTakerPolicy(slice_count=2, interval=timedelta(seconds=90))
    with pytest.raises(BacktestContractError, match="not an exact execution-calendar close"):
        prepare_execution_from_strategy_weights(
            **_prepare_kwargs(policy=policy)  # type: ignore[arg-type]
        )


def test_delayed_policy_preflight_and_fingerprint_use_decision_relative_close() -> None:
    delayed = DelayedMarketPolicy(timedelta(minutes=5))
    prepared = prepare_execution_from_strategy_weights(
        **_prepare_kwargs(policy=delayed)  # type: ignore[arg-type]
    )
    immediate = prepare_execution_from_strategy_weights(
        **_prepare_kwargs(policy=ImmediateMarketPolicy())  # type: ignore[arg-type]
    )

    assert prepared.policy == delayed
    assert delayed.schedule_times(T0, CAL[1]) == (CAL[5],)
    assert prepared.prepared_payload_sha256 != immediate.prepared_payload_sha256

    bars = _bars_for(("BTCUSDT", "ETHUSDT"), CAL).filter(pl.col("ts_init") != CAL[5])
    with pytest.raises(BacktestContractError, match="missing bar"):
        prepare_execution_from_strategy_weights(
            **_prepare_kwargs(policy=delayed, bars=bars)  # type: ignore[arg-type]
        )


def test_overlapping_target_windows_fail() -> None:
    # Immediate targets with decisions one minute apart: earliest of second equals
    # last close of first when both use next_bar on the same calendar.
    # t0 decision -> earliest CAL[1]; t1=CAL[1] decision -> earliest CAL[2] OK for immediate.
    # Use TWAP slice_count=3 so first window ends at CAL[3], second starts at CAL[2].
    policy = TimeWeightedTakerPolicy(slice_count=3, interval=timedelta(minutes=1))
    second_decision = CAL[1]
    with pytest.raises(BacktestContractError, match="overlapping target windows"):
        prepare_execution_from_strategy_weights(
            **_prepare_kwargs(  # type: ignore[arg-type]
                policy=policy,
                second_row=(
                    second_decision,
                    {"BTC": 0.3, "ETH": 0.3, "CASH": 0.4},
                ),
            )
        )


# --------------------------------------------------------------------------- #
# Instrument specs
# --------------------------------------------------------------------------- #


def test_instrument_specs_missing_extra_invalid() -> None:
    with pytest.raises(BacktestContractError, match="missing instruments"):
        prepare_execution_from_strategy_weights(
            **_prepare_kwargs(instrument_specs=(_spec("BTCUSDT"),))  # type: ignore[arg-type]
        )

    with pytest.raises(BacktestContractError, match="extra instruments"):
        prepare_execution_from_strategy_weights(
            **_prepare_kwargs(  # type: ignore[arg-type]
                instrument_specs=(_spec("BTCUSDT"), _spec("ETHUSDT"), _spec("SOLUSDT")),
            )
        )


# --------------------------------------------------------------------------- #
# Funding and reporting
# --------------------------------------------------------------------------- #


def test_funding_duplicates_and_invalid_rows_fail() -> None:
    good = pl.DataFrame(
        {
            "settlement_id": ["f1"],
            "instrument": [_wire("BTCUSDT")],
            "settled_at": [CAL[2]],
            "rate": [0.0001],
            "mark_price": [100.0],
        }
    )
    prepared = prepare_execution_from_strategy_weights(
        **_prepare_kwargs(funding_settlements=good)  # type: ignore[arg-type]
    )
    assert len(prepared.funding_settlements) == 1
    assert prepared.funding_settlements[0].settlement_id == "f1"

    dup_id = pl.DataFrame(
        {
            "settlement_id": ["f1", "f1"],
            "instrument": [_wire("BTCUSDT"), _wire("ETHUSDT")],
            "settled_at": [CAL[2], CAL[3]],
            "rate": [0.0001, 0.0002],
            "mark_price": [100.0, 100.0],
        }
    )
    with pytest.raises(BacktestContractError, match="duplicate funding settlement_id"):
        prepare_execution_from_strategy_weights(
            **_prepare_kwargs(funding_settlements=dup_id)  # type: ignore[arg-type]
        )

    dup_pair = pl.DataFrame(
        {
            "settlement_id": ["f1", "f2"],
            "instrument": [_wire("BTCUSDT"), _wire("BTCUSDT")],
            "settled_at": [CAL[2], CAL[2]],
            "rate": [0.0001, 0.0002],
            "mark_price": [100.0, 100.0],
        }
    )
    with pytest.raises(BacktestContractError, match="duplicate funding \\(instrument"):
        prepare_execution_from_strategy_weights(
            **_prepare_kwargs(funding_settlements=dup_pair)  # type: ignore[arg-type]
        )

    bad_mark = pl.DataFrame(
        {
            "settlement_id": ["f1"],
            "instrument": [_wire("BTCUSDT")],
            "settled_at": [CAL[2]],
            "rate": [0.0001],
            "mark_price": [0.0],
        }
    )
    with pytest.raises(BacktestContractError, match="mark_price"):
        prepare_execution_from_strategy_weights(
            **_prepare_kwargs(funding_settlements=bad_mark)  # type: ignore[arg-type]
        )


def test_empty_funding_frame_still_requires_normalized_schema() -> None:
    with pytest.raises(BacktestContractError, match="missing required columns"):
        prepare_execution_from_strategy_weights(
            **_prepare_kwargs(funding_settlements=pl.DataFrame())  # type: ignore[arg-type]
        )


def test_reporting_times_required_and_strictly_increasing() -> None:
    with pytest.raises(BacktestContractError, match="reporting_times must be non-empty"):
        prepare_execution_from_strategy_weights(
            **_prepare_kwargs(reporting_times=())  # type: ignore[arg-type]
        )

    with pytest.raises(BacktestContractError, match="strictly increasing"):
        prepare_execution_from_strategy_weights(
            **_prepare_kwargs(reporting_times=(CAL[2], CAL[1]))  # type: ignore[arg-type]
        )


# --------------------------------------------------------------------------- #
# Legacy connector unchanged
# --------------------------------------------------------------------------- #


def test_legacy_connector_behavior_unchanged() -> None:
    data = pl.DataFrame(
        {
            "timestamp": [
                datetime(2024, 1, 1),
                datetime(2024, 1, 1),
                datetime(2024, 1, 2),
                datetime(2024, 1, 2),
            ],
            "asset": ["BTC", "ETH", "BTC", "ETH"],
            "close": [100.0, 50.0, 105.0, 51.0],
        }
    )
    weights = StrategyWeights(
        weights=pl.DataFrame(
            {
                "timestamp": [datetime(2024, 1, 1), datetime(2024, 1, 2)],
                "BTC": [0.4, 0.5],
                "ETH": [0.4, 0.3],
                "CASH": [0.2, 0.2],
            }
        ),
        assets=["BTC", "ETH"],
        execution=ExecutionTiming.same_bar(),
    )
    result = run_backtest_from_strategy_weights(
        weights=weights,
        data=data,
        config=BacktestConfig(include_funding=False),
    )
    assert len(result.equity) == 2
    assert result.engine_used == "nautilus"

    prices = pl.DataFrame(
        {
            "timestamp": [
                datetime(2024, 1, 1),
                datetime(2024, 1, 2),
                datetime(2024, 1, 3),
                datetime(2024, 1, 4),
            ],
            "BTC": [100.0, 101.0, 102.0, 103.0],
            "CASH": [1.0, 1.0, 1.0, 1.0],
        }
    )
    decision_weights = StrategyWeights(
        weights=pl.DataFrame(
            {
                "timestamp": [datetime(2024, 1, 1), datetime(2024, 1, 3)],
                "BTC": [0.2, 0.4],
                "CASH": [0.8, 0.6],
            }
        ),
        assets=["BTC"],
    )
    effective = materialize_effective_weights(weights=decision_weights, prices=prices)
    assert effective.weights["BTC"].to_list() == [0.2, 0.2, 0.4]
