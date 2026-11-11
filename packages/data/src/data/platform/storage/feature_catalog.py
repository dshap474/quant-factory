"""Feature catalog validation + migration utilities.

Canonical catalog sources:
- ``packages/features/FEATURES.yaml`` (intended categories + lifecycle)
- ``db/features/REGISTRY.yaml`` (latest realized datasets)
- ``db/features/{resolution}/{category}/data.parquet`` (data reality)
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import polars as pl
import yaml
from config import QUANT_DB_ROOT

from . import delta_read
from .feature_store import FeatureStore

FEATURES_MANIFEST_REL = Path("packages/features/FEATURES.yaml")


@dataclass
class FeatureCatalogValidation:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return len(self.errors) == 0

    def __str__(self) -> str:
        lines = [f"Feature catalog valid: {self.valid}"]
        if self.errors:
            lines.append(f"errors ({len(self.errors)}):")
            lines.extend(f"  - {err}" for err in self.errors)
        if self.warnings:
            lines.append(f"warnings ({len(self.warnings)}):")
            lines.extend(f"  - {warn}" for warn in self.warnings)
        if self.info:
            lines.append(f"info ({len(self.info)}):")
            lines.extend(f"  - {row}" for row in self.info)
        return "\n".join(lines)


@dataclass
class FeatureMigrationResult:
    moved: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    meta_updated: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    registry_path: Path | None = None

    def __str__(self) -> str:
        lines = ["Feature migration complete"]
        lines.append(f"moved: {len(self.moved)}")
        lines.append(f"removed: {len(self.removed)}")
        lines.append(f"meta_updated: {len(self.meta_updated)}")
        lines.append(f"warnings: {len(self.warnings)}")
        if self.registry_path is not None:
            lines.append(f"registry: {self.registry_path}")
        return "\n".join(lines)


def _repo_root(db_root: Path) -> Path:
    return db_root.parent


def _features_root(db_root: Path) -> Path:
    return db_root / "features"


def _registry_path(db_root: Path) -> Path:
    return _features_root(db_root) / "REGISTRY.yaml"


def _manifest_path(db_root: Path) -> Path:
    return _repo_root(db_root) / FEATURES_MANIFEST_REL


def _load_yaml(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    return loaded if isinstance(loaded, dict) else default


def _save_yaml(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        yaml.dump(payload, handle, default_flow_style=False, sort_keys=False)


def load_features_manifest(db_root: Path = QUANT_DB_ROOT) -> dict[str, Any]:
    return _load_yaml(_manifest_path(db_root), {"version": 3, "features": {}})


def load_feature_registry(db_root: Path = QUANT_DB_ROOT) -> dict[str, Any]:
    return _load_yaml(
        _registry_path(db_root),
        {
            "version": 5,
            "description": "quant-factory canonical latest-state feature catalog",
            "categories": {},
            "features": {},
        },
    )


def discover_feature_datasets(db_root: Path = QUANT_DB_ROOT) -> dict[str, Path]:
    """Discover canonical datasets by scanning ``data.parquet`` files and Delta table directories."""
    features_root = _features_root(db_root)
    found: dict[str, Path] = {}
    if not features_root.exists():
        return found

    files, tables = delta_read.walk_lake(features_root)
    for table in tables:  # a Delta feature table is the category directory itself
        rel = table.relative_to(features_root)
        if len(rel.parts) >= 2 and not any(part.startswith("_") for part in rel.parts[1:]):
            found[rel.as_posix()] = table
    for data_file in (file for file in files if file.name == "data.parquet"):
        rel = data_file.relative_to(features_root)
        if len(rel.parts) < 3:
            continue
        resolution = rel.parts[0]
        category_parts = rel.parts[1:-1]
        if not category_parts or any(part.startswith("_") for part in category_parts):
            continue
        key = f"{resolution}/{'/'.join(category_parts)}"
        found[key] = data_file
    return dict(sorted(found.items()))


def list_feature_catalog(db_root: Path = QUANT_DB_ROOT) -> list[dict[str, Any]]:
    manifest = load_features_manifest(db_root)
    registry = load_feature_registry(db_root)
    discovered = discover_feature_datasets(db_root)

    manifest_features = manifest.get("features", {})
    registry_categories = registry.get("categories", {})

    rows: list[dict[str, Any]] = []
    for category, manifest_entry in sorted(manifest_features.items()):
        status = manifest_entry.get("status", "active")
        resolutions = manifest_entry.get("resolutions", [])
        category_meta = registry_categories.get(category, {})
        available = []
        for resolution in resolutions:
            key = f"{resolution}/{category}"
            available.append(
                {
                    "resolution": resolution,
                    "data_path": str(discovered[key]) if key in discovered else None,
                    "published": key in discovered,
                }
            )

        rows.append(
            {
                "category": category,
                "status": status,
                "publication_state": manifest_entry.get("publication_state", "unpublished"),
                "description": manifest_entry.get("description", category_meta.get("description", "")),
                "asset_column": bool(manifest_entry.get("asset_column", category_meta.get("asset_column", False))),
                "resolutions": resolutions,
                "available": available,
            }
        )
    return rows


def _schema_columns(schema: dict[str, Any]) -> list[dict[str, str]]:
    return [{"name": col, "dtype": str(dtype)} for col, dtype in schema.items()]


def _default_viz_config(schema: dict[str, Any]) -> dict[str, Any]:
    numeric_cols = [
        col
        for col, dtype in schema.items()
        if col not in {"timestamp", "asset"} and any(token in str(dtype) for token in ("Int", "Float"))
    ]
    y_default = numeric_cols[0] if numeric_cols else None
    return {
        "x_column": "timestamp",
        "y_default": y_default,
        "y_candidates": numeric_cols[:20],
        "max_points": 3000,
    }


def _build_meta(
    *,
    data_path: Path,
    resolution: str,
    category: str,
    description: str,
    created_by: str,
) -> dict[str, Any]:
    schema = delta_read.lake_schema(data_path)
    lf = delta_read.lake_scan(data_path)
    stats_row = lf.select(
        [
            pl.len().alias("row_count"),
            pl.min("timestamp").alias("date_start"),
            pl.max("timestamp").alias("date_end"),
        ]
    ).collect().row(0, named=True)

    meta = {
        "name": category.replace("/", "_"),
        "description": description,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": created_by,
        "resolution": resolution,
        "category": category,
        "schema": {
            "timestamp_col": "timestamp",
            "asset_col": "asset",
            "columns": _schema_columns(schema),
        },
        "stats": {
            "row_count": int(stats_row["row_count"]),
            "column_count": len(schema),
            "date_range": {
                "start": str(stats_row["date_start"]),
                "end": str(stats_row["date_end"]),
            },
        },
        "viz": _default_viz_config(schema),
    }

    if "asset" in schema:
        asset_count = (
            lf.select(pl.col("asset").drop_nulls().n_unique().alias("asset_count"))
            .collect()
            .item()
        )
        meta["stats"]["asset_count"] = int(asset_count)
    return meta


def _resolve_dataset_path(features_root: Path, dataset_key: str) -> Path:
    resolution, category = dataset_key.split("/", 1)
    return features_root / resolution / Path(category) / "data.parquet"


def _build_registry(
    manifest: dict[str, Any],
    discovered: dict[str, Path],
    *,
    db_root: Path,
) -> dict[str, Any]:
    manifest_categories = manifest.get("features", {})
    categories: dict[str, Any] = {}
    features: dict[str, Any] = {}

    for category, manifest_entry in sorted(manifest_categories.items()):
        categories[category] = {
            "description": manifest_entry.get("description", ""),
            "resolutions": manifest_entry.get("resolutions", []),
            "status": manifest_entry.get("status", "active"),
            "asset_column": bool(manifest_entry.get("asset_column", False)),
        }

    now = datetime.now(timezone.utc).isoformat()
    for dataset_key, data_path in sorted(discovered.items()):
        resolution, category = dataset_key.split("/", 1)
        category_meta = categories.get(category, {})
        features[dataset_key] = {
            "description": category_meta.get("description", category),
            "status": category_meta.get("status", "active"),
            "data_path": str(data_path.relative_to(db_root)),
            "updated_at": now,
        }
        categories.setdefault(
            category,
            {
                "description": category,
                "resolutions": [resolution],
                "status": "active",
                "asset_column": False,
            },
        )
        if resolution not in categories[category]["resolutions"]:
            categories[category]["resolutions"].append(resolution)
            categories[category]["resolutions"].sort()

    return {
        "version": 5,
        "description": "quant-factory canonical latest-state feature catalog",
        "categories": categories,
        "features": features,
    }


def validate_feature_catalog(db_root: Path = QUANT_DB_ROOT) -> FeatureCatalogValidation:
    report = FeatureCatalogValidation()
    features_root = _features_root(db_root)
    manifest = load_features_manifest(db_root)
    registry = load_feature_registry(db_root)
    discovered = discover_feature_datasets(db_root)

    manifest_categories = manifest.get("features", {})
    registry_categories = registry.get("categories", {})
    registry_features = registry.get("features", {})

    if not manifest_categories:
        report.errors.append(f"Missing or empty manifest: {_manifest_path(db_root)}")
    if not features_root.exists():
        report.errors.append(f"features root not found: {features_root}")
        return report

    manifest_set = set(manifest_categories.keys())
    published_manifest_set = {
        category
        for category, manifest_entry in manifest_categories.items()
        if manifest_entry.get("publication_state", "unpublished") == "published"
    }
    registry_set = set(registry_categories.keys())

    for category in sorted(published_manifest_set - registry_set):
        report.errors.append(
            f"published category in manifest but missing in registry.categories: {category}"
        )
    for category in sorted(registry_set - manifest_set):
        report.errors.append(
            f"registry.categories contains category not declared in manifest: {category}"
        )

    for category, manifest_entry in sorted(manifest_categories.items()):
        publication_state = manifest_entry.get("publication_state", "unpublished")
        resolutions = manifest_entry.get("resolutions", [])

        registry_meta = registry_categories.get(category)
        if registry_meta is not None:
            expected_meta = {
                "description": manifest_entry.get("description", ""),
                "resolutions": sorted(manifest_entry.get("resolutions", [])),
                "status": manifest_entry.get("status", "active"),
                "asset_column": bool(manifest_entry.get("asset_column", False)),
            }
            actual_meta = {
                "description": registry_meta.get("description", ""),
                "resolutions": sorted(registry_meta.get("resolutions", [])),
                "status": registry_meta.get("status", "active"),
                "asset_column": bool(registry_meta.get("asset_column", False)),
            }
            for field, expected_value in expected_meta.items():
                if actual_meta[field] != expected_value:
                    report.errors.append(
                        f"registry.categories mismatch for {category} field {field!r}: "
                        f"expected {expected_value!r}, found {actual_meta[field]!r}"
                    )

        for resolution in resolutions:
            key = f"{resolution}/{category}"
            registry_entry = registry_features.get(key)
            realized = key in discovered

            if publication_state == "published":
                if registry_entry is None:
                    report.errors.append(f"published category missing registry.features entry: {key}")
                if not realized:
                    report.errors.append(f"published category missing dataset: {key}")
                    continue
                continue

            if registry_entry is not None:
                report.errors.append(f"unpublished category has registry.features entry: {key}")
            if realized:
                report.errors.append(f"unpublished category has realized dataset: {key}")

    for dataset_key, feature_meta in sorted(registry_features.items()):
        if "/" not in dataset_key:
            report.errors.append(f"invalid registry.features key: {dataset_key}")
            continue

        resolution, category = dataset_key.split("/", 1)
        manifest_entry = manifest_categories.get(category)
        if manifest_entry is None:
            report.errors.append(f"registry.features category not declared in manifest: {dataset_key}")
            continue
        if resolution not in manifest_entry.get("resolutions", []):
            report.errors.append(
                f"registry.features resolution not declared in manifest: {dataset_key}"
            )
        if manifest_entry.get("publication_state", "unpublished") != "published":
            report.errors.append(f"registry.features entry for unpublished category: {dataset_key}")

        data_path = discovered.get(dataset_key)
        if data_path is None or not data_path.exists():
            report.errors.append(f"registry points to missing data: {dataset_key}")
            continue

        meta_path = delta_read.meta_path(data_path)
        if not meta_path.exists():
            report.errors.append(f"missing meta.yaml: {meta_path}")
            continue

        meta = _load_yaml(meta_path, {})
        if "viz" not in meta:
            report.warnings.append(f"missing meta.viz block: {meta_path}")

    for dataset_key in sorted(discovered):
        resolution, category = dataset_key.split("/", 1)
        manifest_entry = manifest_categories.get(category)
        if manifest_entry is None:
            report.errors.append(f"dataset not declared in manifest: {dataset_key}")
            continue
        if resolution not in manifest_entry.get("resolutions", []):
            report.errors.append(f"dataset resolution not declared in manifest: {dataset_key}")
        if manifest_entry.get("publication_state", "unpublished") != "published":
            report.errors.append(
                f"dataset exists for manifest category not marked published: {dataset_key}"
            )
        if dataset_key not in registry_features:
            report.errors.append(f"discovered dataset missing registry.features entry: {dataset_key}")

    report.info.append(f"manifest categories: {len(manifest_categories)}")
    report.info.append(f"published manifest categories: {len(published_manifest_set)}")
    report.info.append(f"registry categories: {len(registry_categories)}")
    report.info.append(f"discovered datasets: {len(discovered)}")
    return report


def _write_meta_for_dataset(
    *,
    db_root: Path,
    dataset_key: str,
    description: str,
    created_by: str,
) -> Path:
    features_root = _features_root(db_root)
    data_path = _resolve_dataset_path(features_root, dataset_key)
    resolution, category = dataset_key.split("/", 1)
    meta = _build_meta(
        data_path=data_path,
        resolution=resolution,
        category=category,
        description=description,
        created_by=created_by,
    )
    meta_path = delta_read.meta_path(data_path)
    _save_yaml(meta_path, meta)
    return meta_path


def _merge_meta_viz_if_needed(data_path: Path) -> bool:
    meta_path = delta_read.meta_path(data_path)
    meta = _load_yaml(meta_path, {})
    if not data_path.exists():
        return False

    schema = delta_read.lake_schema(data_path)
    changed = False

    if "schema" not in meta:
        meta["schema"] = {
            "timestamp_col": "timestamp",
            "asset_col": "asset",
            "columns": _schema_columns(schema),
        }
        changed = True
    elif "columns" not in meta["schema"]:
        meta["schema"]["columns"] = _schema_columns(schema)
        changed = True

    if "viz" not in meta:
        meta["viz"] = _default_viz_config(schema)
        changed = True

    if changed:
        _save_yaml(meta_path, meta)
    return changed


def _find_latest_version_dir(category_dir: Path) -> Path | None:
    version_dirs = sorted(
        [
            child
            for child in category_dir.iterdir()
            if child.is_dir() and child.name.startswith("v") and child.name[1:].isdigit()
        ],
        key=lambda child: int(child.name[1:]),
    )
    return version_dirs[-1] if version_dirs else None


def migrate_feature_catalog(
    db_root: Path = QUANT_DB_ROOT,
    *,
    hard_cutover: bool = False,
    created_by: str = "feature_catalog_migration",
) -> FeatureMigrationResult:
    if not hard_cutover:
        raise ValueError("hard_cutover must be True to execute migration")

    result = FeatureMigrationResult()
    features_root = _features_root(db_root)
    manifest = load_features_manifest(db_root)
    manifest_entries = manifest.get("features", {})

    if not features_root.exists():
        features_root.mkdir(parents=True, exist_ok=True)

    for resolution_dir in sorted(child for child in features_root.iterdir() if child.is_dir()):
        category_dirs = sorted([path for path in resolution_dir.rglob("*") if path.is_dir()])
        for category_dir in category_dirs:
            if not category_dir.exists():
                continue
            latest_dir = _find_latest_version_dir(category_dir)
            if latest_dir is None:
                continue

            src_data = latest_dir / "data.parquet"
            src_meta = latest_dir / "meta.yaml"
            if not src_data.exists():
                continue

            dst_data = category_dir / "data.parquet"
            dst_meta = category_dir / "meta.yaml"
            if dst_data.exists():
                dst_data.unlink()
                result.removed.append(str(dst_data))
            shutil.move(str(src_data), str(dst_data))
            result.moved.append(f"{src_data} -> {dst_data}")

            if src_meta.exists():
                if dst_meta.exists():
                    dst_meta.unlink()
                    result.removed.append(str(dst_meta))
                shutil.move(str(src_meta), str(dst_meta))
                result.moved.append(f"{src_meta} -> {dst_meta}")

            for stale in sorted(
                [
                    child
                    for child in category_dir.iterdir()
                    if child.is_dir() and child.name.startswith("v") and child.name[1:].isdigit()
                ],
                reverse=True,
            ):
                shutil.rmtree(stale)
                result.removed.append(str(stale))

            latest_link = category_dir / "latest"
            if latest_link.exists() or latest_link.is_symlink():
                latest_link.unlink()
                result.removed.append(str(latest_link))

    discovered = discover_feature_datasets(db_root)
    registry = _build_registry(manifest, discovered, db_root=db_root)
    registry_path = _registry_path(db_root)
    _save_yaml(registry_path, registry)
    result.registry_path = registry_path

    for dataset_key, data_path in discovered.items():
        meta_path = delta_read.meta_path(data_path)
        _, category = dataset_key.split("/", 1)
        description = manifest_entries.get(category, {}).get("description", category)
        if not meta_path.exists():
            written = _write_meta_for_dataset(
                db_root=db_root,
                dataset_key=dataset_key,
                description=description,
                created_by=created_by,
            )
            result.meta_updated.append(str(written))
            continue
        if _merge_meta_viz_if_needed(data_path):
            result.meta_updated.append(str(meta_path))

    return result


def ensure_feature_meta_viz(db_root: Path = QUANT_DB_ROOT) -> list[str]:
    changed: list[str] = []
    discovered = discover_feature_datasets(db_root)
    for data_path in discovered.values():
        meta_path = delta_read.meta_path(data_path)
        if meta_path.exists() and _merge_meta_viz_if_needed(data_path):
            changed.append(str(meta_path))
    return changed


def load_feature_store_categories(db_root: Path = QUANT_DB_ROOT) -> dict[str, list[str]]:
    store = FeatureStore()
    by_resolution: dict[str, list[str]] = {}
    for resolution in store.list_resolutions():
        by_resolution[resolution] = store.list_categories(resolution)
    return by_resolution
