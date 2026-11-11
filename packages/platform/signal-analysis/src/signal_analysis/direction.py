"""Score the direction of a signal against a target, per decision date, without ranking.

Usage: ``directional_scores(panel, targets, target_ids=["h9"], min_pairs=25)``. For each
supplied decision date and requested target, over the same eligible finite pairs and the same
exclusion precedence as ``cross_sectional_ic``:

- ``signed_mean``: mean of ``sign(signal) * target``. It is what a unit position that follows
  the signal's sign on every valid pair would have earned in target units, on average, on
  that date; a zero signal is a flat position and contributes zero.
- ``mean_target``: mean of ``target`` over the same pairs, the always-long reference, so the
  paired difference ``signed_mean - mean_target`` is computed on identical pairs.
- ``hit_rate``: share of decided pairs (``signal`` and ``target`` both nonzero) whose signs
  agree; a zero on either side is a tie and is neither hit nor miss.

Cross-sectional IC asks whether a higher signal picks a higher target *among* assets on a
date; these scores ask whether the signal's sign points the way the target moves, asset by
asset, which is a timing question. Descriptive only: no costs, sizing, netting, compounding,
annualization, interval, or verdict.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports and result schema
# --------------------------------------------------------------------------- #
from collections import Counter
from collections.abc import Sequence

import numpy as np
import polars as pl

from .contracts import validate_signal_panel, validate_targets
from .ic import _EXCLUSIONS, _exclusion_reason
from .inference import _mean

_RESULT_SCHEMA = pl.Schema(
    {
        "decision_time": pl.Datetime("us", "UTC"),
        "target_id": pl.String,
        "min_pairs": pl.UInt64,
        "signed_mean": pl.Float64,
        "mean_target": pl.Float64,
        "hit_rate": pl.Float64,
        "status": pl.String,
        "n_positive_signal": pl.UInt64,
        "n_negative_signal": pl.UInt64,
        "n_zero_signal": pl.UInt64,
        "n_hits": pl.UInt64,
        "n_misses": pl.UInt64,
        "n_ties": pl.UInt64,
        "n_total": pl.UInt64,
        "n_eligible": pl.UInt64,
        "n_valid": pl.UInt64,
        **{f"n_{reason}": pl.UInt64 for reason in _EXCLUSIONS},
    }
)


# --------------------------------------------------------------------------- #
# Per-date scoring
# --------------------------------------------------------------------------- #


def _score(valid: pl.DataFrame, min_pairs: int) -> dict[str, object]:
    signal, target = valid["signal"].to_numpy(), valid["target"].to_numpy()
    sign = np.sign(signal)
    agreement = sign * np.sign(target)
    counts = {
        "n_positive_signal": int(np.count_nonzero(sign > 0)),
        "n_negative_signal": int(np.count_nonzero(sign < 0)),
        "n_zero_signal": int(np.count_nonzero(sign == 0)),
        "n_hits": int(np.count_nonzero(agreement > 0)),
        "n_misses": int(np.count_nonzero(agreement < 0)),
        "n_ties": int(np.count_nonzero(agreement == 0)),
    }
    if valid.height < min_pairs:
        return {"signed_mean": None, "mean_target": None, "hit_rate": None, "status": "insufficient_pairs", **counts}
    # sign * target is exact (a sign change or zero), so the signed mean carries the
    # same rounding as the plain mean over the same pairs.
    signed_mean, mean_target = _mean(sign * target), _mean(target)
    decided = counts["n_hits"] + counts["n_misses"]
    hit_rate = counts["n_hits"] / decided if decided else None
    status = "ok" if signed_mean is not None and mean_target is not None else "unavailable_numerical"
    return {"signed_mean": signed_mean, "mean_target": mean_target, "hit_rate": hit_rate, "status": status, **counts}


# --------------------------------------------------------------------------- #
# Public analysis
# --------------------------------------------------------------------------- #


def directional_scores(
    panel: pl.DataFrame,
    targets: pl.DataFrame,
    *,
    target_ids: Sequence[str],
    min_pairs: int,
) -> pl.DataFrame:
    """Return one row per supplied date and requested target with the signed mean, the
    always-long mean, the hit rate, sign and agreement counts, and IC exclusion counts.

    Pairs are the eligible finite pairs of ``cross_sectional_ic`` under its exclusion
    precedence. A date with fewer than ``min_pairs`` valid pairs reports ``insufficient_pairs``
    with null scores; counts are still reported. ``hit_rate`` is null when no pair is decided.
    Assets and dates are never pooled.
    """
    if isinstance(target_ids, (str, bytes)) or not isinstance(target_ids, Sequence) or not target_ids:
        raise ValueError("target_ids must be a nonempty sequence of unique nonempty strings")
    if any(not isinstance(value, str) or not value for value in target_ids) or len(set(target_ids)) != len(target_ids):
        raise ValueError("target_ids must be a nonempty sequence of unique nonempty strings")
    if isinstance(min_pairs, bool) or not isinstance(min_pairs, int) or not 1 <= min_pairs < 2**64:
        raise ValueError("min_pairs must be an integer in [1, 2**64), excluding booleans")
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
            rows.append(
                {
                    "decision_time": decision_time,
                    "target_id": target_id,
                    "min_pairs": min_pairs,
                    **_score(section.filter(pl.col("_reason") == "valid"), min_pairs),
                    "n_total": section.height,
                    "n_eligible": section.height - counts["ineligible"],
                    "n_valid": counts["valid"],
                    **{f"n_{reason}": counts[reason] for reason in _EXCLUSIONS},
                }
            )
    return pl.DataFrame(rows, schema=_RESULT_SCHEMA).sort("decision_time", "target_id")


__all__ = ["directional_scores"]
