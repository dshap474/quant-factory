"""Focused tests for the read-only inference pipeline.

Usage::

    pytest tests/unit/inference/test_pipeline.py

The fixtures below use tiny in-memory stand-ins for fitted preprocessing,
estimators, ensembles, and prediction transforms.  Artifact verification is
owned by ``ml_engine._artifact`` and is exercised separately.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from ml_engine._artifact import ArtifactPayload
from ml_engine.inference import InferencePipeline, PredictionResult

# --------------------------------------------------------------------------- #
# Tiny fitted-state test doubles
# --------------------------------------------------------------------------- #


class _Preprocessor:
    """Record feature selection and return a numeric matrix."""

    def __init__(self) -> None:
        self.seen: list[list[str]] = []

    def transform(self, frame: pd.DataFrame) -> np.ndarray:
        self.seen.append(list(frame.columns))
        return frame.to_numpy(dtype=float)


class _Model:
    """Return one fixed linear combination of the transformed columns."""

    def __init__(self, weights: tuple[float, ...], offset: float = 0.0) -> None:
        self.weights = np.asarray(weights, dtype=float)
        self.offset = offset

    def predict(self, values: Any) -> np.ndarray:
        matrix = np.asarray(values, dtype=float)
        return matrix @ self.weights + self.offset


class _DualModel(_Model):
    """Distinguish regression scores from positive-class probabilities."""

    def predict_proba(self, values: Any) -> np.ndarray:
        return np.tile([0.75, 0.25], (len(values), 1))


class _Ensemble:
    """Combine named base predictions with fixed weights."""

    def __init__(self, weights: tuple[float, ...]) -> None:
        self.model_names = ("left", "right")
        self.weights = np.asarray(weights, dtype=float)

    def predict(self, values: pd.DataFrame) -> np.ndarray:
        return values.to_numpy(dtype=float) @ self.weights


class _Transform:
    """Apply a persisted final affine prediction transform."""

    def transform(self, values: np.ndarray) -> np.ndarray:
        return values * 2.0 + 1.0


def _payload(*, with_ensemble: bool = True) -> ArtifactPayload:
    """Construct a complete in-memory payload for inference tests."""

    return ArtifactPayload(
        config={"feature_cols": ["b", "a"], "task": "regression"},
        schema={
            "feature_cols": ["b", "a"],
            "dtypes": {"a": "float64", "b": "float64"},
            "row_id_col": "row_id",
            "timestamp_col": "timestamp",
            "entity_col": "entity",
        },
        preprocessor=_Preprocessor(),
        models={
            "left": _Model((1.0, 0.0), offset=1.0),
            "right": _Model((0.0, 1.0), offset=2.0),
        },
        ensemble=_Ensemble((0.25, 0.75)) if with_ensemble else None,
        prediction_transform=_Transform(),
        selection={"selected_candidates": ["left"]},
        manifest={"artifact_schema_version": 1, "ml_engine_version": "0.1.0"},
    )


def _frame() -> pd.DataFrame:
    """Return deliberately out-of-order rows and feature columns."""

    return pd.DataFrame(
        {
            "row_id": [9, 3],
            "timestamp": pd.to_datetime(["2024-01-02", "2024-01-01"], utc=True),
            "entity": ["b", "a"],
            "a": np.array([10.0, 20.0], dtype="float64"),
            "b": np.array([1.0, 2.0], dtype="float64"),
            "ignored": ["x", "y"],
        }
    )


# --------------------------------------------------------------------------- #
# Prediction behavior
# --------------------------------------------------------------------------- #


def test_predict_preserves_caller_order_identity_and_feature_order() -> None:
    """Select persisted features without sorting or mutating caller rows."""

    payload = _payload()
    frame = _frame()
    before = frame.copy(deep=True)

    result = InferencePipeline(payload).predict(frame, include_base_predictions=True)

    assert isinstance(result, PredictionResult)
    assert result.row_ids.tolist() == [9, 3]
    assert result.timestamps.tolist() == before["timestamp"].to_numpy().tolist()
    assert result.entities.tolist() == ["b", "a"]
    assert result.base_predictions is not None
    assert list(result.base_predictions.columns) == ["left", "right"]
    # left = b + 1, right = a + 2, ensemble = .25*left + .75*right,
    # then the final transform doubles and adds one.
    expected = 2.0 * (0.25 * np.array([2.0, 3.0]) + 0.75 * np.array([12.0, 22.0])) + 1.0
    np.testing.assert_allclose(result.predictions, expected)
    pd.testing.assert_frame_equal(frame, before)
    assert payload.preprocessor.seen == [["b", "a"]]


def test_predict_without_ensemble_requires_one_selected_model() -> None:
    """A multi-model artifact cannot silently choose an arbitrary estimator."""

    payload = _payload(with_ensemble=False)
    result = InferencePipeline(payload).predict(_frame())
    expected = 2.0 * (np.array([1.0, 2.0]) + 1.0) + 1.0
    np.testing.assert_allclose(result.predictions, expected)


@pytest.mark.parametrize("global_task", ["regression", "binary_classification"])
def test_selected_models_resolve_their_own_persisted_task(global_task) -> None:
    payload = _payload()
    payload.config["task"] = global_task
    payload.config["candidates"] = [
        {"name": "left", "task": "binary_classification"},
        {"name": "right", "task": "regression"},
    ]
    payload.models["left"] = _DualModel((1.0, 0.0))
    payload.models["right"] = _DualModel((0.0, 1.0))
    result = InferencePipeline(payload).predict(_frame(), include_base_predictions=True)
    # Ensemble consumes .25 probabilities for left and raw a=[10,20] for right.
    np.testing.assert_array_equal(result.base_predictions["left"], [0.25, 0.25])
    np.testing.assert_array_equal(result.base_predictions["right"], [10.0, 20.0])
    np.testing.assert_array_equal(result.predictions, [16.125, 31.125])


@pytest.mark.parametrize(
    "candidates",
    [
        "left",
        [None],
        [{"name": "left", "task": "multiclass"}],
        [{"name": "left"}, {"name": "left"}],
        [{"name": "left"}],
    ],
)
def test_invalid_persisted_task_declarations_fail_closed(candidates) -> None:
    payload = _payload()
    payload.config["candidates"] = candidates
    with pytest.raises((TypeError, ValueError), match="candidate|task"):
        InferencePipeline(payload)


@pytest.mark.parametrize(
    ("frame_mutation", "error_type", "message"),
    (
        (lambda frame: frame.drop(columns="a", inplace=True), ValueError, "missing"),
        (
            lambda frame: frame.__setitem__("a", ["one", "two"]),
            TypeError,
            "numeric",
        ),
    ),
)
def test_predict_fails_closed_on_missing_or_incompatible_inputs(
    frame_mutation: Any,
    error_type: type[Exception],
    message: str,
) -> None:
    """Schema and dtype violations fail before preprocessing or model calls."""

    frame = _frame()
    frame_mutation(frame)
    with pytest.raises(error_type, match=message):
        InferencePipeline(_payload()).predict(frame)


def test_pipeline_and_result_expose_immutable_boundaries() -> None:
    """Pipeline state cannot be replaced after loading, and results are copies."""

    pipeline = InferencePipeline(_payload())
    with pytest.raises(FrozenInstanceError):
        pipeline.ensemble = None  # type: ignore[misc]
    with pytest.raises(TypeError):
        pipeline.models["other"] = _Model((1.0, 1.0))  # type: ignore[index]

    result = pipeline.predict(_frame())
    values = result.predictions.copy()
    values[0] = -1000.0
    assert result.predictions[0] != values[0]


# --------------------------------------------------------------------------- #
# Artifact loading boundary
# --------------------------------------------------------------------------- #


def test_load_uses_verified_artifact_loader_with_explicit_trust(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Loading delegates integrity checks and passes an explicit trust decision."""

    payload = _payload()
    calls: list[tuple[Path, bool | None]] = []

    def fake_load(path: Path, *, trusted: bool | None = None) -> ArtifactPayload:
        calls.append((path, trusted))
        return payload

    import ml_engine._artifact as artifact

    monkeypatch.setattr(artifact, "load_artifact", fake_load)
    path = tmp_path / "model-v1"
    pipeline = InferencePipeline.load(path, trusted=True)

    assert isinstance(pipeline, InferencePipeline)
    assert calls == [(path, True)]
