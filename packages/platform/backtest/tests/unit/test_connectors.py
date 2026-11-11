"""Tests for strategy-output connectors into backtest runtime."""

from __future__ import annotations

from datetime import datetime

import polars as pl
from backtest import BacktestConfig
from backtest.connectors import materialize_effective_weights, run_backtest_from_strategy_weights

from strategies import ExecutionTiming, StrategyWeights


def test_run_backtest_from_strategy_weights_panel_data():
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
    assert "total_return" in result.metrics
    assert result.engine_used == "nautilus"


def test_materialize_effective_weights_expands_sparse_next_bar_schedule():
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

    assert effective.weights["timestamp"].to_list() == [
        datetime(2024, 1, 2),
        datetime(2024, 1, 3),
        datetime(2024, 1, 4),
    ]
    assert effective.weights["BTC"].to_list() == [0.2, 0.2, 0.4]
