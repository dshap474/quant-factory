"""Smoke tests for Nautilus engine path."""

from __future__ import annotations

from datetime import datetime, timedelta

import polars as pl
import pytest
from backtest import BacktestConfig, run_backtest


def test_nautilus_engine_runs_with_multi_asset_weights():
    pytest.importorskip("nautilus_trader")

    start = datetime(2024, 1, 1)
    prices = pl.DataFrame(
        {
            "timestamp": [start + timedelta(days=i) for i in range(6)],
            "BTC": [100.0, 102.0, 101.0, 104.0, 106.0, 108.0],
            "ETH": [50.0, 51.0, 49.0, 50.0, 52.0, 53.0],
            "CASH": [1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
        }
    )
    weights = pl.DataFrame(
        {
            "timestamp": [start + timedelta(days=i) for i in range(6)],
            "BTC": [0.4, 0.45, 0.4, 0.5, 0.45, 0.4],
            "ETH": [0.3, 0.25, 0.3, 0.2, 0.25, 0.3],
            "CASH": [0.3, 0.3, 0.3, 0.3, 0.3, 0.3],
        }
    )

    result = run_backtest(
        prices=prices,
        weights=weights,
        config=BacktestConfig(include_funding=False),
    )

    assert result.engine_used == "nautilus"
    assert len(result.equity) == len(prices)
    assert "total_return" in result.metrics
    assert "tracking_error" in result.metrics
    assert "information_ratio" in result.metrics


def test_nautilus_engine_supports_opt_in_sharpe_statistics():
    pytest.importorskip("nautilus_trader")

    start = datetime(2024, 1, 1)
    prices = pl.DataFrame(
        {
            "timestamp": [start + timedelta(days=i) for i in range(6)],
            "BTC": [100.0, 102.0, 101.0, 104.0, 106.0, 108.0],
            "ETH": [50.0, 51.0, 49.0, 50.0, 52.0, 53.0],
            "CASH": [1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
        }
    )
    weights = pl.DataFrame(
        {
            "timestamp": [start + timedelta(days=i) for i in range(6)],
            "BTC": [0.4, 0.45, 0.4, 0.5, 0.45, 0.4],
            "ETH": [0.3, 0.25, 0.3, 0.2, 0.25, 0.3],
            "CASH": [0.3, 0.3, 0.3, 0.3, 0.3, 0.3],
        }
    )

    result = run_backtest(
        prices=prices,
        weights=weights,
        config=BacktestConfig(
            include_funding=False,
            metrics=[
                "sharpe",
                "sharpe_se",
                "sharpe_tstat",
                "sharpe_ci_lower",
                "sharpe_ci_upper",
                "sharpe_adj_autocorr",
            ],
        ),
    )

    for key in [
        "sharpe",
        "sharpe_se",
        "sharpe_tstat",
        "sharpe_ci_lower",
        "sharpe_ci_upper",
        "sharpe_adj_autocorr",
    ]:
        assert key in result.metrics
        assert isinstance(result.metrics[key], float)


def test_benchmark_selection_changes_benchmark_relative_metrics():
    pytest.importorskip("nautilus_trader")

    start = datetime(2024, 1, 1)
    prices = pl.DataFrame(
        {
            "timestamp": [start + timedelta(days=i) for i in range(6)],
            "BTC": [100.0, 102.0, 101.0, 104.0, 106.0, 108.0],
            "ETH": [50.0, 49.0, 50.0, 48.0, 47.0, 46.0],
            "CASH": [1.0, 1.0, 1.0, 1.0, 1.0, 1.0],
        }
    )
    weights = pl.DataFrame(
        {
            "timestamp": [start + timedelta(days=i) for i in range(6)],
            "BTC": [0.6, 0.6, 0.6, 0.6, 0.6, 0.6],
            "ETH": [0.2, 0.2, 0.2, 0.2, 0.2, 0.2],
            "CASH": [0.2, 0.2, 0.2, 0.2, 0.2, 0.2],
        }
    )

    default_benchmark = run_backtest(
        prices=prices,
        weights=weights,
        config=BacktestConfig(
            include_funding=False,
            metrics=["tracking_error", "information_ratio"],
        ),
    )
    eth_benchmark = run_backtest(
        prices=prices,
        weights=weights,
        config=BacktestConfig(
            include_funding=False,
            benchmark="ETH",
            metrics=["tracking_error", "information_ratio"],
        ),
    )

    assert default_benchmark.metrics["tracking_error"] != eth_benchmark.metrics["tracking_error"]
    assert default_benchmark.metrics["information_ratio"] != eth_benchmark.metrics["information_ratio"]
