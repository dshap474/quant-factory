"""Package-owned metadata writer for raw and derived parquet datasets.

The helper writes a compact `meta.yaml` beside a dataset root after a family
writer has successfully produced parquet files. It records lineage and cheap
parquet-footer schema stats without reading full datasets or mutating parquet.

USAGE: call ``write_dataset_metadata(...)`` after canonical Parquet writes;
pass ``metadata=...`` only for source-specific snapshot context.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
import yaml

from data.platform.storage.parquet_runtime import refuse_delta_target

# --------------------------------------------------------------------------- #
# Metadata writer
# --------------------------------------------------------------------------- #

def write_dataset_metadata(
    dataset_root: Path,
    *,
    layer: str,
    family: str,
    resolution: str | None,
    dataset_id: str,
    kind: str,
    source: str,
    implementation_path: str,
    written_paths: list[Path],
    row_counts: dict[str, int],
    description: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> Path:
    """Write package-owned `meta.yaml` for a raw/derived parquet dataset root."""

    refuse_delta_target(dataset_root)
    dataset_root.mkdir(parents=True, exist_ok=True)
    parquet_paths = sorted(path for path in written_paths if path.suffix == ".parquet" and path.exists())
    payload: dict[str, Any] = {
        "version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "owner": "packages/data",
        "layer": layer,
        "family": family,
        "resolution": resolution,
        "dataset_id": dataset_id,
        "kind": kind,
        "source": source,
        "implementation": implementation_path,
        "description": description,
        "artifacts": {
            "parquet_files": [_relative_to(path, dataset_root) for path in parquet_paths],
        },
        "stats": {
            "row_counts": dict(sorted(row_counts.items())),
            "parquet_file_count": len(parquet_paths),
        },
        "schema": {
            "tables": {
                path.stem: _parquet_table_schema(path, dataset_root)
                for path in parquet_paths
            },
        },
    }
    if metadata is not None:
        payload["metadata"] = metadata

    target = dataset_root / "meta.yaml"
    tmp = dataset_root / ".meta.yaml.tmp"
    tmp.write_text(yaml.dump(payload, Dumper=getattr(yaml, "CSafeDumper", yaml.SafeDumper), sort_keys=False), encoding="utf-8")
    tmp.replace(target)
    return target


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #

def _parquet_table_schema(path: Path, dataset_root: Path) -> dict[str, Any]:
    parquet = pq.ParquetFile(path)
    schema = parquet.schema_arrow
    return {
        "path": _relative_to(path, dataset_root),
        "rows": parquet.metadata.num_rows if parquet.metadata is not None else None,
        "columns": [
            {"name": field.name, "dtype": str(field.type)}
            for field in schema
        ],
    }


def _relative_to(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


# --------------------------------------------------------------------------- #
# Public exports
# --------------------------------------------------------------------------- #

__all__ = ["write_dataset_metadata"]
