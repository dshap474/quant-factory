"""Pin the standalone package's explicit runtime imports and method signatures.

Usage::

    pytest tests/integration/test_public_typing.py

These checks intentionally use the public subpackages rather than importing
implementation helpers.  The package is a typed, pandas-boundary library:
runtime classes must be importable from their documented modules, and the
end-to-end methods must retain their explicit parameter and return contracts.
"""

from __future__ import annotations

import inspect
import typing
from pathlib import Path

import pandas as pd

import ml_engine
from ml_engine.inference import InferencePipeline, PredictionResult
from ml_engine.training import (
    CandidateConfig,
    EnsembleConfig,
    MetricConfig,
    PreprocessingConfig,
    SelectionConfig,
    SplitConfig,
    TrainingConfig,
    TrainingPipeline,
    TrainingProgress,
    TrainingResult,
    TrainingRun,
)

# --------------------------------------------------------------------------- #
# Public import and package typing contract
# --------------------------------------------------------------------------- #


def test_public_classes_are_importable_from_documented_subpackages() -> None:
    """Keep all runtime classes on the two explicit public import paths."""
    assert TrainingPipeline.__module__ == "ml_engine.training.pipeline"
    assert TrainingProgress.__module__ == "ml_engine.training.progress"
    assert TrainingResult.__module__ == "ml_engine.training.result"
    assert TrainingRun.__module__ == "ml_engine.training.run"
    assert InferencePipeline.__module__ == "ml_engine.inference.pipeline"
    assert PredictionResult.__module__ == "ml_engine.inference.result"

    for config_type in (
        CandidateConfig,
        EnsembleConfig,
        MetricConfig,
        PreprocessingConfig,
        SelectionConfig,
        SplitConfig,
        TrainingConfig,
    ):
        assert config_type.__module__ == "ml_engine.training.config"


def test_distribution_advertises_py_typed_marker() -> None:
    """Require a PEP 561 marker so consumers can type-check the package."""
    package_root = Path(ml_engine.__file__).resolve().parent
    assert (package_root / "py.typed").is_file()


# --------------------------------------------------------------------------- #
# Explicit execution signatures
# --------------------------------------------------------------------------- #


def test_training_execution_signature_is_explicit() -> None:
    """Training accepts one dataframe and returns one complete result."""
    constructor = inspect.signature(TrainingPipeline)
    assert tuple(constructor.parameters) == ("config",)
    constructor_hints = typing.get_type_hints(TrainingPipeline.__init__)
    assert constructor_hints["config"] is TrainingConfig

    run = inspect.signature(TrainingPipeline.run)
    assert tuple(run.parameters) == ("self", "dataset", "progress")
    assert run.parameters["progress"].kind is inspect.Parameter.KEYWORD_ONLY
    assert run.parameters["progress"].default is None
    run_hints = typing.get_type_hints(TrainingPipeline.run)
    assert run_hints["dataset"] is pd.DataFrame
    assert run_hints["return"] is TrainingResult


def test_artifact_and_inference_signatures_are_explicit() -> None:
    """Save/load/predict expose paths and dataframes, not hidden services."""
    save = inspect.signature(TrainingResult.save)
    assert tuple(save.parameters) == ("self", "path")
    assert typing.get_type_hints(TrainingResult.save)["return"] is Path

    load = inspect.signature(InferencePipeline.load)
    assert tuple(load.parameters) == ("path", "trusted")
    assert typing.get_type_hints(InferencePipeline.load)["return"] is InferencePipeline

    predict = inspect.signature(InferencePipeline.predict)
    assert tuple(predict.parameters) == ("self", "new_data", "include_base_predictions")
    assert predict.parameters["include_base_predictions"].kind is inspect.Parameter.KEYWORD_ONLY
    assert predict.parameters["include_base_predictions"].default is False
    predict_hints = typing.get_type_hints(InferencePipeline.predict)
    assert predict_hints["new_data"] is pd.DataFrame
    assert predict_hints["return"] is PredictionResult


def test_public_methods_have_resolvable_type_hints() -> None:
    """Reject unresolved forward references on the stable execution surface."""
    for method in (
        TrainingPipeline.run,
        TrainingResult.save,
        InferencePipeline.load,
        InferencePipeline.predict,
    ):
        hints = typing.get_type_hints(method)
        assert "return" in hints
        assert all(value is not typing.Any for value in hints.values())
