"""Exercise numeric selection and explicitly timed feature-panel contracts.

Usage: pytest packages/platform/signal-analysis/tests/test_feature_contracts.py
"""

from datetime import datetime, timedelta, timezone

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from signal_analysis.contracts import validate_feature_frame, validate_feature_panel

# --------------------------------------------------------------------------- #
# Explicit fixtures
# --------------------------------------------------------------------------- #


def _panel() -> pl.DataFrame:
    time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return pl.DataFrame(
        {
            "observation_id": ["A:1", "B:1", "C:1"],
            "decision_time": [time] * 3,
            "features_available_at": [time - timedelta(hours=1), time, time],
            "x": [1.0, None, float("inf")],
            "y": [float("nan"), -2.0, 3.0],
            "asset": ["A", "B", "C"],
        }
    )


# --------------------------------------------------------------------------- #
# Matrix contract
# --------------------------------------------------------------------------- #


def test_numeric_contract_preserves_observations_and_has_no_timing_claim():
    frame = _panel().select("x", "y", "asset")
    before = frame.clone()
    validate_feature_frame(frame, feature_columns=("y", "x"))
    validate_feature_frame(frame.head(0), feature_columns=["x"])
    assert_frame_equal(frame, before)


@pytest.mark.parametrize("names", [[], ["x", "x"], [""], [" x"], ["x\t"], [1], [None]])
def test_malformed_feature_selections_are_rejected(names):
    with pytest.raises(ValueError):
        validate_feature_frame(_panel(), feature_columns=names)


@pytest.mark.parametrize("names", ["x", b"x", None, {"x"}])
def test_feature_selection_requires_an_ordered_sequence(names):
    with pytest.raises(TypeError):
        validate_feature_frame(_panel(), feature_columns=names)


@pytest.mark.parametrize("name", ["absent", "asset", "decision_time"])
def test_selected_columns_must_exist_and_be_float64(name):
    with pytest.raises(TypeError):
        validate_feature_frame(_panel(), feature_columns=[name])


def test_matrix_dtype_and_table_type_are_not_coerced():
    with pytest.raises(TypeError):
        validate_feature_frame(_panel().with_columns(pl.col("x").cast(pl.Float32)), feature_columns=["x"])
    with pytest.raises(TypeError):
        validate_feature_frame({"x": [1.0]}, feature_columns=["x"])


# --------------------------------------------------------------------------- #
# Identity and availability contract
# --------------------------------------------------------------------------- #


def test_timed_panel_retains_values_and_accepts_same_time_different_observations():
    frame = _panel()
    before = frame.clone()
    validate_feature_panel(frame, feature_columns=["x", "y"])
    validate_feature_panel(frame.reverse(), feature_columns=["y", "x"])
    validate_feature_panel(frame.head(0), feature_columns=["x"])
    assert_frame_equal(frame, before)


@pytest.mark.parametrize("ids", [["A", "A", "C"], ["A", None, "C"], ["A", "", "C"], ["A", " B", "C"]])
def test_timed_panel_rejects_invalid_or_duplicate_observation_identity(ids):
    with pytest.raises(ValueError):
        validate_feature_panel(_panel().with_columns(pl.Series("observation_id", ids)), feature_columns=["x"])


@pytest.mark.parametrize("column", ["decision_time", "features_available_at"])
def test_timed_panel_requires_nonnull_exact_utc_clocks(column):
    frame = _panel()
    with pytest.raises(ValueError):
        validate_feature_panel(
            frame.with_columns(pl.lit(None, dtype=pl.Datetime("us", "UTC")).alias(column)), feature_columns=["x"]
        )
    with pytest.raises(TypeError):
        validate_feature_panel(frame.with_columns(pl.col(column).dt.replace_time_zone(None)), feature_columns=["x"])
    with pytest.raises(TypeError):
        validate_feature_panel(frame.with_columns(pl.col(column).cast(pl.Datetime("ns", "UTC"))), feature_columns=["x"])


def test_unavailable_selected_features_fail_without_retiming_rows():
    frame = _panel().with_columns(
        (pl.col("decision_time") + pl.duration(microseconds=1)).alias("features_available_at")
    )
    with pytest.raises(ValueError, match="must not follow"):
        validate_feature_panel(frame, feature_columns=["x"])


def test_plain_matrix_cannot_be_mistaken_for_identified_timed_panel():
    frame = _panel().select("x", "y")
    validate_feature_frame(frame, feature_columns=["x", "y"])
    with pytest.raises(TypeError, match="observation_id"):
        validate_feature_panel(frame, feature_columns=["x", "y"])
