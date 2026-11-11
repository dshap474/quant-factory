"""Summarize supplied tree impurity importances with explicit zero semantics.

Usage: ``mean_decrease_impurity(trees, feature_columns=["x"],
normalization="conventional")``; trees has a unique String ``tree_id``.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports and results
# --------------------------------------------------------------------------- #
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np
import polars as pl

from signal_analysis.contracts import validate_feature_frame

from . import _moments


@dataclass(frozen=True)
class ImpurityImportanceResult:
    """Raw tree values and descriptive feature summaries; no OOS claim."""

    raw: pl.DataFrame
    summary: pl.DataFrame


# --------------------------------------------------------------------------- #
# Public operation
# --------------------------------------------------------------------------- #


def mean_decrease_impurity(
    trees: pl.DataFrame,
    *,
    feature_columns: Sequence[str],
    normalization: Literal["conventional", "afml_zero_excluded"],
) -> ImpurityImportanceResult:
    """Aggregate per-tree normalized impurity reductions (AFML §8.3.1).

    Each tree's finite nonnegative values must sum to one, or all be zero for
    a tree with no split. Conventional averaging retains zeros and normalizes
    the resulting feature means. AFML excludes zeros from each feature mean,
    then normalizes across features. Raw zeros are always retained.
    """
    validate_feature_frame(trees, feature_columns=feature_columns)
    if normalization not in {"conventional", "afml_zero_excluded"}:
        raise ValueError("unsupported normalization")
    if "tree_id" not in trees or trees.schema["tree_id"] != pl.String:
        raise ValueError("tree_id must be String")
    ids = trees["tree_id"].to_list()
    if not ids or any(not value or value != value.strip() for value in ids) or len(ids) != len(set(ids)):
        raise ValueError("tree_id must be nonempty, unique, and trimmed")
    trees = trees.sort("tree_id")
    ids = trees["tree_id"].to_list()
    values = trees.select(feature_columns).to_numpy()
    if not np.isfinite(values).all() or np.any(values < 0) or np.any(values > 1 + 1e-12):
        raise ValueError("tree importances must be finite and nonnegative")
    totals = values.sum(axis=1)
    if not np.all((totals == 0) | np.isclose(totals, 1, rtol=0, atol=1e-12)):
        raise ValueError("each tree must sum to one or be entirely zero")
    raw_rows, summary_rows = [], []
    means: list[float | None] = []
    deviations: list[float | None] = []
    counts = []
    for column, name in enumerate(feature_columns):
        vector = values[:, column]
        included = vector if normalization == "conventional" else vector[vector != 0]
        counts.append(len(included))
        mean, deviation = _moments(included, ddof=1)
        means.append(mean)
        deviations.append(deviation)
        for tree_id, value in zip(ids, vector, strict=True):
            raw_rows.append((tree_id, name, float(value), bool(bool(normalization == "conventional" or value != 0))))
    denominator = sum(value for value in means if value is not None)
    for name, mean, deviation, count in zip(feature_columns, means, deviations, counts, strict=True):
        status = "no_nonzero_trees" if mean is None else ("zero_total_importance" if denominator == 0 else "ok")
        importance = mean / denominator if mean is not None and denominator > 0 else None
        # Snippet 8.2 scales by total tree count, not count of nonzero trees.
        dispersion = deviation / np.sqrt(len(ids)) / denominator if deviation is not None and denominator > 0 else None
        summary_rows.append(
            (name, normalization, importance, mean, deviation, dispersion, denominator, len(ids), count, status)
        )
    return ImpurityImportanceResult(
        raw=pl.DataFrame(
            raw_rows,
            schema={"tree_id": pl.String, "feature": pl.String, "tree_importance": pl.Float64, "included": pl.Boolean},
            orient="row",
        ),
        summary=pl.DataFrame(
            summary_rows,
            schema={
                "feature": pl.String,
                "normalization": pl.String,
                "importance": pl.Float64,
                "raw_mean": pl.Float64,
                "tree_sample_std": pl.Float64,
                "scaled_tree_dispersion": pl.Float64,
                "normalization_denominator": pl.Float64,
                "n_trees": pl.UInt64,
                "n_included": pl.UInt64,
                "status": pl.String,
            },
            orient="row",
        ),
    )
