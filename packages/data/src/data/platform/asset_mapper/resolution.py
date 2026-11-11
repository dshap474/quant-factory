"""Point-in-time resolution from provider identifiers to canonical asset IDs.

USAGE:
    resolved = resolve_asset_ids(
        frame,
        db_root=db_root,
        identifier_type="yfinance_symbol",
        identifier_column="asset",
        as_of_column="date",
    )
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from data.platform.errors import DatasetContractError

from .core import (
    IDENTIFIER_TYPES,
    asset_identity_pack_lock,
    asset_mapper_assets_path,
    asset_mapper_identifiers_path,
    asset_mapper_meta_path,
    identifier_value_expression,
    normalize_assets,
    normalize_identifiers,
    validate_identifiers,
    validate_pack_generation,
)

# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #


def load_asset_identity(db_root: Path) -> tuple[pl.DataFrame, pl.DataFrame, str]:
    """Load and validate the canonical identity generation."""
    assets_path = asset_mapper_assets_path(db_root)
    identifiers_path = asset_mapper_identifiers_path(db_root)
    meta_path = asset_mapper_meta_path(db_root)
    present = (assets_path.exists(), identifiers_path.exists(), meta_path.exists())
    if all(present):
        with asset_identity_pack_lock(db_root, shared=True):
            validate_pack_generation(db_root)
            assets = normalize_assets(pl.read_parquet(assets_path))
            identifiers = normalize_identifiers(pl.read_parquet(identifiers_path))
            validate_identifiers(identifiers, assets)
            return assets, identifiers, "canonical"
    if any(present):
        raise DatasetContractError(
            "Canonical asset identity is incomplete",
            assets_exists=present[0],
            identifiers_exists=present[1],
            meta_exists=present[2],
        )
    raise DatasetContractError(
        "Canonical asset identity is not materialized",
        action="materialize db/data/derived/reference/asset-identity/ with a dataset extension",
    )


# --------------------------------------------------------------------------- #
# Resolution
# --------------------------------------------------------------------------- #


def resolve_asset_ids(
    frame: pl.DataFrame,
    *,
    db_root: Path,
    identifier_type: str,
    identifier_column: str,
    as_of_column: str,
    venue: str | None = None,
    venue_column: str | None = None,
    venue_fallback: bool = False,
    allow_missing: bool = False,
) -> pl.DataFrame:
    """Add point-in-time ``asset_id`` values to a frame.

    Missing identifiers fail by default. ``allow_missing=True`` retains them as
    null values so batch pipelines can report explicit coverage diagnostics.
    Ambiguous active mappings always fail. ``venue_fallback=True`` uses global
    history only when no history exists for the requested venue and identifier.
    A scoped history gap stays unresolved. Defaults preserve exact-scope lookup.
    ``venue_column`` supports mixed-venue batches.
    """
    if identifier_type not in IDENTIFIER_TYPES:
        raise DatasetContractError("Unsupported asset identifier type", identifier_type=identifier_type)
    missing_columns = [column for column in (identifier_column, as_of_column) if column not in frame.columns]
    if missing_columns:
        raise DatasetContractError("Asset resolution frame is missing columns", missing_columns=missing_columns)
    if "asset_id" in frame.columns:
        raise DatasetContractError("Asset resolution frame already contains asset_id")
    if frame.schema[as_of_column] != pl.Date:
        raise DatasetContractError(
            "Asset resolution as-of column must use Polars Date",
            column=as_of_column,
            dtype=str(frame.schema[as_of_column]),
        )

    _, identifiers, _ = load_asset_identity(db_root)
    if venue is not None and venue_column is not None:
        raise DatasetContractError("Supply venue or venue_column, not both")
    if venue_column is not None and venue_column not in frame.columns:
        raise DatasetContractError("Venue column is missing", column=venue_column)
    candidates = identifiers.filter(pl.col("identifier_type") == identifier_type).select(
        "identifier_value", "asset_id", "valid_from", "valid_to",
        pl.col("venue").fill_null("").alias("__mapping_venue"),
    )
    requested_venue = pl.col(venue_column) if venue_column else pl.lit(venue, dtype=pl.String)
    working = frame.with_row_index("__identity_row").with_columns(
        identifier_value_expression(identifier_type, identifier_column).alias("__identity_value"),
        requested_venue.cast(pl.String).str.strip_chars().str.to_uppercase().fill_null("").alias("__requested_venue"),
    )
    if venue_fallback:
        # Any scoped history owns the symbol, including gaps outside active intervals.
        scoped = candidates.filter(pl.col("__mapping_venue") != "").select(
            pl.col("identifier_value").alias("__identity_value"),
            pl.col("__mapping_venue").alias("__requested_venue"),
        ).unique().with_columns(pl.lit(True).alias("__has_scoped_history"))
        working = working.join(scoped, on=["__identity_value", "__requested_venue"], how="left", validate="m:1").with_columns(
            pl.when(pl.col("__has_scoped_history").fill_null(False))
            .then(pl.col("__requested_venue")).otherwise(pl.lit("")).alias("__requested_venue")
        ).drop("__has_scoped_history")
    matches = (
        working.select("__identity_row", "__identity_value", "__requested_venue", as_of_column)
        .join(candidates, left_on="__identity_value", right_on="identifier_value", how="inner")
        .filter(
            (pl.col("__requested_venue") == pl.col("__mapping_venue"))
            & (pl.col(as_of_column) >= pl.col("valid_from"))
            & (pl.col("valid_to").is_null() | (pl.col(as_of_column) < pl.col("valid_to")))
        )
    )
    ambiguous = matches.group_by("__identity_row").len().filter(pl.col("len") > 1)
    if ambiguous.height:
        raise DatasetContractError(
            "Asset identifier resolves ambiguously",
            row_indexes=ambiguous.get_column("__identity_row").to_list()[:20],
        )

    resolved = working.join(
        matches.select("__identity_row", "asset_id"),
        on="__identity_row",
        how="left",
        validate="1:1",
    )
    if not allow_missing:
        missing = resolved.filter(pl.col("asset_id").is_null()).get_column("__identity_value").unique().sort()
        if len(missing):
            raise DatasetContractError(
                "Asset identifiers are missing point-in-time mappings",
                identifier_type=identifier_type,
                missing_count=len(missing),
                identifiers=missing.to_list()[:20],
            )
    return resolved.drop("__identity_row", "__identity_value", "__requested_venue")


__all__ = ["load_asset_identity", "resolve_asset_ids"]
