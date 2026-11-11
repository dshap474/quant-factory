"""Unit tests for mechanical parquet runtime helpers."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from data.platform.storage.parquet_runtime import (
    latest_timestamp,
    merge_frames,
    normalize_time_column,
    write_pandas_parquet_atomic,
)


def test_normalize_time_column_converts_datetime_series_to_epoch_ms():
    series = pd.Series(pd.to_datetime(["2024-01-01T00:00:00Z", "2024-01-01T00:01:00Z"], utc=True))
    result = normalize_time_column(series)
    assert list(result.astype("int64")) == [1704067200000, 1704067260000]


def test_latest_timestamp_handles_numeric_epoch_units() -> None:
    expected = pd.Timestamp("2024-01-01T00:00:00Z")

    assert latest_timestamp(pd.DataFrame({"time": [1_704_067_200]})) == expected
    assert latest_timestamp(pd.DataFrame({"time": [1_704_067_200_000]})) == expected
    assert latest_timestamp(pd.DataFrame({"time": [1_704_067_200_000_000]})) == expected
    assert latest_timestamp(pd.DataFrame({"time": [1_704_067_200_000_000_000]})) == expected


def test_normalize_time_column_outputs_milliseconds_for_numeric_epoch_units() -> None:
    expected = [1_704_067_200_000]

    assert normalize_time_column(pd.Series([1_704_067_200])).tolist() == expected
    assert normalize_time_column(pd.Series([1_704_067_200_000])).tolist() == expected
    assert normalize_time_column(pd.Series([1_704_067_200_000_000])).tolist() == expected
    assert normalize_time_column(pd.Series([1_704_067_200_000_000_000])).tolist() == expected


def test_normalize_time_column_handles_mixed_numeric_epoch_units() -> None:
    result = normalize_time_column(
        pd.Series(
            [
                1_704_067_200,
                1_704_153_600_000,
                1_704_240_000_000_000,
                1_704_326_400_000_000_000,
                None,
            ]
        )
    )

    assert result.dropna().astype("int64").tolist() == [
        1_704_067_200_000,
        1_704_153_600_000,
        1_704_240_000_000,
        1_704_326_400_000,
    ]
    assert pd.isna(result.iloc[-1])


def test_latest_timestamp_handles_mixed_numeric_epoch_units() -> None:
    frame = pd.DataFrame(
        {
            "time": [
                1_704_153_600_000,
                1_704_067_200_000_000_000,
            ]
        }
    )

    assert latest_timestamp(frame) == pd.Timestamp("2024-01-02T00:00:00Z")


def test_merge_frames_dedupes_and_keeps_latest():
    existing = pd.DataFrame({"timestamp": [1, 2], "close": [10.0, 20.0]})
    new = pd.DataFrame({"timestamp": [2, 3], "close": [25.0, 30.0]})
    merged = merge_frames(
        existing,
        new,
        dedupe_keys=["timestamp"],
        sort_columns=["timestamp"],
        index_preferred=False,
    )
    assert list(merged["timestamp"]) == [1, 2, 3]
    assert list(merged["close"]) == [10.0, 25.0, 30.0]


def test_write_pandas_parquet_atomic_replaces_target(tmp_path: Path):
    target = tmp_path / "frame.parquet"
    initial = pd.DataFrame({"value": [1, 2]})
    updated = pd.DataFrame({"value": [3, 4]})

    write_pandas_parquet_atomic(initial, target, index=False)
    write_pandas_parquet_atomic(updated, target, index=False)

    reloaded = pd.read_parquet(target)
    assert list(reloaded["value"]) == [3, 4]
