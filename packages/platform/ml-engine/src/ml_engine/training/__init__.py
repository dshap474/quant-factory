"""Stable public API for the standalone training engine.

Usage::

    from ml_engine.training import TrainingPipeline, TrainingResult, TrainingRun

Only the classes listed in ``__all__`` are supported package-level exports.
Implementation details remain available from their defining modules when
needed internally.
"""

# --------------------------------------------------------------------------- #
# Public API imports
# --------------------------------------------------------------------------- #

from .config import (
    CandidateConfig,
    EnsembleConfig,
    MetricConfig,
    PreprocessingConfig,
    SelectionConfig,
    SplitConfig,
    TrainingConfig,
)
from .pipeline import TrainingPipeline
from .progress import TrainingProgress
from .result import TrainingResult
from .run import TrainingRun, current_training_run

# --------------------------------------------------------------------------- #
# Public API inventory
# --------------------------------------------------------------------------- #

__all__ = [
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
]
