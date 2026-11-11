"""Canonical storage for the example raw bars and derived price panel.

USAGE: the family service calls ``write_frame(db_root, RAW, frame, metadata=...)``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import polars as pl
import yaml
from data.platform.storage.parquet_runtime import write_polars_parquet_atomic

# --------------------------------------------------------------------------- #
# Layout
# --------------------------------------------------------------------------- #

RESOLUTION = "1d"
DATA_FILE_NAME = "data.parquet"
META_FILE_NAME = "meta.yaml"


@dataclass(frozen=True, slots=True)
class Surface:
    layer: str
    keys: tuple[str, ...]

    def root(self, db_root: Path) -> Path:
        return db_root / "data" / self.layer / RESOLUTION / "example" / "prices"

    def data_path(self, db_root: Path) -> Path:
        return self.root(db_root) / DATA_FILE_NAME

    def meta_path(self, db_root: Path) -> Path:
        return self.root(db_root) / META_FILE_NAME


RAW = Surface(layer="raw", keys=("symbol", "timestamp"))
DERIVED = Surface(layer="derived", keys=("asset", "timestamp"))


# --------------------------------------------------------------------------- #
# Read and write
# --------------------------------------------------------------------------- #


def read_frame(db_root: Path, surface: Surface) -> pl.DataFrame | None:
    path = surface.data_path(db_root)
    return pl.read_parquet(path) if path.exists() else None


def read_meta(db_root: Path, surface: Surface) -> dict[str, Any] | None:
    path = surface.meta_path(db_root)
    return yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else None


def write_frame(
    db_root: Path, surface: Surface, frame: pl.DataFrame, *, metadata: dict[str, Any], overwrite: bool
) -> tuple[list[Path], int]:
    """Atomically merge ``frame`` on the surface keys (new rows win) and rewrite its metadata."""
    existing = None if overwrite else read_frame(db_root, surface)
    merged = frame if existing is None else pl.concat([existing, frame], how="diagonal_relaxed")
    merged = merged.unique(subset=list(surface.keys), keep="last", maintain_order=True).sort(list(surface.keys))
    parquet_path = surface.data_path(db_root)
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    write_polars_parquet_atomic(merged, parquet_path)

    payload = {**metadata, "stats": _stats(merged), "artifacts": {"parquet_files": [DATA_FILE_NAME]}}
    meta = surface.meta_path(db_root)
    temporary = meta.with_name(".meta.yaml.tmp")
    temporary.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    temporary.replace(meta)
    return [parquet_path, meta], merged.height


def _stats(frame: pl.DataFrame) -> dict[str, Any]:
    stats: dict[str, Any] = {"row_count": frame.height, "column_count": len(frame.columns)}
    if not frame.is_empty():
        stats["min_date"] = frame["timestamp"].min().date().isoformat()
        stats["max_date"] = frame["timestamp"].max().date().isoformat()
    return stats


# --------------------------------------------------------------------------- #
# Public exports
# --------------------------------------------------------------------------- #

__all__ = ["DERIVED", "RAW", "RESOLUTION", "Surface", "read_frame", "read_meta", "write_frame"]
