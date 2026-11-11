"""Aggregate a dated statistic into fixed-length calendar blocks and measure its decorrelation lag.

Autocorrelated daily statistics (for example a cross-sectional IC that reuses overlapping
forward windows) are not independent observations. Following Paleologo, *Elements of
Quantitative Investing* §8.3.1, replace the series with ``floor(N / s)`` non-overlapping,
contiguous block averages of length ``s`` and infer on the blocks. Blocks are anchored to the
caller's declared calendar, so a missing session lowers a block's coverage and never moves an
edge. ``s`` is an explicit parameter (default 30 sessions) that the caller may sweep; the
decorrelation lag ``first_insignificant_lag`` reports is a diagnostic for choosing it, never an
automatic setting.

USAGE:

    from signal_analysis.blocks import block_means, block_samples, first_insignificant_lag
    from signal_analysis.inference import moving_block_mean, newey_west_mean

    blocks = block_means(daily_ic, calendar=calendar, calendar_id="daily", inferential_unit="ic",
                         block_length=30, min_coverage=0.8)
    samples, block_calendar = block_samples(blocks)
    newey_west_mean(samples, calendar=block_calendar, calendar_id="blocks_30",
                    inferential_unit="block_mean_ic", max_lag=0, confidence_level=0.95)
    moving_block_mean(samples, calendar=block_calendar, calendar_id="blocks_30",
                      inferential_unit="block_mean_ic", block_length=1, n_resamples=2000,
                      seed=7, confidence_level=0.95)
    lag = first_insignificant_lag(daily_ic["value"].to_numpy(), max_lag=60)
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports and result contracts
# --------------------------------------------------------------------------- #
import math
from dataclasses import dataclass

import numpy as np
import polars as pl

from signal_analysis.contracts import _validate_table
from signal_analysis.inference import _identifier, _integer, _mean

_UTC = pl.Datetime("us", "UTC")
_BLOCK_SCHEMA = pl.Schema(
    {
        "block_index": pl.UInt64,
        "block_start": _UTC,
        "block_end": _UTC,
        "calendar_id": pl.String,
        "inferential_unit": pl.String,
        "block_length": pl.UInt64,
        "n_expected": pl.UInt64,
        "n_observed": pl.UInt64,
        "n_valid": pl.UInt64,
        "n_missing": pl.UInt64,
        "n_nonfinite": pl.UInt64,
        "mean": pl.Float64,
        "status": pl.String,
    }
)
_BLOCK_STATUSES = ("ok", "insufficient_coverage", "empty", "incomplete_trailing")


@dataclass(frozen=True)
class LagResult:
    """Sample autocorrelations of a series and the first lag inside the white-noise band."""

    lag: int | None
    acf: tuple[float, ...]
    band: float
    n_obs: int
    max_lag: int
    status: str


# --------------------------------------------------------------------------- #
# Calendar-anchored block means
# --------------------------------------------------------------------------- #


def block_means(
    samples: pl.DataFrame,
    *,
    calendar: pl.DataFrame,
    calendar_id: str,
    inferential_unit: str,
    block_length: int = 30,
    min_coverage: float = 1.0,
) -> pl.DataFrame:
    """Return one row per calendar block of ``block_length`` consecutive sessions.

    ``samples`` has ``decision_time`` and Float64 ``value``; ``calendar`` declares every expected
    ``decision_time``. Blocks start at the first calendar row. ``block_start``/``block_end`` are
    the first and last calendar sessions in the block (closed). A block is ``ok`` when it is
    complete in the calendar and ``n_valid / n_expected >= min_coverage``; a trailing block shorter
    than ``block_length`` is ``incomplete_trailing``; a block with no valid value is ``empty``.
    ``mean`` is the compensated mean of the valid values and is null unless the block is ``ok``.
    Missing sessions and nonfinite values are counted; they never shift an edge.
    """
    _identifier(calendar_id, "calendar_id")
    _identifier(inferential_unit, "inferential_unit")
    _integer(block_length, "block_length", 1)
    if isinstance(min_coverage, bool) or not isinstance(min_coverage, (int, float)):
        raise TypeError("min_coverage must be a finite number")
    if not math.isfinite(min_coverage) or not 0 < min_coverage <= 1:
        raise ValueError("min_coverage must satisfy 0 < min_coverage <= 1")
    _validate_table(
        samples,
        pl.Schema({"decision_time": _UTC, "value": pl.Float64}),
        required=["decision_time"],
        key=["decision_time"],
    )
    _validate_table(calendar, pl.Schema({"decision_time": _UTC}), required=["decision_time"], key=["decision_time"])
    if samples.join(calendar.select("decision_time"), on="decision_time", how="anti").height:
        raise ValueError("samples contain decision times outside the declared calendar")
    grid = calendar.select("decision_time").sort("decision_time")
    aligned = grid.join(samples.select("decision_time", "value"), on="decision_time", how="left").with_columns(
        (pl.int_range(pl.len()) // block_length).cast(pl.UInt64).alias("block_index")
    )
    rows = []
    for block_index, block in aligned.group_by("block_index", maintain_order=True):
        values = block["value"]
        missing = values.is_null()
        nonfinite = ~missing & ~values.is_finite().fill_null(False)
        valid = values.filter(~missing & ~nonfinite).to_numpy()
        n_expected = block.height
        row = dict(
            block_index=block_index[0],
            block_start=block["decision_time"][0],
            block_end=block["decision_time"][-1],
            calendar_id=calendar_id,
            inferential_unit=inferential_unit,
            block_length=block_length,
            n_expected=n_expected,
            n_observed=n_expected - int(missing.sum()),
            n_valid=len(valid),
            n_missing=int(missing.sum()),
            n_nonfinite=int(nonfinite.sum()),
            mean=None,
            status="ok",
        )
        if n_expected < block_length:
            row["status"] = "incomplete_trailing"
        elif not len(valid):
            row["status"] = "empty"
        elif len(valid) < min_coverage * n_expected:
            row["status"] = "insufficient_coverage"
        else:
            row["mean"] = _mean(valid)
            if row["mean"] is None:
                row["status"] = "empty"
        rows.append(row)
    return pl.DataFrame(rows, schema=_BLOCK_SCHEMA).sort("block_index")


def block_samples(blocks: pl.DataFrame, *, baseline: pl.DataFrame | None = None) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Return ``(samples, calendar)`` for ``signal_analysis.inference`` from ``ok`` blocks.

    The returned calendar is the sequence of valid blocks keyed on ``block_start``; passing it
    to the inference operations asserts that lag dependence is defined in block units and that
    the excluded blocks (reported in ``blocks``) are disclosed by the caller. With ``baseline``
    the samples carry ``candidate``/``baseline`` means for blocks that are ``ok`` in both frames;
    the two frames must share ``block_index``, ``block_start``, and ``block_end`` exactly.
    """
    _validate_table(blocks, _BLOCK_SCHEMA, required=["block_index", "block_start", "status"], key=["block_index"])
    if baseline is None:
        samples = blocks.filter(pl.col("status") == "ok").select(
            pl.col("block_start").alias("decision_time"), pl.col("mean").alias("value")
        )
    else:
        _validate_table(baseline, _BLOCK_SCHEMA, required=["block_index", "block_start", "status"], key=["block_index"])
        edges = ["block_index", "block_start", "block_end"]
        if not blocks.select(edges).equals(baseline.select(edges)):
            raise ValueError("candidate and baseline blocks must share identical block edges")
        samples = (
            blocks.select(*edges, pl.col("status").alias("_cs"), pl.col("mean").alias("candidate"))
            .join(baseline.select(*edges, pl.col("status").alias("_bs"), pl.col("mean").alias("baseline")), on=edges)
            .filter((pl.col("_cs") == "ok") & (pl.col("_bs") == "ok"))
            .select(pl.col("block_start").alias("decision_time"), "candidate", "baseline")
        )
    samples = samples.sort("decision_time")
    return samples, samples.select("decision_time")


# --------------------------------------------------------------------------- #
# Decorrelation lag diagnostic
# --------------------------------------------------------------------------- #


def first_insignificant_lag(values, *, max_lag: int) -> LagResult:
    """Return the smallest lag whose sample autocorrelation lies inside ``±1.96/sqrt(n)``.

    ``acf[k]`` is the biased sample autocorrelation at lag ``k+1``:
    ``sum((x_t - m)(x_{t+k} - m)) / sum((x_t - m)^2)``. The band is the large-sample white-noise
    band, a diagnostic and not a test. Requires ``n >= max_lag + 2`` finite values; a constant
    series is degenerate; no lag inside the band within ``max_lag`` is reported as unavailable
    with ``lag=None`` and the full ``acf`` retained.
    """
    _integer(max_lag, "max_lag", 1)
    array = np.asarray(values, dtype=np.float64).reshape(-1)
    n = int(array.size)
    if n and not np.isfinite(array).all():
        return LagResult(None, (), math.nan, n, max_lag, "unavailable_nonfinite")
    if n < max_lag + 2:
        return LagResult(None, (), math.nan, n, max_lag, "unavailable_insufficient_observations")
    band = 1.96 / math.sqrt(n)
    scale = float(np.max(np.abs(array))) or 1.0
    centered = array / scale - float(np.mean(array / scale))
    denominator = math.fsum(centered * centered)
    if denominator == 0:
        return LagResult(None, (), band, n, max_lag, "unavailable_degenerate")
    acf = tuple(math.fsum(centered[lag:] * centered[:-lag]) / denominator for lag in range(1, max_lag + 1))
    for lag, value in enumerate(acf, start=1):
        if abs(value) < band:
            return LagResult(lag, acf, band, n, max_lag, "ok")
    return LagResult(None, acf, band, n, max_lag, "unavailable_no_insignificant_lag")


__all__ = ["LagResult", "block_means", "block_samples", "first_insignificant_lag"]
