"""Validate and normalize tabular training input.

Usage::

    prepared = validate_training_data(frame, config)
    X = prepared.frame.loc[:, prepared.feature_cols]
    y = prepared.frame[prepared.target_col]

The helper deliberately owns only the package boundary concerns: a pandas input,
required columns, stable row identity, UTC timestamps, and deterministic ordering.
It does not impute or otherwise learn from feature values.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import numpy as np
import pandas as pd
from pandas.api.types import is_numeric_dtype

from .config import TrainingConfig

# --------------------------------------------------------------------------- #
# Constants and data contracts
# --------------------------------------------------------------------------- #

_INTERNAL_ROW_ID = "__ml_engine_row_id__"
_UTC = "UTC"


@dataclass(frozen=True)
class PreparedData:
    """Immutable description of a validated, timestamp-ordered data frame.

    ``frame`` is a private copy of the caller's input with stable row identity
    and normalized timestamps.
    """

    frame: pd.DataFrame
    feature_cols: tuple[str, ...]
    target_col: str
    timestamp_col: str
    row_id_col: str
    entity_col: str | None
    period_col: str
    target_end_col: str | None
    training_cutoff: pd.Timestamp | None


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #


def _required_columns(config: TrainingConfig) -> tuple[str, ...]:
    """Return required columns in deterministic order, without duplicates."""

    values = [*config.feature_cols, config.target_col, config.timestamp_col]
    for value in (
        config.row_id_col,
        config.entity_col,
        config.period_col,
        config.target_end_col,
        config.weight_col,
    ):
        if value is not None:
            values.append(value)
    return tuple(dict.fromkeys(values))


def _normalize_utc(values: pd.Series, name: str, *, allow_null: bool = False) -> pd.Series:
    """Parse a timestamp series as timezone-aware UTC, failing closed."""

    if not allow_null and values.isna().any():
        raise ValueError(f"{name} must not contain null timestamps")
    try:
        normalized = pd.to_datetime(values, utc=True, errors="raise")
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must contain parseable timestamps") from exc
    if not isinstance(normalized.dtype, pd.DatetimeTZDtype):
        raise TypeError(f"{name} must normalize to timezone-aware UTC")
    return normalized


def _normalized_cutoff(cutoff: Any) -> pd.Timestamp | None:
    """Normalize an optional training cutoff to UTC."""

    if cutoff is None:
        return None
    try:
        value = pd.Timestamp(cutoff)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("training_cutoff must be a parseable timestamp") from exc
    if pd.isna(value):
        raise ValueError("training_cutoff must not be null")
    assert isinstance(value, pd.Timestamp)
    if value.tzinfo is None:
        return value.tz_localize(_UTC)
    return value.tz_convert(_UTC)


def _check_numeric_features(frame: pd.DataFrame, feature_cols: tuple[str, ...]) -> None:
    """Reject unsupported feature dtypes and all-null feature columns."""

    empty = [col for col in feature_cols if frame[col].isna().all()]
    if empty:
        raise ValueError(f"Feature columns are entirely null: {empty}")

    bad_dtype = [col for col in feature_cols if not is_numeric_dtype(frame[col])]
    if bad_dtype:
        raise TypeError(f"Configured features must be numeric: {bad_dtype}")

    # Infinity is not a missing value and silently converting it would violate
    # the strict boundary.  Callers may explicitly map it before this API.
    numeric = frame.loc[:, list(feature_cols)].select_dtypes(include=[np.number])
    if not numeric.empty and np.isinf(numeric.to_numpy(dtype=float, copy=False)).any():
        raise ValueError("Configured features must not contain infinite values")


def _assign_internal_row_id(frame: pd.DataFrame) -> str:
    """Add a deterministic internal row ID and return its column name."""

    name = _INTERNAL_ROW_ID
    suffix = 1
    while name in frame.columns:
        name = f"{_INTERNAL_ROW_ID}_{suffix}"
        suffix += 1
    frame[name] = np.arange(len(frame), dtype=np.int64)
    return name


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def validate_training_data(dataset: pd.DataFrame, config: TrainingConfig) -> PreparedData:
    """Validate, normalize, and stably sort a supervised training frame.

    Naive timestamps are interpreted as UTC.  Rows after ``training_cutoff``
    are excluded from the returned training universe, while rows with unknown
    targets inside that universe remain available for inference-oriented
    callers and are marked by :attr:`PreparedData.eligible_target_mask`.
    """

    if not isinstance(dataset, pd.DataFrame):
        raise TypeError("Training input must be a pandas.DataFrame")
    if not isinstance(config, TrainingConfig):
        raise TypeError("config must be a TrainingConfig")
    if not dataset.columns.is_unique:
        raise ValueError("Training input must not contain duplicate column names")

    required = _required_columns(config)
    missing = [column for column in required if column not in dataset.columns]
    if missing:
        raise ValueError(f"Training input is missing required columns: {missing}")

    frame = dataset.copy(deep=True)
    frame["__ml_engine_original_position__"] = np.arange(len(frame), dtype=np.int64)
    feature_cols = config.feature_cols
    target_col = config.target_col
    timestamp_col = config.timestamp_col
    row_id_col = config.row_id_col
    entity_col = config.entity_col
    period_col = config.period_col or timestamp_col
    target_end_col = config.target_end_col

    if row_id_col is None:
        row_id_col = _assign_internal_row_id(frame)
    else:
        if frame[row_id_col].isna().any():
            raise ValueError(f"row_id_col {row_id_col!r} must not contain null values")
        if frame[row_id_col].duplicated().any():
            raise ValueError(f"row_id_col {row_id_col!r} must be unique")

    if frame[row_id_col].isna().any() or frame[row_id_col].duplicated().any():
        raise ValueError("Stable row identity must be non-null and unique")

    frame[timestamp_col] = _normalize_utc(frame[timestamp_col], timestamp_col)
    if target_end_col is not None:
        frame[target_end_col] = _normalize_utc(
            frame[target_end_col], target_end_col, allow_null=True
        )

    cutoff = _normalized_cutoff(config.training_cutoff)
    if cutoff is not None:
        frame = frame.loc[frame[timestamp_col] <= cutoff].copy()
    if frame.empty:
        raise ValueError("No rows remain after applying training_cutoff")

    _check_numeric_features(frame, feature_cols)
    if frame[target_col].isna().all():
        raise ValueError("Target column is entirely null")

    if entity_col is not None and frame.duplicated([entity_col, timestamp_col, row_id_col]).any():
        raise ValueError("Duplicate (entity, timestamp, row_id) identity")

    frame = frame.sort_values(
        [timestamp_col, "__ml_engine_original_position__"], kind="mergesort"
    ).reset_index(drop=True)
    frame = frame.drop(columns="__ml_engine_original_position__")

    return PreparedData(
        frame=frame,
        feature_cols=feature_cols,
        target_col=target_col,
        timestamp_col=timestamp_col,
        row_id_col=row_id_col,
        entity_col=entity_col,
        period_col=period_col,
        target_end_col=target_end_col,
        training_cutoff=cutoff,
    )
