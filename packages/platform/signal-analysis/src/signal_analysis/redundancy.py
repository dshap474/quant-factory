"""Measure pairwise feature redundancy without selecting or dropping features.

Usage: ``feature_correlations(frame, feature_columns=["x", "y"],
sample_scope="training fold 1", method="spearman", min_pairs=3)``.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports and schema
# --------------------------------------------------------------------------- #
from collections.abc import Sequence
from itertools import combinations_with_replacement
from typing import Literal

import numpy as np
import polars as pl
from scipy.stats import pearsonr, rankdata

from .contracts import validate_feature_frame

_SCHEMA = pl.Schema(
    {
        "feature_left": pl.String,
        "feature_right": pl.String,
        "sample_scope": pl.String,
        "method": pl.String,
        "min_pairs": pl.UInt64,
        "correlation": pl.Float64,
        "status": pl.String,
        "n_total": pl.UInt64,
        "n_valid": pl.UInt64,
        "n_missing_pair": pl.UInt64,
        "n_nonfinite_pair": pl.UInt64,
    }
)


# --------------------------------------------------------------------------- #
# Public measurements
# --------------------------------------------------------------------------- #


def feature_correlations(
    frame: pl.DataFrame,
    *,
    feature_columns: Sequence[str],
    sample_scope: str,
    method: Literal["pearson", "spearman"],
    min_pairs: int,
) -> pl.DataFrame:
    """Return every unordered pair, including diagonals, for the supplied rows.

    Null pairs precede nonfinite pairs in exclusion accounting. Spearman uses
    average tied ranks within each observed pair, so the resulting pairwise
    matrix need not be positive semidefinite. No timing or sample isolation is
    certified by the caller's nonempty sample_scope declaration.
    """
    validate_feature_frame(frame, feature_columns=feature_columns)
    if not isinstance(sample_scope, str) or not sample_scope.strip() or sample_scope != sample_scope.strip():
        raise ValueError("sample_scope must be a nonempty trimmed string")
    if method not in ("pearson", "spearman"):
        raise ValueError("method must be pearson or spearman")
    if isinstance(min_pairs, bool) or not isinstance(min_pairs, int) or not 2 <= min_pairs < 2**64:
        raise ValueError("min_pairs must be an integer in [2, 2**64), excluding booleans")
    rows = []
    for left, right in combinations_with_replacement(sorted(feature_columns), 2):
        missing = frame[left].is_null() | frame[right].is_null()
        finite = (frame[left].is_finite() & frame[right].is_finite()).fill_null(False)
        pairs = (
            frame.filter(~missing & finite).select(left)
            if left == right
            else frame.filter(~missing & finite).select(left, right)
        )
        value, status = None, "insufficient_pairs"
        if pairs.height >= min_pairs:
            x, y = pairs[left].to_numpy(), pairs[right].to_numpy()
            cx, cy = bool(np.all(x == x[0])), bool(np.all(y == y[0]))
            if cx or cy:
                status = "constant_both" if cx and cy else "constant_left" if cx else "constant_right"
            else:
                if method == "spearman":
                    x, y = rankdata(x, method="average"), rankdata(y, method="average")
                normalized = []
                for values in (x, y):
                    with np.errstate(over="ignore"):
                        delta = values - values[0]
                    if not np.isfinite(delta).all():
                        delta = values / 2 - values[0] / 2
                    normalized.append(delta / np.max(np.abs(delta)))
                value = float(pearsonr(*normalized).statistic)
                if not np.isfinite(value):
                    raise ArithmeticError("nonfinite correlation for finite nonconstant values")
                status = "ok"
        rows.append(
            {
                "feature_left": left,
                "feature_right": right,
                "sample_scope": sample_scope,
                "method": method,
                "min_pairs": min_pairs,
                "correlation": value,
                "status": status,
                "n_total": frame.height,
                "n_valid": pairs.height,
                "n_missing_pair": int(missing.sum()),
                "n_nonfinite_pair": int((~missing & ~finite).sum()),
            }
        )
    return pl.DataFrame(rows, schema=_SCHEMA)


def correlation_groups(correlations: pl.DataFrame, *, threshold: float, absolute: bool) -> pl.DataFrame:
    """Label connected components of an explicit correlation-threshold graph.

    Edges use >= threshold, optionally on absolute correlation. Transitive
    members need not meet the pair threshold. Undefined pairs create no edges.
    Every input feature is retained; group labels are the smallest member name.
    """
    if not isinstance(absolute, bool):
        raise TypeError("absolute must be bool")
    if isinstance(threshold, bool) or not isinstance(threshold, (float, int)) or not np.isfinite(threshold):
        raise ValueError("threshold must be finite")
    if not (0 <= threshold <= 1 if absolute else -1 <= threshold <= 1):
        raise ValueError("threshold must be in [0,1] for absolute, otherwise [-1,1]")
    if not isinstance(correlations, pl.DataFrame) or correlations.schema != _SCHEMA:
        raise TypeError("correlations must have the feature_correlations result schema")
    if correlations.is_empty():
        raise ValueError("correlations must contain all unordered pairs, including diagonals")
    for name in ("sample_scope", "method", "min_pairs", "n_total"):
        if correlations[name].null_count() or correlations[name].n_unique() != 1:
            raise ValueError("correlations must describe exactly one sample and method")
    nonnull = [name for name in _SCHEMA if name != "correlation"]
    if correlations.select(pl.any_horizontal(pl.col(nonnull).is_null()).any()).item():
        raise ValueError("only undefined correlation values may be null")
    statuses = ["ok", "insufficient_pairs", "constant_left", "constant_right", "constant_both"]
    if correlations.filter(~pl.col("status").is_in(statuses)).height:
        raise ValueError("unknown correlation status")
    if correlations["method"][0] not in ("pearson", "spearman") or correlations["min_pairs"][0] < 2:
        raise ValueError("invalid correlation method or minimum")
    for row in correlations.iter_rows(named=True):
        if row["n_valid"] + row["n_missing_pair"] + row["n_nonfinite_pair"] != row["n_total"]:
            raise ValueError("correlation coverage counts must reconcile")
        if (row["n_valid"] < row["min_pairs"]) != (row["status"] == "insufficient_pairs"):
            raise ValueError("correlation status must agree with the minimum pair count")
    pairs = correlations.select("feature_left", "feature_right").rows()
    names = sorted(set(correlations["feature_left"]) | set(correlations["feature_right"]))
    if any(not isinstance(name, str) or not name.strip() or name != name.strip() for name in names):
        raise ValueError("invalid feature identity")
    if len(set(pairs)) != len(pairs) or set(pairs) != set(combinations_with_replacement(names, 2)):
        raise ValueError("expected every unordered feature pair exactly once")
    parents = dict(zip(names, names, strict=True))

    def root(name: str) -> str:
        while parents[name] != name:
            name = parents[name]
        return name

    for row in correlations.iter_rows(named=True):
        value = row["correlation"]
        if row["status"] == "ok":
            if value is None or not np.isfinite(value) or not -1 <= value <= 1:
                raise ValueError("ok correlations must be finite and bounded by [-1,1]")
            if (abs(value) if absolute else value) >= threshold:
                a, b = sorted((root(row["feature_left"]), root(row["feature_right"])))
                parents[b] = a
        elif value is not None:
            raise ValueError("undefined correlations require null values")
    return pl.DataFrame(
        {
            "feature": names,
            "group": [root(name) for name in names],
            "sample_scope": [correlations["sample_scope"][0]] * len(names),
            "method": [correlations["method"][0]] * len(names),
            "threshold": [float(threshold)] * len(names),
            "absolute": [absolute] * len(names),
        }
    )


__all__ = ["feature_correlations", "correlation_groups"]
