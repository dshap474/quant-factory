"""Input validation and normalization shared by both ordinary engines.

Purpose: convert aligned Polars frames into finite float64 arrays while
enforcing the public price, weight, funding, and timestamp contracts.

USAGE:
    inputs = prepare_inputs(prices=prices, weights=weights)
"""

from dataclasses import dataclass
from typing import Sequence

import numpy as np
import polars as pl

from .errors import BacktestContractError

# --------------------------------------------------------------------------- #
# Normalized input container
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class EngineInputs:
    """Validated and normalized inputs for the backtest engine.

    Bridges Polars DataFrames (user interface) to NumPy arrays (computation).
    """

    timestamps: pl.Series  # Datetime index
    assets: Sequence[str]  # Asset column names
    prices: pl.DataFrame  # Original price DataFrame
    weights: pl.DataFrame  # Original weight DataFrame
    funding_rates: pl.DataFrame  # Funding rates DataFrame
    price_values: np.ndarray  # (T, N) contiguous NumPy array
    weight_values: np.ndarray  # (T, N) contiguous NumPy array
    funding_values: np.ndarray  # (T, N) contiguous NumPy array


# --------------------------------------------------------------------------- #
# Public preparation
# --------------------------------------------------------------------------- #


def prepare_inputs(
    *,
    prices: pl.DataFrame,
    weights: pl.DataFrame,
    funding_rates: pl.DataFrame | None = None,
    timestamp_col: str = "timestamp",
    allow_inactive_missing_prices: bool = False,
    rebalance_every_bars: int = 1,
) -> EngineInputs:
    """Validate and normalize inputs for the backtest engine.

    Args:
        prices: Price matrix with timestamp column and asset columns.
        weights: Weight matrix with same structure as prices.
        funding_rates: Optional funding rate matrix (defaults to zeros).
        timestamp_col: Name of the timestamp column.

    Returns:
        EngineInputs with validated data and NumPy arrays.

    Raises:
        ValueError: If inputs are invalid or misaligned.
    """
    for frame_name, frame in (("prices", prices), ("weights", weights)):
        if timestamp_col not in frame.columns:
            raise ValueError(f"{frame_name} must include timestamp column '{timestamp_col}'")

    _validate_timestamp_index(prices, timestamp_col, "prices")
    _validate_timestamp_index(weights, timestamp_col, "weights")
    _validate_timestamp_alignment(prices, weights, timestamp_col, "weights")

    # Extract asset columns (all columns except timestamp)
    asset_cols = [c for c in prices.columns if c != timestamp_col]

    if not asset_cols:
        raise ValueError("prices must have at least one asset column")
    if "CASH" not in asset_cols:
        raise ValueError("prices must include CASH column")

    # Validate column alignment
    weight_cols = [c for c in weights.columns if c != timestamp_col]
    if set(asset_cols) != set(weight_cols):
        raise ValueError(f"prices and weights must have same asset columns. Got {asset_cols} vs {weight_cols}")

    # Validate row counts
    if prices.height != weights.height:
        raise ValueError(f"prices and weights must have same number of rows. Got {prices.height} vs {weights.height}")

    # Handle funding rates
    if funding_rates is None:
        funding_rates = prices.select(
            pl.col(timestamp_col),
            *[pl.lit(0.0).alias(c) for c in asset_cols],
        )
    else:
        if timestamp_col not in funding_rates.columns:
            raise ValueError(f"funding_rates must include timestamp column '{timestamp_col}'")
        funding_cols = [c for c in funding_rates.columns if c != timestamp_col]
        if set(asset_cols) != set(funding_cols):
            raise ValueError("funding_rates must have same asset columns as prices")
        if funding_rates.height != prices.height:
            raise ValueError("funding_rates must have same number of rows as prices")
        _validate_timestamp_index(funding_rates, timestamp_col, "funding_rates")
        _validate_timestamp_alignment(prices, funding_rates, timestamp_col, "funding_rates")

    # Ensure consistent column order
    prices = prices.select(timestamp_col, *asset_cols)
    weights = weights.select(timestamp_col, *asset_cols)
    funding_rates = funding_rates.select(timestamp_col, *asset_cols)

    # Validate weight sums
    _validate_weight_sums(weights, timestamp_col)

    # Extract timestamps
    timestamps = prices.get_column(timestamp_col)

    # Convert to NumPy arrays (contiguous, float64)
    price_values = prices.select(asset_cols).to_numpy().astype(np.float64, copy=False)
    weight_values = weights.select(asset_cols).to_numpy().astype(np.float64, copy=False)
    funding_values = funding_rates.select(asset_cols).to_numpy().astype(np.float64, copy=False)

    _validate_finite(weight_values, "weights")
    _validate_finite(funding_values, "funding_rates")
    non_cash_idx = [index for index, asset in enumerate(asset_cols) if asset != "CASH"]
    if allow_inactive_missing_prices:
        # Use the latest scheduled target to identify held assets. Ignored
        # targets cannot excuse missing marks on carried positions.
        selected = np.arange(len(weight_values)) // rebalance_every_bars * rebalance_every_bars
        _validate_inactive_missing_prices(price_values, weight_values[selected], asset_cols, timestamps)
    else:
        _validate_finite(price_values, "prices")
        _validate_positive_non_cash_prices(price_values, non_cash_idx)

    return EngineInputs(
        timestamps=timestamps,
        assets=asset_cols,
        prices=prices,
        weights=weights,
        funding_rates=funding_rates,
        price_values=price_values,
        weight_values=weight_values,
        funding_values=funding_values,
    )


# --------------------------------------------------------------------------- #
# Validation helpers
# --------------------------------------------------------------------------- #


def _validate_inactive_missing_prices(price_values, weight_values, assets, timestamps):
    """Allow absent marks only when no entry, carried holding, or exit needs them.

    The final target is not traded. Each earlier nonzero target requires both
    endpoint prices, including the exit mark even when the next target is zero.
    No observed price is replaced and no held return is imputed.
    """
    cash = assets.index("CASH")
    _validate_finite(price_values[:, cash], "CASH prices")
    risky = [i for i in range(len(assets)) if i != cash]
    values = price_values[:, risky]
    if np.isinf(values).any() or (values <= 0).any():
        raise BacktestContractError("Observed non-CASH prices must be finite and strictly positive.")
    required = np.zeros_like(values, dtype=bool)
    exposed = weight_values[:-1, risky] != 0
    required[:-1] |= exposed
    required[1:] |= exposed
    missing = np.argwhere(required & np.isnan(values))
    if len(missing):
        row, column = map(int, missing[0])
        raise BacktestContractError(
            f"Missing required price for {assets[risky[column]]} at {timestamps[row]} "
            f"(row {row}); entry, valuation, or exit cannot be simulated."
        )


def _validate_weight_sums(weights: pl.DataFrame, timestamp_col: str) -> None:
    """Validate that weights sum to 1.0 for each row."""
    asset_cols = [c for c in weights.columns if c != timestamp_col]
    row_sums = weights.select(asset_cols).sum_horizontal().to_numpy()

    if not np.allclose(row_sums, 1.0, rtol=0.0, atol=1e-6):
        bad_rows = np.where(~np.isclose(row_sums, 1.0, rtol=0.0, atol=1e-6))[0]
        raise BacktestContractError(
            f"Each row of weights must sum to 1.0 (model cash as a column). "
            f"Found invalid sums at rows: {bad_rows[:5].tolist()}..."
        )


def _validate_finite(values: np.ndarray, name: str) -> None:
    if not np.all(np.isfinite(values)):
        raise BacktestContractError(f"Backtest inputs require finite {name}; found non-finite values.")


def _validate_positive_non_cash_prices(price_values: np.ndarray, non_cash_idx: list[int]) -> None:
    risky = price_values[:, non_cash_idx]
    if np.any(risky <= 0.0):
        raise BacktestContractError(
            "Backtest inputs require strictly positive non-CASH prices; CASH prices are not used in price math."
        )


def _validate_timestamp_index(df: pl.DataFrame, timestamp_col: str, frame_name: str) -> None:
    """Validate timestamp index is non-null, sorted, and unique."""
    ts = df.get_column(timestamp_col)

    if ts.null_count() > 0:
        raise ValueError(f"{frame_name}.{timestamp_col} must not contain nulls")
    if not ts.is_sorted():
        raise ValueError(f"{frame_name}.{timestamp_col} must be sorted ascending")
    if ts.n_unique() != len(ts):
        raise ValueError(f"{frame_name}.{timestamp_col} must be unique")


def _validate_timestamp_alignment(
    left: pl.DataFrame,
    right: pl.DataFrame,
    timestamp_col: str,
    right_name: str,
) -> None:
    """Validate exact timestamp alignment between two frames."""
    left_ts = left.get_column(timestamp_col)
    right_ts = right.get_column(timestamp_col)
    if not left_ts.equals(right_ts):
        raise ValueError(f"{right_name}.{timestamp_col} must exactly match prices.{timestamp_col}")
