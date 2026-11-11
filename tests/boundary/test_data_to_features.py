"""B1 Boundary: data loading -> feature inputs.

Validates the raw parquet schema consumed by downstream feature builders.
"""

from __future__ import annotations

import pytest
import polars as pl
import pandas as pd


pytestmark = pytest.mark.boundary


class TestDataToFeaturesBoundary:
    """Validates the contract between data files and features packages."""

    def test_data_has_required_columns(self, populated_db):
        """Parquet data has columns FeaturePipeline expects."""
        df = pl.read_parquet(populated_db / "raw" / "1d" / "index" / "btc.parquet")

        required = {"timestamp", "open", "high", "low", "close", "volume"}
        assert required.issubset(set(df.columns)), (
            f"Missing columns: {required - set(df.columns)}"
        )

    def test_data_timestamp_type(self, populated_db):
        """Timestamp column has correct type."""
        df = pl.read_parquet(populated_db / "raw" / "1d" / "index" / "btc.parquet")

        ts_col = df["timestamp"]
        assert ts_col.dtype in [pl.Datetime("us"), pl.Datetime("ns"), pl.Date], (
            f"Unexpected timestamp type: {ts_col.dtype}"
        )

    def test_data_no_nulls(self, populated_db):
        """Data has no null values in core columns."""
        df = pl.read_parquet(populated_db / "raw" / "1d" / "index" / "btc.parquet")

        for col in ["timestamp", "open", "high", "low", "close", "volume"]:
            null_count = df[col].null_count()
            assert null_count == 0, f"Column {col} has {null_count} null values"

    def test_ohlc_constraints(self, populated_db):
        """OHLC data satisfies price constraints."""
        df = pl.read_parquet(populated_db / "raw" / "1d" / "index" / "btc.parquet").to_pandas()

        assert (df["low"] <= df["open"]).all(), "low > open violation"
        assert (df["low"] <= df["close"]).all(), "low > close violation"
        assert (df["open"] <= df["high"]).all(), "open > high violation"
        assert (df["close"] <= df["high"]).all(), "close > high violation"


class TestDataOutputFormats:
    """Tests various output formats from data loading."""

    def test_polars_to_pandas_conversion(self, populated_db):
        """Parquet data converts cleanly to pandas."""
        df_polars = pl.read_parquet(populated_db / "raw" / "1d" / "index" / "btc.parquet")
        df_pandas = df_polars.to_pandas()

        assert isinstance(df_pandas, pd.DataFrame)
        assert len(df_pandas) == len(df_polars)
        assert set(df_pandas.columns) == set(df_polars.columns)

    def test_data_preserves_precision(self, populated_db):
        """Data preserves numerical precision."""
        df = pl.read_parquet(populated_db / "raw" / "1d" / "index" / "btc.parquet")

        for col in ["open", "high", "low", "close", "volume"]:
            assert df[col].dtype == pl.Float64, (
                f"Column {col} has type {df[col].dtype}, expected Float64"
            )
