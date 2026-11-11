"""Estimate dated means and paired differences on an explicit complete session grid.

Usage: ``newey_west_mean(samples, calendar=calendar, calendar_id="daily",
inferential_unit="session_ic", max_lag=5, confidence_level=0.95)``.
See docs/INFERENCE_AND_EVIDENCE.md for assumptions and unavailable results.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports and result contract
# --------------------------------------------------------------------------- #
import math
from fractions import Fraction

import numpy as np
import polars as pl
from scipy.special import ndtri

from signal_analysis.contracts import _validate_table

_UTC = pl.Datetime("us", "UTC")
_SCHEMA = pl.Schema(
    {
        "method": pl.String,
        "estimand": pl.String,
        "calendar_id": pl.String,
        "inferential_unit": pl.String,
        "start_time": _UTC,
        "end_time": _UTC,
        "n_expected": pl.UInt64,
        "n_observed": pl.UInt64,
        "n_valid": pl.UInt64,
        "n_missing": pl.UInt64,
        "n_nonfinite": pl.UInt64,
        "estimate": pl.Float64,
        "standard_error": pl.Float64,
        "standard_error_kind": pl.String,
        "ci_lower": pl.Float64,
        "ci_upper": pl.Float64,
        "confidence_level": pl.Float64,
        "max_lag": pl.UInt64,
        "block_length": pl.UInt64,
        "n_resamples": pl.UInt64,
        "seed": pl.UInt64,
        "quantile_method": pl.String,
        "expected_tail_draws": pl.Float64,
        "status": pl.String,
    }
)


# --------------------------------------------------------------------------- #
# Shared preparation and stable arithmetic
# --------------------------------------------------------------------------- #


def _identifier(value: str, name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if not value or value.strip() != value:
        raise ValueError(f"{name} must be nonempty without surrounding whitespace")


def _integer(value: int, name: str, minimum: int) -> None:
    if type(value) is not int:
        raise TypeError(f"{name} must be a Python integer, excluding booleans")
    if not minimum <= value < 2**64:
        raise ValueError(f"{name} must satisfy {minimum} <= value < 2**64")


def _mean(values: np.ndarray) -> float | None:
    if not values.size or not np.isfinite(values).all():
        return None
    try:
        # Sum before division to retain tiny cancellation residuals that would
        # disappear when normalized by the largest absolute observation.
        value = math.fsum(values) / len(values)
    except OverflowError:
        # Dividing each input first can still overflow its sum (max-float
        # constants) or erase cancellation residuals. Reduce that fallback exactly.
        exact = sum(Fraction(float(value)) for value in values) / len(values)
        value = float(exact)
        if exact and value == 0:
            return None
    return value if math.isfinite(value) else None


def _center(values: np.ndarray) -> tuple[np.ndarray, float]:
    # Subtract a nearby reference before scaling when representable. This avoids
    # throwing away small, meaningful differences around a large common level.
    with np.errstate(over="ignore", invalid="ignore"):
        shifted = values - values[0]
    if not np.isfinite(shifted).all():
        shifted = values
    scale = float(np.max(np.abs(shifted)))
    scaled = shifted / scale if scale else np.zeros_like(values)
    return scaled - math.fsum(scaled) / len(scaled), scale


def _prepare(
    samples: pl.DataFrame,
    calendar: pl.DataFrame,
    calendar_id: str,
    inferential_unit: str,
    confidence_level: float,
    *,
    paired: bool,
    method: str,
) -> tuple[dict, np.ndarray]:
    _identifier(calendar_id, "calendar_id")
    _identifier(inferential_unit, "inferential_unit")
    if isinstance(confidence_level, bool) or not isinstance(confidence_level, (int, float)):
        raise TypeError("confidence_level must be a finite number")
    if not math.isfinite(confidence_level) or not 0 < confidence_level < 1:
        raise ValueError("confidence_level must be strictly between zero and one")
    fields = ["candidate", "baseline"] if paired else ["value"]
    _validate_table(
        samples,
        pl.Schema({"decision_time": _UTC, **dict.fromkeys(fields, pl.Float64)}),
        required=["decision_time"],
        key=["decision_time"],
    )
    _validate_table(calendar, pl.Schema({"decision_time": _UTC}), required=["decision_time"], key=["decision_time"])
    if samples.join(calendar.select("decision_time"), on="decision_time", how="anti").height:
        raise ValueError("samples contain decision times outside the declared calendar")
    grid = calendar.select("decision_time").sort("decision_time")
    aligned = grid.join(samples.select("decision_time", *fields), on="decision_time", how="left")
    missing = pl.any_horizontal(pl.col(fields).is_null())
    nonfinite = ~missing & ~pl.all_horizontal(pl.col(fields).is_finite()).fill_null(False)
    valid = aligned.filter(~missing & ~nonfinite)
    with np.errstate(over="ignore", invalid="ignore"):
        values = valid["candidate"].to_numpy() - valid["baseline"].to_numpy() if paired else valid["value"].to_numpy()
    row = dict.fromkeys(_SCHEMA)
    row.update(
        method=method,
        estimand="candidate_minus_baseline" if paired else "mean",
        calendar_id=calendar_id,
        inferential_unit=inferential_unit,
        start_time=grid["decision_time"][0] if grid.height else None,
        end_time=grid["decision_time"][-1] if grid.height else None,
        n_expected=grid.height,
        n_observed=samples.height,
        n_valid=valid.height,
        n_missing=aligned.select(missing.sum()).item(),
        n_nonfinite=aligned.select(nonfinite.sum()).item(),
        estimate=_mean(values),
        confidence_level=float(confidence_level),
        status="ok",
    )
    if row["n_missing"] or row["n_nonfinite"]:
        row["status"] = "unavailable_gap_or_missing"
    elif len(values) < 2:
        row["status"] = "unavailable_insufficient_observations"
    elif row["estimate"] is None:
        row["status"] = "unavailable_numerical"
    return row, values


def _frame(row: dict) -> pl.DataFrame:
    return pl.DataFrame([row], schema=_SCHEMA)


def _interval(row: dict, se: float, lower: float, upper: float) -> None:
    if not all(math.isfinite(value) for value in (se, lower, upper)) or se < 0:
        row["status"] = "unavailable_numerical"
    elif se == 0:
        row["status"] = "unavailable_degenerate"
    elif lower >= upper:
        row["status"] = "unavailable_numerical"
    else:
        row.update(standard_error=se, ci_lower=lower, ci_upper=upper)


# --------------------------------------------------------------------------- #
# Newey-West Bartlett HAC
# --------------------------------------------------------------------------- #


def _hac(samples, calendar, calendar_id, inferential_unit, max_lag, confidence_level, *, paired):
    _integer(max_lag, "max_lag", 0)
    row, values = _prepare(
        samples, calendar, calendar_id, inferential_unit, confidence_level, paired=paired, method="newey_west_bartlett"
    )
    row.update(max_lag=max_lag, standard_error_kind="hac_no_finite_sample_correction")
    if row["status"] != "ok":
        return _frame(row)
    n = len(values)
    if max_lag >= n:
        row["status"] = "unavailable_insufficient_observations"
        return _frame(row)
    centered, scale = _center(values)
    quadratic = float(centered @ centered)
    for lag in range(1, max_lag + 1):
        quadratic += 2 * (1 - lag / (max_lag + 1)) * float(centered[lag:] @ centered[:-lag])
    if quadratic < 0:
        # Do not silently clip an invalid variance into a zero-width interval.
        row["status"] = "unavailable_numerical"
        return _frame(row)
    se = (math.sqrt(quadratic) / n) * scale
    z = -float(ndtri((1 - confidence_level) / 2))
    radius = z * se
    _interval(row, se, row["estimate"] - radius, row["estimate"] + radius)
    return _frame(row)


def newey_west_mean(
    samples: pl.DataFrame,
    *,
    calendar: pl.DataFrame,
    calendar_id: str,
    inferential_unit: str,
    max_lag: int,
    confidence_level: float,
) -> pl.DataFrame:
    """Estimate a dated mean with a Bartlett HAC asymptotic normal interval."""
    return _hac(samples, calendar, calendar_id, inferential_unit, max_lag, confidence_level, paired=False)


def newey_west_paired_difference(
    samples: pl.DataFrame,
    *,
    calendar: pl.DataFrame,
    calendar_id: str,
    inferential_unit: str,
    max_lag: int,
    confidence_level: float,
) -> pl.DataFrame:
    """Estimate candidate minus baseline; retain their within-date dependence."""
    return _hac(samples, calendar, calendar_id, inferential_unit, max_lag, confidence_level, paired=True)


# --------------------------------------------------------------------------- #
# Overlapping, nonwrapping moving-block bootstrap
# --------------------------------------------------------------------------- #


def _integer_blocks(values: np.ndarray, length: int) -> tuple[list[int], int, int]:
    """Return exact rolling block sums, sample sum, and shared binary denominator."""
    # Every finite Float64 is an integer divided by a power of two. A common
    # denominator lets rolling sums retain cancellation residuals even when a
    # floating sum, division, or subtraction would overflow or erase them.
    ratios = [float(value).as_integer_ratio() for value in values]
    denominator = max(bottom for _, bottom in ratios)
    integers = [top * (denominator // bottom) for top, bottom in ratios]
    block = sum(integers[:length])
    blocks = [block]
    for start in range(len(integers) - length):
        block += integers[start + length] - integers[start]
        blocks.append(block)
    return blocks, sum(integers), denominator


def _bootstrap(
    samples, calendar, calendar_id, inferential_unit, block_length, n_resamples, seed, confidence_level, *, paired
):
    _integer(block_length, "block_length", 1)
    _integer(n_resamples, "n_resamples", 2)
    _integer(seed, "seed", 0)
    row, values = _prepare(
        samples, calendar, calendar_id, inferential_unit, confidence_level, paired=paired, method="moving_block_basic"
    )
    tail = (1 - confidence_level) / 2
    row.update(
        block_length=block_length,
        n_resamples=n_resamples,
        seed=seed,
        quantile_method="inverted_cdf",
        expected_tail_draws=n_resamples * tail,
        standard_error_kind="exact_conditional_block_mean_variance",
    )
    if row["status"] != "ok":
        return _frame(row)
    n = len(values)
    if block_length >= n or n % block_length:
        raise ValueError("moving blocks require block_length < n and n divisible by block_length; no trim or padding")
    block_sums, sample_sum, denominator = _integer_blocks(values, block_length)
    blocks_per_draw = n // block_length
    m = len(block_sums)
    total = sum(block_sums)
    # These integers represent m * (block sum - conditional mean block sum).
    # Center before conversion to Float64; normalize the norm before squaring.
    deviations = [m * block - total for block in block_sums]
    peak = max(map(abs, deviations))
    row["estimate"] = float(Fraction(sample_sum, n * denominator))
    if peak == 0:
        row["status"] = "unavailable_degenerate"
        return _frame(row)
    norm = math.sqrt(math.fsum((delta / peak) ** 2 for delta in deviations) / (m * blocks_per_draw))
    try:
        se = float(Fraction(peak, m * block_length * denominator) * Fraction(norm))
    except OverflowError:
        row["status"] = "unavailable_numerical"
        return _frame(row)
    if se == 0:
        row["status"] = "unavailable_numerical"
        return _frame(row)
    row["standard_error"] = se
    if n_resamples * tail < 1:
        row["status"] = "unavailable_insufficient_resamples"
        return _frame(row)
    rng = np.random.Generator(np.random.PCG64(seed))
    # Keep exact draw totals through the inverted-CDF order statistic. Both
    # members of a pair use the same indices; no resampled n-row array is built.
    draws = []
    for _ in range(n_resamples):
        starts = rng.integers(0, m, size=blocks_per_draw)
        draws.append(sum(block_sums[start] for start in starts))
    draws.sort()
    low, high = (draws[math.ceil(n_resamples * q) - 1] for q in (tail, 1 - tail))
    # Basic inversion is 2*T - quantile(T*), with a single final rounding.
    if low == high:
        row["status"] = "unavailable_degenerate_resamples"
        return _frame(row)
    try:
        lower = float(Fraction(2 * sample_sum - high, n * denominator))
        upper = float(Fraction(2 * sample_sum - low, n * denominator))
    except OverflowError:
        row["status"] = "unavailable_numerical"
        return _frame(row)
    if lower >= upper:
        row["status"] = "unavailable_numerical"
    else:
        row.update(ci_lower=lower, ci_upper=upper)
    return _frame(row)


def moving_block_mean(
    samples: pl.DataFrame,
    *,
    calendar: pl.DataFrame,
    calendar_id: str,
    inferential_unit: str,
    block_length: int,
    n_resamples: int,
    seed: int,
    confidence_level: float,
) -> pl.DataFrame:
    """Return exact conditional SE and a seeded Monte Carlo basic mean interval."""
    return _bootstrap(
        samples,
        calendar,
        calendar_id,
        inferential_unit,
        block_length,
        n_resamples,
        seed,
        confidence_level,
        paired=False,
    )


def moving_block_paired_difference(
    samples: pl.DataFrame,
    *,
    calendar: pl.DataFrame,
    calendar_id: str,
    inferential_unit: str,
    block_length: int,
    n_resamples: int,
    seed: int,
    confidence_level: float,
) -> pl.DataFrame:
    """Apply the same moving blocks to paired candidate/baseline observations."""
    return _bootstrap(
        samples, calendar, calendar_id, inferential_unit, block_length, n_resamples, seed, confidence_level, paired=True
    )


__all__ = [
    "newey_west_mean",
    "newey_west_paired_difference",
    "moving_block_mean",
    "moving_block_paired_difference",
]
