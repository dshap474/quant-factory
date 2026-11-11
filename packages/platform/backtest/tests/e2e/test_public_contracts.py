"""Hermetic synthetic tests for the backtest package's public boundaries.

Purpose: verify the ordinary Nautilus path, CLI process contract, strategy-data
connector, and terminal ledger semantics with small independent fixtures.

USAGE:
    uv run pytest packages/platform/backtest/tests/e2e/test_public_contracts.py -q
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import numpy as np
import polars as pl
import pytest
from backtest import (
    BacktestConfig,
    prepare_resting_limit_execution,
    run_backtest,
    run_backtest_from_strategy_weights,
    run_resting_limit_backtest,
)
from backtest.errors import BacktestContractError
from polars.testing import assert_frame_equal

from execution import (
    InstrumentKey,
    InstrumentSpec,
    OrderStatus,
    RestingLimitExecutionResult,
    RestingLimitOrder,
    RestingLimitPlan,
)
from strategies import ExecutionTiming, StrategyWeights

# --------------------------------------------------------------------------- #
# Synthetic fixtures
# --------------------------------------------------------------------------- #


def _timestamps(rows: int) -> list[datetime]:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    return [start + timedelta(days=offset) for offset in range(rows)]


def _frame(timestamps: list[datetime], **columns: list[float]) -> pl.DataFrame:
    return pl.DataFrame({"timestamp": timestamps, **columns})


def _ordinary_all_terms_fixture() -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    timestamps = _timestamps(4)
    prices = _frame(
        timestamps,
        BTC=[100.0, 100.0, 110.0, 121.0],
        CASH=[1.0, 1.0, 1.0, 1.0],
    )
    weights = _frame(
        timestamps,
        BTC=[0.0, 0.5, 0.5, 0.0],
        CASH=[1.0, 0.5, 0.5, 1.0],
    )
    funding = _frame(
        timestamps,
        BTC=[0.02, 0.01, -0.02, 0.0],
        CASH=[0.0, 0.0, 0.0, 0.0],
    )
    return prices, weights, funding


def _write_cli_inputs(
    tmp_path: Path,
    *,
    prices: pl.DataFrame,
    weights: pl.DataFrame,
    funding: pl.DataFrame | None = None,
) -> tuple[Path, Path, Path | None]:
    prices_path = tmp_path / "prices.parquet"
    weights_path = tmp_path / "weights.parquet"
    funding_path = tmp_path / "funding.parquet" if funding is not None else None
    prices.write_parquet(prices_path)
    weights.write_parquet(weights_path)
    if funding_path is not None and funding is not None:
        funding.write_parquet(funding_path)
    return prices_path, weights_path, funding_path


def _run_cli(tmp_path: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    environment = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONHASHSEED": "0",
        "PYTHONNOUSERSITE": "1",
        "TZ": "UTC",
    }
    return subprocess.run(
        [sys.executable, "-m", "backtest", "run", *arguments],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


# --------------------------------------------------------------------------- #
# CLI process boundary
# --------------------------------------------------------------------------- #


def test_cli_run_success_matches_public_api_and_writes_ephemeral_output(tmp_path: Path) -> None:
    prices, weights, funding = _ordinary_all_terms_fixture()
    prices_path, weights_path, funding_path = _write_cli_inputs(
        tmp_path,
        prices=prices,
        weights=weights,
        funding=funding,
    )
    assert funding_path is not None
    output_path = tmp_path / "result.json"

    completed = _run_cli(
        tmp_path,
        str(prices_path),
        str(weights_path),
        "--funding-rates",
        str(funding_path),
        "--engine",
        "ledger",
        "--trade-cost-bps",
        "10",
        "--benchmark",
        "BTC",
        "--output",
        str(output_path),
        "--pretty",
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stderr == ""
    stdout_payload = json.loads(completed.stdout)
    file_payload = json.loads(output_path.read_text())
    expected = run_backtest(
        prices=prices,
        weights=weights,
        funding_rates=funding,
        config=BacktestConfig(
            engine="ledger",
            trade_cost_bps=10.0,
            include_funding=True,
            benchmark="BTC",
        ),
    )

    assert stdout_payload == file_payload
    assert stdout_payload["status"] == "ok"
    assert stdout_payload["engine_used"] == "ledger"
    assert stdout_payload["rows"] == prices.height
    assert stdout_payload["engine_meta"] == expected.engine_meta
    assert stdout_payload["metrics"] == pytest.approx(dict(expected.metrics), rel=0.0, abs=0.0)


def test_cli_failure_is_structured_nonzero_and_writes_no_false_result(tmp_path: Path) -> None:
    timestamps = _timestamps(2)
    prices = _frame(timestamps, BTC=[100.0, 101.0])
    weights = _frame(timestamps, BTC=[1.0, 1.0])
    prices_path, weights_path, _ = _write_cli_inputs(tmp_path, prices=prices, weights=weights)
    output_path = tmp_path / "must-not-exist.json"

    completed = _run_cli(
        tmp_path,
        str(prices_path),
        str(weights_path),
        "--engine",
        "ledger",
        "--output",
        str(output_path),
    )

    assert completed.returncode == 1
    assert completed.stderr == ""
    assert json.loads(completed.stdout) == {
        "status": "error",
        "code": "backtest_run_failed",
        "message": "prices must include CASH column",
    }
    assert not output_path.exists()


# --------------------------------------------------------------------------- #
# Ordinary Nautilus known-answer behavior
# --------------------------------------------------------------------------- #


def test_nautilus_ordinary_known_answer_all_terms() -> None:
    pytest.importorskip("nautilus_trader")
    prices, weights, funding = _ordinary_all_terms_fixture()

    result = run_backtest(
        prices=prices,
        weights=weights,
        funding_rates=funding,
        config=BacktestConfig(
            engine="nautilus",
            initial_capital=100_000.0,
            trade_cost_bps=10.0,
            include_funding=True,
            benchmark="BTC",
            metrics=[],
        ),
    )

    # Hand-derived interval vectors:
    # price=[0, 50%*10%, 50%*10%], funding=[0, -50%*1%, -50%*-2%],
    # and turnover=[50%, 0, 50%] at 10 bps. The second 5% price return
    # requires the replay target to be sized from marked current equity.
    expected_price = np.array([0.0, 0.05, 0.05])
    expected_funding = np.array([0.0, -0.005, 0.01])
    expected_cost = np.array([0.0005, 0.0, 0.0005])
    expected_net = np.array([-0.0005, 0.045, 0.0595])
    expected_equity = np.array([100_000.0, 99_950.0, 104_447.75, 110_662.391125])

    np.testing.assert_allclose(result.price_return.to_numpy(), expected_price, rtol=0.0, atol=2e-10)
    np.testing.assert_allclose(result.funding_return.to_numpy(), expected_funding, rtol=0.0, atol=1e-15)
    np.testing.assert_allclose(result.cost_return.to_numpy(), expected_cost, rtol=0.0, atol=1e-15)
    np.testing.assert_allclose(result.net_return.to_numpy(), expected_net, rtol=0.0, atol=2e-10)
    np.testing.assert_allclose(result.equity.to_numpy(), expected_equity, rtol=0.0, atol=5e-5)
    np.testing.assert_allclose(
        result.benchmark_equity.to_numpy(),
        np.array([100_000.0, 100_000.0, 110_000.0, 121_000.0]),
        rtol=0.0,
        atol=1e-10,
    )


def test_nautilus_ordinary_failure_then_success_leaks_no_engine_state() -> None:
    pytest.importorskip("nautilus_trader")
    prices, weights, funding = _ordinary_all_terms_fixture()

    with pytest.raises(BacktestContractError, match="Benchmark asset"):
        run_backtest(
            prices=prices,
            weights=weights,
            funding_rates=funding,
            config=BacktestConfig(
                engine="nautilus",
                benchmark="MISSING",
                include_funding=False,
                trade_cost_bps=0.0,
                metrics=[],
            ),
        )

    config = BacktestConfig(
        engine="nautilus",
        benchmark="BTC",
        include_funding=False,
        trade_cost_bps=0.0,
        metrics=[],
    )
    after_failure = run_backtest(prices=prices, weights=weights, funding_rates=funding, config=config)
    clean_repeat = run_backtest(prices=prices, weights=weights, funding_rates=funding, config=config)

    assert_frame_equal(after_failure.to_dataframe(), clean_repeat.to_dataframe(), check_exact=True)
    assert after_failure.engine_meta == clean_repeat.engine_meta


@pytest.mark.parametrize(
    ("field", "expected_message"),
    [
        pytest.param("nonpositive_price", "positive non-CASH", id="nonpositive-price"),
        pytest.param("nonfinite_funding", "finite funding_rates", id="nonfinite-funding"),
    ],
)
def test_nautilus_ordinary_rejects_silent_numeric_corruption(field: str, expected_message: str) -> None:
    pytest.importorskip("nautilus_trader")
    timestamps = _timestamps(2)
    prices = _frame(
        timestamps,
        BTC=[100.0, 101.0],
        ETH=[50.0, 51.0],
        CASH=[1.0, 1.0],
    )
    weights = _frame(
        timestamps,
        BTC=[0.5, 0.5],
        ETH=[0.0, 0.0],
        CASH=[0.5, 0.5],
    )
    funding = _frame(
        timestamps,
        BTC=[0.0, 0.0],
        ETH=[0.0, 0.0],
        CASH=[0.0, 0.0],
    )
    if field == "nonpositive_price":
        prices = prices.with_columns(pl.Series("ETH", [0.0, 51.0]))
    else:
        funding = funding.with_columns(pl.Series("ETH", [float("nan"), 0.0]))

    with pytest.raises(BacktestContractError, match=expected_message):
        run_backtest(
            prices=prices,
            weights=weights,
            funding_rates=funding,
            config=BacktestConfig(engine="nautilus", benchmark="BTC", metrics=[]),
        )


# --------------------------------------------------------------------------- #
# Public connector and ledger boundaries
# --------------------------------------------------------------------------- #


def test_strategy_panel_rejects_leading_missing_asset_price() -> None:
    timestamps = _timestamps(2)
    panel = pl.DataFrame(
        {
            "timestamp": [timestamps[0], timestamps[1], timestamps[1]],
            "asset": ["BTC", "BTC", "ETH"],
            "close": [100.0, 101.0, 50.0],
        }
    )
    weights = StrategyWeights(
        weights=_frame(
            timestamps,
            BTC=[0.5, 0.5],
            ETH=[0.25, 0.25],
            CASH=[0.25, 0.25],
        ),
        assets=["BTC", "ETH"],
        execution=ExecutionTiming.same_bar(),
    )

    with pytest.raises(ValueError, match="leading null.*ETH"):
        run_backtest_from_strategy_weights(
            weights=weights,
            data=panel,
            config=BacktestConfig(engine="ledger", metrics=[]),
            materialize_timing=False,
        )


def test_ledger_final_target_is_not_executed_without_a_following_interval() -> None:
    timestamps = _timestamps(3)
    prices = _frame(timestamps, BTC=[100.0, 100.0, 100.0], CASH=[1.0, 1.0, 1.0])
    unchanged = _frame(timestamps, BTC=[0.25, 0.25, 0.25], CASH=[0.75, 0.75, 0.75])
    terminal_flip = _frame(timestamps, BTC=[0.25, 0.25, -1.0], CASH=[0.75, 0.75, 2.0])
    config = BacktestConfig(
        engine="ledger",
        include_funding=False,
        trade_cost_bps=25.0,
        metrics=[],
    )

    baseline = run_backtest(prices=prices, weights=unchanged, config=config)
    changed_only_after_last_interval = run_backtest(prices=prices, weights=terminal_flip, config=config)

    assert_frame_equal(
        changed_only_after_last_interval.to_dataframe(),
        baseline.to_dataframe(),
        check_exact=True,
    )


def test_weight_sum_tolerance_is_absolute_not_relative() -> None:
    timestamps = _timestamps(2)
    prices = _frame(timestamps, BTC=[100.0, 101.0], CASH=[1.0, 1.0])
    weights = _frame(
        timestamps,
        BTC=[0.5, 0.5],
        CASH=[0.500002, 0.500002],
    )

    with pytest.raises(BacktestContractError, match="weights must sum to 1.0"):
        run_backtest(
            prices=prices,
            weights=weights,
            config=BacktestConfig(engine="ledger", metrics=[]),
        )


# --------------------------------------------------------------------------- #
# Deterministic resting-limit public boundary
# --------------------------------------------------------------------------- #


def test_resting_limit_public_prepare_run_and_frozen_result_schema() -> None:
    timestamps = [datetime(2024, 3, 1, tzinfo=UTC) + timedelta(minutes=index) for index in range(4)]
    definitions = {
        "BTCUSDT": (100.0, 99.0),
        "ETHUSDT": (50.0, 49.0),
        "SOLUSDT": (20.0, 19.0),
    }

    def spec(symbol: str) -> InstrumentSpec:
        return InstrumentSpec(
            key=InstrumentKey("BINANCE", symbol),
            product="perpetual",
            base_currency=symbol.removesuffix("USDT"),
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

    rows: list[dict[str, object]] = []
    for timestamp in timestamps:
        for symbol, (close, _) in definitions.items():
            high, low = close + 1, close - 0.5
            if timestamp == timestamps[1] and symbol == "BTCUSDT":
                low = 99.0
            if timestamp == timestamps[1] and symbol == "SOLUSDT":
                high, low = 22.0, 18.0
            rows.append(
                {
                    "instrument": f"BINANCE:{symbol}",
                    "source_timestamp": timestamp,
                    "ts_event": timestamp,
                    "ts_init": timestamp,
                    "open": close,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": 10.0,
                }
            )

    plan = RestingLimitPlan(
        plan_id="public-resting-plan",
        orders=(
            RestingLimitOrder(
                "btc-fill",
                InstrumentKey("BINANCE", "BTCUSDT"),
                Decimal("1"),
                Decimal("99"),
                timestamps[0],
                timestamps[2],
            ),
            RestingLimitOrder(
                "eth-expire",
                InstrumentKey("BINANCE", "ETHUSDT"),
                Decimal("1"),
                Decimal("49"),
                timestamps[0],
                timestamps[2],
            ),
            RestingLimitOrder(
                "sol-buy",
                InstrumentKey("BINANCE", "SOLUSDT"),
                Decimal("1"),
                Decimal("19"),
                timestamps[0],
                timestamps[2],
                "sol-entry",
            ),
            RestingLimitOrder(
                "sol-sell",
                InstrumentKey("BINANCE", "SOLUSDT"),
                Decimal("-1"),
                Decimal("21"),
                timestamps[0],
                timestamps[2],
                "sol-entry",
            ),
        ),
    )
    prepared = prepare_resting_limit_execution(
        plan=plan,
        bars=pl.DataFrame(rows),
        instrument_specs=tuple(spec(symbol) for symbol in definitions),
        execution_calendar=timestamps,
        reporting_times=(timestamps[0], timestamps[-1]),
    )
    result = run_resting_limit_backtest(
        prepared=prepared,
        config=BacktestConfig(initial_capital=100_000, frequency="1m", metrics=[]),
    )

    assert result.to_dataframe().columns == [
        "equity",
        "benchmark_equity",
        "price_return",
        "funding_return",
        "cost_return",
        "net_return",
        "turnover",
    ]
    execution = result.resting_limit_execution
    assert isinstance(execution, RestingLimitExecutionResult)
    assert {outcome.status for outcome in execution.outcomes} == {
        OrderStatus.FILLED,
        OrderStatus.EXPIRED,
        OrderStatus.CANCELED,
    }
    assert execution.ambiguous_double_touch_count == 1
