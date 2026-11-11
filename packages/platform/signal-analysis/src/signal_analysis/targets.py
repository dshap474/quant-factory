"""Construct forward returns at exact caller-supplied asset/time endpoints.

Usage: ``targets = build_forward_returns(windows, prices, return_type="log")``;
``windows = horizon_windows(decisions, spans={"h9": (timedelta(days=1), timedelta(days=10))})``.
No calendar resolution, price substitution, or data access occurs here.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports
# --------------------------------------------------------------------------- #
from collections.abc import Mapping
from datetime import timedelta
from typing import Literal

import polars as pl

from .contracts import _validate_table, validate_prices, validate_target_windows

_UTC = pl.Datetime("us", "UTC")

# --------------------------------------------------------------------------- #
# Fixed-offset horizon windows
# --------------------------------------------------------------------------- #


def horizon_windows(
    decisions: pl.DataFrame,
    *,
    spans: Mapping[str, tuple[timedelta, timedelta]],
) -> pl.DataFrame:
    """Build one window per decision and span as fixed offsets from ``decision_time``.

    ``spans`` maps ``target_id`` to ``(start_offset, end_offset)``; both are strictly positive
    and ``start_offset < end_offset``, so every window satisfies the target-window contract.
    Offsets are elapsed time, not sessions: the caller resolves calendars before calling.
    """
    if not isinstance(spans, Mapping) or not spans:
        raise ValueError("spans must be a nonempty mapping of target_id to (start_offset, end_offset)")
    _validate_table(
        decisions,
        pl.Schema({"decision_time": _UTC, "asset": pl.String}),
        required=["decision_time", "asset"],
        key=["decision_time", "asset"],
    )
    frames = []
    for target_id, span in spans.items():
        if not isinstance(target_id, str) or not target_id or target_id.strip() != target_id:
            raise ValueError("target_id must be a nonempty string without surrounding whitespace")
        if not isinstance(span, tuple) or len(span) != 2 or not all(isinstance(o, timedelta) for o in span):
            raise TypeError(f"span for {target_id!r} must be a (timedelta, timedelta) tuple")
        start, end = span
        if start <= timedelta(0) or end <= start:
            raise ValueError(f"span for {target_id!r} must satisfy 0 < start_offset < end_offset")
        frames.append(
            decisions.select(
                "decision_time",
                "asset",
                pl.lit(target_id).alias("target_id"),
                (pl.col("decision_time") + start).cast(_UTC).alias("target_start"),
                (pl.col("decision_time") + end).cast(_UTC).alias("target_end"),
            )
        )
    windows = pl.concat(frames).sort("decision_time", "asset", "target_id")
    validate_target_windows(windows)
    return windows


# --------------------------------------------------------------------------- #
# Forward targets
# --------------------------------------------------------------------------- #


def build_forward_returns(
    windows: pl.DataFrame,
    prices: pl.DataFrame,
    *,
    return_type: Literal["simple", "log"],
) -> pl.DataFrame:
    """Return every window, its return, endpoints, metadata, and validity status.

    Invalid present prices take precedence over missing prices. Nonfinite return
    arithmetic is invalid_target. Output is sorted by decision_time/asset/target_id.
    """
    if return_type not in ("simple", "log"):
        raise ValueError("return_type must be simple or log")
    validate_target_windows(windows)
    validate_prices(prices)
    frame = windows.select("decision_time", "asset", "target_id", "target_start", "target_end")
    for endpoint in ("start", "end"):
        lookup = prices.select(
            "asset", pl.col("timestamp").alias(f"target_{endpoint}"), pl.col("price").alias(f"_{endpoint}_price")
        )
        frame = frame.join(lookup, on=["asset", f"target_{endpoint}"], how="left", validate="m:1")

    entry, exit_ = pl.col("_start_price"), pl.col("_end_price")
    invalid = ((~entry.is_finite()) | (entry <= 0)).fill_null(False) | ((~exit_.is_finite()) | (exit_ <= 0)).fill_null(
        False
    )
    status = (
        pl.when(invalid)
        .then(pl.lit("invalid_price"))
        .when(entry.is_null() & exit_.is_null())
        .then(pl.lit("missing_both_prices"))
        .when(entry.is_null())
        .then(pl.lit("missing_entry_price"))
        .when(exit_.is_null())
        .then(pl.lit("missing_exit_price"))
        .otherwise(pl.lit("ok"))
    )
    # log1p preserves tiny changes; a difference of logs avoids ratio overflow
    # when prices are far apart. Both branches evaluate the same log return.
    relative = (exit_ - entry) / entry
    value = (
        relative
        if return_type == "simple"
        else (pl.when(relative.abs() <= 0.5).then(relative.log1p()).otherwise(exit_.log() - entry.log()))
    )
    frame = frame.with_columns(status.alias("target_status"), value.alias("_return"))
    frame = frame.with_columns(
        pl.when((pl.col("target_status") == "ok") & ~pl.col("_return").is_finite())
        .then(pl.lit("invalid_target"))
        .otherwise(pl.col("target_status"))
        .alias("target_status")
    )
    return frame.select(
        "decision_time",
        "asset",
        "target_id",
        "target_start",
        "target_end",
        pl.when(pl.col("target_status") == "ok")
        .then(pl.col("_return"))
        .otherwise(None)
        .cast(pl.Float64)
        .alias("target"),
        "target_status",
        pl.lit("price_return").alias("target_kind"),
        pl.lit(return_type).alias("return_type"),
    ).sort("decision_time", "asset", "target_id")


__all__ = ["build_forward_returns", "horizon_windows"]
