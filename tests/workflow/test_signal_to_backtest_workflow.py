"""Workflow: signal outputs -> backtest.

Tests the backtest boundary using validated prediction-derived weights.
"""

from __future__ import annotations

import pytest
import numpy as np
import pandas as pd
import polars as pl


pytestmark = pytest.mark.workflow


def _generate_features_from_ohlcv(ohlcv_df: pl.DataFrame) -> pd.DataFrame:
    """Generate simple technical features from OHLCV data.

    Helper function to avoid import issues with fixtures module.
    """
    df = ohlcv_df.to_pandas()

    # Create simple features
    df["return_1"] = df["close"].pct_change()
    df["return_5"] = df["close"].pct_change(5)
    df["return_10"] = df["close"].pct_change(10)
    df["volatility_10"] = df["return_1"].rolling(10).std()
    df["volatility_20"] = df["return_1"].rolling(20).std()
    df["ma_ratio_10_20"] = df["close"].rolling(10).mean() / df["close"].rolling(20).mean()
    df["volume_ma_10"] = df["volume"].rolling(10).mean()

    # Add target
    df["target"] = df["close"].pct_change().shift(-1)

    # Drop NaN rows
    df = df.dropna()

    return df


class TestBacktestWorkflow:
    """Tests the backtest boundary for signal-shaped outputs."""

    def test_workflow_produces_reasonable_metrics(
        self,
        sample_prices_for_backtest,
        sample_weights_for_backtest,
        backtest_config,
    ):
        """Workflow produces reasonable (not degenerate) metrics."""
        from backtest import run_backtest

        backtest_result = run_backtest(
            prices=sample_prices_for_backtest,
            weights=sample_weights_for_backtest,
            config=backtest_config,
        )

        # Check metrics are reasonable (not NaN)
        metrics = backtest_result.metrics
        sharpe_key = "sharpe_ratio" if "sharpe_ratio" in metrics else "sharpe"

        if sharpe_key in metrics:
            sharpe = metrics[sharpe_key]
            assert np.isfinite(sharpe), f"Sharpe is not finite: {sharpe}"
            # For synthetic data, Sharpe can be quite extreme but should still be finite
            # Just verify it's not astronomically large (> 100 is unrealistic)
            assert -100 < sharpe < 100, f"Sharpe out of range: {sharpe}"


class TestWorkflowTimestampAlignment:
    """Tests timestamp alignment through the workflow."""

    def test_timestamps_preserved_in_features(
        self, sample_ohlcv_1000_rows
    ):
        """Timestamps are preserved through feature generation."""
        features_df = _generate_features_from_ohlcv(sample_ohlcv_1000_rows)

        # Original timestamps
        original_ts = set(sample_ohlcv_1000_rows["timestamp"].to_list())
        feature_ts = set(features_df["timestamp"].tolist())

        # Feature timestamps should be subset of original (some dropped for warmup)
        assert feature_ts.issubset(original_ts)
        # Should still have most timestamps
        assert len(feature_ts) > len(original_ts) * 0.9

class TestBacktestOutputValidation:
    """Tests backtest output validation."""

    def test_equity_starts_at_initial_capital(
        self,
        sample_prices_for_backtest,
        sample_weights_for_backtest,
        backtest_config,
    ):
        """Equity curve starts at initial_capital (default 1,000,000)."""
        from backtest import run_backtest

        result = run_backtest(
            prices=sample_prices_for_backtest,
            weights=sample_weights_for_backtest,
            config=backtest_config,
        )

        equity = result.equity
        if isinstance(equity, pl.DataFrame):
            first_value = equity["equity"].to_list()[0]
        elif isinstance(equity, pl.Series):
            first_value = equity.to_list()[0]
        else:
            first_value = equity.iloc[0] if hasattr(equity, "iloc") else equity[0]

        # Default initial_capital is 1,000,000
        expected_initial = backtest_config.initial_capital
        assert np.isclose(first_value, expected_initial, rtol=0.01)

    def test_equity_no_nan(
        self,
        sample_prices_for_backtest,
        sample_weights_for_backtest,
        backtest_config,
    ):
        """Equity curve contains no NaN values."""
        from backtest import run_backtest

        result = run_backtest(
            prices=sample_prices_for_backtest,
            weights=sample_weights_for_backtest,
            config=backtest_config,
        )

        equity = result.equity
        if isinstance(equity, pl.DataFrame):
            null_count = equity["equity"].null_count() if "equity" in equity.columns else 0
        elif isinstance(equity, pl.Series):
            null_count = equity.null_count()
        else:
            null_count = equity.isna().sum() if hasattr(equity, "isna") else 0

        assert null_count == 0
