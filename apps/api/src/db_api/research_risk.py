"""Supplement saved research metrics without changing their published values.

USAGE: surface_risk_metrics(nav, dates, first_return=returns[0])
"""

from collections.abc import Sequence
from datetime import date, timedelta

import polars as pl
from backtest import summarize_path_risk

# --------------------------------------------------------------------------- #
# Research surface starting-mark convention
# --------------------------------------------------------------------------- #


def surface_risk_metrics(
    equity: Sequence[float], dates: Sequence[date], *, first_return: float
) -> dict[str, float | None]:
    """Daily surfaces start from $100; a zero first row is their NAV anchor.

    Older surfaces can start with an earned return instead. Restore the known
    $100 prior-day starting mark in that case so the first return is included.
    """
    if first_return != 0.0:
        equity = [100.0, *equity]
        dates = [dates[0] - timedelta(days=1), *dates]
    return summarize_path_risk(equity, dates, periods_per_year=365.0)


def observed_returns(stream: pl.DataFrame, column: str = "daily_return") -> pl.DataFrame:
    """The dated finite returns an account actually observed; nulls are coverage gaps, not zeros.

    A null return marks a date outside the account's own coverage and is dropped. An observed
    non-finite value is malformed data and raises, never silently skipped.
    """
    observed = stream.filter(pl.col(column).is_not_null())
    if not observed[column].is_finite().all():
        raise ValueError(f"observed {column} values must be finite")
    return observed


def grid_risk_metrics(streams: pl.DataFrame) -> pl.DataFrame:
    """Supplement each configuration from its observed dated return stream.

    Input columns are config_id, date and daily_return. Saved ranks, decisions
    and metrics remain untouched; these values are a read-only API projection.
    Each configuration uses only its own observed returns, compounded in date
    order; a configuration without observations has undefined (null) values.
    """
    records = []
    for (config_id,), stream in streams.partition_by("config_id", as_dict=True).items():
        stream = observed_returns(stream.sort("date"))
        risk: dict[str, float | None] = {"sortino": None, "martin": None}
        if stream.height:
            returns = stream["daily_return"]
            equity = ((returns + 1).cum_prod() * 100).to_list()
            risk = surface_risk_metrics(equity, stream["date"].to_list(), first_return=returns[0])
        records.append({"config_id": config_id, "sortino": risk["sortino"], "martin": risk["martin"],
                        "observed_days": stream.height})
    return pl.DataFrame(records, schema={"config_id": pl.String, "sortino": pl.Float64, "martin": pl.Float64,
                                         "observed_days": pl.Int64})
