"""Summarize supplied dated metric observations across explicit caller groups.

Usage: ``summarize_metric_stability(observations, group_by=["asset", "era"],
weighting="equal", sample_scope="frozen experiment")``; ``assign_eras(frame,
time_col="observation_time", eras=[("early", start, mid), ("late", mid, end)])`` labels
rows by predeclared half-open eras. Results are descriptive means and dispersions,
not significance tests or stacked estimator refits.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports and input contracts
# --------------------------------------------------------------------------- #
from collections.abc import Sequence
from datetime import datetime, timedelta
from fractions import Fraction
from math import isqrt, ldexp
from typing import Literal

import numpy as np
import polars as pl

_UTC = pl.Datetime("us", "UTC")
_IDENTITY = ["observation_time", "asset", "feature", "metric"]
_RESULT_SCHEMA = {
    "sample_scope": pl.String,
    "weighting": pl.String,
    "mean": pl.Float64,
    "std_population": pl.Float64,
    "minimum": pl.Float64,
    "maximum": pl.Float64,
    "status": pl.String,
    "n_total": pl.UInt64,
    "n_valid": pl.UInt64,
    "n_missing": pl.UInt64,
    "n_nonfinite": pl.UInt64,
    "n_zero_weight": pl.UInt64,
    "weight_sum": pl.Float64,
    "n_dates": pl.UInt64,
    "n_dates_supplied": pl.UInt64,
    "n_assets": pl.UInt64,
    "n_assets_supplied": pl.UInt64,
    "first_observation_time": _UTC,
    "last_observation_time": _UTC,
    "first_valid_time": _UTC,
    "last_valid_time": _UTC,
}


def _validate_observations(frame: pl.DataFrame, group_by: Sequence[str], weighting: str) -> list[str]:
    if not isinstance(frame, pl.DataFrame):
        raise TypeError("observations must be a Polars DataFrame")
    if isinstance(group_by, (str, bytes)) or not isinstance(group_by, Sequence):
        raise TypeError("group_by must be a sequence of column names")
    if any(not isinstance(name, str) or not name.strip() or name != name.strip() for name in group_by):
        raise ValueError("group_by names must be nonempty trimmed strings")
    if len(set(group_by)) != len(group_by):
        raise ValueError("group_by names must be unique")
    forbidden = set(_RESULT_SCHEMA) | {"feature", "metric", "value", "weight", "observation_time"}
    if set(group_by) & forbidden:
        raise ValueError("group_by must contain asset and/or caller-supplied string group columns")
    if weighting not in ("equal", "supplied"):
        raise ValueError("weighting must be equal or supplied")
    string_columns = list(dict.fromkeys(["asset", "feature", "metric", *group_by]))
    schema = {"observation_time": _UTC, "value": pl.Float64, **dict.fromkeys(string_columns, pl.String)}
    if weighting == "supplied":
        schema["weight"] = pl.Float64
    for name, dtype in schema.items():
        if frame.schema.get(name) != dtype:
            raise TypeError(f"column {name!r} must have dtype {dtype}")
    for name in ["observation_time", *string_columns]:
        if frame[name].null_count():
            raise ValueError(f"column {name!r} must not contain nulls")
    for name in string_columns:
        if frame.filter((pl.col(name) == "") | (pl.col(name) != pl.col(name).str.strip_chars())).height:
            raise ValueError(f"column {name!r} must contain nonempty trimmed strings")
    if frame.select(_IDENTITY).is_duplicated().any():
        raise ValueError("duplicate observation_time/asset/feature/metric identity")
    if (
        weighting == "supplied"
        and frame.filter(~pl.col("weight").is_finite().fill_null(False) | (pl.col("weight") < 0)).height
    ):
        raise ValueError("supplied weights must be finite and nonnegative on every row")
    return ["feature", "metric", *group_by]


# --------------------------------------------------------------------------- #
# Predeclared era labels
# --------------------------------------------------------------------------- #


def assign_eras(
    frame: pl.DataFrame,
    *,
    time_col: str,
    eras: Sequence[tuple[str, datetime, datetime]],
    label_col: str = "era",
) -> pl.DataFrame:
    """Add a String ``label_col`` naming the half-open era ``[start, end)`` holding each row.

    Eras are ``(label, start, end)`` with UTC-aware endpoints, unique labels, ``start < end``,
    and no overlap; unordered or overlapping eras raise. A boundary instant belongs to the era
    that starts there. Rows outside every era get a null label; nothing is dropped or inferred.
    """
    if not isinstance(frame, pl.DataFrame):
        raise TypeError("frame must be a Polars DataFrame")
    if time_col not in frame.columns or frame.schema[time_col] != _UTC:
        raise TypeError(f"column {time_col!r} must have dtype {_UTC}")
    if label_col in frame.columns:
        raise ValueError(f"frame already has a {label_col!r} column")
    if isinstance(eras, (str, bytes)) or not isinstance(eras, Sequence) or not eras:
        raise ValueError("eras must be a nonempty sequence of (label, start, end)")
    seen: set[str] = set()
    previous_end: datetime | None = None
    for era in eras:
        if not isinstance(era, tuple) or len(era) != 3:
            raise TypeError("each era must be a (label, start, end) tuple")
        label, start, end = era
        if not isinstance(label, str) or not label or label.strip() != label:
            raise ValueError("era labels must be nonempty strings without surrounding whitespace")
        if label in seen:
            raise ValueError(f"duplicate era label {label!r}")
        seen.add(label)
        for instant in (start, end):
            if not isinstance(instant, datetime) or instant.tzinfo is None or instant.utcoffset() != timedelta(0):
                raise TypeError("era endpoints must be timezone-aware datetimes with UTC offset zero")
        if not start < end:
            raise ValueError(f"era {label!r} must satisfy start < end")
        if previous_end is not None and start < previous_end:
            raise ValueError(f"era {label!r} overlaps or precedes the previous era")
        previous_end = end
    label = pl.lit(None, dtype=pl.String)
    for name, start, end in reversed(eras):
        label = pl.when((pl.col(time_col) >= start) & (pl.col(time_col) < end)).then(pl.lit(name)).otherwise(label)
    return frame.with_columns(label.alias(label_col))


# --------------------------------------------------------------------------- #
# Public descriptive summary
# --------------------------------------------------------------------------- #


def _sqrt_fraction(value: Fraction) -> float:
    """Round a nonnegative rational square root to Float64, including subnormals."""
    if not value:
        return 0.0
    numerator, denominator = value.numerator, value.denominator
    exponent = (numerator.bit_length() - denominator.bit_length()) // 2
    below = (
        (numerator < denominator << (2 * exponent)) if exponent >= 0 else (numerator << (-2 * exponent) < denominator)
    )
    if below:
        exponent -= 1
    # Normal values have 53 significand bits; subnormals use a fixed 2**-1074 grid.
    unit = max(exponent - 52, -1074)
    if unit < 0:
        numerator <<= -2 * unit
    else:
        denominator <<= 2 * unit
    significand = isqrt(numerator // denominator)
    # Compare to the exact squared midpoint; choose the even significand on ties.
    midpoint = denominator * (2 * significand + 1) ** 2
    if 4 * numerator > midpoint or (4 * numerator == midpoint and significand % 2):
        significand += 1
    return ldexp(float(significand), unit)


def _weighted_moments(values: np.ndarray, weights: np.ndarray) -> tuple[float, float, float]:
    """Reduce exact binary weighted raw moments before final Float64 rounding."""
    x = [Fraction(float(value)) for value in values]
    w = [Fraction(float(weight)) for weight in weights]
    total = sum(w)
    mean = sum(a * b for a, b in zip(x, w, strict=True)) / total
    variance = sum(a * a * b for a, b in zip(x, w, strict=True)) / total - mean * mean
    try:
        return float(mean), _sqrt_fraction(variance), float(total)
    except OverflowError as exc:
        raise ArithmeticError("usable weight sum or summary moment exceeds finite Float64 domain") from exc


def summarize_metric_stability(
    observations: pl.DataFrame,
    *,
    group_by: Sequence[str],
    weighting: Literal["equal", "supplied"],
    sample_scope: str,
) -> pl.DataFrame:
    """Summarize each feature/metric within explicit asset/era/regime groups.

    [] pools supplied observation rows; ["asset"] retains asset estimands.
    An equal row mean is not an equal asset mean when asset coverage differs.
    Supplied weights let callers choose that estimand explicitly. Dispersion is
    population weighted standard deviation (ddof=0), never a standard error.
    No calendar, universe, missing observation, era or regime is inferred.
    """
    keys = _validate_observations(observations, group_by, weighting)
    if not isinstance(sample_scope, str) or not sample_scope.strip() or sample_scope != sample_scope.strip():
        raise ValueError("sample_scope must be a nonempty trimmed string")
    schema = {**dict.fromkeys(keys, pl.String), **_RESULT_SCHEMA}
    rows = []
    for labels, group in observations.sort(_IDENTITY).group_by(keys, maintain_order=True):
        weights = group["weight"] if weighting == "supplied" else pl.Series("weight", [1.0] * group.height)
        missing = group["value"].is_null()
        finite = group["value"].is_finite().fill_null(False)
        zero = ~missing & finite & (weights == 0)
        usable = ~missing & finite & (weights > 0)
        valid = group.filter(usable)
        values = valid["value"].to_numpy()
        mean = std = minimum = maximum = None
        weight_sum = 0.0
        if valid.height:
            w = weights.filter(usable).to_numpy()
            mean, std, weight_sum = _weighted_moments(values, w)
            minimum, maximum = float(np.min(values)), float(np.max(values))
        rows.append(
            {
                **dict(zip(keys, labels, strict=True)),
                "sample_scope": sample_scope,
                "weighting": weighting,
                "mean": mean,
                "std_population": std,
                "minimum": minimum,
                "maximum": maximum,
                "status": "ok" if valid.height else "no_valid_observations",
                "n_total": group.height,
                "n_valid": valid.height,
                "n_missing": int(missing.sum()),
                "n_nonfinite": int((~missing & ~finite).sum()),
                "n_zero_weight": int(zero.sum()),
                "weight_sum": weight_sum,
                "n_dates": valid["observation_time"].n_unique(),
                "n_dates_supplied": group["observation_time"].n_unique(),
                "n_assets": valid["asset"].n_unique(),
                "n_assets_supplied": group["asset"].n_unique(),
                "first_observation_time": group["observation_time"].min(),
                "last_observation_time": group["observation_time"].max(),
                "first_valid_time": valid["observation_time"].min(),
                "last_valid_time": valid["observation_time"].max(),
            }
        )
    return pl.DataFrame(rows, schema=schema).sort(keys)


__all__ = ["assign_eras", "summarize_metric_stability"]
