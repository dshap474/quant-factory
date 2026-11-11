"""Normalize estimator and prediction-transform outputs for training and inference.

Usage::

    scores = predict_scores(model, transformed_features, task="regression")
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports
# --------------------------------------------------------------------------- #

from typing import Any

import numpy as np


# --------------------------------------------------------------------------- #
# Prediction normalization
# --------------------------------------------------------------------------- #


def prediction_array(values: Any, *, label: str, expected_rows: int) -> np.ndarray:
    """Return one copied prediction value per input row."""

    array = np.asarray(values)
    if array.ndim == 2 and array.shape[1] == 1:
        array = array[:, 0]
    if array.ndim != 1 or len(array) != expected_rows:
        raise ValueError(f"{label} must return one prediction per input row")
    return array.copy()


def predict_scores(model: Any, features: Any, *, task: str) -> np.ndarray:
    """Run one fitted estimator through the shared task-aware score contract."""

    if not hasattr(model, "predict"):
        raise TypeError("model must implement predict()")
    if task == "binary_classification" and hasattr(model, "predict_proba"):
        probabilities = np.asarray(model.predict_proba(features))
        if probabilities.ndim != 2 or probabilities.shape[1] != 2:
            raise ValueError("binary predict_proba() must return exactly two columns")
        values = probabilities[:, 1]
    elif task == "binary_classification" and hasattr(model, "decision_function"):
        values = model.decision_function(features)
    else:
        values = model.predict(features)
    return prediction_array(values, label="model", expected_rows=len(features))


__all__ = ["predict_scores", "prediction_array"]
