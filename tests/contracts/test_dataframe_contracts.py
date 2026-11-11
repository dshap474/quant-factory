"""Contract tests for DataFrame schemas.

Validates column presence, types, and nullability contracts
between packages.
"""

from __future__ import annotations

import pytest
import numpy as np
import polars as pl
import pandas as pd


class TestOHLCVContract:
    """Tests OHLCV DataFrame contract."""

    def test_ohlcv_has_required_columns(self, sample_ohlcv_100_rows):
        """OHLCV DataFrames must have required columns."""
        required = {"timestamp", "open", "high", "low", "close", "volume"}
        actual = set(sample_ohlcv_100_rows.columns)

        assert required.issubset(actual), (
            f"Missing required columns: {required - actual}"
        )

    def test_ohlcv_timestamp_is_datetime(self, sample_ohlcv_100_rows):
        """OHLCV timestamp must be datetime type."""
        ts_dtype = sample_ohlcv_100_rows["timestamp"].dtype

        valid_types = [
            pl.Datetime("us"),
            pl.Datetime("ns"),
            pl.Datetime("ms"),
            pl.Date,
        ]

        assert ts_dtype in valid_types, (
            f"Timestamp type {ts_dtype} not in valid types"
        )

    def test_ohlcv_prices_are_float64(self, sample_ohlcv_100_rows):
        """OHLCV prices must be float64."""
        for col in ["open", "high", "low", "close"]:
            assert sample_ohlcv_100_rows[col].dtype == pl.Float64, (
                f"{col} is {sample_ohlcv_100_rows[col].dtype}, expected Float64"
            )

    def test_ohlcv_no_nulls(self, sample_ohlcv_100_rows):
        """OHLCV must have no null values."""
        for col in ["timestamp", "open", "high", "low", "close", "volume"]:
            null_count = sample_ohlcv_100_rows[col].null_count()
            assert null_count == 0, f"{col} has {null_count} nulls"

    def test_ohlcv_constraints_satisfied(self, sample_ohlcv_100_rows):
        """OHLCV price constraints must be satisfied."""
        df = sample_ohlcv_100_rows.to_pandas()

        # low <= open, close
        assert (df["low"] <= df["open"]).all(), "low > open violation"
        assert (df["low"] <= df["close"]).all(), "low > close violation"

        # open, close <= high
        assert (df["open"] <= df["high"]).all(), "open > high violation"
        assert (df["close"] <= df["high"]).all(), "close > high violation"


class TestFeatureDataFrameContract:
    """Tests feature DataFrame contract."""

    def test_features_all_numeric(self, sample_features_df):
        """Feature columns must be numeric."""
        for col in sample_features_df.columns:
            if col not in ["timestamp", "target"]:
                assert np.issubdtype(sample_features_df[col].dtype, np.number), (
                    f"Feature {col} is not numeric: {sample_features_df[col].dtype}"
                )

    def test_features_no_nan(self, sample_features_df):
        """Features must have no NaN (after processing)."""
        for col in sample_features_df.columns:
            if col not in ["timestamp"]:
                nan_count = sample_features_df[col].isna().sum()
                assert nan_count == 0, f"{col} has {nan_count} NaN values"

    def test_features_no_inf(self, sample_features_df):
        """Features must have no infinite values."""
        for col in sample_features_df.columns:
            if col not in ["timestamp", "target"]:
                if np.issubdtype(sample_features_df[col].dtype, np.floating):
                    inf_count = np.isinf(sample_features_df[col]).sum()
                    assert inf_count == 0, f"{col} has {inf_count} inf values"


class TestWeightsContract:
    """Tests trading weights contract."""

    def test_weights_normalized(self, sample_weights_for_backtest):
        """Weights should sum to 1.0 per row (not per column)."""
        df = sample_weights_for_backtest.to_pandas() if hasattr(
            sample_weights_for_backtest, 'to_pandas'
        ) else sample_weights_for_backtest

        weight_cols = [c for c in df.columns if c != "timestamp"]

        # Calculate row sums
        row_sums = df[weight_cols].sum(axis=1)

        # Each row should sum to approximately 1.0
        assert np.allclose(row_sums, 1.0, atol=0.01), (
            f"Row sums not close to 1.0: min={row_sums.min()}, max={row_sums.max()}"
        )

    def test_weights_no_nan(self, sample_weights_for_backtest):
        """Weights must have no NaN."""
        df = sample_weights_for_backtest
        weight_cols = [c for c in df.columns if c != "timestamp"]

        for col in weight_cols:
            null_count = df[col].null_count()
            assert null_count == 0, f"{col} has {null_count} nulls"
