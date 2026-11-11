"""Load a verified predictive artifact and execute read-only inference.

Usage::

    pipeline = InferencePipeline.load("models/model-v1", trusted=True)
    result = pipeline.predict(new_data, include_base_predictions=True)

``InferencePipeline`` never fits, updates, selects, registers, or writes.  The
artifact loader performs manifest and checksum verification before this class
receives any serialized model state.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

import numpy as np
import pandas as pd

from .._artifact_format import ArtifactPayload
from .._predict import predict_scores, prediction_array
from .result import PredictionResult

# --------------------------------------------------------------------------- #
# Schema and prediction helpers
# --------------------------------------------------------------------------- #


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    """Return a mapping boundary value or fail with a useful schema error."""

    if not isinstance(value, Mapping):
        raise TypeError(f"artifact {label} must be a mapping")
    return value


def _ordered_names(value: Any, label: str) -> tuple[str, ...]:
    """Validate an ordered schema list."""

    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        raise TypeError(f"artifact {label} must be an ordered list of names")
    names = tuple(value)
    if not names or any(not isinstance(name, str) or not name for name in names):
        raise ValueError(f"artifact {label} must contain non-empty string names")
    if len(set(names)) != len(names):
        raise ValueError(f"artifact {label} contains duplicate names")
    return names


def _apply_transform(transform: Any, values: np.ndarray, expected_rows: int) -> np.ndarray:
    """Apply the persisted final prediction transform without fitting it."""

    if transform is None:
        return values
    if not hasattr(transform, "transform"):
        raise TypeError("prediction transform must implement transform()")
    transformed = transform.transform(values.reshape(-1, 1))
    return prediction_array(
        transformed,
        label="prediction transform",
        expected_rows=expected_rows,
    )


def _model_tasks(config: Mapping[str, Any], models: Mapping[str, Any]) -> dict[str, str]:
    """Resolve persisted candidate overrides, with a legacy global-task fallback."""
    default = str(config["task"])
    candidates = config.get("candidates")
    if candidates is None:
        return dict.fromkeys(models, default)
    if not isinstance(candidates, (list, tuple)):
        raise TypeError("artifact candidates must be an ordered list")
    tasks: dict[str, str] = {}
    for value in candidates:
        candidate = _mapping(value, "candidate")
        name = candidate.get("name")
        if not isinstance(name, str) or not name or name in tasks:
            raise ValueError("artifact candidate names must be nonempty and unique")
        task = candidate.get("task")
        task = default if task is None else task
        if task not in {"regression", "binary_classification"}:
            raise ValueError(f"artifact candidate {name!r} must declare a supported task")
        tasks[name] = task
    missing = [name for name in models if name not in tasks]
    if missing:
        raise ValueError(f"artifact models lack candidate declarations: {missing}")
    return {name: tasks[name] for name in models}


# --------------------------------------------------------------------------- #
# Immutable inference pipeline
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True, init=False)
class InferencePipeline:
    """An immutable, read-only execution view over one ``ArtifactPayload``."""

    config: Mapping[str, Any]
    schema: Mapping[str, Any]
    preprocessor: Any
    models: Mapping[str, Any]
    ensemble: Any | None
    prediction_transform: Any | None
    manifest: Mapping[str, Any]
    selection: Mapping[str, Any]
    artifact_path: Path | None
    _tasks: Mapping[str, str]

    def __init__(self, payload: ArtifactPayload, artifact_path: Path | None = None) -> None:
        """Build an inference view from the typed loader payload.

        Callers normally use :meth:`load`; this constructor is kept explicit so
        tests and in-memory integrations can pass an already verified payload.
        """

        if not isinstance(payload, ArtifactPayload):
            raise TypeError("payload must be an ArtifactPayload")
        config = _mapping(payload.config, "config")
        schema = _mapping(payload.schema, "schema")
        models = _mapping(payload.models, "models")
        manifest = _mapping(payload.manifest, "manifest")
        selection = _mapping(payload.selection, "selection")
        if not models:
            raise ValueError("artifact must contain at least one fitted model")
        if config.get("task") not in {"regression", "binary_classification"}:
            raise ValueError("artifact config must declare a supported task")
        object.__setattr__(self, "config", config)
        object.__setattr__(self, "schema", MappingProxyType(dict(schema)))
        object.__setattr__(self, "preprocessor", payload.preprocessor)
        object.__setattr__(self, "models", MappingProxyType(dict(models)))
        object.__setattr__(self, "ensemble", payload.ensemble)
        object.__setattr__(self, "prediction_transform", payload.prediction_transform)
        object.__setattr__(self, "manifest", MappingProxyType(dict(manifest)))
        object.__setattr__(self, "selection", MappingProxyType(dict(selection)))
        object.__setattr__(self, "artifact_path", artifact_path)
        object.__setattr__(self, "_tasks", MappingProxyType(_model_tasks(config, models)))

    # ------------------------------------------------------------------ #
    # Loading
    # ------------------------------------------------------------------ #

    @classmethod
    def load(cls, path: str | Path, *, trusted: bool = False) -> InferencePipeline:
        """Verify and load one trusted artifact directory.

        ``joblib`` artifacts can execute serialized Python while loading.  The
        Callers must pass ``trusted=True`` because joblib deserialization can
        execute Python code.
        """

        from ml_engine._artifact import load_artifact

        artifact_path = Path(path)
        payload = load_artifact(artifact_path, trusted=trusted)
        return cls(payload, artifact_path=artifact_path)

    # ------------------------------------------------------------------ #
    # Persisted schema contract
    # ------------------------------------------------------------------ #

    def _schema_values(
        self,
    ) -> tuple[tuple[str, ...], Mapping[str, Any], str | None, str | None, str | None]:
        """Resolve ordered features, dtypes, and identity columns explicitly."""

        feature_value = self.schema.get("feature_cols")
        if feature_value is None:
            raise ValueError("artifact schema does not declare ordered feature columns")
        feature_cols = _ordered_names(feature_value, "feature columns")
        dtypes_value = self.schema.get("dtypes")
        if dtypes_value is None:
            dtypes: Mapping[str, Any] = {}
        else:
            dtypes = _mapping(dtypes_value, "dtypes")
        row_id_col = self.schema.get("row_id_col")
        timestamp_col = self.schema.get("timestamp_col")
        entity_col = self.schema.get("entity_col")
        for name, value in (
            ("row_id_col", row_id_col),
            ("timestamp_col", timestamp_col),
            ("entity_col", entity_col),
        ):
            if value is not None and (not isinstance(value, str) or not value):
                raise ValueError(f"artifact {name} must be a non-empty string or null")
        return feature_cols, dtypes, row_id_col, timestamp_col, entity_col

    def _validate_input(
        self, frame: pd.DataFrame
    ) -> tuple[tuple[str, ...], Mapping[str, Any], str | None, str | None, str | None]:
        """Validate required columns and persisted dtypes without changing input."""

        if not isinstance(frame, pd.DataFrame):
            raise TypeError("new_data must be a pandas.DataFrame")
        if frame.columns.duplicated().any():
            raise ValueError("new_data must not contain duplicate column names")
        feature_cols, dtypes, row_id_col, timestamp_col, entity_col = self._schema_values()
        required = list(feature_cols)
        for column in (row_id_col, timestamp_col, entity_col):
            if column is not None and column not in required:
                required.append(column)
        missing = [column for column in required if column not in frame.columns]
        if missing:
            raise ValueError(f"new_data is missing required columns: {missing}")
        for column in dtypes:
            if column in frame.columns and not pd.api.types.is_numeric_dtype(frame[column]):
                raise TypeError(f"new_data column {column!r} must be numeric")
        return feature_cols, dtypes, row_id_col, timestamp_col, entity_col

    # ------------------------------------------------------------------ #
    # Read-only prediction
    # ------------------------------------------------------------------ #

    def _selected_model_names(self) -> tuple[str, ...]:
        """Resolve selected base models from the persisted selection report."""

        if self.ensemble is not None and hasattr(self.ensemble, "model_names"):
            ensemble_names = _ordered_names(self.ensemble.model_names, "ensemble model names")
            missing = [name for name in ensemble_names if name not in self.models]
            if missing:
                raise ValueError(f"ensemble references missing models: {missing}")
            return ensemble_names
        selected = self.selection.get("selected_candidates")
        if isinstance(selected, (list, tuple)):
            selected_names = _ordered_names(selected, "selected models")
        elif selected is None:
            selected_names = ()
        else:
            raise TypeError("artifact selected_candidates must be an ordered list")
        if selected_names:
            missing = [name for name in selected_names if name not in self.models]
            if missing:
                raise ValueError(f"artifact selection references missing models: {missing}")
            return selected_names
        return tuple(self.models)

    def _base_predictions(self, transformed: Any) -> pd.DataFrame:
        """Run each selected model and return aligned predictions in model order."""

        names = self._selected_model_names()
        values: dict[str, np.ndarray] = {}
        for name in names:
            model = self.models[name]
            try:
                values[name] = predict_scores(model, transformed, task=self._tasks[name])
            except (TypeError, ValueError) as exc:
                raise type(exc)(f"model {name!r}: {exc}") from exc
        return pd.DataFrame(values)

    def _final_prediction(self, base: pd.DataFrame) -> np.ndarray:
        """Combine selected base models and apply the persisted transform."""

        if self.ensemble is None:
            if base.shape[1] != 1:
                raise ValueError("multiple selected models require a persisted ensemble")
            final = base.iloc[:, 0].to_numpy(copy=True)
        else:
            if not hasattr(self.ensemble, "predict"):
                raise TypeError("ensemble does not implement predict()")
            final = prediction_array(
                self.ensemble.predict(base),
                label="ensemble",
                expected_rows=len(base),
            )
        return _apply_transform(self.prediction_transform, final, len(base))

    def predict(
        self,
        new_data: pd.DataFrame,
        *,
        include_base_predictions: bool = False,
    ) -> PredictionResult:
        """Generate row-aligned predictions without mutating ``new_data``."""

        feature_cols, _, row_id_col, timestamp_col, entity_col = self._validate_input(new_data)
        features = new_data.loc[:, list(feature_cols)].copy(deep=True)
        transformed = features
        if self.preprocessor is not None:
            if not hasattr(self.preprocessor, "transform"):
                raise TypeError("preprocessor does not implement transform()")
            transformed = self.preprocessor.transform(features)
        base = self._base_predictions(transformed)
        final = self._final_prediction(base)

        row_ids = (
            new_data[row_id_col].to_numpy() if row_id_col is not None else new_data.index.to_numpy()
        )
        timestamps = new_data[timestamp_col].to_numpy() if timestamp_col is not None else None
        entities = new_data[entity_col].to_numpy() if entity_col is not None else None
        return PredictionResult(
            predictions=final,
            row_ids=row_ids,
            timestamps=timestamps,
            entities=entities,
            base_predictions=base if include_base_predictions else None,
            metadata=self.manifest,
        )


__all__ = ["InferencePipeline"]
