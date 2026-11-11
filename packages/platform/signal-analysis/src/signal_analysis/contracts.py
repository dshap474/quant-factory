"""Validate public feature, signal, target-window, price, and target tables.

Usage: ``validate_signal_panel(panel)``; ``validate_feature_frame(frame, feature_columns=["x"])``.
Validation raises TypeError for schema errors and ValueError for invalid contents.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports and schemas
# --------------------------------------------------------------------------- #
from collections.abc import Sequence

import polars as pl

_UTC = pl.Datetime("us", "UTC")
_SIGNAL_SCHEMA = pl.Schema(
    {
        "decision_time": _UTC,
        "asset": pl.String,
        "signal_available_at": _UTC,
        "signal": pl.Float64,
        "eligible": pl.Boolean,
    }
)
_FEATURE_PANEL_SCHEMA = pl.Schema({"observation_id": pl.String, "decision_time": _UTC, "features_available_at": _UTC})
_WINDOW_SCHEMA = pl.Schema(
    {"decision_time": _UTC, "asset": pl.String, "target_id": pl.String, "target_start": _UTC, "target_end": _UTC}
)
_PRICE_SCHEMA = pl.Schema({"asset": pl.String, "timestamp": _UTC, "price": pl.Float64})
_TARGET_SCHEMA = pl.Schema(
    {
        **_WINDOW_SCHEMA,
        "target": pl.Float64,
        "target_status": pl.String,
        "target_kind": pl.String,
        "return_type": pl.String,
    }
)
_TARGET_STATUSES = (
    "ok",
    "missing_entry_price",
    "missing_exit_price",
    "missing_both_prices",
    "invalid_price",
    "invalid_target",
    "missing_target",
)


# --------------------------------------------------------------------------- #
# Shared validation
# --------------------------------------------------------------------------- #


def _validate_table(frame: pl.DataFrame, schema: pl.Schema, *, required: list[str], key: list[str]) -> None:
    if not isinstance(frame, pl.DataFrame):
        raise TypeError("expected a Polars DataFrame")
    for name, dtype in schema.items():
        if name not in frame.schema or frame.schema[name] != dtype:
            raise TypeError(f"column {name!r} must have dtype {dtype}")
    if frame.select(pl.any_horizontal(pl.col(required).is_null()).any()).item():
        raise ValueError(f"null values are not allowed in {required}")
    for name in required:
        if (
            schema[name] == pl.String
            and frame.select((pl.col(name).eq("") | pl.col(name).ne(pl.col(name).str.strip_chars())).any()).item()
        ):
            raise ValueError(f"column {name!r} must contain nonempty strings without surrounding whitespace")
    if frame.select(key).is_duplicated().any():
        raise ValueError(f"duplicate keys in {key}")


# --------------------------------------------------------------------------- #
# Public contracts
# --------------------------------------------------------------------------- #


def validate_feature_frame(frame: pl.DataFrame, *, feature_columns: Sequence[str]) -> None:
    """Check an explicit numeric feature selection without filtering its values.

    This matrix-level contract makes no timing, identity, eligibility, or fitting
    claim. Missing and nonfinite values remain visible for the owning calculation
    to reject or account for. Extra columns are allowed and inputs are unchanged.
    """
    if not isinstance(frame, pl.DataFrame):
        raise TypeError("expected a Polars DataFrame")
    if isinstance(feature_columns, (str, bytes)) or not isinstance(feature_columns, Sequence):
        raise TypeError("feature_columns must be a sequence of column names")
    if not feature_columns or any(
        not isinstance(name, str) or not name or name != name.strip() for name in feature_columns
    ):
        raise ValueError("feature_columns must contain nonempty names without surrounding whitespace")
    if len(feature_columns) != len(set(feature_columns)):
        raise ValueError("feature_columns must be unique")
    for name in feature_columns:
        if name not in frame.schema or frame.schema[name] != pl.Float64:
            raise TypeError(f"feature column {name!r} must have dtype Float64")


def validate_feature_panel(panel: pl.DataFrame, *, feature_columns: Sequence[str]) -> None:
    """Check an identified, explicitly timed feature matrix.

    ``features_available_at`` is the caller's latest availability timestamp over
    the selected feature values for each observation. It must not follow the
    decision. This assertion cannot prove historical provenance or model fitting
    isolation. Callers select eligible observations before this calculation API.
    """
    validate_feature_frame(panel, feature_columns=feature_columns)
    if set(feature_columns) & set(_FEATURE_PANEL_SCHEMA.names()):
        raise ValueError("feature columns must not overlap feature-panel identity or clocks")
    _validate_table(
        panel,
        _FEATURE_PANEL_SCHEMA,
        required=list(_FEATURE_PANEL_SCHEMA),
        key=["observation_id"],
    )
    if panel.filter(pl.col("features_available_at") > pl.col("decision_time")).height:
        raise ValueError("features_available_at must not follow decision_time")


def validate_signal_panel(panel: pl.DataFrame) -> None:
    """Require one eligible-or-excluded signal per asset and decision time."""
    _validate_table(
        panel,
        _SIGNAL_SCHEMA,
        required=["decision_time", "asset", "signal_available_at", "eligible"],
        key=["decision_time", "asset"],
    )
    if panel.filter(pl.col("signal_available_at") > pl.col("decision_time")).height:
        raise ValueError("signal_available_at must not follow decision_time")


def validate_target_windows(windows: pl.DataFrame) -> None:
    """Require unique, strictly future windows with explicit UTC endpoints."""
    _validate_table(
        windows,
        _WINDOW_SCHEMA,
        required=list(_WINDOW_SCHEMA),
        key=["decision_time", "asset", "target_id"],
    )
    invalid = (pl.col("target_start") <= pl.col("decision_time")) | (pl.col("target_end") <= pl.col("target_start"))
    if windows.filter(invalid).height:
        raise ValueError("windows must satisfy decision_time < target_start < target_end")


def validate_prices(prices: pl.DataFrame) -> None:
    """Validate price identity and schema; bad price values become target statuses."""
    _validate_table(prices, _PRICE_SCHEMA, required=["asset", "timestamp"], key=["asset", "timestamp"])


def validate_targets(targets: pl.DataFrame) -> None:
    """Validate target timing, finite-or-missing values, and per-target metadata."""
    _validate_table(
        targets,
        _TARGET_SCHEMA,
        required=[*_WINDOW_SCHEMA, "target_status", "target_kind"],
        key=["decision_time", "asset", "target_id"],
    )
    validate_target_windows(targets)
    if targets.filter(~pl.col("target_status").is_in(_TARGET_STATUSES)).height:
        raise ValueError("unknown target_status")
    ok = pl.col("target_status") == "ok"
    invalid_value = (ok & ~pl.col("target").is_finite().fill_null(False)) | (~ok & pl.col("target").is_not_null())
    if targets.filter(invalid_value).height:
        raise ValueError("ok targets must be finite; other target statuses require null values")
    invalid_type = pl.col("return_type").is_not_null() & ~pl.col("return_type").is_in(["simple", "log"])
    missing_type = (pl.col("target_kind") == "price_return") & pl.col("return_type").is_null()
    if targets.filter(invalid_type | missing_type).height:
        raise ValueError("return_type must be simple/log, or null for non-price-return targets")
    metadata = targets.group_by("target_id").agg(pl.col("target_kind", "return_type").n_unique())
    if metadata.filter((pl.col("target_kind") != 1) | (pl.col("return_type") != 1)).height:
        raise ValueError("target_kind and return_type must be consistent within each target_id")


__all__ = [
    "validate_feature_frame",
    "validate_feature_panel",
    "validate_signal_panel",
    "validate_target_windows",
    "validate_prices",
    "validate_targets",
]
