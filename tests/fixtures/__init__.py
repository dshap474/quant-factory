"""Shared fixture modules for quant-factory integration tests.

This package contains reusable data generators, model factories,
and assertion helpers used across test categories.
"""

from .data_generators import (
    generate_ohlcv,
    generate_multi_asset_ohlcv,
    generate_features_from_ohlcv,
    generate_trading_weights,
)
from .assertion_helpers import (
    assert_dataframe_schema,
    assert_no_future_leakage,
    assert_timestamps_aligned,
    assert_weights_normalized,
    assert_no_null_timestamps,
    assert_monotonic_timestamps,
    assert_ohlc_constraints,
    assert_prediction_bounds,
    # E2E assertion helpers
    assert_experiment_result_valid,
    assert_artifacts_complete,
    assert_predictions_schema,
    assert_metrics_reasonable,
    assert_model_registered,
)

__all__ = [
    # Data generators
    "generate_ohlcv",
    "generate_multi_asset_ohlcv",
    "generate_features_from_ohlcv",
    "generate_trading_weights",
    # Basic assertion helpers
    "assert_dataframe_schema",
    "assert_no_future_leakage",
    "assert_timestamps_aligned",
    "assert_weights_normalized",
    "assert_no_null_timestamps",
    "assert_monotonic_timestamps",
    "assert_ohlc_constraints",
    "assert_prediction_bounds",
    # E2E assertion helpers
    "assert_experiment_result_valid",
    "assert_artifacts_complete",
    "assert_predictions_schema",
    "assert_metrics_reasonable",
    "assert_model_registered",
]

