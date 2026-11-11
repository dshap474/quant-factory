"""Custom assertion helpers for quant-factory integration tests.

Provides specialized assertions for validating cross-package data contracts,
time-series integrity, and financial data constraints.

Usage:
    from fixtures import assert_dataframe_schema, assert_no_future_leakage

    assert_dataframe_schema(df, required_columns=["timestamp", "close"])
    assert_no_future_leakage(features_df, target_series)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

import numpy as np
import pandas as pd
import polars as pl

if TYPE_CHECKING:
    pass


def assert_dataframe_schema(
    df: pl.DataFrame | pd.DataFrame,
    required_columns: Sequence[str],
    optional_columns: Sequence[str] | None = None,
    allow_extra: bool = True,
) -> None:
    """Assert that a DataFrame has the expected schema.

    Args:
        df: DataFrame to validate
        required_columns: Columns that must be present
        optional_columns: Columns that may be present (not required)
        allow_extra: Whether extra columns are allowed

    Raises:
        AssertionError: If schema validation fails
    """
    if isinstance(df, pl.DataFrame):
        actual_columns = set(df.columns)
    else:
        actual_columns = set(df.columns)

    required = set(required_columns)
    optional = set(optional_columns) if optional_columns else set()
    expected = required | optional

    # Check required columns
    missing = required - actual_columns
    if missing:
        raise AssertionError(
            f"Missing required columns: {missing}. "
            f"Found columns: {sorted(actual_columns)}"
        )

    # Check for unexpected columns
    if not allow_extra:
        extra = actual_columns - expected
        if extra:
            raise AssertionError(
                f"Unexpected columns found: {extra}. "
                f"Expected only: {sorted(expected)}"
            )


def assert_no_future_leakage(
    features: pd.DataFrame,
    target: pd.Series,
    max_correlation: float = 0.99,
) -> None:
    """Assert that features don't contain future information about the target.

    Checks for suspiciously high correlation between features and target,
    which may indicate look-ahead bias.

    Args:
        features: Feature DataFrame
        target: Target Series (must be aligned with features)
        max_correlation: Maximum allowed correlation before raising

    Raises:
        AssertionError: If any feature has suspiciously high correlation
    """
    for col in features.columns:
        if features[col].dtype in [np.float64, np.float32, np.int64, np.int32]:
            corr = features[col].corr(target)
            if abs(corr) > max_correlation:
                raise AssertionError(
                    f"Feature '{col}' has suspiciously high correlation with target "
                    f"({corr:.4f}). This may indicate future leakage."
                )


def assert_timestamps_aligned(
    *dfs: pl.DataFrame | pd.DataFrame,
    timestamp_col: str = "timestamp",
) -> None:
    """Assert that multiple DataFrames have aligned timestamps.

    Args:
        *dfs: DataFrames to check
        timestamp_col: Name of timestamp column

    Raises:
        AssertionError: If timestamps are not aligned
    """
    if len(dfs) < 2:
        return

    def get_timestamps(df):
        if isinstance(df, pl.DataFrame):
            return set(df[timestamp_col].to_list())
        else:
            return set(df[timestamp_col].tolist())

    reference_ts = get_timestamps(dfs[0])
    for i, df in enumerate(dfs[1:], start=1):
        other_ts = get_timestamps(df)
        if reference_ts != other_ts:
            missing = reference_ts - other_ts
            extra = other_ts - reference_ts
            raise AssertionError(
                f"DataFrame {i} has misaligned timestamps. "
                f"Missing {len(missing)} timestamps, {len(extra)} extra timestamps."
            )


def assert_weights_normalized(
    weights: np.ndarray | pd.Series | pd.DataFrame,
    tolerance: float = 1e-6,
    allow_short: bool = True,
) -> None:
    """Assert that trading weights are properly normalized.

    Args:
        weights: Trading weights (array, Series, or DataFrame)
        tolerance: Numerical tolerance for sum check
        allow_short: Whether negative weights (short positions) are allowed

    Raises:
        AssertionError: If weights are not normalized
    """
    if isinstance(weights, pd.DataFrame):
        weights = weights.values
    elif isinstance(weights, pd.Series):
        weights = weights.values

    if weights.ndim == 1:
        weights = weights.reshape(-1, 1)

    # Check for NaN
    if np.isnan(weights).any():
        raise AssertionError("Weights contain NaN values")

    # Check sum (absolute values should sum to ~1 for each row)
    abs_sums = np.abs(weights).sum(axis=1)
    if not np.allclose(abs_sums, 1.0, atol=tolerance):
        bad_rows = np.where(~np.isclose(abs_sums, 1.0, atol=tolerance))[0]
        raise AssertionError(
            f"Weights not normalized at rows {bad_rows[:5]}... "
            f"Sums: {abs_sums[bad_rows[:5]]}"
        )

    # Check for short positions if not allowed
    if not allow_short and (weights < 0).any():
        raise AssertionError("Negative weights found but short positions not allowed")


def assert_no_null_timestamps(
    df: pl.DataFrame | pd.DataFrame,
    timestamp_col: str = "timestamp",
) -> None:
    """Assert that timestamp column has no null values.

    Args:
        df: DataFrame to check
        timestamp_col: Name of timestamp column

    Raises:
        AssertionError: If null timestamps are found
    """
    if isinstance(df, pl.DataFrame):
        null_count = df[timestamp_col].null_count()
    else:
        null_count = df[timestamp_col].isna().sum()

    if null_count > 0:
        raise AssertionError(f"Found {null_count} null values in {timestamp_col}")


def assert_monotonic_timestamps(
    df: pl.DataFrame | pd.DataFrame,
    timestamp_col: str = "timestamp",
    strict: bool = True,
) -> None:
    """Assert that timestamps are monotonically increasing.

    Args:
        df: DataFrame to check
        timestamp_col: Name of timestamp column
        strict: If True, timestamps must be strictly increasing (no duplicates)

    Raises:
        AssertionError: If timestamps are not monotonic
    """
    if isinstance(df, pl.DataFrame):
        ts = df[timestamp_col].to_pandas()
    else:
        ts = df[timestamp_col]

    if strict:
        is_monotonic = ts.is_monotonic_increasing and ts.is_unique
        condition = "strictly monotonically increasing"
    else:
        is_monotonic = ts.is_monotonic_increasing
        condition = "monotonically increasing"

    if not is_monotonic:
        raise AssertionError(f"Timestamps are not {condition}")


def assert_ohlc_constraints(
    df: pl.DataFrame | pd.DataFrame,
) -> None:
    """Assert OHLC price constraints are satisfied.

    Validates:
        - low <= open, close <= high
        - All prices are positive
        - No NaN values

    Args:
        df: DataFrame with open, high, low, close columns

    Raises:
        AssertionError: If OHLC constraints are violated
    """
    if isinstance(df, pl.DataFrame):
        df = df.to_pandas()

    # Check for required columns
    required = ["open", "high", "low", "close"]
    missing = set(required) - set(df.columns)
    if missing:
        raise AssertionError(f"Missing OHLC columns: {missing}")

    # Check for NaN
    for col in required:
        if df[col].isna().any():
            raise AssertionError(f"NaN values found in {col}")

    # Check positivity
    for col in required:
        if (df[col] <= 0).any():
            raise AssertionError(f"Non-positive values found in {col}")

    # Check low <= open, close
    if (df["low"] > df["open"]).any():
        raise AssertionError("low > open violation found")
    if (df["low"] > df["close"]).any():
        raise AssertionError("low > close violation found")

    # Check open, close <= high
    if (df["open"] > df["high"]).any():
        raise AssertionError("open > high violation found")
    if (df["close"] > df["high"]).any():
        raise AssertionError("close > high violation found")


def assert_prediction_bounds(
    predictions: np.ndarray | pd.Series,
    min_val: float | None = None,
    max_val: float | None = None,
) -> None:
    """Assert that predictions are within expected bounds.

    Args:
        predictions: Prediction values
        min_val: Minimum allowed value (inclusive)
        max_val: Maximum allowed value (inclusive)

    Raises:
        AssertionError: If predictions are out of bounds
    """
    if isinstance(predictions, pd.Series):
        predictions = predictions.values

    # Check for NaN
    if np.isnan(predictions).any():
        nan_count = np.isnan(predictions).sum()
        raise AssertionError(f"Predictions contain {nan_count} NaN values")

    # Check bounds
    if min_val is not None and (predictions < min_val).any():
        actual_min = predictions.min()
        raise AssertionError(f"Predictions below minimum {min_val}: min={actual_min}")

    if max_val is not None and (predictions > max_val).any():
        actual_max = predictions.max()
        raise AssertionError(f"Predictions above maximum {max_val}: max={actual_max}")


# =============================================================================
# E2E Test Assertions
# =============================================================================


def assert_experiment_result_valid(result) -> None:
    """Assert ExperimentResult has all expected fields.

    Args:
        result: ExperimentResult from ExperimentRunner.run()

    Raises:
        AssertionError: If result is missing required fields or has invalid values.
    """
    assert result is not None, "ExperimentResult is None"
    assert result.model_id is not None, "model_id is None"
    assert result.signal_name is not None, "signal_name is None"
    assert result.cv_metrics is not None, "cv_metrics is None"
    assert result.backtest_metrics is not None, "backtest_metrics is None"
    assert result.predictions is not None, "predictions is None"

    # Check predictions have data
    assert len(result.predictions) > 0, "predictions DataFrame is empty"

    # Check artifacts path if available
    if result.artifacts_path is not None:
        from pathlib import Path
        assert Path(result.artifacts_path).exists(), (
            f"artifacts_path does not exist: {result.artifacts_path}"
        )


def assert_artifacts_complete(artifacts_path) -> None:
    """Assert all expected artifact files exist.

    Args:
        artifacts_path: Path to artifacts directory

    Raises:
        AssertionError: If any required artifact file is missing.
    """
    from pathlib import Path

    artifacts_path = Path(artifacts_path)
    assert artifacts_path.exists(), f"Artifacts directory does not exist: {artifacts_path}"

    # Required files
    required_files = ["config.json", "metrics.json"]
    for filename in required_files:
        filepath = artifacts_path / filename
        assert filepath.exists(), f"Missing required artifact: {filename}"

    # Optional but expected files
    optional_files = ["predictions.parquet", "model.pkl", "feature_state.json"]
    for filename in optional_files:
        filepath = artifacts_path / filename
        if not filepath.exists():
            import warnings
            warnings.warn(f"Optional artifact not found: {filename}")


def assert_predictions_schema(predictions: pl.DataFrame) -> None:
    """Assert predictions DataFrame has correct schema.

    Args:
        predictions: Predictions DataFrame from ExperimentRunner

    Raises:
        AssertionError: If schema is incorrect.
    """
    required_cols = {"timestamp", "prediction"}
    actual_cols = set(predictions.columns)
    missing = required_cols - actual_cols

    assert not missing, f"Missing prediction columns: {missing}"

    # Check timestamp is datetime
    ts_dtype = predictions["timestamp"].dtype
    assert ts_dtype in [pl.Datetime("us"), pl.Datetime("ns"), pl.Date], (
        f"timestamp has wrong dtype: {ts_dtype}"
    )

    # Check prediction is numeric
    pred_dtype = predictions["prediction"].dtype
    assert pred_dtype in [pl.Float64, pl.Float32, pl.Int64, pl.Int32], (
        f"prediction has wrong dtype: {pred_dtype}"
    )


def assert_metrics_reasonable(
    metrics: dict[str, float],
    min_sharpe: float = -5.0,
    max_sharpe: float = 5.0,
) -> None:
    """Assert metrics are within reasonable bounds.

    Validates that computed metrics are not obviously wrong
    (e.g., Sharpe ratio of 100 indicates a bug).

    Args:
        metrics: Dictionary of metric name -> value
        min_sharpe: Minimum reasonable Sharpe ratio
        max_sharpe: Maximum reasonable Sharpe ratio

    Raises:
        AssertionError: If metrics are outside reasonable bounds.
    """
    if "sharpe" in metrics:
        sharpe = metrics["sharpe"]
        if sharpe is not None and np.isfinite(sharpe):
            assert min_sharpe <= sharpe <= max_sharpe, (
                f"Sharpe ratio {sharpe} outside reasonable bounds [{min_sharpe}, {max_sharpe}]"
            )

    # Check correlation bounds if present
    if "corr_mean" in metrics:
        corr = metrics["corr_mean"]
        if corr is not None and np.isfinite(corr):
            assert -1 <= corr <= 1, f"Correlation {corr} outside [-1, 1]"


def assert_model_registered(
    registry,
    model_id: str,
    expected_status=None,
) -> None:
    """Assert model is registered with expected status.

    Args:
        registry: ModelRegistry instance
        model_id: ID of model to check
        expected_status: Expected ModelStatus (optional)

    Raises:
        AssertionError: If model not found or status doesn't match.
    """
    model = registry.get(model_id)
    assert model is not None, f"Model {model_id} not found in registry"

    if expected_status is not None:
        assert model.status == expected_status, (
            f"Model {model_id} has status {model.status}, expected {expected_status}"
        )
