"""Fit chosen estimator candidates on every row with an observed target.

Usage::

    result = fit_full_data(
        frame,
        feature_cols=("feature_a", "feature_b"),
        target_col="target",
        candidates=(CandidateConfig("ridge", Ridge()),),
        preprocessing=PreprocessingConfig(scale="standard"),
        task="regression",
        random_seed=7,
    )
    predictions = result.predict(new_frame, candidate="ridge")
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports
# --------------------------------------------------------------------------- #

from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
import pandas as pd
from sklearn.base import clone

from ..._predict import predict_scores
from ..config import CandidateConfig, PreprocessingConfig
from ..preprocessing import build_preprocessor

# --------------------------------------------------------------------------- #
# Full-fit result
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class FullFitResult:
    """Fitted preprocessing and estimators produced from all labeled rows."""

    preprocessor: Any
    estimators: dict[str, Any]
    train_rows: int
    task: Literal["regression", "binary_classification"]

    def predict(self, frame: pd.DataFrame, *, candidate: str | None = None) -> np.ndarray:
        """Score ``frame`` row-aligned with the fitted preprocessing and one estimator.

        ``candidate`` may be omitted only when exactly one estimator was fitted. The
        fitted preprocessing enforces the training feature schema on ``frame``.
        """

        if candidate is None:
            if len(self.estimators) != 1:
                raise ValueError("candidate is required when several estimators were fitted")
            (candidate,) = self.estimators
        if candidate not in self.estimators:
            raise ValueError(f"unknown full-fit candidate: {candidate!r}")
        if not isinstance(frame, pd.DataFrame):
            raise TypeError("frame must be a pandas.DataFrame")
        transformed = self.preprocessor.transform(frame)
        return predict_scores(self.estimators[candidate], transformed, task=self.task)


# --------------------------------------------------------------------------- #
# Candidate construction
# --------------------------------------------------------------------------- #


def clone_candidate_estimator(candidate: CandidateConfig, seed: int) -> Any:
    """Clone and seed one sklearn-compatible estimator template."""

    params = dict(candidate.params)
    if "random_state" not in params:
        names = candidate.estimator.get_params(deep=False)
        if "random_state" in names:
            params["random_state"] = seed
    estimator = clone(candidate.estimator)
    if params:
        estimator.set_params(**params)
    if not hasattr(estimator, "fit") or not hasattr(estimator, "predict"):
        raise TypeError(f"Candidate {candidate.name!r} is not sklearn-compatible")
    return estimator


# --------------------------------------------------------------------------- #
# Full-data methodology
# --------------------------------------------------------------------------- #


def fit_full_data(
    frame: pd.DataFrame,
    *,
    feature_cols: tuple[str, ...],
    target_col: str,
    candidates: tuple[CandidateConfig, ...],
    preprocessing: PreprocessingConfig,
    task: Literal["regression", "binary_classification"],
    random_seed: int,
    weight_col: str | None = None,
) -> FullFitResult:
    """Fit preprocessing and chosen candidates using all labeled rows."""

    if not isinstance(frame, pd.DataFrame):
        raise TypeError("frame must be a pandas.DataFrame")
    if not feature_cols or len(feature_cols) != len(set(feature_cols)):
        raise ValueError("feature_cols must be non-empty and unique")
    if not candidates:
        raise ValueError("candidates must not be empty")
    required = (*feature_cols, target_col, *((weight_col,) if weight_col is not None else ()))
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(f"missing full-fit columns: {missing}")
    training_rows = frame.loc[frame[target_col].notna()]
    if training_rows.empty:
        raise ValueError("full-data training requires at least one observed target")

    preprocessor = build_preprocessor(preprocessing, feature_cols, task=task)
    features = training_rows.loc[:, list(feature_cols)]
    target = training_rows[target_col]
    weights = None
    if weight_col is not None:
        try:
            weights = training_rows[weight_col].to_numpy(dtype=float)
        except (TypeError, ValueError) as exc:
            raise ValueError("sample weights must be numeric") from exc
        if not np.isfinite(weights).all() or np.any(weights <= 0):
            raise ValueError("sample weights must be finite and strictly positive")
    transformed = preprocessor.fit_transform(features, target)
    estimators: dict[str, Any] = {}
    for candidate in candidates:
        estimator = clone_candidate_estimator(candidate, random_seed)
        if weights is None:
            estimator.fit(transformed, target)
        else:
            estimator.fit(transformed, target, sample_weight=weights)
        estimators[candidate.name] = estimator
    return FullFitResult(
        preprocessor=preprocessor,
        estimators=estimators,
        train_rows=len(training_rows),
        task=task,
    )


__all__ = ["FullFitResult", "fit_full_data"]
