"""Adapt signal prediction frames and price panels to the signal-analysis table contracts.

The signals prediction-frame contract stores one naive daily ``timestamp`` per bar. A bar
dated ``d`` is the UTC session for that date, so its close instant is ``d + bar_close_offset``
(one day for daily bars). Every signal-analysis table is keyed on close instants, and this
module is the single place that conversion happens.

Clock convention (naive or ``Date`` timestamps are interpreted as UTC; tz-aware timestamps
are converted to UTC, never shifted):

    decision_time       = timestamp + bar_close_offset + availability_lag
    signal_available_at = decision_time
    price timestamp     = timestamp + bar_close_offset

``availability_lag`` (default zero) only models evaluation latency inside signal analysis; it never
shifts the published prediction frame, which stays unlagged.

USAGE:

    from datetime import timedelta
    from signals.analysis_panel import prediction_frame_to_signal_panel, price_frame_from_panel

    panel = prediction_frame_to_signal_panel(
        predictions, signal_col="prediction", bar_close_offset=timedelta(days=1),
        eligible=pl.col("asset") != "BTC",
    )
    prices = price_frame_from_panel(feature_panel, price_col="close", bar_close_offset=timedelta(days=1))
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports
# --------------------------------------------------------------------------- #
from datetime import timedelta

import polars as pl
from signal_analysis.contracts import validate_prices, validate_signal_panel

_UTC = pl.Datetime("us", "UTC")

# --------------------------------------------------------------------------- #
# Clock helpers
# --------------------------------------------------------------------------- #


def _close_instant(frame: pl.DataFrame, timestamp_col: str, offset: timedelta) -> pl.Expr:
    """Return ``timestamp_col`` as a UTC close instant shifted by ``offset``."""
    if timestamp_col not in frame.columns:
        raise KeyError(f"frame has no {timestamp_col!r} column")
    dtype = frame.schema[timestamp_col]
    column = pl.col(timestamp_col)
    if dtype == pl.Date:
        instant = column.cast(pl.Datetime("us")).dt.replace_time_zone("UTC")
    elif isinstance(dtype, pl.Datetime):
        instant = column.cast(pl.Datetime("us", dtype.time_zone))
        instant = (
            instant.dt.replace_time_zone("UTC") if dtype.time_zone is None else instant.dt.convert_time_zone("UTC")
        )
    else:
        raise TypeError(f"column {timestamp_col!r} must be Date or Datetime, got {dtype}")
    return (instant + offset).cast(_UTC)


def _require_asset(frame: pl.DataFrame, asset_col: str) -> None:
    if asset_col not in frame.columns:
        raise KeyError(
            f"frame has no {asset_col!r} column; single-asset signals must add a constant asset column explicitly"
        )


# --------------------------------------------------------------------------- #
# Public adapters
# --------------------------------------------------------------------------- #


def prediction_frame_to_signal_panel(
    predictions: pl.DataFrame,
    *,
    signal_col: str = "prediction",
    timestamp_col: str = "timestamp",
    asset_col: str = "asset",
    bar_close_offset: timedelta,
    availability_lag: timedelta = timedelta(0),
    eligible: pl.Expr | None = None,
) -> pl.DataFrame:
    """Build a validated signal-analysis signal panel from a prediction frame.

    ``eligible`` is evaluated against ``predictions`` and defaults to ``True`` for every row.
    Non-finite signals are kept (the IC accounting excludes them by reason). Duplicate
    ``(timestamp, asset)`` keys fail through the signal-analysis contract.
    """
    _require_asset(predictions, asset_col)
    if signal_col not in predictions.columns:
        raise KeyError(f"frame has no {signal_col!r} column")
    decision_time = _close_instant(predictions, timestamp_col, bar_close_offset + availability_lag)
    panel = predictions.select(
        decision_time.alias("decision_time"),
        pl.col(asset_col).cast(pl.String).alias("asset"),
        decision_time.alias("signal_available_at"),
        pl.col(signal_col).cast(pl.Float64).alias("signal"),
        (pl.lit(True) if eligible is None else eligible).cast(pl.Boolean).alias("eligible"),
    ).sort("decision_time", "asset")
    validate_signal_panel(panel)
    return panel


def price_frame_from_panel(
    frame: pl.DataFrame,
    *,
    price_col: str,
    timestamp_col: str = "timestamp",
    asset_col: str = "asset",
    bar_close_offset: timedelta,
) -> pl.DataFrame:
    """Build a validated signal-analysis price table keyed on close instants.

    Null prices are dropped so a missing bar reports as a missing endpoint, never as
    ``invalid_price``. Non-positive or non-finite prices are kept for the target builder to flag.
    """
    _require_asset(frame, asset_col)
    if price_col not in frame.columns:
        raise KeyError(f"frame has no {price_col!r} column")
    prices = (
        frame.filter(pl.col(price_col).is_not_null())
        .select(
            pl.col(asset_col).cast(pl.String).alias("asset"),
            _close_instant(frame, timestamp_col, bar_close_offset).alias("timestamp"),
            pl.col(price_col).cast(pl.Float64).alias("price"),
        )
        .sort("asset", "timestamp")
    )
    validate_prices(prices)
    return prices


__all__ = ["prediction_frame_to_signal_panel", "price_frame_from_panel"]
