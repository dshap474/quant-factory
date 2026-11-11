"""Read-only family/preset overview of the actual published feature snapshot.

USAGE: ``feature_overview(db_root, "1d/my/category/data.parquet")``.
"""

from __future__ import annotations

import hashlib
import json
import os
from contextlib import nullcontext, suppress
from functools import lru_cache
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock
from typing import Any, Callable

import yaml
from data.platform.storage import delta_read
from data.query import get_parquet_metadata, resolve_parquet_path
from fastapi import HTTPException
from features.api import list_feature_presets

from .dataset_profile_common import column_blocks
from .duck import cursor
from .parquet import _quote_ident, source_sql
from .parquet import fingerprint as fingerprint_of

# --------------------------------------------------------------------------- #
# Bounded projections and snapshot-keyed diagnostics
# --------------------------------------------------------------------------- #

# Batches keep a wide minute panel from consuming tens of GiB. Independent
# snapshots may profile concurrently; duplicate requests share one computation.
_PROFILE_LOCKS = tuple(Lock() for _ in range(8))

# Reports an asset panel's cross-sectional IC status; an installed extension that serves the IC registers it.
AssetIcStatus = Callable[[Path, Path], str]
_asset_ic_status: AssetIcStatus | None = None


def register_asset_ic_status(status: AssetIcStatus) -> None:
    """Install the reader behind ``analysis.ic`` for asset panels; without one they report ``missing``."""
    global _asset_ic_status
    _asset_ic_status = status


def _cache_path(target: Path) -> Path:
    cache_home = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    key = hashlib.sha256(str(target).encode()).hexdigest()
    return cache_home / "quant-factory" / "feature-overview" / f"{key}.json"


def _read_snapshot_cache(target: Path, fingerprint: tuple[int, int]) -> dict[str, Any] | None:
    try:
        cached = json.loads(_cache_path(target).read_text())
        if cached["version"] == 1 and cached["fingerprint"] == list(fingerprint):
            snapshot = cached["snapshot"]
            required = ("rows", "assets", "start", "end", "keys", "columns", "stats", "months")
            if isinstance(snapshot, dict) and all(key in snapshot for key in required):
                return snapshot
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def _write_snapshot_cache(target: Path, fingerprint: tuple[int, int], snapshot: dict[str, Any]) -> None:
    # Derived cache only, outside the canonical lake. Failure leaves reads usable.
    temporary = None
    try:
        destination = _cache_path(target)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(mode="w", dir=destination.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump({"version": 1, "fingerprint": fingerprint, "snapshot": snapshot}, stream)
        temporary.replace(destination)
    except OSError:
        pass
    finally:
        if temporary is not None:
            with suppress(OSError):
                temporary.unlink(missing_ok=True)


def _month_key(value: Any) -> str:
    if hasattr(value, "hour"):
        return str(value.replace(day=1, hour=0, minute=0, second=0, microsecond=0))
    return str(value.replace(day=1))


@lru_cache(maxsize=8)
def _snapshot_stats(db_root: Path, path: str, fingerprint: tuple[int, int], diagnostics: bool = True) -> dict[str, Any]:
    target = resolve_parquet_path(scope="features", path=path, db_root=db_root)
    if diagnostics:
        cached = _read_snapshot_cache(target, fingerprint)
        if cached is not None:
            if fingerprint_of(target) != fingerprint:
                raise HTTPException(409, "The feature snapshot changed during profiling; refresh to retry")
            return cached
    metadata = get_parquet_metadata(scope="features", path=path, db_root=db_root)
    columns = [column.name for column in metadata.columns
               if column.name not in {"timestamp", "asset"}
               and any(kind in column.dtype.lower() for kind in ("float", "int", "double", "decimal"))]
    names = {column.name for column in metadata.columns}
    if "timestamp" not in names:
        raise HTTPException(422, "A family overview requires a timestamp column")
    keys = ["timestamp", *(["asset"] if "asset" in names else [])]
    source, delta = source_sql(target)
    assets_sql = 'count(DISTINCT "asset")' if "asset" in names else "1"
    monthly: list[tuple[Any, ...]] = []
    with cursor(delta=delta) as conn:
        timestamp_type = conn.execute(f'SELECT typeof("timestamp") FROM {source} LIMIT 1').fetchone()
        if timestamp_type and not timestamp_type[0].startswith(("TIMESTAMP", "DATE")):
            raise HTTPException(422, "A family overview requires temporal timestamps")
        assets, start, end = conn.execute(
            f'SELECT {assets_sql}, min("timestamp"), max("timestamp") FROM {source} WHERE "timestamp" IS NOT NULL'
        ).fetchone()
        # Project each batch at the scan: never decompress the whole wide panel
        # at once. Identical monthly groups allow exact horizontal assembly.
        for offset in range(0, len(columns), 32) if diagnostics else ():
            aggregates = []
            for column in columns[offset:offset + 32]:
                value = f"CAST({_quote_ident(column)} AS DOUBLE)"
                aggregates += [f"count({_quote_ident(column)})", f"count_if(isfinite({value}))",
                               f"min(CASE WHEN isfinite({value}) THEN {value} END)",
                               f"max(CASE WHEN isfinite({value}) THEN {value} END)",
                               f'max(CASE WHEN isfinite({value}) THEN "timestamp" END)']
            batch = conn.execute(
                f'SELECT min("timestamp"), count(*), {assets_sql}, {", ".join(aggregates)} FROM {source} '
                "GROUP BY date_trunc('month', \"timestamp\") ORDER BY 1"
            ).fetchall()
            monthly = [(*row, *extra[3:]) for row, extra in zip(monthly, batch, strict=True)] if offset else batch
    counts = {_month_key(row[0]): {"rows": row[1], "assets": row[2]} for row in monthly if row[0] is not None}
    stats: dict[str, Any] = {}
    for index, column in enumerate(columns if diagnostics else []):
        offset = 3 + 5 * index
        non_null = finite = 0
        low = high = latest = None
        months: dict[str, int] = {}
        for row in monthly:
            first, (column_non_null, column_finite, column_min, column_max, column_latest) = row[0], row[offset:offset + 5]
            column_finite = column_finite or 0
            non_null += column_non_null or 0
            finite += column_finite
            if column_finite:
                low = column_min if low is None else min(low, column_min)
                high = column_max if high is None else max(high, column_max)
            if first is None:
                continue
            if column_finite:
                latest = column_latest if latest is None else max(latest, column_latest)
            month = _month_key(first)
            months[month] = months.get(month, 0) + column_finite
        stats[column] = {
            "finite": finite, "nulls": metadata.total_rows - non_null,
            "invalid": non_null - finite,
            "constant": finite > 0 and low == high,
            "latest": str(latest) if latest is not None else None,
            "months": months,
        }
    if fingerprint_of(target) != fingerprint:
        raise HTTPException(409, "The feature snapshot changed during profiling; refresh to retry")
    snapshot = {
        "rows": metadata.total_rows, "assets": assets if start is not None else 0,
        "start": str(start) if start is not None else None,
        "end": str(end) if end is not None else None,
        "keys": keys, "columns": columns, "stats": stats, "months": counts,
    }
    if diagnostics:
        _write_snapshot_cache(target, fingerprint, snapshot)
    return snapshot


def _summary(columns: list[str], snapshot: dict[str, Any]) -> dict[str, Any]:
    stats = [snapshot["stats"][column] for column in columns]
    cells = snapshot["rows"] * len(columns)
    return {
        "features": len(columns),
        "coverage": sum(item["finite"] for item in stats) / cells if cells else None,
        "null_cells": sum(item["nulls"] for item in stats),
        "invalid_cells": sum(item["invalid"] for item in stats),
        "empty_features": sum(item["finite"] == 0 for item in stats),
        "constant_features": sum(item["constant"] for item in stats),
    }


def _coverage(columns: list[str], snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    return [{
        "timestamp": month[:10], "assets": row["assets"], "rows": row["rows"],
        "coverage": sum(snapshot["stats"][column]["months"].get(month, 0) for column in columns)
        / (row["rows"] * len(columns)) if row["rows"] and columns else None,
    } for month, row in snapshot["months"].items()]


def _blocks(path: str, selected: list[str], snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    declared = column_blocks("features", path)
    blocks = []
    for item in declared.counts(selected):
        block = item["id"]
        columns = [column for column in selected if declared.of(column) == block]
        blocks.append({"id": block, "label": item["label"],
                       "summary": _summary(columns, snapshot), "coverage": _coverage(columns, snapshot),
                       "latest": max((snapshot["stats"][column]["latest"] or "" for column in columns), default="") or None})
    return blocks


# --------------------------------------------------------------------------- #
# Family overview
# --------------------------------------------------------------------------- #


def feature_overview(db_root: Path, path: str, *, diagnostics: bool = True) -> dict[str, Any]:
    target = resolve_parquet_path(scope="features", path=path, db_root=db_root)
    parts = Path(path).parts
    if len(parts) < 3 or parts[-1] != "data.parquet":
        raise HTTPException(422, "Select a canonical feature panel")
    category = "/".join(parts[1:-1])
    fingerprint = fingerprint_of(target)
    with _PROFILE_LOCKS[hash(target) % len(_PROFILE_LOCKS)] if diagnostics else nullcontext():
        snapshot = _snapshot_stats(db_root, path, fingerprint, diagnostics)
    meta_path = delta_read.meta_path(target)
    directory = delta_read.analysis_dir(target, db_root / "features")
    meta = yaml.load(meta_path.read_text(), Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader)) if meta_path.exists() else {}
    meta = meta if isinstance(meta, dict) else {}
    # The full panel is the family's built-in default, not a preset file: it is the published snapshot itself.
    definitions = [{"name": "full", "description": "Full panel: every feature in the published snapshot",
                    "full": True, "columns": None, "blocks": [], "parameters": {}}]
    definitions += [{**item, "full": False} for item in list_feature_presets(category) if item["resolution"] == parts[0]]
    presets = []
    for definition in definitions:
        requested = definition["columns"]
        missing = sorted(set(requested or []) - set(snapshot["columns"]))
        available = definition["full"] or (bool(requested) and not missing)
        columns = snapshot["columns"] if definition["full"] else list(dict.fromkeys(requested or []))
        presets.append({
            "name": definition["name"], "description": definition["description"],
            "kind": "full" if definition["full"] else "subset" if requested else "configuration",
            "available": available, "missing_columns": missing,
            "definition_changes": [],
            "columns": columns if available else [],
            "declared_features": len(requested) if requested else None,
            "summary": _summary(columns, snapshot) if available and diagnostics else None,
            "coverage": _coverage(columns, snapshot) if available and diagnostics else [],
            "blocks": _blocks(path, columns, snapshot) if available and diagnostics else [],
            "configured_blocks": definition["blocks"],
        })
    return {
        "path": path, "category": category,
        "build": {"id": f"{fingerprint[0]:x}-{fingerprint[1]:x}", "published_at": str(meta.get("created_at", "")) or None,
                  "rows": snapshot["rows"], "assets": snapshot["assets"], "start": snapshot["start"],
                  "end": snapshot["end"], "features": len(snapshot["columns"]), "keys": snapshot["keys"]},
        "default_preset": "full",
        "presets": presets,
        "analysis": {
            "correlation": "unverified" if (directory / "analysis_cluster_heatmap.parquet").exists() else "missing",
            # Asset panels carry cross-sectional rank IC, verified against this snapshot's build id.
            "ic": (_asset_ic_status(db_root, target) if _asset_ic_status else "missing") if "asset" in snapshot["keys"]
            else "unverified" if (directory / "analysis_horizon_ic_matrix.parquet").exists() else "missing",
        },
    }

