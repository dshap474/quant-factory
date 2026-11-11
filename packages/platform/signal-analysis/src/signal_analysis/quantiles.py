"""Describe mean targets within signal-rank quantiles per decision date.

Usage: ``quantile_conditional_means(panel, targets, target_ids=["h9"], n_quantiles=5,
min_pairs=25)``. The result is a descriptive conditional mean per date and quantile; it is
not a simulated portfolio, a return stream, or a monotonicity test.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports and result schema
# --------------------------------------------------------------------------- #
from collections import Counter
from collections.abc import Sequence

import polars as pl

from .contracts import validate_signal_panel, validate_targets
from .ic import _EXCLUSIONS, _exclusion_reason
from .inference import _mean

_RESULT_SCHEMA = pl.Schema(
    {
        "decision_time": pl.Datetime("us", "UTC"),
        "target_id": pl.String,
        "quantile": pl.Int64,
        "n_quantiles": pl.UInt64,
        "min_pairs": pl.UInt64,
        "n_pairs": pl.UInt64,
        "mean_target": pl.Float64,
        "status": pl.String,
        "n_total": pl.UInt64,
        "n_valid": pl.UInt64,
        **{f"n_{reason}": pl.UInt64 for reason in _EXCLUSIONS},
    }
)


# --------------------------------------------------------------------------- #
# Public analysis
# --------------------------------------------------------------------------- #


def quantile_conditional_means(
    panel: pl.DataFrame,
    targets: pl.DataFrame,
    *,
    target_ids: Sequence[str],
    n_quantiles: int,
    min_pairs: int,
) -> pl.DataFrame:
    """Return ``n_quantiles`` rows per supplied date and target with the mean target in each.

    Pairs are the same eligible finite pairs, with the same exclusion precedence, as
    ``cross_sectional_ic``. Valid pairs are sorted by ``(signal, asset)``; the 1-based ordinal
    rank ``k`` of ``n`` pairs falls in quantile ``floor((k - 1) * q / n) + 1``. Ties broken by
    asset name are deterministic, not meaningful. A date with ``n < max(min_pairs, q)`` valid
    pairs reports every quantile as ``insufficient_pairs`` with a null mean.
    """
    if isinstance(target_ids, (str, bytes)) or not isinstance(target_ids, Sequence) or not target_ids:
        raise ValueError("target_ids must be a nonempty sequence of unique nonempty strings")
    if any(not isinstance(value, str) or not value for value in target_ids) or len(set(target_ids)) != len(target_ids):
        raise ValueError("target_ids must be a nonempty sequence of unique nonempty strings")
    for name, value in (("n_quantiles", n_quantiles), ("min_pairs", min_pairs)):
        if isinstance(value, bool) or not isinstance(value, int) or not 2 <= value < 2**64:
            raise ValueError(f"{name} must be an integer in [2, 2**64), excluding booleans")
    validate_signal_panel(panel)
    validate_targets(targets)
    keys = ["decision_time", "asset"]
    selected = targets.filter(pl.col("target_id").is_in(list(target_ids)))
    if selected.join(panel.select(keys), on=keys, how="anti").height:
        raise ValueError("requested targets contain keys absent from the signal panel")

    rows: list[dict[str, object]] = []
    signals = panel.select(*keys, "signal", "eligible").sort(*keys)
    floor = max(min_pairs, n_quantiles)
    for target_id in target_ids:
        lookup = selected.filter(pl.col("target_id") == target_id).select(*keys, "target", "target_status")
        aligned = signals.join(lookup, on=keys, how="left", validate="1:1").with_columns(_exclusion_reason())
        for (decision_time,), section in aligned.sort(*keys).group_by("decision_time", maintain_order=True):
            counts = Counter(section["_reason"].to_list())
            valid = section.filter(pl.col("_reason") == "valid").sort("signal", "asset")
            n = valid.height
            if n >= floor:
                assigned = valid.with_columns(
                    ((pl.int_range(pl.len()) * n_quantiles) // n + 1).cast(pl.Int64).alias("quantile")
                )
                members = {q: group["target"].to_numpy() for (q,), group in assigned.group_by("quantile")}
            else:
                members = {}
            common = {
                "decision_time": decision_time,
                "target_id": target_id,
                "n_quantiles": n_quantiles,
                "min_pairs": min_pairs,
                "n_total": section.height,
                "n_valid": n,
                **{f"n_{reason}": counts[reason] for reason in _EXCLUSIONS},
            }
            for quantile in range(1, n_quantiles + 1):
                values = members.get(quantile)
                if n < floor:
                    mean, status, n_pairs = None, "insufficient_pairs", 0
                else:
                    n_pairs = 0 if values is None else len(values)
                    mean = None if values is None else _mean(values)
                    status = "ok" if mean is not None else "unavailable_numerical"
                rows.append({**common, "quantile": quantile, "n_pairs": n_pairs, "mean_target": mean, "status": status})
    return pl.DataFrame(rows, schema=_RESULT_SCHEMA).sort("decision_time", "target_id", "quantile")


__all__ = ["quantile_conditional_means"]
