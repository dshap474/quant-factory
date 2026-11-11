"""Boundary and contract tests for predeclared era labels.

Usage: ``uv run --no-sync pytest packages/platform/signal-analysis/tests/test_eras.py -q``.
"""

# --------------------------------------------------------------------------- #
# Imports and fixtures
# --------------------------------------------------------------------------- #

from datetime import datetime, timedelta, timezone

import polars as pl
import pytest

from signal_analysis.stability import assign_eras, summarize_metric_stability

UTC = pl.Datetime("us", "UTC")
T0 = datetime(2025, 1, 1, tzinfo=timezone.utc)
DAY = timedelta(days=1)
ERAS = [("e1", T0, T0 + 3 * DAY), ("e2", T0 + 3 * DAY, T0 + 6 * DAY), ("e3", T0 + 6 * DAY, T0 + 9 * DAY)]


def series(n=9):
    return pl.DataFrame(
        {"observation_time": [T0 + i * DAY for i in range(n)], "value": [float(i) for i in range(n)]},
        schema={"observation_time": UTC, "value": pl.Float64},
    )


# --------------------------------------------------------------------------- #
# Known answers
# --------------------------------------------------------------------------- #


def test_boundary_instant_belongs_to_the_later_era_and_means_are_exact():
    labelled = assign_eras(series(), time_col="observation_time", eras=ERAS)
    assert labelled["era"].to_list() == ["e1"] * 3 + ["e2"] * 3 + ["e3"] * 3
    summary = summarize_metric_stability(
        labelled.with_columns(pl.lit("ALL").alias("asset"), pl.lit("s").alias("feature"), pl.lit("ic").alias("metric")),
        group_by=["era"],
        weighting="equal",
        sample_scope="test",
    )
    assert summary["era"].to_list() == ["e1", "e2", "e3"]
    assert summary["mean"].to_list() == [1.0, 4.0, 7.0]


def test_rows_outside_every_era_get_a_null_label_and_nothing_is_dropped():
    labelled = assign_eras(series(12), time_col="observation_time", eras=ERAS[:2])
    assert labelled.height == 12
    assert labelled["era"].null_count() == 6
    assert labelled["era"].to_list()[6:] == [None] * 6


def test_gaps_between_eras_are_allowed_and_custom_label_column():
    eras = [("a", T0, T0 + DAY), ("b", T0 + 5 * DAY, T0 + 6 * DAY)]
    labelled = assign_eras(series(), time_col="observation_time", eras=eras, label_col="regime")
    assert labelled["regime"].to_list() == ["a", None, None, None, None, "b", None, None, None]


# --------------------------------------------------------------------------- #
# Contracts
# --------------------------------------------------------------------------- #


def test_overlapping_and_unordered_eras_raise():
    with pytest.raises(ValueError, match="overlaps or precedes"):
        assign_eras(
            series(), time_col="observation_time", eras=[("a", T0, T0 + 4 * DAY), ("b", T0 + 3 * DAY, T0 + 6 * DAY)]
        )
    with pytest.raises(ValueError, match="overlaps or precedes"):
        assign_eras(series(), time_col="observation_time", eras=[ERAS[1], ERAS[0]])


def test_bad_eras_raise():
    with pytest.raises(ValueError, match="start < end"):
        assign_eras(series(), time_col="observation_time", eras=[("a", T0 + DAY, T0)])
    with pytest.raises(ValueError, match="duplicate era label"):
        assign_eras(series(), time_col="observation_time", eras=[("a", T0, T0 + DAY), ("a", T0 + DAY, T0 + 2 * DAY)])
    with pytest.raises(TypeError, match="UTC offset zero"):
        assign_eras(series(), time_col="observation_time", eras=[("a", datetime(2025, 1, 1), T0 + DAY)])
    with pytest.raises(TypeError):
        assign_eras(
            series().with_columns(pl.col("observation_time").dt.replace_time_zone(None)),
            time_col="observation_time",
            eras=ERAS,
        )
    with pytest.raises(ValueError, match="already has"):
        assign_eras(series().with_columns(pl.lit("x").alias("era")), time_col="observation_time", eras=ERAS)
    with pytest.raises(ValueError):
        assign_eras(series(), time_col="observation_time", eras=[])
