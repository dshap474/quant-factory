"""Mechanical information-availability helpers for point-in-time data.

USAGE:
    frame = add_available_at(
        frame,
        event_time_column="timestamp",
        event_delay=timedelta(days=1),
        source_time_columns=("published_at",),
    )
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Sequence

import polars as pl

AVAILABLE_AT_COLUMN = "available_at"
_UTC_DATETIME = pl.Datetime("us", "UTC")

# --------------------------------------------------------------------------- #
# Validation and normalization
# --------------------------------------------------------------------------- #


def _require_columns(frame: pl.DataFrame, columns: Sequence[str]) -> None:
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")


def _as_utc(column: str, dtype: pl.DataType, *, assume_time_zone: str) -> pl.Expr:
    expression = pl.col(column)
    if dtype == pl.Date:
        return expression.cast(pl.Datetime("us")).dt.replace_time_zone(assume_time_zone).dt.convert_time_zone("UTC")
    if not isinstance(dtype, pl.Datetime):
        raise ValueError(f"Column {column!r} must be Date or Datetime, got {dtype}")
    if dtype.time_zone is None:
        return expression.cast(pl.Datetime("us")).dt.replace_time_zone(assume_time_zone).dt.convert_time_zone("UTC")
    return expression.cast(pl.Datetime("us", dtype.time_zone)).dt.convert_time_zone("UTC")


def _require_utc_datetime(frame: pl.DataFrame, column: str) -> None:
    _require_columns(frame, [column])
    if frame.schema[column] != _UTC_DATETIME:
        raise ValueError(f"Column {column!r} must have dtype {_UTC_DATETIME}, got {frame.schema[column]}")


# --------------------------------------------------------------------------- #
# Availability derivation
# --------------------------------------------------------------------------- #


def add_available_at(
    frame: pl.DataFrame,
    *,
    event_time_column: str,
    event_delay: timedelta = timedelta(0),
    source_time_columns: Sequence[str] = (),
    output_column: str = AVAILABLE_AT_COLUMN,
    assume_time_zone: str = "UTC",
) -> pl.DataFrame:
    """Add the earliest UTC timestamp at which each complete row was knowable."""
    if event_delay < timedelta(0):
        raise ValueError("event_delay must be non-negative")
    if output_column in frame.columns:
        raise ValueError(f"Output column {output_column!r} already exists")

    input_columns = [event_time_column, *source_time_columns]
    _require_columns(frame, input_columns)
    if frame.get_column(event_time_column).null_count():
        raise ValueError(f"Event-time column {event_time_column!r} contains null values")

    candidates = [
        _as_utc(event_time_column, frame.schema[event_time_column], assume_time_zone=assume_time_zone)
        + pl.duration(microseconds=event_delay // timedelta(microseconds=1))
    ]
    candidates.extend(
        _as_utc(column, frame.schema[column], assume_time_zone=assume_time_zone) for column in source_time_columns
    )
    return frame.with_columns(pl.max_horizontal(candidates).cast(_UTC_DATETIME).alias(output_column))


# --------------------------------------------------------------------------- #
# Point-in-time filtering and validation
# --------------------------------------------------------------------------- #


def filter_available_as_of(
    frame: pl.DataFrame,
    *,
    as_of: datetime,
    available_at_column: str = AVAILABLE_AT_COLUMN,
    include_unknown: bool = False,
) -> pl.DataFrame:
    """Keep observations known at an inclusive, timezone-aware cutoff."""
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must be timezone-aware")
    _require_utc_datetime(frame, available_at_column)

    availability = pl.col(available_at_column)
    if not include_unknown and frame.get_column(available_at_column).null_count():
        raise ValueError(f"Availability column {available_at_column!r} contains null values")
    cutoff = as_of.astimezone(timezone.utc)
    predicate = availability <= pl.lit(cutoff).cast(_UTC_DATETIME)
    if include_unknown:
        predicate = predicate | availability.is_null()
    return frame.filter(predicate)


def validate_information_set(
    frame: pl.DataFrame,
    *,
    decision_time_column: str,
    available_at_column: str = AVAILABLE_AT_COLUMN,
) -> None:
    """Reject rows that use information after their decision timestamp."""
    _require_utc_datetime(frame, decision_time_column)
    _require_utc_datetime(frame, available_at_column)
    for column in (decision_time_column, available_at_column):
        if frame.get_column(column).null_count():
            raise ValueError(f"Timestamp column {column!r} contains null values")

    violations = frame.filter(pl.col(available_at_column) > pl.col(decision_time_column))
    if violations.is_empty():
        return
    sample = violations.select(decision_time_column, available_at_column).head(5).to_dicts()
    raise ValueError(f"Information-set validation failed for {violations.height} rows; sample={sample}")


__all__ = [
    "AVAILABLE_AT_COLUMN",
    "add_available_at",
    "filter_available_as_of",
    "validate_information_set",
]
