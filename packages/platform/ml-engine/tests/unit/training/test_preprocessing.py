"""Tests for strict, fold-local sklearn preprocessing.

Usage::

    pytest tests/unit/training/test_preprocessing.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from sklearn.pipeline import Pipeline

from ml_engine.training.config import PreprocessingConfig
from ml_engine.training.preprocessing import build_preprocessor

# --------------------------------------------------------------------------- #
# Fixtures and helpers
# --------------------------------------------------------------------------- #


def _config(**overrides: object) -> PreprocessingConfig:
    """Create a canonical preprocessing config."""

    return PreprocessingConfig(**overrides)  # type: ignore[arg-type]


def _data() -> pd.DataFrame:
    """Return a small numeric feature frame."""

    return pd.DataFrame({"b": [4.0, 5.0, 6.0], "a": [1.0, 2.0, 3.0]})


# --------------------------------------------------------------------------- #
# Preprocessing behavior
# --------------------------------------------------------------------------- #


def test_passthrough_reorders_features_and_ignores_extra_columns() -> None:
    """Required columns are selected in configured order."""

    transformer = build_preprocessor(_config(), ("a", "b"))
    source = _data().assign(extra=99)
    transformed = transformer.fit_transform(source)

    assert isinstance(transformer, Pipeline)
    np.testing.assert_allclose(transformed, [[1, 4], [2, 5], [3, 6]])
    np.testing.assert_array_equal(transformer.get_feature_names_out(), ["a", "b"])


def test_missing_values_require_an_imputer() -> None:
    """Strict passthrough never silently fills missing values."""

    transformer = build_preprocessor(_config(), ("a", "b"))
    with pytest.raises(ValueError, match="Missing feature"):
        transformer.fit(_data().assign(a=[1.0, np.nan, 3.0]))


def test_imputation_and_scaling_are_fit_on_training_rows_only() -> None:
    """Evaluation sentinels cannot change learned imputation/scaling state."""

    config = _config(
        impute_strategy="median",
        scale="standard",
        missing_policy="error",
    )
    train = pd.DataFrame({"a": [1.0, np.nan, 3.0], "b": [10.0, 20.0, 30.0]})
    evaluation = pd.DataFrame({"a": [1000.0], "b": [1000.0]})
    transformer = build_preprocessor(config, ("a", "b"))
    transformer.fit(train)
    first = transformer.transform(evaluation)
    second = transformer.transform(evaluation.assign(a=2000.0, b=2000.0))

    assert not np.allclose(first, second)
    assert transformer.named_steps["imputer"].statistics_[0] == 2.0


def test_fixed_clipping_is_applied_without_leaking_evaluation_values() -> None:
    """Configured clipping bounds are explicit and deterministic."""

    transformer = build_preprocessor(_config(clip_min=0.0, clip_max=1.0), ("a", "b"))
    transformer.fit(_data())
    transformed = transformer.transform(pd.DataFrame({"a": [-5.0], "b": [9.0]}))

    np.testing.assert_allclose(transformed, [[0.0, 1.0]])


def test_feature_selection_is_fold_local_and_caps_output_width() -> None:
    """Target-aware selection sees only the target passed to fit."""

    transformer = build_preprocessor(
        _config(max_features=1),
        ("a", "b"),
    )
    transformer.fit(_data(), np.array([0.0, 1.0, 2.0]))
    transformed = transformer.transform(_data())

    assert transformed.shape == (3, 1)


@pytest.mark.parametrize("task", ("regression", "binary_classification"))
@pytest.mark.parametrize(
    "config",
    (
        _config(),
        _config(impute_strategy="mean"),
        _config(impute_strategy="median"),
        _config(impute_strategy="most_frequent"),
        _config(impute_strategy="constant", impute_fill_value=-2.0),
        _config(scale="standard"),
        _config(scale="minmax"),
        _config(scale="robust"),
        _config(scale="maxabs"),
        _config(clip_min={"a": -1.0}, clip_max={"b": 2.0}),
        _config(winsorize=(0.1, 0.9)),
        _config(max_features=1),
        _config(max_features=9),
        _config(impute_strategy="median", winsorize=(0.1, 0.9), scale="standard", max_features=1),
    ),
)
def test_fit_transform_matches_separate_fit_and_transform(
    config: PreprocessingConfig, task: str
) -> None:
    """Training matrices and later predictions retain the established fit semantics."""

    train = pd.DataFrame(
        {"a": [-3.0, 1.0, 4.0, 2.0, -1.0, 6.0], "b": [7.0, -2.0, 1.0, 4.0, 3.0, 0.0]}
    )
    if config.impute_strategy is not None:
        train.loc[1, "a"] = np.nan
    target = np.array([0, 1, 0, 1, 0, 1])
    evaluation = pd.DataFrame({"a": [-100.0, 100.0], "b": [200.0, -200.0]})
    separate = build_preprocessor(config, ("a", "b"), task=task)
    combined = build_preprocessor(config, ("a", "b"), task=task)
    separate.fit(train, target)

    np.testing.assert_array_equal(combined.fit_transform(train, target), separate.transform(train))
    np.testing.assert_array_equal(combined.transform(evaluation), separate.transform(evaluation))
    np.testing.assert_array_equal(
        combined.get_feature_names_out(), separate.get_feature_names_out()
    )


@pytest.mark.parametrize(
    ("frame", "message"),
    (
        (_data().drop(columns="a"), "Missing required"),
        (_data().assign(a=["x", "y", "z"]), "numeric"),
    ),
)
def test_schema_guard_rejects_missing_or_incompatible_inputs(
    frame: pd.DataFrame, message: str
) -> None:
    """Every transform call enforces the persisted input schema."""

    transformer = build_preprocessor(_config(), ("a", "b"))
    transformer.fit(_data())
    with pytest.raises((TypeError, ValueError), match=message):
        transformer.transform(frame)
