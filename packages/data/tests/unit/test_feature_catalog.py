"""Tests for latest-state feature catalog validation and migration."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import polars as pl
import yaml
from data.platform.storage.feature_catalog import (
    migrate_feature_catalog,
    validate_feature_catalog,
)


def _write_manifest(root: Path, payload: dict) -> None:
    manifest_path = root / "packages" / "features" / "FEATURES.yaml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as handle:
        yaml.dump(payload, handle, default_flow_style=False, sort_keys=False)


def _simple_df(with_asset: bool = True) -> pl.DataFrame:
    base = {
        "timestamp": [datetime(2024, 1, 1) + timedelta(days=i) for i in range(3)],
        "feature_a": [0.1, 0.2, 0.3],
        "feature_b": [1.0, 0.8, 0.6],
    }
    if with_asset:
        base["asset"] = ["ASSET_A", "ASSET_A", "ASSET_A"]
    return pl.DataFrame(base)


def test_validate_feature_catalog_happy_path(tmp_path: Path) -> None:
    root = tmp_path
    db_root = root / "db"
    data_path = db_root / "features" / "1d" / "cross_sectional" / "example" / "panel" / "data.parquet"
    data_path.parent.mkdir(parents=True, exist_ok=True)
    _simple_df(with_asset=True).write_parquet(data_path)
    (data_path.parent / "meta.yaml").write_text("viz:\n  y_default: feature_a\n", encoding="utf-8")

    registry = {
        "version": 5,
        "description": "test registry",
        "categories": {
            "cross_sectional/example/panel": {
                "description": "example panel",
                "resolutions": ["1d"],
                "status": "active",
                "asset_column": True,
            }
        },
        "features": {
            "1d/cross_sectional/example/panel": {
                "description": "example panel",
                "status": "active",
                "data_path": "features/1d/cross_sectional/example/panel/data.parquet",
            }
        },
    }
    with open(db_root / "features" / "REGISTRY.yaml", "w", encoding="utf-8") as handle:
        yaml.dump(registry, handle, default_flow_style=False, sort_keys=False)

    _write_manifest(
        root,
        {
            "version": 3,
            "features": {
                "cross_sectional/example/panel": {
                    "status": "active",
                    "publication_state": "published",
                    "description": "example panel",
                    "resolutions": ["1d"],
                    "asset_column": True,
                }
            },
        },
    )

    result = validate_feature_catalog(db_root)
    assert result.valid
    assert not result.errors


def test_validate_feature_catalog_rejects_unpublished_realized_dataset(tmp_path: Path) -> None:
    root = tmp_path
    db_root = root / "db"
    data_path = db_root / "features" / "1d" / "example" / "asset" / "spot" / "data.parquet"
    data_path.parent.mkdir(parents=True, exist_ok=True)
    _simple_df(with_asset=False).write_parquet(data_path)
    (data_path.parent / "meta.yaml").write_text("viz:\n  y_default: feature_a\n", encoding="utf-8")

    registry = {
        "version": 5,
        "description": "test registry",
        "categories": {
            "example/asset/spot": {
                "description": "example spot",
                "resolutions": ["1d"],
                "status": "draft",
                "asset_column": False,
            }
        },
        "features": {
            "1d/example/asset/spot": {
                "description": "example spot",
                "status": "draft",
                "data_path": "features/1d/example/asset/spot/data.parquet",
            }
        },
    }
    with open(db_root / "features" / "REGISTRY.yaml", "w", encoding="utf-8") as handle:
        yaml.dump(registry, handle, default_flow_style=False, sort_keys=False)

    _write_manifest(
        root,
        {
            "version": 3,
            "features": {
                "example/asset/spot": {
                    "status": "draft",
                    "publication_state": "unpublished",
                    "description": "example spot",
                    "resolutions": ["1d"],
                    "asset_column": False,
                }
            },
        },
    )

    result = validate_feature_catalog(db_root)
    assert not result.valid
    assert any(
        "unpublished category has registry.features entry: 1d/example/asset/spot" in err for err in result.errors
    )
    assert any("unpublished category has realized dataset: 1d/example/asset/spot" in err for err in result.errors)


def test_migrate_feature_catalog_flattens_versioned_dataset(tmp_path: Path) -> None:
    root = tmp_path
    db_root = root / "db"
    version_dir = db_root / "features" / "1d" / "example" / "asset" / "futures" / "v2"
    version_dir.mkdir(parents=True, exist_ok=True)
    _simple_df(with_asset=False).write_parquet(version_dir / "data.parquet")
    (version_dir / "meta.yaml").write_text("viz:\n  y_default: feature_a\n", encoding="utf-8")

    _write_manifest(
        root,
        {
            "version": 3,
            "features": {
                "example/asset/futures": {
                    "status": "active",
                    "publication_state": "published",
                    "description": "example futures",
                    "resolutions": ["1d"],
                    "asset_column": False,
                }
            },
        },
    )

    result = migrate_feature_catalog(db_root, hard_cutover=True)

    canonical = db_root / "features" / "1d" / "example" / "asset" / "futures" / "data.parquet"
    assert canonical.exists()
    assert not version_dir.exists()
    assert (db_root / "features" / "REGISTRY.yaml").exists()
    assert result.registry_path == db_root / "features" / "REGISTRY.yaml"


def test_migrate_feature_catalog_keeps_latest_version_when_multiple_exist(tmp_path: Path) -> None:
    root = tmp_path
    db_root = root / "db"
    v1_dir = db_root / "features" / "1d" / "example" / "asset" / "futures" / "v1"
    v2_dir = db_root / "features" / "1d" / "example" / "asset" / "futures" / "v2"
    v1_dir.mkdir(parents=True, exist_ok=True)
    v2_dir.mkdir(parents=True, exist_ok=True)
    pl.DataFrame({"timestamp": [datetime(2024, 1, 1)], "feature_a": [1.0]}).write_parquet(v1_dir / "data.parquet")
    pl.DataFrame({"timestamp": [datetime(2024, 1, 1)], "feature_a": [2.0]}).write_parquet(v2_dir / "data.parquet")

    _write_manifest(
        root,
        {
            "version": 3,
            "features": {
                "example/asset/futures": {
                    "status": "active",
                    "publication_state": "published",
                    "description": "example futures",
                    "resolutions": ["1d"],
                    "asset_column": False,
                }
            },
        },
    )

    migrate_feature_catalog(db_root, hard_cutover=True)

    canonical = pl.read_parquet(
        db_root / "features" / "1d" / "example" / "asset" / "futures" / "data.parquet"
    )
    assert canonical["feature_a"].to_list() == [2.0]
