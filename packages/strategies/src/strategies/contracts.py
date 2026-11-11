"""Runtime contracts and validation helpers for strategy outputs."""

from __future__ import annotations

import numbers
import re
from typing import Any

import polars as pl

from .weights import ExecutionTiming, StrategyWeights

ID_PATTERN = re.compile(r"^[a-z][a-z0-9_\-]{0,127}$")
MEMORY_VERSION_PATTERN = re.compile(r"^v\d{3}$")


def validate_identifier(value: str, label: str) -> None:
    """Validate canonical identifier format."""
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    if not ID_PATTERN.match(value):
        raise ValueError(f"{label} must match {ID_PATTERN.pattern}. Got: {value}")


def validate_metrics(metrics: dict[str, Any], label: str = "metrics") -> None:
    """Validate metrics dict contains numeric values."""
    if not isinstance(metrics, dict):
        raise ValueError(f"{label} must be a dict")
    for key, value in metrics.items():
        if not isinstance(key, str) or not key:
            raise ValueError(f"{label} keys must be non-empty strings")
        if value is None:
            raise ValueError(f"{label}.{key} must be a number, got None")
        if not isinstance(value, numbers.Real):
            raise ValueError(
                f"{label}.{key} must be numeric, got {type(value).__name__}"
            )


def validate_memory_version(value: str) -> None:
    """Validate vNNN memory version naming."""
    if not isinstance(value, str) or not MEMORY_VERSION_PATTERN.match(value):
        raise ValueError(f"memory_version must match vNNN. Got: {value!r}")


def validate_data_range(data_range: dict[str, str], label: str = "data_range") -> None:
    """Validate data range dict has start/end string values."""
    if not isinstance(data_range, dict):
        raise ValueError(f"{label} must be a dict")
    for key in ("start", "end"):
        if key not in data_range:
            raise ValueError(f"{label} missing '{key}'")
        if not isinstance(data_range[key], str) or not data_range[key]:
            raise ValueError(f"{label}.{key} must be a non-empty string")


def _is_datetime_dtype(dtype: pl.DataType) -> bool:
    return isinstance(dtype, pl.Datetime) or dtype == pl.Date


def validate_timestamp_column(df: pl.DataFrame, column: str = "timestamp") -> None:
    """Ensure timestamp column exists and is date/datetime."""
    if column not in df.columns:
        raise ValueError(f"Missing '{column}' column")
    dtype = df[column].dtype
    if not _is_datetime_dtype(dtype):
        raise ValueError(f"'{column}' must be date/datetime dtype, got {dtype}")


def validate_numeric_column(df: pl.DataFrame, column: str) -> None:
    """Ensure a column is numeric and non-null."""
    if column not in df.columns:
        raise ValueError(f"Missing '{column}' column")
    dtype = df[column].dtype
    if not dtype.is_numeric():
        raise ValueError(f"'{column}' must be numeric, got {dtype}")
    if df[column].null_count() > 0:
        raise ValueError(f"'{column}' contains null values")


def validate_backtest_equity(df: pl.DataFrame) -> None:
    """Validate backtest equity frame."""
    validate_timestamp_column(df, "timestamp")
    validate_numeric_column(df, "equity")
    if "benchmark_equity" in df.columns:
        validate_numeric_column(df, "benchmark_equity")


def validate_strategy_weights_contract(
    weights: StrategyWeights,
    *,
    output_type: str | None = None,
    neutrality_tolerance: float = 0.01,
) -> None:
    """Validate canonical strategy weights and optional output-type invariants."""
    weights.validate()  # ExecutionTiming enforces its own timing invariants

    if output_type == "market_neutral":
        if weights.get_net_exposure().null_count():
            raise ValueError("Market-neutral output cannot be established from partial hold targets alone")
        if not weights.is_market_neutral(tolerance=neutrality_tolerance):
            raise ValueError(
                "Market-neutral strategies must keep net exposure near zero "
                f"(tolerance={neutrality_tolerance})."
            )


def execution_timing_from_mode(mode: str) -> ExecutionTiming:
    """Convert a preset execution mode into canonical execution timing."""
    if mode == "same_bar":
        return ExecutionTiming.same_bar()
    if mode == "next_bar":
        return ExecutionTiming.next_bar()
    raise ValueError(
        "execution_mode must be one of {'same_bar', 'next_bar'}"
    )
