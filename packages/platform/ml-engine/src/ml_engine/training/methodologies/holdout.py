"""Build one chronological train/test holdout.

Usage::

    plan = build_holdout_plan(
        frame,
        SplitConfig("chronological_holdout", 12, 4),
        timestamp_col="timestamp",
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
# Holdout methodology
# --------------------------------------------------------------------------- #


def build_holdout_plan(
    frame: pd.DataFrame,
    config: SplitConfig,
    *,
    timestamp_col: str,
    row_id_col: str | None = None,
    period_col: str | None = None,
    target_end_col: str | None = None,
    training_cutoff: Any | None = None,
) -> FoldPlan:
    """Build exactly one chronological holdout fold."""

    if config.kind != "chronological_holdout":
        raise ValueError("holdout methodology requires kind='chronological_holdout'")
    return build_fold_plan(
        frame,
        config,
        timestamp_col=timestamp_col,
        row_id_col=row_id_col,
        period_col=period_col,
        target_end_col=target_end_col,
        training_cutoff=training_cutoff,
    )


__all__ = ["build_holdout_plan"]
