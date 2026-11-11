"""Public point-in-time asset-identity resolution.

USAGE:
    from data.api import resolve_asset_ids

    resolved = resolve_asset_ids(
        frame,
        identifier_type="yfinance_symbol",
        identifier_column="asset",
        as_of_column="date",
    )
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from data.config.paths import resolve_db_root
from data.platform.asset_mapper import resolve_asset_ids as _resolve_asset_ids

# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def resolve_asset_ids(
    frame: pl.DataFrame,
    *,
    identifier_type: str,
    identifier_column: str,
    as_of_column: str,
    venue: str | None = None,
    venue_column: str | None = None,
    venue_fallback: bool = False,
    db_root: str | Path | None = None,
    allow_missing: bool = False,
) -> pl.DataFrame:
    """Add effective-dated canonical ``asset_id`` values to a Polars frame."""
    return _resolve_asset_ids(
        frame,
        db_root=resolve_db_root(db_root),
        identifier_type=identifier_type,
        identifier_column=identifier_column,
        as_of_column=as_of_column,
        venue=venue,
        venue_column=venue_column,
        venue_fallback=venue_fallback,
        allow_missing=allow_missing,
    )


__all__ = ["resolve_asset_ids"]
