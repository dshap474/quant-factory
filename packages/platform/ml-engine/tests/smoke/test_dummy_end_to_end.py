"""Smoke-test complete training and inference workflows with dummy daily data.

Usage::

    uv run pytest packages/platform/ml-engine/tests/smoke/test_dummy_end_to_end.py -q
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports
# --------------------------------------------------------------------------- #

from pathlib import Path

import numpy as np
import pandas as pd

from ml_engine.inference import InferencePipeline
from ml_engine.training import TrainingConfig, TrainingPipeline, TrainingResult


# --------------------------------------------------------------------------- #
# Smoke helpers
# --------------------------------------------------------------------------- #


def _future_rows(frame: pd.DataFrame, *, row_id_start: int) -> pd.DataFrame:
    """Build a small inference batch matching a persisted feature schema."""

    return pd.DataFrame(
        {
            "row_id": np.arange(row_id_start, row_id_start + 4, dtype=np.int64),
            "timestamp": pd.date_range(
                frame["timestamp"].max() + pd.Timedelta(days=1),
                periods=4,
                freq="D",
            ),
            "feature_trend": [-0.75, -0.25, 0.25, 0.75],
            "feature_cycle": [0.5, -0.5, 0.25, -0.25],
        }
    )


def _assert_saved_predictions_match(
    result: TrainingResult,
    new_data: pd.DataFrame,
    artifact_path: Path,
    *,
    expected_models: tuple[str, ...],
) -> None:
    """Save, reload, and compare in-memory and persisted inference outputs."""

    inference_pipeline = result.inference_pipeline
    in_memory = inference_pipeline.predict(new_data, include_base_predictions=True)
    saved = result.save(artifact_path)
    loaded = InferencePipeline.load(saved, trusted=True)
    reloaded = loaded.predict(new_data, include_base_predictions=True)

    np.testing.assert_allclose(reloaded.predictions, in_memory.predictions)
    np.testing.assert_array_equal(reloaded.row_ids, new_data["row_id"].to_numpy())
    assert reloaded.base_predictions is not None
    assert tuple(reloaded.base_predictions.columns) == expected_models
    assert np.isfinite(reloaded.predictions).all()


# --------------------------------------------------------------------------- #
# Complete daily workflows
# --------------------------------------------------------------------------- #


def test_exact_purged_regression_trains_evaluates_saves_and_predicts(
    daily_regression_frame: pd.DataFrame,
    purged_regression_config: TrainingConfig,
    tmp_path: Path,
) -> None:
    """Run exact-purged walk-forward regression through persisted inference."""

    result = TrainingPipeline(purged_regression_config).run(daily_regression_frame)
    folds = result.fold_plan.folds

    assert len(folds) == 4
    assert folds[0].eval_indices[0] == 67
    assert folds[0].train_count == 60
    assert result.selected_candidates == ("linear", "ridge")
    assert result.ensemble_oos is not None
    assert len(result.ensemble_oos) == 112
    assert set(result.candidate_metrics) == {"linear", "ridge"}
    assert all(summary.n_folds == 4 for summary in result.candidate_metrics.values())

    for fold in folds:
        train_target_ends = daily_regression_frame.iloc[list(fold.train_indices)]["target_end"]
        assert (train_target_ends < fold.eval_start).all()

    _assert_saved_predictions_match(
        result,
        _future_rows(daily_regression_frame, row_id_start=30_000),
        tmp_path / "purged-regression",
        expected_models=("linear", "ridge"),
    )


def test_fixed_gap_classification_trains_evaluates_saves_and_predicts(
    daily_classification_frame: pd.DataFrame,
    fixed_gap_classification_config: TrainingConfig,
    tmp_path: Path,
) -> None:
    """Run fixed-gap expanding classification through persisted inference."""

    result = TrainingPipeline(fixed_gap_classification_config).run(daily_classification_frame)
    folds = result.fold_plan.folds

    assert len(folds) == 6
    assert folds[0].train_indices == tuple(range(50))
    assert folds[0].eval_indices == tuple(range(57, 77))
    assert folds[0].embargo_start == daily_classification_frame.loc[50, "timestamp"]
    assert folds[0].embargo_end == daily_classification_frame.loc[56, "timestamp"]
    assert result.selected_candidates == ("logistic",)
    assert result.candidate_metrics["logistic"].n_observations == 120
    assert result.candidate_oos["prediction"].between(0.0, 1.0, inclusive="neither").all()

    _assert_saved_predictions_match(
        result,
        _future_rows(daily_classification_frame, row_id_start=40_000),
        tmp_path / "fixed-gap-classification",
        expected_models=("logistic",),
    )


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit("run this module through pytest")
