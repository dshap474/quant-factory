"""Verify the standalone ml-engine package's curated public API.

Usage::

    pytest tests/unit/test_public_api.py

These tests intentionally assert both the exact export inventory and the
identity of each package-level name with its defining module.
"""

# --------------------------------------------------------------------------- #
# Imports
# --------------------------------------------------------------------------- #

from __future__ import annotations

import importlib

import pytest

# --------------------------------------------------------------------------- #
# Approved public API inventory
# --------------------------------------------------------------------------- #

TRAINING_EXPORTS = (
    "CandidateConfig",
    "EnsembleConfig",
    "MetricConfig",
    "PreprocessingConfig",
    "SelectionConfig",
    "SplitConfig",
    "TrainingConfig",
    "TrainingPipeline",
    "TrainingProgress",
    "TrainingResult",
    "TrainingRun",
    "current_training_run",
)

INFERENCE_EXPORTS = ("InferencePipeline", "PredictionResult")
METHODOLOGY_EXPORTS = (
    "Fold",
    "FoldPlan",
    "FullFitResult",
    "build_fold_plan",
    "build_holdout_plan",
    "build_walk_forward_plan",
    "fit_full_data",
)


@pytest.mark.parametrize(
    ("package_name", "expected_exports"),
    (
        ("ml_engine.training", TRAINING_EXPORTS),
        ("ml_engine.training.methodologies", METHODOLOGY_EXPORTS),
        ("ml_engine.inference", INFERENCE_EXPORTS),
    ),
)
def test_public_api_inventory(
    package_name: str,
    expected_exports: tuple[str, ...],
) -> None:
    """Expose exactly the approved stable names from each subpackage."""
    package = importlib.import_module(package_name)

    assert tuple(package.__all__) == expected_exports
    assert set(package.__dict__) >= set(expected_exports)


@pytest.mark.parametrize(
    ("package_name", "module_name", "export_name"),
    (
        ("ml_engine.training", "ml_engine.training.config", "CandidateConfig"),
        ("ml_engine.training", "ml_engine.training.config", "EnsembleConfig"),
        ("ml_engine.training", "ml_engine.training.config", "MetricConfig"),
        (
            "ml_engine.training",
            "ml_engine.training.config",
            "PreprocessingConfig",
        ),
        ("ml_engine.training", "ml_engine.training.config", "SelectionConfig"),
        ("ml_engine.training", "ml_engine.training.config", "SplitConfig"),
        ("ml_engine.training", "ml_engine.training.config", "TrainingConfig"),
        ("ml_engine.training", "ml_engine.training.pipeline", "TrainingPipeline"),
        ("ml_engine.training", "ml_engine.training.progress", "TrainingProgress"),
        ("ml_engine.training", "ml_engine.training.result", "TrainingResult"),
        ("ml_engine.training", "ml_engine.training.run", "TrainingRun"),
        (
            "ml_engine.training.methodologies",
            "ml_engine.training.methodologies._folds",
            "Fold",
        ),
        (
            "ml_engine.training.methodologies",
            "ml_engine.training.methodologies._folds",
            "FoldPlan",
        ),
        (
            "ml_engine.training.methodologies",
            "ml_engine.training.methodologies.full_fit",
            "FullFitResult",
        ),
        (
            "ml_engine.training.methodologies",
            "ml_engine.training.methodologies._folds",
            "build_fold_plan",
        ),
        (
            "ml_engine.training.methodologies",
            "ml_engine.training.methodologies.holdout",
            "build_holdout_plan",
        ),
        (
            "ml_engine.training.methodologies",
            "ml_engine.training.methodologies.walk_forward",
            "build_walk_forward_plan",
        ),
        (
            "ml_engine.training.methodologies",
            "ml_engine.training.methodologies.full_fit",
            "fit_full_data",
        ),
        ("ml_engine.inference", "ml_engine.inference.pipeline", "InferencePipeline"),
        ("ml_engine.inference", "ml_engine.inference.result", "PredictionResult"),
    ),
)
def test_public_api_names_are_reexports(
    package_name: str,
    module_name: str,
    export_name: str,
) -> None:
    """Keep package-level names identical to their defining classes."""
    package = importlib.import_module(package_name)
    module = importlib.import_module(module_name)

    assert getattr(package, export_name) is getattr(module, export_name)


def test_root_package_does_not_reexport_training_or_inference_names() -> None:
    """Keep the root package free of runtime API aliases."""
    root_package = importlib.import_module("ml_engine")

    for export_name in TRAINING_EXPORTS + INFERENCE_EXPORTS:
        assert not hasattr(root_package, export_name)
