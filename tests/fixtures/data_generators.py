"""Data generators for quant-factory integration tests.

Provides deterministic synthetic data generation for testing cross-package
workflows. All generators use Geometric Brownian Motion for realistic price
dynamics and are fully reproducible given a random seed.

Usage:
    from fixtures import generate_ohlcv, generate_multi_asset_ohlcv

    rng = np.random.default_rng(42)
    ohlcv = generate_ohlcv(rng, n_rows=1000)
    panel = generate_multi_asset_ohlcv(rng, assets=["BTC", "ETH"], n_rows_per_asset=500)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
import polars as pl

if TYPE_CHECKING:
    from numpy.random import Generator as NPGenerator


def generate_ohlcv(
    rng: NPGenerator,
    n_rows: int,
    start_price: float = 100.0,
    drift: float = 0.0001,
    volatility: float = 0.02,
    freq: str = "1h",
    start_date: str = "2020-01-01",
) -> pl.DataFrame:
    """Generate realistic OHLCV data using Geometric Brownian Motion.

    Args:
        rng: NumPy random generator for reproducibility
        n_rows: Number of rows to generate
        start_price: Initial price level
        drift: Average return per period (default: 0.01% hourly)
        volatility: Standard deviation of returns (default: 2% hourly)
        freq: Timestamp frequency (default: "1h")
        start_date: Start date for timestamps

    Returns:
        Polars DataFrame with columns:
            - timestamp: datetime
            - open: float
            - high: float
            - low: float
            - close: float
            - volume: float

    Properties guaranteed:
        1. Realistic price dynamics (GBM with drift)
        2. OHLC constraint: low <= min(open, close) and max(open, close) <= high
        3. No nulls or NaN values
        4. Monotonic timestamps
        5. Volume follows log-normal distribution
        6. Deterministic given seed

    Example:
        >>> rng = np.random.default_rng(42)
        >>> df = generate_ohlcv(rng, n_rows=100)
        >>> df.shape
        (100, 6)
    """
    # Geometric Brownian motion for realistic prices
    returns = rng.normal(drift, volatility, n_rows)
    close = start_price * np.exp(np.cumsum(returns))

    # OHLC with realistic spreads (ensure constraints are met)
    spread_high = rng.uniform(0.001, 0.03, n_rows)
    spread_low = rng.uniform(0.001, 0.03, n_rows)
    high = close * (1 + spread_high)
    low = close * (1 - spread_low)

    # Open is between low and high
    open_pct = rng.uniform(0, 1, n_rows)
    open_ = low + open_pct * (high - low)

    # Volume follows log-normal distribution
    volume = rng.lognormal(10, 1, n_rows)

    # Generate timestamps
    timestamps = pd.date_range(start_date, periods=n_rows, freq=freq)

    return pl.DataFrame({
        "timestamp": timestamps,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })


def generate_multi_asset_ohlcv(
    rng: NPGenerator,
    assets: list[str],
    n_rows_per_asset: int,
    correlated: bool = True,
    correlation_strength: float = 0.3,
    **kwargs,
) -> pl.DataFrame:
    """Generate panel data with multiple assets for cross-asset tests.

    Each asset has its own price dynamics with optional correlation through
    a common market factor.

    Args:
        rng: NumPy random generator for reproducibility
        assets: List of asset names (e.g., ["BTC", "ETH", "SOL"])
        n_rows_per_asset: Number of rows per asset
        correlated: Whether to add correlation between assets
        correlation_strength: Strength of market factor correlation (0-1)
        **kwargs: Additional arguments passed to generate_ohlcv

    Returns:
        Polars DataFrame with columns:
            - timestamp, open, high, low, close, volume (from generate_ohlcv)
            - asset: str (asset identifier)

    Example:
        >>> rng = np.random.default_rng(42)
        >>> df = generate_multi_asset_ohlcv(rng, ["BTC", "ETH"], 500)
        >>> df.shape
        (1000, 7)
    """
    # Default starting prices by asset
    default_prices = {"BTC": 40000.0, "ETH": 2500.0, "SOL": 100.0}

    # Generate common market factor for correlation
    if correlated:
        market_factor = rng.normal(0, 1, n_rows_per_asset)
    else:
        market_factor = np.zeros(n_rows_per_asset)

    dfs = []
    for asset in assets:
        # Get asset-specific starting price
        start_price = default_prices.get(asset, 100.0)

        # Generate base OHLCV
        df = generate_ohlcv(rng, n_rows_per_asset, start_price=start_price, **kwargs)

        # Add correlation through market factor (affects returns, thus prices)
        if correlated:
            # Apply market factor to close prices
            factor_effect = 1 + correlation_strength * market_factor * 0.02
            df = df.with_columns([
                (pl.col("close") * factor_effect).alias("close"),
                (pl.col("open") * factor_effect).alias("open"),
                (pl.col("high") * factor_effect).alias("high"),
                (pl.col("low") * factor_effect).alias("low"),
            ])

        # Add asset column
        df = df.with_columns(pl.lit(asset).alias("asset"))
        dfs.append(df)

    return pl.concat(dfs)


def generate_features_from_ohlcv(
    ohlcv: pl.DataFrame | pd.DataFrame,
    include_target: bool = True,
    target_horizon: int = 1,
) -> pd.DataFrame:
    """Generate technical features from OHLCV data.

    Creates a set of common technical indicators suitable for ML models.

    Args:
        ohlcv: OHLCV DataFrame (Polars or Pandas)
        include_target: Whether to include target column
        target_horizon: Periods ahead for target (default: 1)

    Returns:
        Pandas DataFrame with features and optional target

    Features generated:
        - return_1, return_5, return_10: Price returns
        - volatility_10, volatility_20: Rolling volatility
        - ma_ratio_10_20: Moving average ratio
        - volume_ma_10: Volume moving average
        - rsi_14: Relative Strength Index
    """
    # Convert to pandas if needed
    if isinstance(ohlcv, pl.DataFrame):
        df = ohlcv.to_pandas()
    else:
        df = ohlcv.copy()

    # Price returns
    df["return_1"] = df["close"].pct_change()
    df["return_5"] = df["close"].pct_change(5)
    df["return_10"] = df["close"].pct_change(10)

    # Volatility
    df["volatility_10"] = df["return_1"].rolling(10).std()
    df["volatility_20"] = df["return_1"].rolling(20).std()

    # Moving average ratio
    ma_10 = df["close"].rolling(10).mean()
    ma_20 = df["close"].rolling(20).mean()
    df["ma_ratio_10_20"] = ma_10 / ma_20

    # Volume features
    df["volume_ma_10"] = df["volume"].rolling(10).mean()
    df["volume_ratio"] = df["volume"] / df["volume_ma_10"]

    # RSI (simplified)
    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.inf)
    df["rsi_14"] = 100 - (100 / (1 + rs))

    # Target (next period return direction)
    if include_target:
        df["target"] = (df["close"].shift(-target_horizon) > df["close"]).astype(float)

    # Drop NaN rows
    df = df.dropna()

    return df


def generate_trading_weights(
    rng: NPGenerator,
    n_rows: int,
    n_assets: int = 1,
    strategy: str = "random",
    normalize: bool = True,
) -> np.ndarray:
    """Generate trading weights for backtest.

    Args:
        rng: NumPy random generator
        n_rows: Number of time periods
        n_assets: Number of assets
        strategy: Weight generation strategy:
            - "random": Random weights in [-1, 1]
            - "long_only": Random weights in [0, 1]
            - "momentum": Autocorrelated weights
        normalize: Whether to normalize weights to sum to 1

    Returns:
        NumPy array of shape (n_rows, n_assets)
    """
    if strategy == "random":
        weights = rng.uniform(-1, 1, (n_rows, n_assets))
    elif strategy == "long_only":
        weights = rng.uniform(0, 1, (n_rows, n_assets))
    elif strategy == "momentum":
        # Autocorrelated weights (simulate momentum strategy)
        weights = np.zeros((n_rows, n_assets))
        weights[0] = rng.uniform(-1, 1, n_assets)
        for i in range(1, n_rows):
            innovation = rng.normal(0, 0.1, n_assets)
            weights[i] = 0.9 * weights[i - 1] + innovation
        weights = np.clip(weights, -1, 1)
    else:
        raise ValueError(f"Unknown strategy: {strategy}")

    if normalize and n_assets > 1:
        row_sums = np.abs(weights).sum(axis=1, keepdims=True)
        row_sums = np.where(row_sums == 0, 1, row_sums)
        weights = weights / row_sums

    return weights.squeeze() if n_assets == 1 else weights
