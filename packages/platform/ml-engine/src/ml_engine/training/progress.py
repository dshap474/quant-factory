"""Immutable progress values emitted by the supervised training pipeline.

Usage::

    updates: list[TrainingProgress] = []
    result = TrainingPipeline(config).run(frame, progress=updates.append)

The callback is optional.  When omitted, training follows the existing
in-memory execution path and performs no progress-related I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


# --------------------------------------------------------------------------- #
# Public progress value
# --------------------------------------------------------------------------- #


TrainingStage = Literal[
    "validation",
    "planning",
    "cross_validation",
    "evaluation",
    "selection",
    "ensemble",
    "final_refit",
]


@dataclass(frozen=True)
class TrainingProgress:
    """One exact training lifecycle boundary or candidate-fold update."""

    stage: TrainingStage
    task: str
    target: str
    feature_count: int
    final_refit: bool
    candidate: str | None = None
    candidate_index: int | None = None
    candidate_count: int | None = None
    fold_index: int | None = None
    fold_count: int | None = None
    completed_fits: int = 0
    total_fits: int | None = None


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


__all__ = ["TrainingProgress", "TrainingStage"]
