"""Tier-1 toolchain certification: pinned-LightGBM determinism and vintage sensitivity.

Usage::

    pytest tests/integration/test_toolchain_certification.py

These are standing engine-boundary certifications rather than per-run version
checks: they prove
properties of the pinned toolchain and the engine's fold/refit machinery, not of
any strategy run, and rerun on engine/dependency/toolchain changes.

1. Double-fit determinism: with the pinned LightGBM policy
   (``deterministic=True``, ``n_jobs=1``, fixed ``random_state``), running the
   identical pipeline twice yields bit-identical out-of-sample predictions.
2. Future-vintage mutation: mutating only TARGET values from a cut date forward
   leaves every fold whose training window ends before the cut bit-identical
   (anti-lookahead) and changes every fold that trains on mutated rows (the
   engine really consumes the data the fold plan declares).
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports and fixture builders
# --------------------------------------------------------------------------- #

import numpy as np
import pandas as pd
import pytest

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

lightgbm = pytest.importorskip("lightgbm")

ROWS = 48
SEED = 20260824

# Pinned deterministic fit policy (mirrors the repo-wide LightGBM contract).
PINNED_LGBM = {
    "deterministic": True,
    "n_jobs": 1,
    "random_state": SEED,
    "n_estimators": 40,
    "learning_rate": 0.2,
    "min_child_samples": 2,
    "verbosity": -1,
}


def _frame() -> pd.DataFrame:
    """Timestamped nonlinear fixture with enough signal for real tree splits."""
    rng = np.random.default_rng(SEED)
    x = np.arange(float(ROWS))
    timestamp = pd.date_range("2024-01-01", periods=ROWS, freq="D")
    feature_a = np.sin(x / 3.0)
    feature_b = rng.normal(size=ROWS)
    return pd.DataFrame(
        {
            "row_id": np.arange(1_000, 1_000 + ROWS, dtype=np.int64),
            "timestamp": timestamp,
            "target_end": timestamp + pd.to_timedelta(1, unit="D"),
            "feature_a": feature_a,
            "feature_b": feature_b,
            "target": 2.0 * feature_a + 0.5 * feature_b + rng.normal(scale=0.1, size=ROWS),
        }
    )


def _config() -> TrainingConfig:
    return TrainingConfig(
        feature_cols=["feature_a", "feature_b"],
        target_col="target",
        timestamp_col="timestamp",
        row_id_col="row_id",
        target_end_col="target_end",
        split=SplitConfig(kind="purged", min_train_periods=16, eval_periods=8),
        preprocessing=PreprocessingConfig(),
        candidates=[CandidateConfig(name="gbm", estimator=lightgbm.LGBMRegressor(**PINNED_LGBM))],
        metrics=[MetricConfig(name="rmse")],
        selection=SelectionConfig(primary_metric="rmse", direction="minimize"),
        ensemble=EnsembleConfig(kind="none"),
        random_seed=SEED,
    )


def _oos_predictions(result: object) -> pd.DataFrame:
    return (
        result.candidate_oos.loc[:, ["row_id", "prediction"]]
        .sort_values("row_id")
        .reset_index(drop=True)
    )


def _folds(result: object) -> tuple[object, ...]:
    plan = result.fold_plan
    values = getattr(plan, "folds", plan)
    return tuple(values() if callable(values) else values)


# --------------------------------------------------------------------------- #
# 1. Pinned-toolchain double-fit determinism
# --------------------------------------------------------------------------- #


def test_pinned_lightgbm_double_fit_is_bit_identical() -> None:
    """The identical pipeline run twice must reproduce predictions bit-exactly."""
    frame = _frame()
    first = TrainingPipeline(_config()).run(frame)
    second = TrainingPipeline(_config()).run(frame.copy())

    first_oos = _oos_predictions(first)
    second_oos = _oos_predictions(second)
    assert np.array_equal(first_oos["row_id"].to_numpy(), second_oos["row_id"].to_numpy())
    assert np.array_equal(first_oos["prediction"].to_numpy(), second_oos["prediction"].to_numpy())
    # The fit is real, not degenerate: tree splits produced varying predictions.
    assert first_oos["prediction"].nunique() > 1


# --------------------------------------------------------------------------- #
# 2. Future-vintage mutation oracle
# --------------------------------------------------------------------------- #


def test_future_target_mutation_respects_fold_boundaries() -> None:
    """Mutated future targets change exactly the folds that train on them."""
    frame = _frame()
    baseline = TrainingPipeline(_config()).run(frame)
    folds = _folds(baseline)
    assert len(folds) >= 2, "certification needs at least two walk-forward folds"

    # Cut at the first row of the LAST fold's training tail so at least one
    # earlier fold trains entirely before the cut and the last fold trains on it.
    early_train_end = max(folds[0].train_indices)
    cut = early_train_end + 1
    assert any(max(fold.train_indices) >= cut for fold in folds)

    mutated = frame.copy()
    mutated.loc[cut:, "target"] = -5.0 * mutated.loc[cut:, "target"] + 0.1
    perturbed = TrainingPipeline(_config()).run(mutated)

    base_oos = _oos_predictions(baseline).set_index("row_id")["prediction"]
    pert_oos = _oos_predictions(perturbed).set_index("row_id")["prediction"]
    assert set(base_oos.index) == set(pert_oos.index)

    for fold in folds:
        eval_ids = frame.iloc[list(fold.eval_indices)]["row_id"].astype(int)
        base_vals = base_oos.loc[eval_ids].to_numpy()
        pert_vals = pert_oos.loc[eval_ids].to_numpy()
        if max(fold.train_indices) < cut:
            # Anti-lookahead: this fold never saw a mutated row.
            assert np.array_equal(base_vals, pert_vals)
        else:
            # The engine consumed the mutated vintage: the fit must change.
            assert not np.array_equal(base_vals, pert_vals)
