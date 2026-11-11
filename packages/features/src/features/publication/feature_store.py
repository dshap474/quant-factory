"""Canonical FeatureStore I/O helpers for feature runners."""

from __future__ import annotations

from pathlib import Path

import polars as pl
from config import QUANT_DB_ROOT
from data.api import FeatureStore, FeatureStoreConfig, FeatureVersion


def _build_store(
    db_root: Path,
    require_asset_column: bool,
    allow_label_columns: bool = False,
    row_group_size: int | None = None,
) -> FeatureStore:
    return FeatureStore(
        FeatureStoreConfig(
            db_root=db_root,
            require_asset_column=require_asset_column,
            allow_metadata_feature_columns=allow_label_columns,
            row_group_size=row_group_size,
        )
    )


def read_feature_dataset(
    *,
    resolution: str,
    category: str,
    version: str = "latest",
    columns: list[str] | None = None,
    assets: list[str] | None = None,
    start: str | None = None,
    end: str | None = None,
    db_root: Path = QUANT_DB_ROOT,
    require_asset_column: bool = False,
) -> pl.DataFrame:
    store = _build_store(db_root=db_root, require_asset_column=require_asset_column)
    return store.read(
        resolution=resolution,
        category=category,
        version=version,
        columns=columns,
        assets=assets,
        start=start,
        end=end,
    )


def write_feature_dataset(
    *,
    data: pl.DataFrame,
    resolution: str,
    category: str,
    version: str | None = None,
    description: str | None = None,
    created_by: str = "feature_runner",
    force: bool = False,
    db_root: Path = QUANT_DB_ROOT,
    require_asset_column: bool = False,
    extra_meta: dict | None = None,
    allow_label_columns: bool = False,
    row_group_size: int | None = None,
) -> FeatureVersion:
    """Write one canonical dataset; ``allow_label_columns`` admits String columns the caller validated.

    ``row_group_size`` bounds rows per Parquet row group; ``None`` keeps the writer default.
    """
    store = _build_store(
        db_root=db_root,
        require_asset_column=require_asset_column,
        allow_label_columns=allow_label_columns,
        row_group_size=row_group_size,
    )
    return store.write(
        data=data,
        resolution=resolution,
        category=category,
        version=version,
        description=description,
        created_by=created_by,
        force=force,
        extra_meta=extra_meta,
    )
