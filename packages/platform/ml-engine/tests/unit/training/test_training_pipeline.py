"""Focused end-to-end checks for explicit training orchestration.

Usage::

    uv run pytest tests/unit/training/test_training_pipeline.py -q
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd
import pytest
from sklearn.base import BaseEstimator, RegressorMixin
from sklearn.linear_model import LinearRegression, LogisticRegression

from ml_engine.training import (
    CandidateConfig,
    MetricConfig,
    PreprocessingConfig,
    SelectionConfig,
    SplitConfig,
    TrainingConfig,
    TrainingPipeline,
)

# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


class AffineTransform:
    """A supported transform-only object without serialization hooks."""

    def transform(self, values: np.ndarray) -> np.ndarray:
        return 3 * values - 2


class WeightedMeanRegressor(RegressorMixin, BaseEstimator):
    """Expose received fit weights while returning one deterministic mean."""

    def fit(
        self,
        features: object,
        target: object,
        sample_weight: object | None = None,
    ) -> WeightedMeanRegressor:
        values = np.asarray(target, dtype=float)
        weights = None if sample_weight is None else np.asarray(sample_weight, dtype=float)
        self.sample_weight_ = weights
        self.mean_ = float(np.average(values, weights=weights))
        return self

    def predict(self, features: object) -> np.ndarray:
        return np.full(len(features), self.mean_, dtype=float)  # type: ignore[arg-type]


def _config() -> TrainingConfig:
    """Build one deterministic holdout configuration."""
    return TrainingConfig(
        feature_cols=("feature",),
        target_col="target",
        timestamp_col="timestamp",
        split=SplitConfig(
            kind="chronological_holdout",
            min_train_periods=5,
            eval_periods=3,
        ),
        candidates=(CandidateConfig(name="linear", estimator=LinearRegression()),),
        metrics=(MetricConfig(name="rmse"),),
        selection=SelectionConfig(primary_metric="rmse", direction="minimize"),
        random_seed=11,
    )


def _frame() -> pd.DataFrame:
    """Return an intentionally unsorted timestamped regression frame."""
    values = np.arange(8.0)
    return pd.DataFrame(
        {
            "row": np.arange(8),
            "timestamp": pd.date_range("2024-01-01", periods=8, freq="D")[::-1],
            "feature": values,
            "target": 2.0 * values + 1.0,
        }
    )


# --------------------------------------------------------------------------- #
# Pipeline behavior
# --------------------------------------------------------------------------- #


def test_transform_only_object_survives_training_and_artifact_roundtrip(tmp_path) -> None:
    """Dedicated object persistence supports the documented minimal contract."""
    from ml_engine.inference import InferencePipeline

    result = TrainingPipeline(
        dataclasses.replace(_config(), prediction_transform=AffineTransform())
    ).run(_frame())
    features = _frame().drop(columns="target")
    expected = 3 * (2 * features["feature"].to_numpy() + 1) - 2
    np.testing.assert_allclose(result.inference_pipeline.predict(features).predictions, expected)
    loaded = InferencePipeline.load(result.save(tmp_path / "affine"), trusted=True)
    np.testing.assert_allclose(loaded.predict(features).predictions, expected)


def test_run_returns_oos_rows_and_selected_final_estimator() -> None:
    """Fit folds in timestamp order and keep the result write-free."""
    result = TrainingPipeline(_config()).run(_frame())

    assert result.selected_candidates == ("linear",)
    assert list(result.candidate_oos["candidate"].unique()) == ["linear"]
    assert set(result.candidate_oos["row_id"]) == {0, 1, 2}
    assert result.candidate_oos["timestamp"].is_monotonic_increasing
    assert result.selection_report.selected_name == "linear"
    assert set(result.final_estimators) == {"linear"}


def test_run_preserves_unknown_targets_outside_fit_and_oos() -> None:
    """Without score-only endpoint markers, unknown labels retain legacy behavior."""
    frame = _frame()
    frame.loc[0, "target"] = np.nan
    result = TrainingPipeline(_config()).run(frame)

    assert result.candidate_oos["target"].notna().all()
    assert result.candidate_metrics["linear"].n_observations == len(result.candidate_oos)


def test_purged_pipeline_predicts_score_only_evaluation_rows() -> None:
    """Unknown-target evaluation rows are predicted but excluded from evaluation summaries."""

    frame = _frame().sort_values("timestamp").reset_index(drop=True)
    frame["target_end"] = frame["timestamp"]
    frame["weight"] = 1.0
    frame.loc[3, ["target", "target_end", "weight"]] = np.nan
    config = TrainingConfig(
        feature_cols=("feature",),
        target_col="target",
        timestamp_col="timestamp",
        target_end_col="target_end",
        weight_col="weight",
        split=SplitConfig(kind="purged", min_train_periods=2, eval_periods=2),
        candidates=(CandidateConfig(name="linear", estimator=WeightedMeanRegressor()),),
        metrics=(MetricConfig(name="rmse"),),
        selection=SelectionConfig(primary_metric="rmse", direction="minimize"),
        random_seed=11,
    )

    result = TrainingPipeline(config).run(frame)

    score_only = result.oos_predictions.loc[result.oos_predictions["row_id"] == 3]
    assert len(score_only) == 1
    assert score_only["prediction"].notna().all()
    assert score_only["target"].isna().all()
    summary = result.candidate_metrics["linear"]
    assert summary.n_rows == result.candidate_oos["target"].notna().sum()
    assert summary.coverage == 1.0


def test_sample_weights_reach_fold_fits_and_final_refit() -> None:
    """Every estimator fit receives the configured positive training-row weights."""

    frame = _frame().assign(weight=np.arange(1.0, 9.0))
    config = TrainingConfig(
        feature_cols=("feature",),
        target_col="target",
        timestamp_col="timestamp",
        weight_col="weight",
        split=SplitConfig("chronological_holdout", 5, 3),
        candidates=(CandidateConfig("weighted", WeightedMeanRegressor()),),
        metrics=(MetricConfig("rmse"),),
        selection=SelectionConfig("rmse", "minimize"),
        random_seed=11,
        keep_fold_models=True,
    )

    result = TrainingPipeline(config).run(frame)

    fold = result.fold_models["weighted"][0]
    np.testing.assert_array_equal(fold.sample_weight_, [8.0, 7.0, 6.0, 5.0, 4.0])
    np.testing.assert_array_equal(
        result.final_estimators["weighted"].sample_weight_,
        [8.0, 7.0, 6.0, 5.0, 4.0, 3.0, 2.0, 1.0],
    )


@pytest.mark.parametrize("weight", [0.0, -1.0, np.nan, np.inf])
def test_invalid_training_sample_weights_fail_closed(weight: float) -> None:
    frame = _frame().assign(weight=1.0)
    frame.loc[7, "weight"] = weight
    config = TrainingConfig(
        feature_cols=("feature",),
        target_col="target",
        timestamp_col="timestamp",
        weight_col="weight",
        split=SplitConfig("chronological_holdout", 5, 3),
        candidates=(CandidateConfig("weighted", WeightedMeanRegressor()),),
        metrics=(MetricConfig("rmse"),),
        selection=SelectionConfig("rmse", "minimize"),
        random_seed=11,
    )

    with pytest.raises(ValueError, match="weight"):
        TrainingPipeline(config).run(frame)


def test_final_refit_can_be_disabled_without_losing_oos_results(tmp_path: object) -> None:
    """OOS selection remains available while every inference artifact access fails clearly."""

    config = dataclasses.replace(_config(), final_refit=False)
    result = TrainingPipeline(config).run(_frame())

    assert not result.candidate_oos.empty
    assert result.selection_report.selected_name == "linear"
    with pytest.raises(RuntimeError, match="final_refit=False"):
        _ = result.final_estimators
    with pytest.raises(RuntimeError, match="final_refit=False"):
        _ = result.final_preprocessor
    with pytest.raises(RuntimeError, match="final_refit=False"):
        _ = result.inference_pipeline
    with pytest.raises(RuntimeError, match="final_refit=False"):
        result.save(tmp_path)  # type: ignore[arg-type]


def test_fold_models_are_retained_only_when_requested() -> None:
    """Estimator retention is opt-in and keyed first by candidate, then fold."""

    default = TrainingPipeline(_config()).run(_frame())
    retained = TrainingPipeline(dataclasses.replace(_config(), keep_fold_models=True)).run(_frame())

    assert default.fold_models == {}
    assert default.fold_preprocessors == {}
    with pytest.raises(RuntimeError, match="keep_fold_models=True"):
        default.predict_fold(_frame(), candidate="linear", fold=0)
    assert set(retained.fold_models) == {"linear"}
    assert set(retained.fold_models["linear"]) == {0}
    assert hasattr(retained.fold_models["linear"][0], "coef_")
    assert set(retained.fold_preprocessors["linear"]) == {0}
    for name, fold in [("unknown", 0), ("linear", 99)]:
        with pytest.raises(ValueError, match="retained"):
            retained.predict_fold(_frame(), candidate=name, fold=fold)


@pytest.mark.parametrize("final_refit", [False, True])
def test_retained_fold_prediction_applies_fitted_candidate_preprocessing(final_refit) -> None:
    """Analytical linear fits retain distinct fold/candidate transforms, without refitting."""
    x = np.arange(10.0)
    frame = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=10, freq="D"),
            "x": x,
            "z": 100 + 10 * x,
            "target": 2 * x + 3,
            "weight": x + 1,
        }
    )
    # Missing only in the last evaluation row: its prediction must use the
    # training-fold imputer mean, even when a later full-data refit exists.
    frame.loc[9, ["x", "z"]] = np.nan
    config = dataclasses.replace(
        _config(),
        feature_cols=("x", "z"),
        weight_col="weight",
        split=SplitConfig(kind="expanding", min_train_periods=4, eval_periods=2, step_periods=2),
        candidates=tuple(
            CandidateConfig(name=name, estimator=LinearRegression(), feature_cols=(name,))
            for name in ["x", "z"]
        ),
        preprocessing=PreprocessingConfig(impute_strategy="mean", scale="standard"),
        keep_fold_models=True,
        final_refit=final_refit,
    )
    result = TrainingPipeline(config).run(frame)
    transformers = [p for folds in result.fold_preprocessors.values() for p in folds.values()]
    assert len({id(p) for p in transformers}) == 6
    for fold in result.fold_plan:
        evaluation = frame.iloc[list(fold.eval_indices)]
        train_x = x[list(fold.train_indices)]
        expected = 2 * x[list(fold.eval_indices)] + 3
        if 9 in fold.eval_indices:
            expected[-1] = 2 * train_x.mean() + 3
        for name in ["x", "z"]:
            transform = result.fold_preprocessors[name][fold.fold]
            before = transform.named_steps["imputer"].statistics_.copy()
            predictions = result.predict_fold(evaluation, candidate=name, fold=fold.fold)
            np.testing.assert_allclose(predictions, expected, rtol=0, atol=1e-12)
            stored = result.candidate_oos.query("candidate == @name and fold == @fold.fold")[
                "prediction"
            ]
            np.testing.assert_array_equal(predictions, stored.to_numpy())
            np.testing.assert_array_equal(transform.named_steps["imputer"].statistics_, before)
            np.testing.assert_array_equal(
                result.predict_fold(evaluation.iloc[::-1], candidate=name, fold=fold.fold),
                predictions[::-1],
            )
            with pytest.raises(ValueError, match="Missing required"):
                result.predict_fold(evaluation.drop(columns=name), candidate=name, fold=fold.fold)


@pytest.mark.parametrize("candidate_task_override", [False, True])
def test_binary_classification_uses_positive_class_probabilities(
    candidate_task_override, tmp_path
) -> None:
    """Binary OOS and inference predictions use scores, not hard labels."""
    frame = _frame().assign(target=np.array([0, 1, 0, 1, 0, 1, 0, 1]))
    config = TrainingConfig(
        feature_cols=("feature",),
        target_col="target",
        timestamp_col="timestamp",
        split=SplitConfig(
            kind="chronological_holdout",
            min_train_periods=5,
            eval_periods=3,
        ),
        candidates=(
            CandidateConfig(
                name="logistic",
                estimator=LogisticRegression(),
                task="binary_classification" if candidate_task_override else None,
            ),
        ),
        metrics=(MetricConfig(name="log_loss"),),
        selection=SelectionConfig(primary_metric="log_loss", direction="minimize"),
        random_seed=11,
        task="regression" if candidate_task_override else "binary_classification",
        preprocessing=PreprocessingConfig(scale="standard"),
        keep_fold_models=True,
        final_refit=True,
    )

    result = TrainingPipeline(config).run(frame)

    assert result.candidate_oos["prediction"].between(0.0, 1.0, inclusive="neither").all()
    fold = result.fold_plan.folds[0]
    prediction = result.predict_fold(
        frame.iloc[list(fold.eval_indices)], candidate="logistic", fold=fold.fold
    )
    np.testing.assert_array_equal(prediction, result.candidate_oos["prediction"].to_numpy())
    served = result.inference_pipeline.predict(frame).predictions
    assert np.all((served > 0.0) & (served < 1.0))
    # The task declaration is already serialized in config.candidates; verify
    # that its semantics survive real artifact save/load without a schema bump.
    from ml_engine.inference import InferencePipeline

    saved = result.save(tmp_path / "binary")
    loaded = InferencePipeline.load(saved, trusted=True)
    np.testing.assert_array_equal(loaded.predict(frame).predictions, served)
