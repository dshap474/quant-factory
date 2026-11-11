"""Verify optional training progress without changing training results.

Usage::

    uv run pytest packages/platform/ml-engine/tests/unit/training/test_progress.py -q
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd
import pytest
from sklearn.dummy import DummyRegressor
from sklearn.linear_model import LinearRegression

from ml_engine.training import (
    CandidateConfig,
    MetricConfig,
    SelectionConfig,
    SplitConfig,
    TrainingConfig,
    TrainingPipeline,
    TrainingProgress,
)


# --------------------------------------------------------------------------- #
# Deterministic fixtures
# --------------------------------------------------------------------------- #


def _frame() -> pd.DataFrame:
    """Return one tiny ordered regression dataset."""

    values = np.arange(8.0)
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=8, freq="D"),
            "feature": values,
            "target": 2.0 * values + 1.0,
        }
    )


def _config(*, final_refit: bool = True) -> TrainingConfig:
    """Return a two-candidate, one-fold configuration."""

    return TrainingConfig(
        feature_cols=("feature",),
        target_col="target",
        timestamp_col="timestamp",
        split=SplitConfig("chronological_holdout", 5, 3),
        candidates=(
            CandidateConfig("linear", LinearRegression()),
            CandidateConfig("mean", DummyRegressor()),
        ),
        metrics=(MetricConfig("rmse"),),
        selection=SelectionConfig("rmse", "minimize"),
        random_seed=11,
        final_refit=final_refit,
    )


# --------------------------------------------------------------------------- #
# Progress contract
# --------------------------------------------------------------------------- #


def test_progress_reports_exact_candidate_fold_boundaries() -> None:
    """Emit before and after each fit with stable one-based indices and totals."""

    updates: list[TrainingProgress] = []
    TrainingPipeline(_config()).run(_frame(), progress=updates.append)

    assert [item.stage for item in updates[:3]] == [
        "validation",
        "planning",
        "cross_validation",
    ]
    fit_updates = [item for item in updates if item.stage == "cross_validation" and item.candidate]
    assert [item.candidate for item in fit_updates] == ["linear", "linear", "mean", "mean"]
    assert [item.candidate_index for item in fit_updates] == [1, 1, 2, 2]
    assert [item.fold_index for item in fit_updates] == [1, 1, 1, 1]
    assert [item.completed_fits for item in fit_updates] == [0, 1, 1, 2]
    assert all(item.candidate_count == 2 for item in fit_updates)
    assert all(item.fold_count == 1 for item in fit_updates)
    assert all(item.total_fits == 2 for item in fit_updates)
    assert [item.stage for item in updates[-3:]] == ["evaluation", "selection", "final_refit"]
    assert all(item.candidate == "mean" for item in updates[-3:])
    assert all(item.candidate_index == 2 for item in updates[-3:])
    assert all(item.fold_index == 1 for item in updates[-3:])
    assert all(item.completed_fits == item.total_fits == 2 for item in updates[-3:])


def test_callback_is_optional_and_does_not_change_results() -> None:
    """Observation alone leaves selected models and OOS values unchanged."""

    baseline = TrainingPipeline(_config()).run(_frame())
    observed = TrainingPipeline(_config()).run(_frame(), progress=lambda _update: None)

    assert observed.selected_candidates == baseline.selected_candidates
    pd.testing.assert_frame_equal(observed.candidate_oos, baseline.candidate_oos)
    assert observed.selection_report.to_dict() == baseline.selection_report.to_dict()


def test_final_refit_stage_is_omitted_when_disabled() -> None:
    """An OOS-only run reports only stages it actually reaches."""

    updates: list[TrainingProgress] = []
    TrainingPipeline(_config(final_refit=False)).run(_frame(), progress=updates.append)

    assert "final_refit" not in {item.stage for item in updates}
    assert updates[-1].stage == "selection"
    assert updates[-1].completed_fits == updates[-1].total_fits == 2


def test_callback_failures_propagate() -> None:
    """A failing required observer stops training at the exact callback boundary."""

    def fail_on_planning(update: TrainingProgress) -> None:
        if update.stage == "planning":
            raise OSError("status write failed")

    with pytest.raises(OSError, match="status write failed"):
        TrainingPipeline(_config()).run(_frame(), progress=fail_on_planning)


def test_progress_values_are_immutable() -> None:
    """Consumers cannot mutate an emitted engine lifecycle value."""

    update = TrainingProgress("validation", "regression", "target", 1, False)

    with pytest.raises(dataclasses.FrozenInstanceError):
        update.stage = "planning"  # type: ignore[misc]
