"""Focused tests for explicit training methodology entry points.

Usage::

    uv run pytest tests/unit/training/test_methodologies.py -q
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports
# --------------------------------------------------------------------------- #

import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LinearRegression

from ml_engine.training import CandidateConfig, PreprocessingConfig, SplitConfig
from ml_engine.training.methodologies import (
    build_holdout_plan,
    build_walk_forward_plan,
    fit_full_data,
)

# --------------------------------------------------------------------------- #
# Methodology boundaries
# --------------------------------------------------------------------------- #


def test_methodology_planners_reject_the_wrong_policy() -> None:
    """Each planning entry point accepts only its named methodology."""

    frame = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=6, tz="UTC"),
            "row_id": range(6),
        }
    )

    with pytest.raises(ValueError, match="holdout methodology"):
        build_holdout_plan(
            frame,
            SplitConfig("expanding", 3, 2),
            timestamp_col="timestamp",
            row_id_col="row_id",
        )
    with pytest.raises(ValueError, match="walk-forward methodology"):
        build_walk_forward_plan(
            frame,
            SplitConfig("chronological_holdout", 3, 2),
            timestamp_col="timestamp",
            row_id_col="row_id",
        )


def test_full_fit_uses_every_labeled_row_and_leaves_template_unfitted() -> None:
    """Full-data fitting skips evaluation and returns deployable fitted state."""

    template = LinearRegression()
    frame = pd.DataFrame(
        {
            "feature": np.arange(6.0),
            "target": [1.0, 3.0, 5.0, 7.0, 9.0, np.nan],
        }
    )

    result = fit_full_data(
        frame,
        feature_cols=("feature",),
        target_col="target",
        candidates=(CandidateConfig("linear", template),),
        preprocessing=PreprocessingConfig(),
        task="regression",
        random_seed=7,
    )

    assert result.train_rows == 5
    assert set(result.estimators) == {"linear"}
    assert not hasattr(template, "coef_")
    transformed = result.preprocessor.transform(frame.loc[:4, ["feature"]])
    predictions = result.estimators["linear"].predict(transformed)
    np.testing.assert_allclose(predictions, frame.loc[:4, "target"])


def test_full_fit_predict_applies_fitted_preprocessing_and_schema_guard() -> None:
    """Full-fit prediction scales with training statistics and rejects schema drift."""

    frame = pd.DataFrame(
        {
            "a": [0.0, 1.0, 2.0, 3.0, 4.0],
            "b": [1.0, 0.0, 1.0, 0.0, 1.0],
            "target": [1.0, 2.0, 5.0, 6.0, 9.0],
        }
    )
    result = fit_full_data(
        frame,
        feature_cols=("a", "b"),
        target_col="target",
        candidates=(
            CandidateConfig("linear", LinearRegression()),
            CandidateConfig("other", LinearRegression(fit_intercept=False)),
        ),
        preprocessing=PreprocessingConfig(scale="standard"),
        task="regression",
        random_seed=7,
    )
    new = pd.DataFrame({"b": [0.0, 1.0], "a": [10.0, -1.0], "extra": [9.0, 9.0]})

    expected = result.estimators["linear"].predict(result.preprocessor.transform(new))
    np.testing.assert_allclose(result.predict(new, candidate="linear"), expected)
    np.testing.assert_allclose(result.predict(new, candidate="linear"), 2.0 * new["a"] + new["b"])
    with pytest.raises(ValueError, match="candidate is required"):
        result.predict(new)
    with pytest.raises(ValueError, match="unknown full-fit candidate"):
        result.predict(new, candidate="missing")
    with pytest.raises(ValueError, match="Missing required feature columns"):
        result.predict(new.drop(columns="b"), candidate="linear")
    with pytest.raises(ValueError, match="Missing feature values"):
        result.predict(new.assign(a=[np.nan, 1.0]), candidate="linear")
