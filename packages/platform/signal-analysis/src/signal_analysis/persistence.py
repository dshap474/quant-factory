"""Measure how much a cross-sectional signal's ranking persists across decision dates.

Usage: ``signal_rank_autocorrelation(panel, lags=[1, 5, 10, 20], min_pairs=25)``. For each
decision date and lag ``L``, the Spearman correlation between the signal at that date and at
the ``L``-th preceding decision date over assets eligible with finite signals on both dates;
the lag-level row reports the mean over dates. Lags count declared decision dates in the
panel, not elapsed time. Descriptive only: persistence is neither skill nor turnover.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports and result schema
# --------------------------------------------------------------------------- #
from collections.abc import Sequence

import polars as pl

from .contracts import validate_signal_panel
from .ic import _correlation
from .inference import _mean

_RESULT_SCHEMA = pl.Schema(
    {
        "lag": pl.UInt64,
        "min_pairs": pl.UInt64,
        "n_dates_supplied": pl.UInt64,
        "n_dates_lagged": pl.UInt64,
        "n_dates": pl.UInt64,
        "mean_rank_corr": pl.Float64,
        "status": pl.String,
    }
)
_DATE_SCHEMA = pl.Schema(
    {
        "lag": pl.UInt64,
        "decision_time": pl.Datetime("us", "UTC"),
        "lagged_decision_time": pl.Datetime("us", "UTC"),
        "n_pairs": pl.UInt64,
        "rank_corr": pl.Float64,
        "status": pl.String,
    }
)


# --------------------------------------------------------------------------- #
# Public analysis
# --------------------------------------------------------------------------- #


def signal_rank_autocorrelation(
    panel: pl.DataFrame,
    *,
    lags: Sequence[int],
    min_pairs: int,
    per_date: bool = False,
) -> pl.DataFrame:
    """Return one row per lag with the mean per-date Spearman rank autocorrelation.

    ``n_dates_lagged`` counts dates that have an ``L``-th predecessor; ``n_dates`` counts those
    whose correlation is ``ok`` (at least ``min_pairs`` common pairs and neither side constant).
    ``status`` is ``ok`` or ``no_valid_dates``. With ``per_date=True`` the per-date table is
    returned instead (``lag, decision_time, lagged_decision_time, n_pairs, rank_corr, status``).
    """
    if isinstance(lags, (str, bytes)) or not isinstance(lags, Sequence) or not lags:
        raise ValueError("lags must be a nonempty sequence of unique positive integers")
    if any(isinstance(lag, bool) or not isinstance(lag, int) or not 1 <= lag < 2**64 for lag in lags):
        raise ValueError("lags must be a nonempty sequence of unique positive integers")
    if len(set(lags)) != len(lags):
        raise ValueError("lags must be a nonempty sequence of unique positive integers")
    if isinstance(min_pairs, bool) or not isinstance(min_pairs, int) or not 2 <= min_pairs < 2**64:
        raise ValueError("min_pairs must be an integer in [2, 2**64), excluding booleans")
    validate_signal_panel(panel)
    usable = panel.filter(pl.col("eligible") & pl.col("signal").is_finite().fill_null(False)).select(
        "decision_time", "asset", "signal"
    )
    dates = panel["decision_time"].unique().sort().to_list()
    sections = {date: group for (date,), group in usable.group_by("decision_time")}
    date_rows: list[dict[str, object]] = []
    for lag in lags:
        for index in range(lag, len(dates)):
            current, previous = dates[index], dates[index - lag]
            if current not in sections or previous not in sections:
                pairs = pl.DataFrame(schema={"signal": pl.Float64, "target": pl.Float64})
            else:
                pairs = sections[current].join(
                    sections[previous].select("asset", pl.col("signal").alias("target")), on="asset", how="inner"
                )
            value, status = _correlation(pairs.sort("asset"), "spearman", min_pairs)
            date_rows.append(
                {
                    "lag": lag,
                    "decision_time": current,
                    "lagged_decision_time": previous,
                    "n_pairs": pairs.height,
                    "rank_corr": value,
                    "status": status,
                }
            )
    by_date = pl.DataFrame(date_rows, schema=_DATE_SCHEMA).sort("lag", "decision_time")
    if per_date:
        return by_date
    rows = []
    for lag in lags:
        section = by_date.filter(pl.col("lag") == lag)
        valid = section.filter(pl.col("status") == "ok")
        mean = _mean(valid["rank_corr"].to_numpy()) if valid.height else None
        rows.append(
            {
                "lag": lag,
                "min_pairs": min_pairs,
                "n_dates_supplied": len(dates),
                "n_dates_lagged": section.height,
                "n_dates": valid.height,
                "mean_rank_corr": mean,
                "status": "ok" if mean is not None else "no_valid_dates",
            }
        )
    return pl.DataFrame(rows, schema=_RESULT_SCHEMA).sort("lag")


__all__ = ["signal_rank_autocorrelation"]
