"""Explicit training methodologies for evaluation and final fitting.

Usage::

    from ml_engine.training.methodologies import (
        build_fold_plan,
        build_holdout_plan,
        build_walk_forward_plan,
        fit_full_data,
    )
"""

# --------------------------------------------------------------------------- #
# Public methodology imports
# --------------------------------------------------------------------------- #

from ._folds import Fold, FoldPlan, build_fold_plan
from .full_fit import FullFitResult, fit_full_data
from .holdout import build_holdout_plan
from .walk_forward import build_walk_forward_plan

# --------------------------------------------------------------------------- #
# Public methodology inventory
# --------------------------------------------------------------------------- #

__all__ = [
    "Fold",
    "FoldPlan",
    "FullFitResult",
    "build_fold_plan",
    "build_holdout_plan",
    "build_walk_forward_plan",
    "fit_full_data",
]
