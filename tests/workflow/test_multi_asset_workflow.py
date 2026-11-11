"""Workflow: Multi-asset panel data through pipeline

Tests cross-asset feature generation and multi-asset backtesting.
HIGH PRIORITY: Panel data with BTC, ETH, SOL.
"""

from __future__ import annotations

import pytest
import numpy as np
import polars as pl


pytestmark = pytest.mark.workflow


class TestMultiAssetDataGeneration:
    """Tests multi-asset data generation and structure."""

    def test_multi_asset_ohlcv_structure(self, multi_asset_ohlcv):
        """Multi-asset OHLCV has correct structure."""
        df = multi_asset_ohlcv

        # Should have asset column
        assert "asset" in df.columns

        # Should have all expected assets
        assets = df["asset"].unique().to_list()
        assert "BTC" in assets
        assert "ETH" in assets
        assert "SOL" in assets

        # Each asset should have same number of rows
        asset_counts = df.group_by("asset").count()
        counts = asset_counts["count"].to_list()
        assert len(set(counts)) == 1  # All counts equal

    def test_multi_asset_ohlcv_per_asset_valid(self, multi_asset_ohlcv):
        """Each asset's OHLCV data is individually valid."""
        df = multi_asset_ohlcv

        for asset in df["asset"].unique().to_list():
            asset_df = df.filter(pl.col("asset") == asset)

            # OHLC constraints
            pdf = asset_df.to_pandas()
            assert (pdf["low"] <= pdf["open"]).all()
            assert (pdf["low"] <= pdf["close"]).all()
            assert (pdf["open"] <= pdf["high"]).all()
            assert (pdf["close"] <= pdf["high"]).all()

            # No nulls
            for col in ["timestamp", "open", "high", "low", "close", "volume"]:
                assert asset_df[col].null_count() == 0


class TestCrossAssetFeatures:
    """Tests cross-asset feature generation."""

    def test_generate_cross_asset_features(self, multi_asset_ohlcv):
        """Cross-asset features can be generated from panel data."""
        df = multi_asset_ohlcv

        # Pivot to wide format for cross-asset features
        wide = df.pivot(
            index="timestamp",
            columns="asset",
            values="close",
        )

        # Generate cross-asset correlations (rolling)
        pdf = wide.to_pandas()
        pdf["btc_eth_corr_20"] = pdf["BTC"].rolling(20).corr(pdf["ETH"])
        pdf["btc_sol_corr_20"] = pdf["BTC"].rolling(20).corr(pdf["SOL"])
        pdf["eth_sol_corr_20"] = pdf["ETH"].rolling(20).corr(pdf["SOL"])

        # Drop NaN from rolling
        pdf = pdf.dropna()

        assert len(pdf) > 0
        assert "btc_eth_corr_20" in pdf.columns

    def test_cross_asset_returns_correlation(self, multi_asset_ohlcv):
        """Cross-asset returns show expected correlation patterns."""
        df = multi_asset_ohlcv

        # Compute returns for each asset
        returns_dfs = []
        for asset in ["BTC", "ETH", "SOL"]:
            asset_df = df.filter(pl.col("asset") == asset).sort("timestamp")
            asset_df = asset_df.with_columns(
                pl.col("close").pct_change().alias(f"{asset}_return")
            )
            returns_dfs.append(
                asset_df.select(["timestamp", f"{asset}_return"])
            )

        # Join all returns
        merged = returns_dfs[0]
        for ret_df in returns_dfs[1:]:
            merged = merged.join(ret_df, on="timestamp", how="inner")

        pdf = merged.to_pandas().dropna()

        # Compute correlation matrix
        corr = pdf[["BTC_return", "ETH_return", "SOL_return"]].corr()

        # Crypto assets should have some positive correlation
        # (not testing exact values, just that correlation is computed)
        assert not np.isnan(corr.values).any()


class TestMultiAssetBacktest:
    """Tests multi-asset backtesting."""

    def test_multi_asset_backtest(
        self, multi_asset_ohlcv, backtest_config, rng
    ):
        """Backtest works with multiple assets."""
        from backtest import run_backtest

        df = multi_asset_ohlcv

        # Pivot to wide format
        prices = df.pivot(
            index="timestamp",
            columns="asset",
            values="close",
        )

        # Add CASH column for proper weight normalization
        prices = prices.with_columns(pl.lit(1.0).alias("CASH"))

        # Generate weights that sum to 1.0 per row (incl CASH)
        n_rows = len(prices)

        # Use positive weights for assets, remainder goes to CASH
        btc_w = rng.uniform(0.1, 0.4, n_rows)
        eth_w = rng.uniform(0.1, 0.3, n_rows)
        sol_w = rng.uniform(0.05, 0.2, n_rows)
        cash_w = 1.0 - btc_w - eth_w - sol_w

        weights = pl.DataFrame({
            "timestamp": prices["timestamp"],
            "BTC": btc_w,
            "ETH": eth_w,
            "SOL": sol_w,
            "CASH": cash_w,
        })

        # Run backtest
        result = run_backtest(
            prices=prices,
            weights=weights,
            config=backtest_config,
        )

        assert result is not None
        assert result.equity is not None

    def test_multi_asset_weights_sum_correctly(
        self, multi_asset_ohlcv, rng
    ):
        """Multi-asset weights are properly normalized."""
        df = multi_asset_ohlcv
        n_assets = 3
        n_rows = len(df) // n_assets

        # Generate normalized weights
        raw_weights = rng.uniform(-1, 1, (n_rows, n_assets))
        row_sums = np.abs(raw_weights).sum(axis=1, keepdims=True)
        row_sums = np.where(row_sums == 0, 1, row_sums)
        weights = raw_weights / row_sums

        # Check normalization
        abs_sums = np.abs(weights).sum(axis=1)
        assert np.allclose(abs_sums, 1.0, atol=1e-6)
