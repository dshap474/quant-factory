"""Public ledger regression checks for genuinely unheld missing price histories.

USAGE: .venv/bin/python -m pytest packages/platform/backtest/tests/e2e/test_inactive_missing_prices.py -q
"""

from datetime import UTC, datetime, timedelta

import numpy as np
import polars as pl
import pytest
from backtest import BacktestConfig, run_backtest, run_backtest_from_strategy_weights

from strategies import ExecutionTiming, StrategyWeights

# --------------------------------------------------------------------------- #
# Tiny entry/hold/exit market
# --------------------------------------------------------------------------- #


def frames():
    times = [datetime(2022, 1, 1, tzinfo=UTC) + timedelta(days=i) for i in range(5)]
    prices = pl.DataFrame(
        {"timestamp": times, "BTC": [100.0] * 5, "NEW": [None, 10.0, 11.0, 12.0, None], "CASH": [1.0] * 5}
    )
    weights = pl.DataFrame(
        {"timestamp": times, "BTC": [0.0] * 5, "NEW": [0.0, 0.5, 0.5, 0.0, 0.0], "CASH": [1.0, 0.5, 0.5, 1.0, 1.0]}
    )
    return prices, weights


def config(**kwargs):
    return BacktestConfig(
        engine="ledger",
        initial_capital=100,
        trade_cost_bps=0,
        include_funding=False,
        benchmark="BTC",
        allow_inactive_missing_prices=True,
        **kwargs,
    )


# --------------------------------------------------------------------------- #
# Public boundary checks
# --------------------------------------------------------------------------- #


def test_inactive_gaps_preserved_and_real_returns_earned():
    prices, weights = frames()
    result = run_backtest(prices=prices, weights=weights, config=config())
    np.testing.assert_allclose(result.equity.to_numpy(), [100, 100, 105, 105 * (1 + 0.5 / 11), 105 * (1 + 0.5 / 11)])
    assert prices["NEW"].null_count() == 2
    assert result.engine_meta["allow_inactive_missing_prices"] is True


def test_strict_default_still_rejects_missing_prices():
    prices, weights = frames()
    with pytest.raises(ValueError, match="finite prices"):
        run_backtest(prices=prices, weights=weights, config=BacktestConfig(engine="ledger"))


@pytest.mark.parametrize("row", [1, 2, 3])
def test_entry_hold_and_exit_marks_are_required(row):
    prices, weights = frames()
    prices = (
        prices.with_row_index()
        .with_columns(pl.when(pl.col("index") == row).then(None).otherwise(pl.col("NEW")).alias("NEW"))
        .drop("index")
    )
    with pytest.raises(ValueError, match="Missing required price for NEW"):
        run_backtest(prices=prices, weights=weights, config=config())


@pytest.mark.parametrize("value", [0.0, -1.0, np.inf, -np.inf])
def test_invalid_observed_inactive_price_rejected(value):
    prices, weights = frames()
    prices = prices.with_columns(pl.col("NEW").fill_null(value))
    with pytest.raises(ValueError, match="Observed"):
        run_backtest(prices=prices, weights=weights, config=config())


def test_benchmark_must_be_complete():
    prices, weights = frames()
    prices = prices.with_columns(pl.lit(None, dtype=pl.Float64).alias("BTC"))
    with pytest.raises(ValueError, match="Benchmark prices"):
        run_backtest(prices=prices, weights=weights, config=config())
    with pytest.raises(ValueError, match="explicit"):
        run_backtest(
            prices=frames()[0],
            weights=weights,
            config=BacktestConfig(engine="ledger", allow_inactive_missing_prices=True),
        )


def test_nautilus_cannot_silently_accept_option():
    with pytest.raises(ValueError, match="requires engine"):
        BacktestConfig(allow_inactive_missing_prices=True)


def test_connector_applies_one_lag_and_does_not_fill_wide_prices():
    prices, weights = frames()
    decisions = weights.with_columns(pl.col("NEW").shift(-1).fill_null(0), pl.col("CASH").shift(-1).fill_null(1))
    intent = StrategyWeights(weights=decisions, assets=["BTC", "NEW"], execution=ExecutionTiming.next_bar())
    result = run_backtest_from_strategy_weights(weights=intent, data=prices, config=config())
    assert len(result.equity) == 4
    np.testing.assert_allclose(result.net_return.to_numpy(), [0.05, 0.5 / 11, 0])
