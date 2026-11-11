"""Compute signed cross-sectional IC with explicit pair coverage.

Usage: ``cross_sectional_ic(panel, targets, target_ids=["next"],
method="spearman", min_pairs=3)``. Results are descriptive, without p-values.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports and result schema
# --------------------------------------------------------------------------- #
from collections import Counter
from collections.abc import Sequence
from typing import Literal

import numpy as np
import polars as pl
from numpy.typing import NDArray
from scipy.stats import pearsonr, rankdata

from .contracts import validate_signal_panel, validate_targets

_EXCLUSIONS = ("ineligible", "missing_signal", "nonfinite_signal", "missing_target", "invalid_target")
_RESULT_SCHEMA = pl.Schema(
    {
        "decision_time": pl.Datetime("us", "UTC"),
        "target_id": pl.String,
        "method": pl.String,
        "min_pairs": pl.UInt64,
        "ic": pl.Float64,
        "status": pl.String,
        "n_total": pl.UInt64,
        "n_eligible": pl.UInt64,
        "n_valid": pl.UInt64,
        **{f"n_{reason}": pl.UInt64 for reason in _EXCLUSIONS},
    }
)


# --------------------------------------------------------------------------- #
# Pair accounting and numerical correlation
# --------------------------------------------------------------------------- #


def _exclusion_reason() -> pl.Expr:
    return (
        pl.when(~pl.col("eligible"))
        .then(pl.lit("ineligible"))
        .when(pl.col("signal").is_null())
        .then(pl.lit("missing_signal"))
        .when(~pl.col("signal").is_finite())
        .then(pl.lit("nonfinite_signal"))
        .when(pl.col("target_status").is_null() | pl.col("target_status").str.starts_with("missing_"))
        .then(pl.lit("missing_target"))
        .when(pl.col("target_status") != "ok")
        .then(pl.lit("invalid_target"))
        .otherwise(pl.lit("valid"))
        .alias("_reason")
    )


def _normalize(values: NDArray[np.float64]) -> NDArray[np.float64]:
    # Subtract before scaling to preserve adjacent floats in nearly constant data.
    with np.errstate(over="ignore"):
        delta = values - values[0]
    if not np.isfinite(delta).all():
        delta = values / 2 - values[0] / 2
    return delta / np.max(np.abs(delta))


def _correlation(pairs: pl.DataFrame, method: str, min_pairs: int) -> tuple[float | None, str]:
    if pairs.height < min_pairs:
        return None, "insufficient_pairs"
    left, right = pairs["signal"].to_numpy(), pairs["target"].to_numpy()
    left_constant, right_constant = bool(np.all(left == left[0])), bool(np.all(right == right[0]))
    if left_constant or right_constant:
        status = (
            "constant_both"
            if left_constant and right_constant
            else ("constant_signal" if left_constant else "constant_target")
        )
        return None, status
    if method == "spearman":
        left, right = rankdata(left, method="average"), rankdata(right, method="average")
    value = float(pearsonr(_normalize(left), _normalize(right)).statistic)
    if not np.isfinite(value):
        raise ArithmeticError("nonfinite correlation for finite nonconstant inputs")
    return value, "ok"


# --------------------------------------------------------------------------- #
# Public analysis
# --------------------------------------------------------------------------- #


def cross_sectional_ic(
    panel: pl.DataFrame,
    targets: pl.DataFrame,
    *,
    target_ids: Sequence[str],
    method: Literal["pearson", "spearman"],
    min_pairs: int,
) -> pl.DataFrame:
    """Score each supplied date/target using eligible finite pairs only.

    Both tables are validated in full. Unrequested valid target rows are ignored;
    requested orphan rows fail. Missing requested targets count as coverage losses.
    """
    if isinstance(target_ids, (str, bytes)) or not isinstance(target_ids, Sequence) or not target_ids:
        raise ValueError("target_ids must be a nonempty sequence of unique nonempty strings")
    if any(not isinstance(value, str) or not value for value in target_ids) or len(set(target_ids)) != len(target_ids):
        raise ValueError("target_ids must be a nonempty sequence of unique nonempty strings")
    if method not in ("pearson", "spearman"):
        raise ValueError("method must be pearson or spearman")
    if isinstance(min_pairs, bool) or not isinstance(min_pairs, int) or not 2 <= min_pairs < 2**64:
        raise ValueError("min_pairs must be an integer in [2, 2**64), excluding booleans")
    validate_signal_panel(panel)
    validate_targets(targets)
    keys = ["decision_time", "asset"]
    selected = targets.filter(pl.col("target_id").is_in(list(target_ids)))
    if selected.join(panel.select(keys), on=keys, how="anti").height:
        raise ValueError("requested targets contain keys absent from the signal panel")

    rows: list[dict[str, object]] = []
    signals = panel.select(*keys, "signal", "eligible").sort(*keys)
    for target_id in target_ids:
        lookup = selected.filter(pl.col("target_id") == target_id).select(*keys, "target", "target_status")
        aligned = signals.join(lookup, on=keys, how="left", validate="1:1").sort(*keys)
        aligned = aligned.with_columns(_exclusion_reason())
        for (decision_time,), section in aligned.group_by("decision_time", maintain_order=True):
            counts = Counter(section["_reason"].to_list())
            ic, status = _correlation(section.filter(pl.col("_reason") == "valid"), method, min_pairs)
            rows.append(
                {
                    "decision_time": decision_time,
                    "target_id": target_id,
                    "method": method,
                    "min_pairs": min_pairs,
                    "ic": ic,
                    "status": status,
                    "n_total": section.height,
                    "n_eligible": section.height - counts["ineligible"],
                    "n_valid": counts["valid"],
                    **{f"n_{reason}": counts[reason] for reason in _EXCLUSIONS},
                }
            )
    return pl.DataFrame(rows, schema=_RESULT_SCHEMA).sort("decision_time", "target_id")


__all__ = ["cross_sectional_ic"]
