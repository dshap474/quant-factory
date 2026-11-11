"""Tests for the public point-in-time information-availability contract.

USAGE:
    uv run pytest packages/data/tests/unit/test_information_availability.py -q
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import polars as pl
import pytest
from data.api import (
    AVAILABLE_AT_COLUMN,
    add_available_at,
    filter_available_as_of,
    validate_information_set,
)

# --------------------------------------------------------------------------- #
# Availability derivation
# --------------------------------------------------------------------------- #


def test_add_available_at_uses_latest_required_timestamp() -> None:
    frame = pl.DataFrame(
        {
            "timestamp": [datetime(2024, 1, 2), datetime(2024, 1, 3)],
            "published_at": [
                datetime(2024, 1, 2, 6, tzinfo=timezone.utc),
                datetime(2024, 1, 5, tzinfo=timezone.utc),
            ],
            "value": [1.0, 2.0],
        },
        schema_overrides={"timestamp": pl.Datetime("us")},
    )

    result = add_available_at(
        frame,
        event_time_column="timestamp",
        event_delay=timedelta(days=1),
        source_time_columns=("published_at",),
    )

    assert result.schema[AVAILABLE_AT_COLUMN] == pl.Datetime("us", "UTC")
    assert result[AVAILABLE_AT_COLUMN].to_list() == [
        datetime(2024, 1, 3, tzinfo=timezone.utc),
        datetime(2024, 1, 5, tzinfo=timezone.utc),
    ]
    assert result.columns == [*frame.columns, AVAILABLE_AT_COLUMN]
    assert AVAILABLE_AT_COLUMN not in frame.columns


@pytest.mark.parametrize(
    ("value", "dtype"),
    [
        (date(2024, 1, 2), pl.Date),
        (datetime(2024, 1, 2, 3), pl.Datetime("us")),
        (datetime(2024, 1, 2, 3, tzinfo=timezone.utc), pl.Datetime("us", "UTC")),
    ],
)
def test_add_available_at_normalizes_supported_temporal_types(
    value: date | datetime,
    dtype: pl.DataType,
) -> None:
    frame = pl.DataFrame({"event": [value]}, schema_overrides={"event": dtype})

    result = add_available_at(frame, event_time_column="event")

    assert result.schema[AVAILABLE_AT_COLUMN] == pl.Datetime("us", "UTC")


def test_add_available_at_rejects_invalid_inputs() -> None:
    event = pl.DataFrame({"event": [datetime(2024, 1, 1)]})
    with pytest.raises(ValueError, match="Missing"):
        add_available_at(event, event_time_column="missing")
    with pytest.raises(ValueError, match="Date or Datetime"):
        add_available_at(pl.DataFrame({"event": [1]}), event_time_column="event")
    with pytest.raises(ValueError, match="null"):
        add_available_at(
            pl.DataFrame({"event": [None]}, schema={"event": pl.Datetime("us")}),
            event_time_column="event",
        )
    with pytest.raises(ValueError, match="non-negative"):
        add_available_at(
            event,
            event_time_column="event",
            event_delay=timedelta(seconds=-1),
        )
    with pytest.raises(ValueError, match="already exists"):
        add_available_at(
            event.with_columns(pl.col("event").alias(AVAILABLE_AT_COLUMN)),
            event_time_column="event",
        )


# --------------------------------------------------------------------------- #
# Filtering and validation
# --------------------------------------------------------------------------- #


def test_filter_available_as_of_is_inclusive_and_preserves_unknown_only_explicitly() -> None:
    frame = pl.DataFrame(
        {
            "id": [1, 2, 3],
            AVAILABLE_AT_COLUMN: [
                datetime(2024, 1, 1, tzinfo=timezone.utc),
                datetime(2024, 1, 2, tzinfo=timezone.utc),
                None,
            ],
        },
        schema_overrides={AVAILABLE_AT_COLUMN: pl.Datetime("us", "UTC")},
    )
    cutoff = datetime(2024, 1, 1, tzinfo=timezone.utc)

    with pytest.raises(ValueError, match="null"):
        filter_available_as_of(frame, as_of=cutoff)

    result = filter_available_as_of(frame, as_of=cutoff, include_unknown=True)
    assert result["id"].to_list() == [1, 3]


def test_filter_available_as_of_rejects_naive_cutoff_and_wrong_dtype() -> None:
    aware = pl.DataFrame(
        {AVAILABLE_AT_COLUMN: [datetime(2024, 1, 1, tzinfo=timezone.utc)]},
        schema_overrides={AVAILABLE_AT_COLUMN: pl.Datetime("us", "UTC")},
    )
    with pytest.raises(ValueError, match="timezone-aware"):
        filter_available_as_of(aware, as_of=datetime(2024, 1, 1))

    naive = pl.DataFrame({AVAILABLE_AT_COLUMN: [datetime(2024, 1, 1)]})
    with pytest.raises(ValueError, match="must have dtype"):
        filter_available_as_of(naive, as_of=datetime(2024, 1, 1, tzinfo=timezone.utc))


def test_validate_information_set_allows_past_and_equal_but_rejects_future() -> None:
    frame = pl.DataFrame(
        {
            "decision_time": [
                datetime(2024, 1, 2, tzinfo=timezone.utc),
                datetime(2024, 1, 2, tzinfo=timezone.utc),
            ],
            AVAILABLE_AT_COLUMN: [
                datetime(2024, 1, 1, tzinfo=timezone.utc),
                datetime(2024, 1, 2, tzinfo=timezone.utc),
            ],
        },
        schema_overrides={
            "decision_time": pl.Datetime("us", "UTC"),
            AVAILABLE_AT_COLUMN: pl.Datetime("us", "UTC"),
        },
    )
    validate_information_set(frame, decision_time_column="decision_time")

    invalid = frame.with_columns(
        pl.when(pl.int_range(pl.len()) == 1)
        .then(pl.lit(datetime(2024, 1, 3, tzinfo=timezone.utc)))
        .otherwise(pl.col(AVAILABLE_AT_COLUMN))
        .alias(AVAILABLE_AT_COLUMN)
    )
    with pytest.raises(ValueError, match="1 rows; sample="):
        validate_information_set(invalid, decision_time_column="decision_time")


@pytest.mark.parametrize(
    "frame",
    [
        pl.DataFrame(
            {"decision_time": [None], AVAILABLE_AT_COLUMN: [datetime(2024, 1, 1, tzinfo=timezone.utc)]},
            schema_overrides={
                "decision_time": pl.Datetime("us", "UTC"),
                AVAILABLE_AT_COLUMN: pl.Datetime("us", "UTC"),
            },
        ),
        pl.DataFrame({"decision_time": [datetime(2024, 1, 1)], AVAILABLE_AT_COLUMN: [datetime(2024, 1, 1)]}),
    ],
)
def test_validate_information_set_rejects_null_or_wrong_dtype(frame: pl.DataFrame) -> None:
    with pytest.raises(ValueError):
        validate_information_set(frame, decision_time_column="decision_time")
