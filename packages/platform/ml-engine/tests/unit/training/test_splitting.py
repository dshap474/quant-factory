"""Focused tests for immutable chronological fold planning.

Usage::

    pytest tests/unit/training/test_splitting.py

The fixtures intentionally include duplicate timestamps and exact target-end
boundaries so row-count and off-by-one leakage regressions fail loudly.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports and fixtures
# --------------------------------------------------------------------------- #
from dataclasses import FrozenInstanceError

import pandas as pd
import pytest

from ml_engine.training.config import SplitConfig
from ml_engine.training.methodologies import (
    Fold,
    FoldPlan,
    build_fold_plan,
    build_holdout_plan,
    build_walk_forward_plan,
)


def _frame(rows: int = 10) -> pd.DataFrame:
    """Return deterministic daily rows with stable IDs and label endpoints."""

    timestamps = pd.date_range("2024-01-01", periods=rows, freq="D", tz="UTC")
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "row_id": [f"row-{index}" for index in range(rows)],
            "period": [f"p{index // 2}" for index in range(rows)],
            "target_end": timestamps + pd.Timedelta(days=1),
        }
    )


def _plan(frame: pd.DataFrame, config: SplitConfig, **kwargs: object) -> FoldPlan:
    """Build a plan using the fixture's explicit identity columns."""

    planner = (
        build_holdout_plan if config.kind == "chronological_holdout" else build_walk_forward_plan
    )
    return planner(
        frame,
        config,
        timestamp_col="timestamp",
        row_id_col="row_id",
        **kwargs,
    )


# --------------------------------------------------------------------------- #
# Chronological policies
# --------------------------------------------------------------------------- #


def test_build_fold_plan_is_publicly_exported() -> None:
    """The shared planner is available at the stable methodologies boundary."""

    assert callable(build_fold_plan)


def test_holdout_is_one_complete_train_eval_window_with_embargo() -> None:
    """Holdout uses final evaluation periods and leaves the configured gap."""

    plan = _plan(_frame(8), SplitConfig("chronological_holdout", 3, 2, embargo_periods=1))

    assert len(plan) == 1
    fold = plan[0]
    assert fold.fold == 0
    assert fold.train_indices == (0, 1, 2, 3, 4)
    assert fold.eval_indices == (6, 7)
    assert fold.train_count == 5
    assert fold.eval_count == 2
    assert fold.embargo_start == pd.Timestamp("2024-01-06", tz="UTC")
    assert fold.embargo_end == pd.Timestamp("2024-01-06", tz="UTC")


def test_expanding_and_rolling_have_deterministic_disjoint_evaluation_rows() -> None:
    """Expanding grows while rolling keeps a bounded training window."""

    frame = _frame(10)
    expanding = _plan(frame, SplitConfig("expanding", 3, 2, step_periods=2, embargo_periods=1))
    rolling = _plan(
        frame,
        SplitConfig("rolling", 3, 2, step_periods=2, train_periods=3, embargo_periods=1),
    )

    assert [(fold.train_indices, fold.eval_indices) for fold in expanding] == [
        ((0, 1, 2), (4, 5)),
        ((0, 1, 2, 3, 4), (6, 7)),
        ((0, 1, 2, 3, 4, 5, 6), (8, 9)),
    ]
    assert [(fold.train_indices, fold.eval_indices) for fold in rolling] == [
        ((0, 1, 2), (4, 5)),
        ((2, 3, 4), (6, 7)),
        ((4, 5, 6), (8, 9)),
    ]
    assert all(
        not set(left.eval_indices).intersection(right.eval_indices)
        for index, left in enumerate(expanding)
        for right in expanding[index + 1 :]
    )


def test_rolling_starts_after_its_full_training_window() -> None:
    """A rolling window may exceed its minimum usable-period requirement."""

    plan = _plan(
        _frame(12),
        SplitConfig("rolling", 3, 2, step_periods=2, train_periods=5),
    )

    assert plan[0].train_indices == (0, 1, 2, 3, 4)
    assert plan[0].eval_indices == (5, 6)


def test_expanding_can_include_one_partial_final_evaluation_window() -> None:
    """An explicit partial-window policy assigns all trailing periods once."""

    plan = _plan(
        _frame(11),
        SplitConfig(
            "expanding",
            3,
            3,
            step_periods=3,
            include_partial_final_window=True,
        ),
    )

    assert [fold.eval_indices for fold in plan] == [(3, 4, 5), (6, 7, 8), (9, 10)]


def test_timestamp_bounds_are_nanoseconds_for_lower_resolution_inputs() -> None:
    """Microsecond-backed pandas timestamps must not be interpreted as nanoseconds."""

    frame = _frame(6)
    frame["timestamp"] = frame["timestamp"].astype("datetime64[us, UTC]")
    plan = _plan(frame, SplitConfig("expanding", 3, 2))

    assert plan[0].eval_start == pd.Timestamp("2024-01-04", tz="UTC")
    assert plan[0].eval_end == pd.Timestamp("2024-01-05", tz="UTC")


def test_period_units_group_duplicate_rows_instead_of_counting_rows() -> None:
    """A configured period column makes each period one split unit."""

    frame = _frame(8)
    plan = _plan(
        frame,
        SplitConfig("expanding", 2, 1),
        period_col="period",
    )

    assert len(plan) == 2
    assert plan[0].train_indices == (0, 1, 2, 3)
    assert plan[0].eval_indices == (4, 5)
    assert plan.unit == "period"


def test_numerai_walk_forward_geometry_is_explicit() -> None:
    """Numerai-style era lengths and embargoes map to the intended windows."""

    timestamps = pd.date_range("2020-01-01", periods=780, freq="D", tz="UTC")
    frame = pd.DataFrame(
        {
            "timestamp": timestamps,
            "row_id": range(780),
            "era": range(1, 781),
            "target_end": timestamps + pd.Timedelta(days=1),
        }
    )
    plan = _plan(
        frame,
        SplitConfig(
            "purged",
            min_train_periods=148,
            eval_periods=156,
            step_periods=156,
            embargo_periods=8,
        ),
        period_col="era",
        target_end_col="target_end",
    )

    assert len(plan) == 4
    assert plan[0].train_indices == tuple(range(148))
    assert plan[0].eval_indices == tuple(range(156, 312))
    assert plan[-1].eval_indices == tuple(range(624, 780))


# --------------------------------------------------------------------------- #
# Purging and fail-closed invariants
# --------------------------------------------------------------------------- #


def test_purged_excludes_target_end_equal_to_eval_start() -> None:
    """Closed label intervals treat target_end == eval_start as overlapping."""

    frame = _frame(7)
    frame.loc[1, "target_end"] = frame.loc[2, "timestamp"]
    plan = _plan(
        frame,
        SplitConfig("purged", 1, 1),
        period_col="period",
        target_end_col="target_end",
    )

    first = plan[0]
    assert first.eval_indices == (2, 3)
    assert first.train_indices == (0,)
    assert first.purge_start == frame.loc[1, "timestamp"]
    assert first.purge_end == frame.loc[2, "timestamp"]
    assert all(frame.loc[index, "target_end"] < first.eval_start for index in first.train_indices)


def test_closed_purge_boundary_retains_endpoint_at_evaluation_start() -> None:
    """The opt-in closed rule admits an endpoint observable at the boundary."""

    frame = _frame(6)
    frame["target_end"] = frame["timestamp"] + pd.Timedelta(days=10)
    frame.loc[0, "target_end"] = frame.loc[1, "timestamp"]

    strict = _plan(
        frame,
        SplitConfig("purged", 1, 1),
        target_end_col="target_end",
    )
    closed = _plan(
        frame,
        SplitConfig("purged", 1, 1, purge_boundary="closed"),
        target_end_col="target_end",
    )

    assert strict[0].eval_indices == (2,)
    assert closed[0].eval_indices == (1,)
    assert closed[0].train_indices == (0,)
    assert frame.loc[closed[0].train_indices[0], "target_end"] == closed[0].eval_start


def test_pinned_first_evaluation_period_uses_exact_requested_boundary() -> None:
    """A pinned fold skeleton does not search for an earlier usable boundary."""

    frame = _frame(8)
    frame["target_end"] = frame["timestamp"]
    plan = _plan(
        frame,
        SplitConfig("purged", 2, 2, first_eval_period=4),
        target_end_col="target_end",
    )

    assert plan[0].train_indices == (0, 1, 2, 3)
    assert plan[0].eval_indices == (4, 5)


def test_pinned_first_evaluation_period_fails_closed_on_invalid_coverage() -> None:
    """Pinned boundaries reject out-of-range indices and insufficient retained periods."""

    frame = _frame(6)
    frame["target_end"] = frame["timestamp"] + pd.Timedelta(days=10)

    with pytest.raises(ValueError, match="first_eval_period"):
        _plan(
            frame,
            SplitConfig("purged", 1, 1, first_eval_period=6),
            target_end_col="target_end",
        )
    with pytest.raises(ValueError, match="min_train_periods"):
        _plan(
            frame,
            SplitConfig("purged", 1, 1, first_eval_period=2),
            target_end_col="target_end",
        )


def test_null_target_end_rows_are_never_trainable_but_remain_evaluable() -> None:
    """Score-only periods do not satisfy training coverage or disappear from evaluation."""

    frame = _frame(7)
    frame["target_end"] = frame["timestamp"]
    frame.loc[[1, 6], "target_end"] = pd.NaT
    plan = _plan(
        frame,
        SplitConfig("purged", 2, 1, include_partial_final_window=True),
        target_end_col="target_end",
    )

    assert plan[0].eval_indices == (3,)
    assert plan[0].train_indices == (0, 2)
    assert all(1 not in fold.train_indices and 6 not in fold.train_indices for fold in plan)
    assert 6 in plan[-1].eval_indices


@pytest.mark.parametrize("horizon_days", [1, 7, 14, 30])
def test_purged_daily_walk_forward_resolves_post_purge_training_minimum(
    horizon_days: int,
) -> None:
    """The first fold keeps 1,095 raw warm-up days across common horizons."""

    timestamps = pd.date_range("2019-01-01", periods=2_005, freq="D", tz="UTC")
    frame = pd.DataFrame(
        {
            "timestamp": timestamps,
            "row_id": range(len(timestamps)),
            "target_end": timestamps + pd.Timedelta(days=horizon_days),
        }
    )
    plan = _plan(
        frame,
        SplitConfig(
            "purged",
            min_train_periods=1_095 - horizon_days,
            eval_periods=182,
            step_periods=182,
        ),
        target_end_col="target_end",
    )

    first = plan[0]
    assert first.eval_indices == tuple(range(1_095, 1_277))
    assert first.train_indices == tuple(range(1_095 - horizon_days))
    assert first.train_count == 1_095 - horizon_days
    assert first.eval_indices[0] - first.train_count == horizon_days
    assert all(frame.loc[index, "target_end"] < first.eval_start for index in first.train_indices)


def test_balanced_daily_walk_forward_has_five_complete_oos_windows() -> None:
    """The documented 2,005-day development geometry yields 910 OOS days."""

    timestamps = pd.date_range("2019-01-01", periods=2_005, freq="D", tz="UTC")
    frame = pd.DataFrame(
        {
            "timestamp": timestamps,
            "row_id": range(len(timestamps)),
            "target_end": timestamps + pd.Timedelta(days=30),
        }
    )
    plan = _plan(
        frame,
        SplitConfig("purged", min_train_periods=1_065, eval_periods=182, step_periods=182),
        target_end_col="target_end",
    )

    assert len(plan) == 5
    assert sum(fold.eval_count for fold in plan) == 910
    assert [fold.eval_indices for fold in plan] == [
        tuple(range(start, start + 182)) for start in range(1_095, 2_005, 182)
    ]
    assert len({index for fold in plan for index in fold.eval_indices}) == 910
    assert plan[-1].eval_indices == tuple(range(1_823, 2_005))


def test_purged_walk_forward_handles_variable_target_ends_row_by_row() -> None:
    """One long label delays only the boundaries it actually overlaps."""

    frame = _frame(12)
    frame["target_end"] = frame["timestamp"]
    frame.loc[0, "target_end"] = frame.loc[5, "timestamp"]
    plan = _plan(
        frame,
        SplitConfig("purged", min_train_periods=4, eval_periods=2),
        target_end_col="target_end",
    )

    first = plan[0]
    assert first.eval_indices == (5, 6)
    assert first.train_indices == (1, 2, 3, 4)
    assert all(frame.loc[index, "target_end"] < first.eval_start for index in first.train_indices)


def test_purged_walk_forward_fails_when_no_usable_training_window_fits() -> None:
    """A short dataset must not silently weaken the retained-period minimum."""

    frame = _frame(10)
    frame["target_end"] = frame["timestamp"] + pd.Timedelta(days=3)

    with pytest.raises(ValueError, match="no evaluation boundary retains"):
        _plan(
            frame,
            SplitConfig("purged", min_train_periods=7, eval_periods=2),
            target_end_col="target_end",
        )


def test_purged_walk_forward_reports_insufficient_complete_window_geometry() -> None:
    """A missing full evaluation window is distinct from purge loss."""

    frame = _frame(10)
    frame["target_end"] = frame["timestamp"]

    with pytest.raises(ValueError, match="cannot fit min_train_periods"):
        _plan(
            frame,
            SplitConfig("purged", min_train_periods=8, eval_periods=5),
            target_end_col="target_end",
        )


@pytest.mark.parametrize(
    ("boundary", "expected_train"),
    [
        ("strict", [(0,), (0, 2, 3)]),
        ("closed", [(0, 2), (0, 2, 3, 4)]),
    ],
)
def test_shared_purge_migration_preserves_irregular_grouped_memberships(
    boundary: str,
    expected_train: list[tuple[int, ...]],
) -> None:
    """Hand-derived pre-migration memberships preserve missing and touching labels."""

    origin = pd.Timestamp("2024-01-01", tz="UTC")
    frame = pd.DataFrame(
        {
            "timestamp": [origin + pd.Timedelta(days=day) for day in [0, 0, 2, 2, 5, 5, 10, 10]],
            "row_id": [f"id-{index}" for index in range(8)],
            "period": ["a", "a", "b", "b", "c", "c", "d", "d"],
            "target_end": [
                pd.NaT if day is None else origin + pd.Timedelta(days=day)
                for day in [2, None, 5, 6, 10, 11, 10, 10]
            ],
        }
    )
    plan = _plan(
        frame,
        SplitConfig("purged", 1, 1, first_eval_period=2, purge_boundary=boundary),
        period_col="period",
        target_end_col="target_end",
    )

    assert [fold.eval_indices for fold in plan] == [(4, 5), (6, 7)]
    assert [fold.train_indices for fold in plan] == expected_train
    assert plan[0].purge_start == origin + pd.Timedelta(days=2)
    assert plan[0].purge_end == origin + pd.Timedelta(days=6)
    assert plan[1].purge_start == origin + pd.Timedelta(days=5)
    assert plan[1].purge_end == origin + pd.Timedelta(days=11)
    assert all(fold.embargo_start is None and fold.embargo_end is None for fold in plan)
    assert all(1 not in fold.train_indices for fold in plan)


def test_plan_records_stable_row_ids_and_is_frozen() -> None:
    """Fold metadata is immutable and row IDs preserve the caller identity."""

    frame = _frame(6).iloc[[3, 0, 2, 1, 5, 4]].reset_index(drop=True)
    plan = _plan(frame, SplitConfig("expanding", 2, 2))

    assert plan[0].train_row_ids == tuple(frame.loc[list(plan[0].train_indices), "row_id"])
    assert plan[0].eval_row_ids == tuple(frame.loc[list(plan[0].eval_indices), "row_id"])
    with pytest.raises(FrozenInstanceError):
        plan[0].train_indices = ()  # type: ignore[misc]
    assert isinstance(plan[0], Fold)


@pytest.mark.parametrize(
    ("config", "kwargs", "message"),
    [
        (SplitConfig("expanding", 2, 2, step_periods=1), {}, "evaluation windows overlap"),
        (SplitConfig("purged", 2, 2), {}, "target_end_col"),
    ],
)
def test_invalid_split_invariants_fail_closed(
    config: SplitConfig,
    kwargs: dict[str, object],
    message: str,
) -> None:
    """Overlapping evaluation rows and missing purge metadata are errors."""

    with pytest.raises(ValueError, match=message):
        _plan(_frame(8), config, **kwargs)
