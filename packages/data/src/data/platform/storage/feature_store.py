"""Canonical latest-state feature storage with lineage tracking.

The FeatureStore writes exactly one realized dataset per
``resolution/category`` pair:

- ``db/features/<resolution>/<category>/data.parquet``
- ``db/features/<resolution>/<category>/meta.yaml``
- ``db/features/REGISTRY.yaml``

A loop that writes many datasets should wrap them in ``registry_batch()``: each
``write`` then queues its registry entry and the registry is loaded and saved once
when the block exits (a ~1 MB registry costs ~0.2 s per load+save).

USAGE:
    store = FeatureStore(FeatureStoreConfig(features_root=db_root / "data/derived"))
    with store.registry_batch():
        for asset, frame in frames.items():
            store.write(frame, resolution="1d", category=f"example/dataset/{asset}", force=True)

Legacy ``version=...`` arguments are accepted at the API boundary for
backwards compatibility but are ignored. The on-disk contract is
latest-state only.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import polars as pl
import yaml
from config import QUANT_DB_ROOT

from . import delta_read
from .locks import table_lock
from .parquet_runtime import write_polars_parquet_atomic, write_text_atomic

# The registry is re-read on every write; libyaml handles it about 8x faster than pure Python.
_REGISTRY_LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
_REGISTRY_DUMPER = getattr(yaml, "CDumper", yaml.Dumper)


@dataclass
class FeatureVersion:
    """Represents one canonical latest-state feature dataset."""

    resolution: str
    category: str
    path: Path
    created_at: datetime | None = None
    version: str | None = None

    @property
    def data_path(self) -> Path:
        return self.path if delta_read.is_delta_dir(self.path) else self.path / "data.parquet"

    @property
    def meta_path(self) -> Path:
        return delta_read.meta_path(self.data_path)

    def exists(self) -> bool:
        return self.data_path.exists()


@dataclass
class FeatureStoreConfig:
    """Configuration for FeatureStore."""

    db_root: Path = field(default_factory=lambda: QUANT_DB_ROOT)
    features_root: Path | None = None  # defaults to db_root / "features"; derived families use db_root / "data/derived"
    compression: str = "zstd"
    compression_level: int = 3
    require_asset_column: bool = True
    allow_metadata_feature_columns: bool = False
    row_group_size: int | None = None  # None keeps the Parquet writer's default


class FeatureStore:
    """Canonical latest-state feature store."""

    VALID_RESOLUTIONS = ("1m", "5m", "15m", "1h", "4h", "1d", "derived")
    TIMESTAMP_COL = "timestamp"
    ASSET_COL = "asset"

    def __init__(self, config: FeatureStoreConfig | None = None):
        self.config = config or FeatureStoreConfig()
        self.features_root = self.config.features_root or self.config.db_root / "features"
        self._registry_cache: dict[str, Any] | None = None
        self._registry_pending: list[dict[str, Any]] | None = None

    def _is_allowed_feature_dtype(self, dtype: pl.DataType) -> bool:
        if dtype == pl.Float64:
            return True
        if not self.config.allow_metadata_feature_columns:
            return False
        return dtype == pl.String or str(dtype).startswith("Datetime")

    def write(
        self,
        data: pl.DataFrame,
        resolution: str,
        category: str,
        version: str | None = None,
        sources: list[str] | None = None,
        description: str | None = None,
        created_by: str = "feature_pipeline",
        force: bool = False,
        extra_meta: dict[str, Any] | None = None,
    ) -> FeatureVersion:
        del version
        if resolution not in self.VALID_RESOLUTIONS:
            raise ValueError(f"Invalid resolution '{resolution}'. Must be one of {self.VALID_RESOLUTIONS}")

        errors = self._validate_data(data)
        if errors:
            raise ValueError("Data validation failed:\n" + "\n".join(f"  - {e}" for e in errors))

        dataset_dir = self.features_root / resolution / Path(category)
        data_path = dataset_dir / "data.parquet"
        meta_path = dataset_dir / "meta.yaml"

        if data_path.exists() and not force:
            raise ValueError(f"Dataset already exists at {data_path}. Use force=True (CLI: --force) to overwrite.")

        write_polars_parquet_atomic(
            data,
            data_path,
            compression=self.config.compression,
            compression_level=self.config.compression_level,
            row_group_size=self.config.row_group_size,
        )

        meta = self._generate_metadata(
            data=data,
            resolution=resolution,
            category=category,
            sources=sources,
            description=description,
            created_by=created_by,
        )
        if extra_meta:
            meta = _deep_merge_dicts(meta, extra_meta)
        write_text_atomic(yaml.dump(meta, default_flow_style=False, sort_keys=False), meta_path)

        self._update_registry(
            resolution=resolution,
            category=category,
            description=description,
            asset_column=self.config.require_asset_column,
        )

        return FeatureVersion(
            resolution=resolution,
            category=category,
            path=dataset_dir,
            created_at=datetime.now(timezone.utc),
            version=None,
        )

    def read(
        self,
        resolution: str,
        category: str,
        version: str = "latest",
        columns: list[str] | None = None,
        assets: list[str] | None = None,
        start: str | datetime | None = None,
        end: str | datetime | None = None,
    ) -> pl.DataFrame:
        del version
        data_path = self._resolve_dataset_path(resolution, category)
        if delta_read.is_delta_dir(data_path.parent):  # a Delta feature table is the category directory
            data_path = data_path.parent
        elif not data_path.exists():
            raise FileNotFoundError(f"Feature data not found at {data_path}")

        lf = delta_read.lake_scan(data_path)
        available = lf.collect_schema().names()

        if columns is not None:
            index_cols = [self.TIMESTAMP_COL]
            if self.ASSET_COL in available:
                index_cols.append(self.ASSET_COL)
            cols = index_cols + [col for col in columns if col not in (self.TIMESTAMP_COL, self.ASSET_COL)]
            cols = [col for col in cols if col in available]
            lf = lf.select(cols)

        if assets is not None and self.ASSET_COL in available:
            lf = lf.filter(pl.col(self.ASSET_COL).is_in(assets))

        if start is not None:
            if isinstance(start, str):
                start = datetime.fromisoformat(start.replace("Z", "+00:00"))
            lf = lf.filter(pl.col(self.TIMESTAMP_COL) >= start)
        if end is not None:
            if isinstance(end, str):
                end = datetime.fromisoformat(end.replace("Z", "+00:00"))
            lf = lf.filter(pl.col(self.TIMESTAMP_COL) <= end)

        return lf.collect()

    def list_resolutions(self) -> list[str]:
        if not self.features_root.exists():
            return []
        return sorted(
            child.name
            for child in self.features_root.iterdir()
            if child.is_dir() and child.name in self.VALID_RESOLUTIONS
        )

    def list_categories(self, resolution: str) -> list[str]:
        res_path = self.features_root / resolution
        if not res_path.exists():
            return []

        categories: list[str] = []
        files, tables = delta_read.walk_lake(res_path)
        for table in tables:
            rel = table.relative_to(res_path)
            if not any(part.startswith("_") for part in rel.parts):
                categories.append(rel.as_posix())
        for data_file in (file for file in files if file.name == "data.parquet"):
            rel = data_file.relative_to(res_path)
            if len(rel.parts) < 2:
                continue
            category_parts = rel.parts[:-1]
            if any(part.startswith("_") for part in category_parts):
                continue
            categories.append("/".join(category_parts))
        return sorted(set(categories))

    def get_latest_version(self, resolution: str, category: str) -> str | None:
        data_path = self._resolve_dataset_path(resolution, category)
        return "latest" if data_path.exists() else None

    def get_meta(
        self,
        resolution: str,
        category: str,
        version: str = "latest",
    ) -> dict[str, Any]:
        del version
        meta_path = _dataset_meta(self._resolve_dataset_dir(resolution, category))
        if not meta_path.exists():
            raise FileNotFoundError(f"Metadata not found at {meta_path}")
        with open(meta_path, encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {}

    def get_version(
        self,
        resolution: str,
        category: str,
        version: str = "latest",
    ) -> FeatureVersion:
        del version
        path = self._resolve_dataset_dir(resolution, category)
        meta = {}
        if _dataset_meta(path).exists():
            meta = self.get_meta(resolution, category)
        created_at = meta.get("created_at")
        return FeatureVersion(
            resolution=resolution,
            category=category,
            path=path,
            created_at=datetime.fromisoformat(created_at) if created_at else None,
            version=None,
        )

    def load_registry(self) -> dict[str, Any]:
        registry_path = self.features_root / "REGISTRY.yaml"
        if not registry_path.exists():
            return self._default_registry()
        with open(registry_path, encoding="utf-8") as handle:
            loaded = yaml.load(handle, Loader=_REGISTRY_LOADER) or self._default_registry()
        return loaded if isinstance(loaded, dict) else self._default_registry()

    def save_registry(self, registry: dict[str, Any]) -> None:
        registry_path = self.features_root / "REGISTRY.yaml"
        text = yaml.dump(registry, Dumper=_REGISTRY_DUMPER, default_flow_style=False, sort_keys=False)
        write_text_atomic(text, registry_path)
        self._registry_cache = registry

    def _resolve_dataset_dir(self, resolution: str, category: str) -> Path:
        return self.features_root / resolution / Path(category)

    def _resolve_dataset_path(self, resolution: str, category: str) -> Path:
        return self._resolve_dataset_dir(resolution, category) / "data.parquet"

    def _validate_data(self, data: pl.DataFrame) -> list[str]:
        errors: list[str] = []
        if self.TIMESTAMP_COL not in data.columns:
            errors.append(f"Missing required '{self.TIMESTAMP_COL}' column")
        elif not str(data[self.TIMESTAMP_COL].dtype).startswith("Datetime"):
            errors.append(f"Column '{self.TIMESTAMP_COL}' must be Datetime, got {data[self.TIMESTAMP_COL].dtype}")

        if self.config.require_asset_column and self.ASSET_COL not in data.columns:
            errors.append(f"Missing required '{self.ASSET_COL}' column")

        skip_cols = {self.TIMESTAMP_COL, self.ASSET_COL}
        for col in data.columns:
            if col in skip_cols:
                continue
            if not self._is_allowed_feature_dtype(data[col].dtype):
                errors.append(f"Column '{col}' must be Float64, got {data[col].dtype}")

        if self.ASSET_COL in data.columns:
            n_rows = len(data)
            n_unique = data.select([self.TIMESTAMP_COL, self.ASSET_COL]).unique().height
            if n_unique < n_rows:
                errors.append(f"Duplicate (timestamp, asset) pairs: {n_rows - n_unique} duplicates found")
        return errors

    def _generate_metadata(
        self,
        *,
        data: pl.DataFrame,
        resolution: str,
        category: str,
        sources: list[str] | None,
        description: str | None,
        created_by: str,
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        columns = [{"name": col, "dtype": str(data[col].dtype)} for col in data.columns]

        stats: dict[str, Any] = {
            "row_count": len(data),
            "column_count": len(data.columns),
        }
        if self.TIMESTAMP_COL in data.columns:
            ts = data[self.TIMESTAMP_COL]
            stats["date_range"] = {"start": str(ts.min()), "end": str(ts.max())}

        if self.ASSET_COL in data.columns:
            assets = [a for a in data[self.ASSET_COL].unique().sort().to_list() if a is not None]
            stats["assets"] = assets
            stats["asset_count"] = len(assets)
            asset_coverage: dict[str, dict[str, float | int]] = {}
            feature_cols = [c for c in data.columns if c not in {self.TIMESTAMP_COL, self.ASSET_COL}]
            for col in feature_cols:
                # Filter the asset series alone: filtering the frame copies every column per pass.
                covered = data[self.ASSET_COL].filter(data[col].is_not_null()).unique().len()
                if assets:
                    asset_coverage[col] = {
                        "count": int(covered),
                        "ratio": round(covered / len(assets), 4),
                    }
            if asset_coverage:
                stats["asset_coverage"] = asset_coverage

        null_rates: dict[str, float] = {}
        for col in data.columns:
            if col in {self.TIMESTAMP_COL, self.ASSET_COL}:
                continue
            null_count = data[col].null_count()
            if null_count > 0:
                null_rates[col] = round(null_count / len(data), 4)
        if null_rates:
            stats["null_rates"] = null_rates

        return {
            "name": category.replace("/", "_"),
            "description": description or f"{category} features at {resolution} resolution",
            "created_at": now.isoformat(),
            "created_by": created_by,
            "resolution": resolution,
            "category": category,
            "schema": {
                "timestamp_col": self.TIMESTAMP_COL,
                "asset_col": self.ASSET_COL,
                "columns": columns,
            },
            "lineage": {"sources": sources or []},
            "stats": stats,
        }

    @contextmanager
    def registry_batch(self) -> Iterator[None]:
        """Queue registry entries from every ``write`` in the block; load and save the registry once on exit.

        Entries of writes that completed are flushed even when the block raises, so the registry
        never lags data that is already on disk.
        """
        if self._registry_pending is not None:  # nested: the outer batch flushes
            yield
            return
        self._registry_pending = []
        try:
            yield
        finally:
            pending, self._registry_pending = self._registry_pending, None
            if pending:
                self._apply_registry_updates(pending)

    def _update_registry(
        self,
        *,
        resolution: str,
        category: str,
        description: str | None,
        asset_column: bool,
    ) -> None:
        update = {
            "resolution": resolution,
            "category": category,
            "description": description,
            "asset_column": asset_column,
            "now": datetime.now(timezone.utc).isoformat(),
        }
        if self._registry_pending is not None:
            self._registry_pending.append(update)
            return
        self._apply_registry_updates([update])

    def _apply_registry_updates(self, updates: list[dict[str, Any]]) -> None:
        with table_lock(_RegistryLockKey(self.config.db_root, self.features_root / "REGISTRY.yaml")):
            registry = self.load_registry()
            for update in updates:
                self._apply_registry_update(registry, **update)
            self.save_registry(registry)

    def _apply_registry_update(
        self,
        registry: dict[str, Any],
        *,
        resolution: str,
        category: str,
        description: str | None,
        asset_column: bool,
        now: str,
    ) -> None:
        registry.setdefault("categories", {})
        registry.setdefault("features", {})

        category_meta = registry["categories"].get(category, {})
        merged_resolutions = sorted(set(category_meta.get("resolutions", [])) | {resolution})
        # A category shared across resolutions keeps its own description; each
        # resolution's description lives on its feature entry, so the last
        # resolution published never relabels the others.
        shared = merged_resolutions != [resolution] and "description" in category_meta
        registry["categories"][category] = {
            "description": category_meta["description"] if shared
            else description or category_meta.get("description", f"{category} features"),
            "resolutions": merged_resolutions,
            "status": category_meta.get("status", "active"),
            "asset_column": asset_column,
        }

        feature_key = f"{resolution}/{category}"
        data_path = self._resolve_dataset_path(resolution, category)
        try:
            registry_data_path = data_path.relative_to(self.config.db_root)
        except ValueError:
            registry_data_path = data_path
        registry["features"][feature_key] = {
            "description": description or registry["categories"][category]["description"],
            "status": registry["categories"][category]["status"],
            "data_path": str(registry_data_path),
            "updated_at": now,
        }

    def _default_registry(self) -> dict[str, Any]:
        return {
            "version": 5,
            "description": "quant-factory canonical latest-state feature catalog",
            "categories": {},
            "features": {},
        }


@dataclass(frozen=True)
class _RegistryLockKey:
    """``table_lock`` target for a REGISTRY.yaml read-modify-write (``<db_root>/.locks/tables/<key>.lock``)."""

    db_root: Path
    registry: Path

    @property
    def key(self) -> str:
        try:
            return self.registry.relative_to(self.db_root).as_posix()
        except ValueError:
            return self.registry.as_posix().strip("/")


def _dataset_meta(dataset_dir: Path) -> Path:
    """A category's ``meta.yaml``: in ``_qf/`` when the category directory is a Delta table."""
    return delta_read.meta_path(dataset_dir if delta_read.is_delta_dir(dataset_dir) else dataset_dir / "data.parquet")


def _deep_merge_dicts(base: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged
