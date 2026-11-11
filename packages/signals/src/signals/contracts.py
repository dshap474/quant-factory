"""Canonical signal output contracts."""

from __future__ import annotations

import polars as pl

from .ids import validate_identifier

REQUIRED_COLUMNS = ("timestamp", "prediction")
OPTIONAL_COLUMNS = ("asset", "model_id", "predicted_at", "run_id", "signal_name")


def validate_prediction_columns(predictions: pl.DataFrame) -> None:
    """Validate required prediction columns only."""
    if not isinstance(predictions, pl.DataFrame):
        raise TypeError("predictions must be a polars DataFrame")
    if "timestamp" not in predictions.columns:
        raise ValueError("Missing 'timestamp' column")
    timestamp_dtype = predictions["timestamp"].dtype
    if not (isinstance(timestamp_dtype, pl.Datetime) or timestamp_dtype == pl.Date):
        raise ValueError(f"'timestamp' must be date/datetime dtype, got {timestamp_dtype}")
    if "prediction" not in predictions.columns:
        raise ValueError("Missing 'prediction' column")
    prediction_dtype = predictions["prediction"].dtype
    if not prediction_dtype.is_numeric():
        raise ValueError(f"'prediction' must be numeric, got {prediction_dtype}")
    if predictions["prediction"].null_count() > 0:
        raise ValueError("'prediction' contains null values")
    if len(predictions) == 0:
        return
    if predictions["timestamp"].null_count() > 0:
        raise ValueError("'timestamp' contains null values")


def validate_prediction_frame(
    predictions: pl.DataFrame,
    *,
    signal_name: str | None = None,
) -> None:
    """Validate the canonical signal output contract."""
    validate_prediction_columns(predictions)

    if len(predictions) == 0:
        return

    key_cols = ["timestamp"]
    if "asset" in predictions.columns:
        if predictions["asset"].null_count() > 0:
            raise ValueError("'asset' contains null values")
        if not any(token in str(predictions["asset"].dtype) for token in ("Utf8", "String", "Categorical", "Enum")):
            raise ValueError(f"'asset' must be string-like, got {predictions['asset'].dtype}")
        key_cols.append("asset")

    if "model_id" in predictions.columns:
        for model_id in predictions["model_id"].drop_nulls().unique().to_list():
            validate_identifier(str(model_id), "model_id")

    if "run_id" in predictions.columns:
        for run_id in predictions["run_id"].drop_nulls().unique().to_list():
            validate_identifier(str(run_id), "run_id")

    if signal_name is not None:
        validate_identifier(signal_name, "signal_name")

    if "signal_name" in predictions.columns:
        values = [str(value) for value in predictions["signal_name"].drop_nulls().unique().to_list()]
        if not values:
            raise ValueError("'signal_name' must contain at least one non-null value when present")
        for value in values:
            validate_identifier(value, "signal_name")
        if signal_name is not None and values != [signal_name]:
            raise ValueError("predictions.signal_name must match the runner signal_id")

    if "predicted_at" in predictions.columns:
        predicted_dtype = predictions["predicted_at"].dtype
        if not (isinstance(predicted_dtype, pl.Datetime) or predicted_dtype == pl.Date):
            raise ValueError(f"'predicted_at' must be date/datetime dtype, got {predicted_dtype}")
        if predictions["predicted_at"].null_count() > 0:
            raise ValueError("'predicted_at' contains null values")

    sorted_df = predictions.sort(key_cols)
    has_duplicates = sorted_df.select(
        pl.struct(key_cols).is_duplicated().any().alias("has_duplicates")
    )["has_duplicates"][0]
    if has_duplicates:
        raise ValueError(f"duplicate keys found for {key_cols}")


validate_signal_frame = validate_prediction_frame
validate_predictions_frame = validate_prediction_frame
