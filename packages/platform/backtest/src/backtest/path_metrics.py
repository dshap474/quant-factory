"""Risk reporting from full-resolution dated NAV observations.

USAGE: summarize_path_risk([100, 90, 110], dates, periods_per_year=365)
       robust_sortino_ratio(daily_returns, periods_per_year=365)   # top 1% of returns clipped
"""

from collections.abc import Sequence
from datetime import date
from math import isfinite, sqrt

import numpy as np

# --------------------------------------------------------------------------- #
# Target downside risk
# --------------------------------------------------------------------------- #


def sortino_ratio(returns: Sequence[float] | np.ndarray, *, periods_per_year: float) -> float | None:
    """Zero-target Sortino; RMS shortfall uses all N returns, not only losses.

    See CME / Red Rock, 'Sortino: A Sharper Ratio'. Empty or zero-downside
    samples are undefined (None). Returns are interval observations, no anchor.
    """
    values = np.asarray(returns, dtype=np.float64)
    if values.ndim != 1 or not np.isfinite(values).all():
        raise ValueError("returns must be a finite one-dimensional sequence")
    if not isfinite(periods_per_year) or periods_per_year <= 0:
        raise ValueError("periods_per_year must be finite and positive")
    if values.size == 0:
        return None
    downside = np.minimum(values, 0.0)
    scale = float(np.max(np.abs(downside)))
    if scale == 0:
        return None
    # Scaling avoids underflow in squared tiny shortfalls.
    rms = sqrt(float(np.mean((downside / scale) ** 2)))
    result = float(np.mean(values) / scale / rms * sqrt(periods_per_year))
    return result if isfinite(result) else None


def robust_sortino_ratio(
    returns: Sequence[float] | np.ndarray, *, periods_per_year: float, upper_quantile: float = 0.99
) -> float | None:
    """Zero-target Sortino after clipping returns above their ``upper_quantile``.

    Sortino ignores upside variance, so a few spike days can carry it; clipping the
    top tail shows how much of the ratio survives without them. Losses are untouched.
    """
    values = np.asarray(returns, dtype=np.float64)
    if not 0 < upper_quantile <= 1:
        raise ValueError("upper_quantile must be in (0, 1]")
    if values.ndim == 1 and values.size and np.isfinite(values).all():
        values = np.minimum(values, np.quantile(values, upper_quantile))
    return sortino_ratio(values, periods_per_year=periods_per_year)


# --------------------------------------------------------------------------- #
# Dated path reporting
# --------------------------------------------------------------------------- #


def summarize_path_risk(
    equity: Sequence[float], dates: Sequence[date], *, periods_per_year: float = 365.0
) -> dict[str, float | None]:
    """Sortino, robust (p99-clipped) Sortino, Martin and calendar-day underwater durations from a NAV path.

    The first NAV is the starting mark, not a return observation. Longest duration
    runs from a high-water mark to recovery (equality counts) or the final date.
    Current duration is zero at a high-water mark. No unobserved recovery is inferred.
    Martin is calendar-day CAGR (365 days, zero cash rate) divided by RMS
    fractional drawdown over all observed NAV marks, including the starting mark.
    Without drawdown or elapsed time it is undefined (None).
    """
    values = np.asarray(equity, dtype=np.float64)
    if values.ndim != 1 or len(values) != len(dates) or not len(values):
        raise ValueError("equity and dates must be nonempty aligned sequences")
    if not np.isfinite(values).all() or np.any(values < 0) or values[0] <= 0:
        raise ValueError("equity must be finite and nonnegative with a positive starting mark")
    if any(right <= left for left, right in zip(dates, dates[1:], strict=False)):
        raise ValueError("dates must be strictly increasing")
    returns = values[1:] / values[:-1] - 1 if np.all(values[:-1] > 0) else None
    drawdowns = values / np.maximum.accumulate(values) - 1
    ulcer_index = sqrt(float(np.mean(drawdowns ** 2)))
    elapsed_days = (dates[-1] - dates[0]).days
    martin = None
    if returns is not None and elapsed_days > 0 and ulcer_index > 0:
        with np.errstate(over="ignore", invalid="ignore"):
            cagr = float((values[-1] / values[0]) ** (365.0 / elapsed_days) - 1)
            ratio = cagr / ulcer_index
        if isfinite(ratio):
            martin = ratio
    peak = values[0]
    peak_date = dates[0]
    longest = current = 0
    underwater = False
    for value, day in zip(values[1:], dates[1:], strict=True):
        elapsed = (day - peak_date).days
        if value >= peak:
            if underwater:
                longest = max(longest, elapsed)
            peak, peak_date = value, day
            underwater = False
            current = 0
        else:
            underwater = True
            current = elapsed
            longest = max(longest, current)
    return {
        "sortino": sortino_ratio(returns, periods_per_year=periods_per_year) if returns is not None else None,
        "robust_sortino": (robust_sortino_ratio(returns, periods_per_year=periods_per_year)
                           if returns is not None else None),
        "martin": martin,
        "longest_drawdown_days": float(longest),
        "current_drawdown_days": float(current),
    }
