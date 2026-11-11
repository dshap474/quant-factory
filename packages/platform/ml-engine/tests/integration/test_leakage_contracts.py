"""Adversarial tests for the public training leakage contracts.

Usage::

    pytest tests/integration/test_leakage_contracts.py

The cases use sklearn-compatible estimators through the public configuration
surface.  They check that evaluation values cannot fit preprocessing or
selection, label-information intervals are purged, candidate selection uses
OOS evidence, and learned ensemble scores are meta-OOS only.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports and tiny estimators
# --------------------------------------------------------------------------- #
from typing import Any

import numpy as np
import pandas as pd
import pytest
from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.linear_model import LinearRegression, Ridge

from ml_engine.training import (
    CandidateConfig,
    EnsembleConfig,
    MetricConfig,
    PreprocessingConfig,
    SelectionConfig,
    SplitConfig,
    TrainingConfig,
    TrainingPipeline,
)


class TrainingMeanRegressor(BaseEstimator, RegressorMixin):
    """Return the mean of the transformed training matrix for each row."""

    def fit(self, X: Any, y: Any) -> TrainingMeanRegressor:
        del y
        self.training_mean_ = float(np.asarray(X, dtype=float).mean())
        return self

    def predict(self, X: Any) -> np.ndarray:
        return np.full(len(X), self.training_mean_, dtype=float)


class MemorizingRegressor(BaseEstimator, RegressorMixin):
    """Fit perfectly on seen rows but return a bad value for unseen rows."""

    def fit(self, X: Any, y: Any) -> MemorizingRegressor:
        values = np.asarray(X, dtype=float)
        self._known_ = {tuple(row): float(target) for row, target in zip(values, y, strict=True)}
        return self

    def predict(self, X: Any) -> np.ndarray:
        values = np.asarray(X, dtype=float)
        return np.asarray([self._known_.get(tuple(row), 0.0) for row in values], dtype=float)


# --------------------------------------------------------------------------- #
# Fixture builders
# --------------------------------------------------------------------------- #


def _frame(rows: int = 24) -> pd.DataFrame:
    """Return a timestamped linear fixture with explicit label end times."""
    x = np.arange(float(rows))
    timestamp = pd.date_range("2024-01-01", periods=rows, freq="D")
    return pd.DataFrame(
        {
            "row_id": np.arange(5_000, 5_000 + rows, dtype=np.int64),
            "timestamp": timestamp,
            "target_end": timestamp + pd.to_timedelta(1, unit="D"),
            "period": (np.arange(rows) // 2).astype(np.int64),
            "feature_a": x,
            "feature_b": np.cos(x / 4.0),
            "target": 3.0 * x + 2.0,
        }
    )


def _base_config(
    *,
    candidate_configs: list[CandidateConfig],
    split: SplitConfig | None = None,
    preprocessing: PreprocessingConfig | None = None,
    selection: SelectionConfig | None = None,
    ensemble: EnsembleConfig | None = None,
    period_col: str | None = None,
    target_end_col: str | None = None,
) -> TrainingConfig:
    """Build a common explicit config while varying one contract at a time."""
    return TrainingConfig(
        feature_cols=["feature_a", "feature_b"],
        target_col="target",
        timestamp_col="timestamp",
        row_id_col="row_id",
        period_col=period_col,
        target_end_col=target_end_col,
        split=split
        or SplitConfig(kind="chronological_holdout", min_train_periods=12, eval_periods=6),
        preprocessing=preprocessing or PreprocessingConfig(),
        candidates=candidate_configs,
        metrics=[MetricConfig(name="rmse")],
        selection=selection or SelectionConfig(primary_metric="rmse", direction="minimize"),
        ensemble=ensemble or EnsembleConfig(kind="none"),
        random_seed=23,
    )


def _folds(result: Any) -> tuple[Any, ...]:
    """Normalize the immutable public fold-plan value for assertions."""
    plan = result.fold_plan
    values = getattr(plan, "folds", plan)
    return tuple(values() if callable(values) else values)


def _fold_ids(fold: Any, side: str, frame: pd.DataFrame) -> set[int]:
    """Read row IDs from a fold record, accepting its documented aliases."""
    for name in (f"{side}_row_ids", f"{side}_ids"):
        values = getattr(fold, name, None)
        if values is not None:
            return {int(value) for value in values}
    positions = getattr(fold, f"{side}_indices")
    return set(frame.iloc[list(positions)]["row_id"].astype(int))


# --------------------------------------------------------------------------- #
# Fold-local preprocessing and target-independent selection
# --------------------------------------------------------------------------- #


def test_evaluation_sentinel_cannot_change_fold_local_preprocessing() -> None:
    """Changing only evaluation features leaves a train-fitted scaler unchanged."""
    frame = _frame()
    config = _base_config(
        candidate_configs=[CandidateConfig(name="probe", estimator=TrainingMeanRegressor())],
        preprocessing=PreprocessingConfig(scale="standard"),
    )
    baseline = TrainingPipeline(config).run(frame)

    changed = frame.copy()
    changed.loc[12:, "feature_a"] = 10_000_000.0
    perturbed = TrainingPipeline(config).run(changed)
    baseline_oos = baseline.candidate_oos.loc[:, ["row_id", "prediction"]].sort_values("row_id")
    perturbed_oos = perturbed.candidate_oos.loc[:, ["row_id", "prediction"]].sort_values("row_id")
    pd.testing.assert_frame_equal(
        baseline_oos.reset_index(drop=True), perturbed_oos.reset_index(drop=True)
    )
    assert np.allclose(baseline_oos["prediction"], 0.0, atol=1e-12)


def test_selection_ignores_final_refit_and_uses_only_oos_predictions() -> None:
    """An in-sample memorizer must lose to the OOS-correct linear candidate."""
    frame = _frame()
    config = _base_config(
        candidate_configs=[
            CandidateConfig(name="memorizer", estimator=MemorizingRegressor()),
            CandidateConfig(name="linear", estimator=LinearRegression()),
        ]
    )
    result = TrainingPipeline(config).run(frame)
    assert result.selection_report.selected_name == "linear"
    assert result.selected_candidates == ("linear",)
    memorizer_rmse = result.candidate_metrics["memorizer"].metrics["rmse"]
    linear_rmse = result.candidate_metrics["linear"].metrics["rmse"]
    assert float(linear_rmse) < float(memorizer_rmse)


# --------------------------------------------------------------------------- #
# Purging and learned ensemble meta-cross-fitting
# --------------------------------------------------------------------------- #


def test_purged_split_excludes_overlapping_label_information() -> None:
    """No training row may end inside the chronological evaluation interval."""
    frame = _frame()
    config = _base_config(
        candidate_configs=[CandidateConfig(name="linear", estimator=LinearRegression())],
        period_col="period",
        target_end_col="target_end",
        split=SplitConfig(kind="purged", min_train_periods=6, eval_periods=2),
    )
    result = TrainingPipeline(config).run(frame)
    assert _folds(result)
    for fold in _folds(result):
        train_ids = _fold_ids(fold, "train", frame)
        eval_ids = _fold_ids(fold, "eval", frame)
        assert train_ids.isdisjoint(eval_ids)
        eval_start = frame.loc[frame["row_id"].isin(eval_ids), "timestamp"].min()
        train_end_times = frame.loc[frame["row_id"].isin(train_ids), "target_end"]
        assert (train_end_times < eval_start).all()


def test_pipeline_resolves_first_purged_fold_from_usable_periods() -> None:
    """The public pipeline delays evaluation until the post-purge minimum is met."""

    frame = _frame(30)
    frame["target_end"] = frame["timestamp"] + pd.to_timedelta(3, unit="D")
    config = _base_config(
        candidate_configs=[CandidateConfig(name="linear", estimator=LinearRegression())],
        target_end_col="target_end",
        split=SplitConfig(kind="purged", min_train_periods=10, eval_periods=5),
    )

    first = _folds(TrainingPipeline(config).run(frame))[0]

    assert first.eval_indices == tuple(range(13, 18))
    assert first.train_indices == tuple(range(10))


def test_learned_ensemble_reports_only_chronological_meta_oos_rows() -> None:
    """Stacking scores exclude the early rows used to fit meta-combiners."""
    frame = _frame()
    config = _base_config(
        candidate_configs=[
            CandidateConfig(name="left", estimator=LinearRegression()),
            CandidateConfig(name="right", estimator=Ridge(alpha=1.0)),
        ],
        ensemble=EnsembleConfig(
            kind="stacking",
            base_models=("left", "right"),
            combiner=Ridge(alpha=1.0),
            meta_splits=2,
        ),
    )
    result = TrainingPipeline(config).run(frame)
    assert result.ensemble_oos is not None
    unique_base_rows = result.candidate_oos["row_id"].nunique()
    assert len(result.ensemble_oos) < unique_base_rows
    assert result.ensemble_oos["prediction"].notna().all()
    assert set(result.ensemble_oos["row_id"]).issubset(set(result.candidate_oos["row_id"]))
    earliest_base_row = (
        result.candidate_oos.sort_values("timestamp")["row_id"].drop_duplicates().iloc[0]
    )
    assert earliest_base_row not in set(result.ensemble_oos["row_id"])


def test_multi_model_none_fallback_selects_one_model_when_meta_fit_fails() -> None:
    """An explicit none fallback degrades to one deterministic selected model."""

    config = _base_config(
        candidate_configs=[
            CandidateConfig(name="left", estimator=LinearRegression()),
            CandidateConfig(name="right", estimator=Ridge(alpha=1.0)),
        ],
        ensemble=EnsembleConfig(
            kind="stacking",
            base_models=("left", "right"),
            combiner=Ridge(alpha=1.0),
            meta_splits=100,
            fallback="none",
        ),
    )

    result = TrainingPipeline(config).run(_frame())

    assert len(result.selected_candidates) == 1
    assert set(result.final_estimators) == set(result.selected_candidates)
    assert result.final_ensemble is None
    assert result.warnings


def test_multi_model_ensemble_requires_one_persisted_feature_schema() -> None:
    """Reject selected models whose feature subsets cannot share v1 preprocessing."""
    frame = _frame()
    config = _base_config(
        candidate_configs=[
            CandidateConfig(name="left", estimator=LinearRegression(), feature_cols=("feature_a",)),
            CandidateConfig(
                name="right",
                estimator=Ridge(alpha=1.0),
                feature_cols=("feature_a", "feature_b"),
            ),
        ],
        ensemble=EnsembleConfig(
            kind="equal_weight",
            base_models=("left", "right"),
        ),
    )

    with pytest.raises(ValueError, match="identical candidate feature_cols"):
        TrainingPipeline(config).run(frame)


def test_single_candidate_feature_subset_remains_allowed() -> None:
    """A single selected candidate may use a declared subset of features."""
    frame = _frame()
    config = _base_config(
        candidate_configs=[
            CandidateConfig(name="left", estimator=LinearRegression(), feature_cols=("feature_a",))
        ]
    )

    result = TrainingPipeline(config).run(frame)

    assert result.selected_candidates == ("left",)
    assert result.feature_schema["feature_cols"] == ["feature_a"]


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

if __name__ == "__main__":  # pragma: no cover
    raise SystemExit("run this module through pytest")
