"""Scoped dataset browsing, markdown, stats, and overview helpers.

A Delta table directory lists and counts as one parquet dataset (size and update time from its
log); its ``_delta_log`` and ``_qf`` internals are hidden.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import yaml
from data.platform.storage import delta_read
from fastapi import HTTPException

from .dataset_index import get_parquet_index

Scope = Literal["data", "features"]

_MAX_OVERVIEW_DEPTH = 3


def get_scope_root(db_root: Path, scope: Scope) -> Path:
    return db_root / scope


def get_file_info(path: Path) -> dict[str, Any]:
    """Get info about a file or directory."""
    if delta_read.is_delta_dir(path):
        size, updated = _table_size_and_mtime(path)
        return {"name": path.name, "is_dir": False, "size": size, "modified": updated, "type": "parquet"}
    stat = path.stat()
    info = {
        "name": path.name,
        "is_dir": path.is_dir(),
        "size": stat.st_size if not path.is_dir() else None,
        "modified": stat.st_mtime,
    }

    suffix = path.suffix.lower()

    if suffix == ".parquet" and path.is_file():
        info["type"] = "parquet"
    elif suffix in {".md", ".markdown"} and path.is_file():
        info["type"] = "markdown"
    elif suffix in {".yaml", ".yml"} and path.is_file():
        info["type"] = "yaml"
    elif suffix == ".json" and path.is_file():
        info["type"] = "json"
    else:
        info["type"] = "dir" if path.is_dir() else "file"

    return info


def list_directory(db_root: Path, scope: Scope, path: str = "") -> dict[str, Any]:
    scope_root = get_scope_root(db_root, scope)
    if not scope_root.exists():
        raise HTTPException(status_code=404, detail=f"{scope.title()} root not found")

    target = _resolve_scoped_path(scope_root, path)
    if not target.is_dir():
        raise HTTPException(status_code=400, detail=f"Path '{path}' is not a directory")

    return {
        "path": path.strip("/"),
        "items": [
            get_file_info(item)
            for item in sorted(target.iterdir())
            if not item.name.startswith(".")
            and item.name not in delta_read.INTERNAL_DIRS
            and not _hidden_browser_file(scope, item)
        ],
    }


def preview_markdown(db_root: Path, scope: Scope, path: str) -> dict[str, Any]:
    scope_root = get_scope_root(db_root, scope)
    if not scope_root.exists():
        raise HTTPException(status_code=404, detail=f"{scope.title()} root not found")

    target = _resolve_scoped_path(scope_root, path)
    if target.suffix.lower() not in {".md", ".markdown"}:
        raise HTTPException(status_code=400, detail="Only markdown files can be previewed")

    content = target.read_text(encoding="utf-8", errors="replace")
    return {
        "path": path,
        "bytes": target.stat().st_size,
        "lines": len(content.splitlines()),
        "content": content,
    }


def preview_structured_file(db_root: Path, scope: Scope, path: str) -> dict[str, Any]:
    scope_root = get_scope_root(db_root, scope)
    if not scope_root.exists():
        raise HTTPException(status_code=404, detail=f"{scope.title()} root not found")

    target = _resolve_scoped_path(scope_root, path)
    suffix = target.suffix.lower()
    if suffix not in {".json", ".yaml", ".yml"}:
        raise HTTPException(status_code=400, detail="Only JSON and YAML files can be previewed")

    raw = target.read_text(encoding="utf-8", errors="replace")
    try:
        content = json.loads(raw) if suffix == ".json" else yaml.safe_load(raw)
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise HTTPException(status_code=400, detail=f"Could not parse structured file: {exc}") from exc
    return {
        "path": path,
        "bytes": target.stat().st_size,
        "file_type": suffix.lstrip("."),
        "content": content,
    }


def compute_scope_stats(db_root: Path, scope: Scope) -> dict[str, Any]:
    stats = {
        "parquet_files": 0,
        "total_size_mb": 0.0,
        "directories": {},
    }
    # An empty lake (scope root not created yet) is a valid state: report zeros.
    if not get_scope_root(db_root, scope).exists():
        return stats

    for entry in get_parquet_index(db_root, scope):
        stats["parquet_files"] += 1
        stats["total_size_mb"] += entry.size_bytes / (1024 * 1024)

        relative = entry.relative_path
        top_dir = relative.parts[0] if relative.parts else "root"
        stats["directories"][top_dir] = stats["directories"].get(top_dir, 0) + 1

    stats["total_size_mb"] = round(stats["total_size_mb"], 2)
    return stats


def compute_scope_overview(db_root: Path, scope: Scope) -> dict[str, Any]:
    scope_root = get_scope_root(db_root, scope)
    if not scope_root.exists():
        raise HTTPException(status_code=404, detail=f"{scope.title()} root not found")

    root_node = _summarize_directory(scope_root, scope_root, depth=0, max_depth=_MAX_OVERVIEW_DEPTH)
    branches = [
        {
            "name": child["name"],
            "path": child["path"],
            "kind": child["kind"],
            "parquet_files": child["parquet_files"],
            "size_mb": child["size_mb"],
            "updated_at": child["updated_at"],
            "children": child["children"],
        }
        for child in root_node["children"]
    ]

    featured_surfaces: list[dict[str, Any]] = []
    for branch in branches:
        candidates = sorted(
            _collect_featured_candidates(branch, depth=1),
            key=lambda node: (node["size_mb"], node["parquet_files"], len(node["path"].split("/"))),
            reverse=True,
        )
        featured_surfaces.extend(candidates[:3])

    return {
        "summary": {
            "parquet_files": root_node["parquet_files"],
            "total_size_mb": root_node["size_mb"],
            "updated_at": root_node["updated_at"],
        },
        "branches": branches,
        "tree": branches,
        "featured_surfaces": featured_surfaces,
    }


def _resolve_scoped_path(scope_root: Path, path: str) -> Path:
    target = scope_root / path.strip("/")
    try:
        target.resolve().relative_to(scope_root.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Access denied") from exc

    if not target.exists():
        raise HTTPException(status_code=404, detail=f"Path '{path}' not found")

    return target


def _hidden_browser_file(scope: Scope, path: Path) -> bool:
    return (
        scope == "features" and path.is_file() and path.name.startswith("analysis_") and path.suffix.lower() == ".png"
    )


def _table_size_and_mtime(path: Path) -> tuple[int, float | None]:
    """Live bytes and last commit time (epoch seconds) of a Delta table."""
    from data.platform.storage import delta_tables as dtab

    ref = delta_read.path_ref(path)
    committed = dtab.table_commit_time(ref)
    return dtab.table_stats(ref).bytes, committed.timestamp() if committed is not None else None


def _summarize_directory(
    path: Path,
    scope_root: Path,
    *,
    depth: int,
    max_depth: int,
) -> dict[str, Any]:
    relative_path = "" if path == scope_root else str(path.relative_to(scope_root))
    direct_parquet_files = list(path.glob("*.parquet"))

    if depth >= max_depth or delta_read.is_delta_dir(path):
        files, tables = delta_read.walk_lake(path)
        stats = [(file.stat().st_size, file.stat().st_mtime) for file in files]
        stats += [_table_size_and_mtime(table) for table in tables]
        parquet_files = len(stats)
        size_mb = sum(size for size, _ in stats) / (1024 * 1024)
        updated_at = _iso_mtime(max((mtime for _, mtime in stats if mtime is not None), default=None))
        children: list[dict[str, Any]] = []
    else:
        child_nodes = [
            _summarize_directory(child, scope_root, depth=depth + 1, max_depth=max_depth)
            for child in sorted(path.iterdir())
            if child.is_dir() and not child.name.startswith(".")
        ]
        stats = [(stat.st_size, stat.st_mtime) for stat in (file.stat() for file in direct_parquet_files)]
        parquet_files = len(stats) + sum(child["parquet_files"] for child in child_nodes)
        size_mb = sum(size for size, _ in stats) / (1024 * 1024) + sum(child["size_mb"] for child in child_nodes)
        # UTC ISO stamps share one format, so the string max is the newest.
        stamps = [_iso_mtime(mtime) for _, mtime in stats] + [child["updated_at"] for child in child_nodes]
        updated_at = max((stamp for stamp in stamps if stamp), default=None)
        children = child_nodes

    kind = "root" if depth == 0 else "branch" if depth == 1 else "directory"

    return {
        "name": path.name,
        "path": relative_path,
        "kind": kind,
        "parquet_files": parquet_files,
        "size_mb": round(size_mb, 2),
        "updated_at": updated_at,
        "children": children,
    }


def _iso_mtime(mtime: float | None) -> str | None:
    """File mtime as a second-precision UTC ISO stamp, or None."""
    if mtime is None:
        return None
    return datetime.fromtimestamp(mtime, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _collect_featured_candidates(node: dict[str, Any], *, depth: int) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    if depth >= 2 and node["parquet_files"] > 0:
        candidates.append(
            {
                "name": node["name"],
                "path": node["path"],
                "parquet_files": node["parquet_files"],
                "size_mb": node["size_mb"],
                "kind": node["kind"],
            }
        )

    for child in node.get("children", []):
        candidates.extend(_collect_featured_candidates(child, depth=depth + 1))

    return candidates
