"""Build expanding, rolling, or purged walk-forward folds.

Usage::

    plan = build_walk_forward_plan(
        frame,
        SplitConfig("purged", 148, 156, embargo_periods=8),
        timestamp_col="timestamp",
        period_col="era",
        target_end_col="target_end",
    )
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports
# --------------------------------------------------------------------------- #

from typing import Any

import pandas as pd

from ..config import SplitConfig
from ._folds import FoldPlan, build_fold_plan

# --------------------------------------------------------------------------- #
# Walk-forward methodology
# --------------------------------------------------------------------------- #


def build_walk_forward_plan(
    frame: pd.DataFrame,
    config: SplitConfig,
    *,
    timestamp_col: str,
    row_id_col: str | None = None,
    period_col: str | None = None,
    target_end_col: str | None = None,
    training_cutoff: Any | None = None,
) -> FoldPlan:
    """Build deterministic expanding, rolling, or purged folds."""

    if config.kind not in {"expanding", "rolling", "purged"}:
        raise ValueError("walk-forward methodology requires expanding, rolling, or purged kind")
    return build_fold_plan(
        frame,
        config,
        timestamp_col=timestamp_col,
        row_id_col=row_id_col,
        period_col=period_col,
        target_end_col=target_end_col,
        training_cutoff=training_cutoff,
    )


__all__ = ["build_walk_forward_plan"]
