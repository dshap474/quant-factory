"""Small helpers for publishing canonical feature datasets."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import polars as pl
from config import QUANT_DB_ROOT

from .feature_store import read_feature_dataset, write_feature_dataset
from .validation import ASSET_COL, TIMESTAMP_COL, ensure_timestamp_datetime, validate_feature_frame


@dataclass
class FeaturePublishResult:
    """Result from computing and optionally writing one feature dataset."""

    features: pl.DataFrame
    config: dict
    saved: bool
    data_path: Path | None = None

    def summary(self) -> str:
        lines = [
            "FeaturePublishResult",
            "=" * 40,
            f"Rows: {len(self.features):,}",
            f"Columns: {len(self.features.columns):,}",
            f"Saved: {self.saved}",
        ]
        if self.data_path:
            lines.append(f"Path: {self.data_path}")
        return "\n".join(lines)


def publish_feature_frame(
    *,
    features: pl.DataFrame,
    config: dict,
    category: str,
    resolution: str = "1d",
    save: bool = True,
    force: bool = False,
    description: str | None = None,
    created_by: str = "feature_runner",
    require_asset_column: bool = False,
    db_root: Path = QUANT_DB_ROOT,
    extra_meta: dict | None = None,
    label_columns: tuple[str, ...] = (),
    row_group_size: int | None = None,
) -> FeaturePublishResult:
    """Validate a feature frame and optionally write it to ``db/features``."""
    validated = validate_feature_frame(
        features,
        require_asset=require_asset_column,
        category=category,
        label_columns=label_columns,
    )
    data_path = None
    if save:
        written = write_feature_dataset(
            data=validated,
            resolution=resolution,
            category=category,
            description=description,
            created_by=created_by,
            force=force,
            db_root=db_root,
            require_asset_column=require_asset_column,
            extra_meta=extra_meta,
            allow_label_columns=bool(label_columns),
            row_group_size=row_group_size,
        )
        data_path = written.data_path
    return FeaturePublishResult(
        features=validated,
        config=config,
        saved=save,
        data_path=data_path,
    )


def run_feature_publication(
    family: object,
    *,
    require_asset_column: bool,
) -> FeaturePublishResult:
    """Run a small family-local publisher object."""
    run_config = family.run_config
    source = family.load_data()
    features = family.compute(source)
    meta_overrides = None
    if hasattr(family, "get_meta_overrides"):
        meta_overrides = family.get_meta_overrides(features)
    return publish_feature_frame(
        features=features,
        config=family.get_config_dict(),
        category=run_config.category,
        resolution=run_config.resolution,
        save=run_config.save,
        force=run_config.force,
        description=run_config.description,
        created_by=getattr(run_config, "created_by", "feature_runner"),
        require_asset_column=require_asset_column,
        db_root=getattr(run_config, "db_root", QUANT_DB_ROOT),
        extra_meta=meta_overrides,
        label_columns=tuple(getattr(run_config, "label_columns", ())),
        row_group_size=getattr(run_config, "row_group_size", None),
    )


def bootstrap_feature_packages() -> None:
    """Compatibility no-op; ``features`` mounts extension family sources on import."""
    return None


__all__ = [
    "ASSET_COL",
    "TIMESTAMP_COL",
    "FeaturePublishResult",
    "bootstrap_feature_packages",
    "ensure_timestamp_datetime",
    "publish_feature_frame",
    "read_feature_dataset",
    "run_feature_publication",
    "validate_feature_frame",
    "write_feature_dataset",
]
