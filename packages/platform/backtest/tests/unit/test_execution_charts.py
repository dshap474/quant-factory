"""Semantic and PNG tests for reusable execution chart reporting.

Purpose: prove exact planned/actual trajectories, fill-side handling, and the
public in-memory rendering surface owned by packages/platform/backtest.

USAGE:
    uv run --project packages/platform/backtest pytest \
      packages/platform/backtest/tests/unit/test_execution_charts.py -q
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import matplotlib
import matplotlib.dates as mdates
import matplotlib.image as mpimg
import polars as pl
import pytest
from backtest import (
    BacktestConfig,
    prepare_execution_from_strategy_weights,
    render_execution_png,
    run_backtest_from_strategy_weights,
)
from backtest.errors import BacktestContractError
from backtest.execution_charts import RawFill as _RawFill
from backtest.execution_charts import assemble_chart_data as _assemble_chart_data
from backtest.execution_charts.rendering import _draw_trajectory_panel
from matplotlib.figure import Figure

from execution import ImmediateMarketPolicy, InstrumentKey, InstrumentSpec
from strategies import ExecutionTiming, StrategyWeights

# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

DECISION = datetime(2025, 1, 2, tzinfo=UTC)
INSTRUMENT = "BINANCE:BTCUSDT"
BTC_KEY = InstrumentKey(venue="BINANCE", symbol="BTCUSDT")


def _btc_spec() -> InstrumentSpec:
    return InstrumentSpec(
        key=BTC_KEY,
        product="perpetual",
        base_currency="BTC",
        quote_currency="USDT",
        settlement_currency="USDT",
        is_inverse=False,
        multiplier=Decimal("1"),
        price_increment=Decimal("0.1"),
        quantity_increment=Decimal("0.001"),
        min_quantity=Decimal("0.001"),
        max_quantity=Decimal("1000"),
        min_notional=Decimal("5"),
        max_notional=Decimal("100000000"),
        maker_fee_rate=Decimal(0),
        taker_fee_rate=Decimal("0.0005"),
    )


def _normalized_bars() -> pl.DataFrame:
    times = [DECISION + timedelta(minutes=index) for index in range(61)]
    sources = [ts - timedelta(minutes=1) for ts in times]
    prices = [100.0 + index * 0.1 for index in range(61)]
    return pl.DataFrame(
        {
            "instrument": [INSTRUMENT] * len(times),
            "source_timestamp": sources,
            "ts_event": sources,
            "ts_init": times,
            "open": prices,
            "high": [price + 0.2 for price in prices],
            "low": [price - 0.2 for price in prices],
            "close": prices,
            "volume": [10_000.0] * len(times),
        }
    )


# --------------------------------------------------------------------------- #
# Exact semantic model
# --------------------------------------------------------------------------- #


def test_trajectory_math_is_exact_for_partial_buy_and_sell() -> None:
    bars = pl.concat(
        [
            _normalized_bars(),
            _normalized_bars().with_columns(pl.lit("BINANCE:ETHUSDT").alias("instrument")),
        ]
    )
    for sign in (Decimal(1), Decimal(-1)):
        data = _assemble_chart_data(
            bars=bars,
            instrument=INSTRUMENT,
            target_id="target-1",
            decision_at=DECISION,
            terminal_at=DECISION + timedelta(minutes=2),
            intended_quantity=sign * Decimal("10"),
            decision_price=Decimal("100"),
            arrival_price=Decimal("101"),
            shortfall_total=Decimal("2"),
            multiplier=Decimal(1),
            intents=(
                (DECISION + timedelta(minutes=1), sign * Decimal("5")),
                (DECISION + timedelta(minutes=2), sign * Decimal("5")),
            ),
            fills=(
                _RawFill(
                    filled_at=DECISION + timedelta(minutes=1),
                    quantity=sign * Decimal("5"),
                    price=Decimal("101"),
                    fee=Decimal("0.3535"),
                ),
            ),
            title="Synthetic",
        )

        assert data.bars.get_column("instrument").unique().to_list() == [INSTRUMENT]
        assert data.planned_notionals == (Decimal(0), Decimal("500"), Decimal("1000"))
        assert data.actual_notionals == (Decimal(0), Decimal("505"), Decimal("505"))
        assert data.actual_times[-1] == DECISION + timedelta(minutes=2)
        assert data.completion_ratio == Decimal("0.5")
        assert data.fill_vwap == Decimal("101")
        assert data.total_fee == Decimal("0.3535")
        assert data.shortfall_bps == Decimal("20")


def test_rejected_execution_has_zero_actual_trajectory() -> None:
    data = _assemble_chart_data(
        bars=_normalized_bars(),
        instrument=INSTRUMENT,
        target_id="target-1",
        decision_at=DECISION,
        terminal_at=DECISION + timedelta(minutes=1),
        intended_quantity=Decimal("10"),
        decision_price=Decimal("100"),
        arrival_price=Decimal("100"),
        shortfall_total=Decimal("1000"),
        multiplier=Decimal(1),
        intents=((DECISION + timedelta(minutes=1), Decimal("10")),),
        fills=(),
        title="Rejected",
    )

    assert data.actual_notionals == (Decimal(0), Decimal(0))
    assert data.actual_times[-1] == DECISION + timedelta(minutes=1)
    assert data.completion_ratio == 0
    assert data.fill_vwap is None
    assert data.shortfall_bps == Decimal("10000")


def test_chart_data_rejects_invalid_or_missing_bars() -> None:
    invalid = _normalized_bars().with_columns((pl.col("low") - 10).alias("high"))
    with pytest.raises(BacktestContractError, match="invalid high"):
        _assemble_chart_data(
            bars=invalid,
            instrument=INSTRUMENT,
            target_id="target-1",
            decision_at=DECISION,
            terminal_at=DECISION + timedelta(minutes=1),
            intended_quantity=Decimal(1),
            decision_price=Decimal("100"),
            arrival_price=Decimal("100"),
            shortfall_total=Decimal(0),
            multiplier=Decimal(1),
            intents=((DECISION + timedelta(minutes=1), Decimal(1)),),
            fills=(),
            title="Invalid",
        )


# --------------------------------------------------------------------------- #
# Public renderer and PNG contract
# --------------------------------------------------------------------------- #


def test_public_renderer_writes_exact_png_and_rejects_ambiguous_selection(tmp_path: Path) -> None:
    bars = _normalized_bars()
    spec = _btc_spec()
    decision = DECISION
    terminal = decision + timedelta(hours=1)
    weights = StrategyWeights(
        pl.DataFrame({"timestamp": [decision], "BTC": [1.0], "CASH": [0.0]}),
        ["BTC"],
        execution=ExecutionTiming.next_bar(),
        metadata={"scenario": "execution_chart_public_renderer"},
    )
    references = pl.DataFrame(
        {
            "decision_at": [decision],
            "instrument": [INSTRUMENT],
            "observed_at": [decision],
            "price": [bars.filter(pl.col("ts_init") == decision).item(0, "close")],
        }
    )
    calendar = tuple(bars.get_column("ts_init").to_list())
    prepared = prepare_execution_from_strategy_weights(
        weights=weights,
        asset_instruments={"BTC": BTC_KEY},
        reference_prices=references,
        bars=bars,
        instrument_specs=(spec,),
        execution_calendar=calendar,
        reporting_times=(decision, terminal),
        policy=ImmediateMarketPolicy(),
    )
    result = run_backtest_from_strategy_weights(
        weights=weights,
        data=None,
        config=BacktestConfig(
            initial_capital=100_000.0,
            frequency="daily",
            benchmark=INSTRUMENT,
            metrics=[],
        ),
        prepared_execution=prepared,
    )
    assert result.execution is not None
    output = tmp_path / "public.png"

    rendered = render_execution_png(
        execution=result.execution,
        bars=bars,
        instrument_spec=spec,
        output=output,
    )

    assert rendered == output.resolve()
    assert output.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert mpimg.imread(output).shape[:2] == (900, 1600)
    with pytest.raises(BacktestContractError, match="exactly one target quantity"):
        render_execution_png(
            execution=result.execution,
            bars=bars,
            instrument_spec=spec,
            output=tmp_path / "missing.png",
            target_id="unknown",
        )


def test_renderer_preserves_backend_and_formats_ticks_as_utc(tmp_path: Path) -> None:
    data = _assemble_chart_data(
        bars=_normalized_bars(),
        instrument=INSTRUMENT,
        target_id="target-1",
        decision_at=DECISION,
        terminal_at=DECISION + timedelta(minutes=1),
        intended_quantity=Decimal("10"),
        decision_price=Decimal("100"),
        arrival_price=Decimal("100"),
        shortfall_total=Decimal(0),
        multiplier=Decimal(1),
        intents=((DECISION + timedelta(minutes=1), Decimal("10")),),
        fills=(),
        title="Backend isolation",
    )
    original_backend = matplotlib.get_backend()
    matplotlib.use("svg")
    try:
        from backtest.execution_charts import render_chart_data

        render_chart_data(data, output=tmp_path / "isolated.png", overwrite=False)
        assert matplotlib.get_backend().lower() == "svg"
    finally:
        matplotlib.use(original_backend)

    with matplotlib.rc_context({"timezone": "US/Pacific"}):
        figure = Figure()
        axis = figure.subplots()
        _draw_trajectory_panel(axis, data)
        formatter = axis.xaxis.get_major_formatter()
        assert formatter(mdates.date2num(DECISION)) == "00:00:00"
        figure.clear()
