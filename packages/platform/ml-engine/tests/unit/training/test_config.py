"""Unit tests for the immutable training configuration contracts.

Usage::

    uv run pytest tests/unit/training/test_config.py -q

These tests cover constructor-level validation only.  Dataset-dependent
validation belongs to the training pipeline and is covered by its own tests.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError, is_dataclass

import pytest
from sklearn.linear_model import Ridge

from ml_engine.training.config import (
    CandidateConfig,
    EnsembleConfig,
    MetricConfig,
    PreprocessingConfig,
    SelectionConfig,
    SplitConfig,
    TrainingConfig,
)

# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


def _candidate(name: str = "ridge") -> CandidateConfig:
    """Build an unfitted named estimator candidate."""
    return CandidateConfig(name=name, estimator=Ridge())


def _config(**overrides: object) -> TrainingConfig:
    """Build a valid baseline config while keeping tests explicit."""
    values: dict[str, object] = {
        "feature_cols": ("feature_a", "feature_b"),
        "target_col": "target",
        "timestamp_col": "timestamp",
        "split": SplitConfig("expanding", 3, 1),
        "candidates": (_candidate(),),
        "metrics": (MetricConfig("rmse"),),
        "selection": SelectionConfig("rmse", "minimize"),
        "random_seed": 7,
    }
    values.update(overrides)
    return TrainingConfig(**values)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- #
# Happy paths and immutability
# --------------------------------------------------------------------------- #


def test_valid_configuration_normalizes_sequences_and_defaults() -> None:
    config = _config(feature_cols=["feature_a", "feature_b"])

    assert is_dataclass(config)
    assert config.feature_cols == ("feature_a", "feature_b")
    assert config.period_col is None
    assert config.metrics == (MetricConfig("rmse"),)
    assert config.split.kind == "expanding"
    assert config.split.purge_boundary == "strict"
    assert config.split.first_eval_period is None
    assert config.ensemble.kind == "none"
    assert config.weight_col is None
    assert config.final_refit is True
    assert config.keep_fold_models is False


def test_configuration_records_are_frozen() -> None:
    config = _config()

    with pytest.raises(FrozenInstanceError):
        config.random_seed = 8  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# Component-level validation
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("factory", "match"),
    [
        (lambda: CandidateConfig(name="", estimator=Ridge()), "name"),
        (lambda: CandidateConfig(name="bad", estimator=Ridge(), feature_cols=()), "feature_cols"),
        (lambda: SplitConfig(kind="unknown", min_train_periods=2, eval_periods=1), "kind"),
        (lambda: SplitConfig(kind="rolling", min_train_periods=2, eval_periods=1), "rolling"),
        (lambda: PreprocessingConfig(winsorize=(0.8, 0.2)), "winsorize"),
        (lambda: SelectionConfig("rmse", "minimize", min_coverage=1.1), "coverage"),
        (lambda: EnsembleConfig(kind="fixed_weight"), "weights"),
    ],
)
def test_invalid_component_values_fail_closed(factory: object, match: str) -> None:
    with pytest.raises((TypeError, ValueError), match=match):
        factory()  # type: ignore[operator]


def test_metric_requires_minimum_observation_count() -> None:
    with pytest.raises(ValueError, match="min_observations"):
        MetricConfig("rmse", min_observations=0)


# --------------------------------------------------------------------------- #
# Top-level cross-field validation
# --------------------------------------------------------------------------- #


def test_duplicate_features_are_rejected() -> None:
    with pytest.raises(ValueError, match="feature_cols"):
        _config(feature_cols=("feature_a", "feature_a"))


def test_duplicate_candidates_are_rejected() -> None:
    with pytest.raises(ValueError, match="candidate names"):
        _config(candidates=(_candidate("same"), _candidate("same")))


def test_primary_metric_must_be_configured() -> None:
    with pytest.raises(ValueError, match="primary_metric"):
        _config(metrics=(MetricConfig("mae"),))


def test_purged_split_requires_target_end_column() -> None:
    split = SplitConfig(kind="purged", min_train_periods=2, eval_periods=1)
    with pytest.raises(ValueError, match="target_end_col"):
        _config(split=split)


@pytest.mark.parametrize("options", [{"purge_boundary": "closed"}, {"first_eval_period": 3}])
def test_purge_options_are_rejected_outside_purged_splits(options: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="purged"):
        SplitConfig("expanding", 2, 1, **options)  # type: ignore[arg-type]


@pytest.mark.parametrize("boundary", ["left", "open", "inclusive"])
def test_unknown_purge_boundaries_fail_closed(boundary: str) -> None:
    with pytest.raises(ValueError, match="purge_boundary"):
        SplitConfig("purged", 2, 1, purge_boundary=boundary)  # type: ignore[arg-type]


def test_weight_column_cannot_overlap_features_target_or_timestamp() -> None:
    for column in ("feature_a", "target", "timestamp"):
        with pytest.raises(ValueError, match="weight_col"):
            _config(weight_col=column)


@pytest.mark.parametrize("seed", [True, False, "7", 7.0])
def test_random_seed_must_be_an_integer(seed: object) -> None:
    with pytest.raises(TypeError, match="random_seed"):
        _config(random_seed=seed)
