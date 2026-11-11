"""Training outputs and the explicit artifact write boundary.

Usage::

    result = TrainingPipeline(config).run(frame)
    scores = result.predict_fold(features, candidate="linear", fold=0)  # keep_fold_models=True
    result.save("models/example")

The result is intentionally an in-memory value.  Training does not persist
anything until :meth:`TrainingResult.save` is called by its caller.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports
# --------------------------------------------------------------------------- #

import os
from collections.abc import Mapping
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ml_engine._artifact import ArtifactPayload, save_artifact
from ml_engine._artifact_format import ArtifactSerializationError, _jsonable
from ml_engine._predict import predict_scores

from .config import TrainingConfig
from .evaluation import EvaluationSummary
from .methodologies import FoldPlan
from .selection import SelectionReport


# --------------------------------------------------------------------------- #
# Serialization helpers
# --------------------------------------------------------------------------- #


def _json_mapping(value: Any, label: str) -> dict[str, Any]:
    """Serialize a mapping value while preserving a narrow static type."""

    converted = _jsonable(value)
    if not isinstance(converted, dict):
        raise TypeError(f"{label} must serialize to a mapping")
    return converted


# --------------------------------------------------------------------------- #
# Training result
# --------------------------------------------------------------------------- #


@dataclass
class TrainingResult:
    """Complete output of one leakage-safe training run.

    Fields are deliberately plain values so the object can be inspected in a
    notebook without a registry or service.  ``save`` is the only method that
    writes an artifact.
    """

    config: TrainingConfig
    feature_schema: Mapping[str, Any]
    transformed_feature_schema: Mapping[str, Any]
    fold_plan: FoldPlan
    candidate_oos: pd.DataFrame
    candidate_metrics: Mapping[str, EvaluationSummary]
    selection_report: SelectionReport
    selected_candidates: tuple[str, ...]
    _final_preprocessor: Any
    _final_estimators: Mapping[str, Any] | None
    training_cutoff: Any
    data_bounds: Mapping[str, Any]
    metadata: Mapping[str, Any]
    random_seed: int
    warnings: tuple[str, ...]
    fold_models: Mapping[str, Mapping[int, Any]]
    ensemble_oos: pd.DataFrame | None = None
    ensemble_metrics: EvaluationSummary | None = None
    final_ensemble: Any = None
    prediction_transform: Any = None
    _inference_pipeline: Any = None
    fold_preprocessors: Mapping[str, Mapping[int, Any]] = field(default_factory=dict)

    def predict_fold(self, frame: pd.DataFrame, *, candidate: str, fold: int) -> np.ndarray:
        """Predict with a retained fold's fitted preprocessing and estimator.

        Requires ``keep_fold_models=True``. Input uses the fitted preprocessor's
        pandas schema policy and predictions preserve input row order. Scores
        match ``candidate_oos`` (including binary positive-class probabilities);
        no final-refit ensemble or prediction transform is applied. This method
        neither fits nor writes, and does not assert that supplied rows are OOS.
        """
        if not self.config.keep_fold_models:
            raise RuntimeError("fold prediction requires keep_fold_models=True")
        try:
            model = self.fold_models[candidate][fold]
            preprocessor = self.fold_preprocessors[candidate][fold]
        except KeyError as exc:
            raise ValueError(
                f"No retained fitted pipeline for candidate {candidate!r}, fold {fold!r}"
            ) from exc
        declaration = next(item for item in self.config.candidates if item.name == candidate)
        return predict_scores(
            model, preprocessor.transform(frame), task=declaration.task or self.config.task
        )

    @property
    def final_preprocessor(self) -> Any:
        """Return final-refit preprocessing or fail when refitting was disabled."""

        if not self.config.final_refit:
            raise RuntimeError("final preprocessor is unavailable because final_refit=False")
        return self._final_preprocessor

    @property
    def final_estimators(self) -> Mapping[str, Any]:
        """Return final-refit estimators or fail when refitting was disabled."""

        if not self.config.final_refit or self._final_estimators is None:
            raise RuntimeError("final estimators are unavailable because final_refit=False")
        return self._final_estimators

    @property
    def inference_pipeline(self) -> Any:
        """Return in-memory inference or fail when no final refit exists."""

        if not self.config.final_refit or self._inference_pipeline is None:
            raise RuntimeError("inference pipeline is unavailable because final_refit=False")
        return self._inference_pipeline

    @property
    def oos_predictions(self) -> pd.DataFrame:
        """Return selected/ensemble OOS rows in the canonical long-table shape."""
        if self.ensemble_oos is not None:
            return self.ensemble_oos
        if not self.selected_candidates or "candidate" not in self.candidate_oos:
            return self.candidate_oos
        return self.candidate_oos.loc[
            self.candidate_oos["candidate"].isin(self.selected_candidates)
        ].reset_index(drop=True)

    # ------------------------------------------------------------------ #
    # Artifact writing
    # ------------------------------------------------------------------ #

    def _artifact_payload(self) -> ArtifactPayload:
        """Build the single payload used by in-memory and saved inference."""

        schema = _json_mapping(self.feature_schema, "feature_schema")
        schema["transformed_feature_schema"] = _jsonable(self.transformed_feature_schema)
        metrics = {
            str(name): value.to_dict() if hasattr(value, "to_dict") else _jsonable(value)
            for name, value in self.candidate_metrics.items()
        }
        if self.ensemble_metrics is not None:
            metrics["ensemble"] = (
                self.ensemble_metrics.to_dict()
                if hasattr(self.ensemble_metrics, "to_dict")
                else _jsonable(self.ensemble_metrics)
            )
        selection = (
            self.selection_report.to_dict()
            if hasattr(self.selection_report, "to_dict")
            else _jsonable(self.selection_report)
        )
        selection = _json_mapping(selection or {}, "selection")
        selection["selected_candidates"] = list(self.selected_candidates)
        config = {item.name: getattr(self.config, item.name) for item in fields(self.config)}
        transform = config.pop("prediction_transform")
        config = _json_mapping(config, "config")
        try:
            config["prediction_transform"] = _jsonable(transform)
        except ArtifactSerializationError:
            # Transform-only objects need no JSON hooks: fitted state is stored
            # separately in prediction_transform.joblib, never reconstructed here.
            config["prediction_transform"] = {
                "class": f"{type(transform).__module__}.{type(transform).__qualname__}",
                "state": "prediction_transform.joblib",
            }
        return ArtifactPayload(
            config=config,
            schema=schema,
            preprocessor=self.final_preprocessor,
            models=dict(self.final_estimators),
            ensemble=self.final_ensemble,
            prediction_transform=self.prediction_transform,
            oos_predictions=self.oos_predictions,
            metrics=metrics,
            selection=selection,
            manifest={
                **_json_mapping(self.metadata, "metadata"),
                "selected_candidates": list(self.selected_candidates),
                "training_cutoff": _jsonable(self.training_cutoff),
                "data_bounds": _jsonable(self.data_bounds),
                "random_seed": self.random_seed,
            },
        )

    def save(self, path: str | os.PathLike[str]) -> Path:
        """Atomically save this result and return the destination path.

        Existing destinations are rejected; callers must choose a new version.
        """

        return save_artifact(Path(path), self._artifact_payload())


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

__all__ = ["TrainingResult"]
