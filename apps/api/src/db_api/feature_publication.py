"""Read-only access to the sidecars a feature publication writes beside its panel.

A published panel carries two operator-facing sidecars next to `data.parquet`:
`meta.yaml` (per-column formula, unit, dependencies, coverage, plus panel-level
as-of parameters and upstream freshness) and, for coordinator-driven families, a
machine-readable run report saying which sources updated and which did not.
Neither is parquet, so both are served here rather than through `data.query`.

USAGE:
    panel_meta(db_root, "1d/cross_sectional/example/panel/data.parquet")
    panel_run_report(db_root, "1d/cross_sectional/example/panel/data.parquet")
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports
# --------------------------------------------------------------------------- #
import json
from pathlib import Path
from typing import Any

import yaml
from data.platform.storage import delta_read
from data.query import resolve_parquet_path
from fastapi import HTTPException

# --------------------------------------------------------------------------- #
# Resolution helpers
# --------------------------------------------------------------------------- #

RUN_REPORT_FILENAMES = ("refresh_report.json", "run_report.json", "run_report.yaml")


def _panel_dir(db_root: Path, path: str) -> tuple[Path, str]:
    """Directory holding one canonical panel's sidecars (``meta.yaml``, run reports), with its category.

    That is the panel's own directory, or ``<table>/_qf`` for a Delta table.
    """
    parts = Path(path).parts
    if len(parts) < 3 or parts[-1] != "data.parquet":
        raise HTTPException(422, "Select a canonical feature panel")
    target = resolve_parquet_path(scope="features", path=path, db_root=db_root)
    return delta_read.meta_path(target).parent, "/".join(parts[1:-1])


def _load_sidecar(path: Path) -> dict[str, Any]:
    if path.suffix == ".json":
        loaded = json.loads(path.read_text(encoding="utf-8"))
    else:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, dict) else {}


def _section(meta: dict[str, Any], key: str) -> dict[str, Any]:
    value = meta.get(key)
    return value if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


def _int_or_none(value: Any) -> int | None:
    return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


# --------------------------------------------------------------------------- #
# Panel meta
# --------------------------------------------------------------------------- #


def _owed(meta: dict[str, Any]) -> dict[str, Any] | None:
    """Work the publication itself declares still owed, or None when it declares none.

    A panel published ahead of the family it belongs to says so in its own meta: the
    broad panel is stale against this variant until it is re-materialized. That admission
    is the operator's, not ours, so it is passed through rather than re-derived.
    """
    block = _section(meta, "owed")
    if not block:
        return None
    return {
        "summary": block.get("owed"),
        "reason": block.get("reason"),
        "columns_that_will_change": _string_list(block.get("columns_that_will_change")),
        "columns_that_will_be_added": _string_list(block.get("columns_that_will_be_added")),
        "columns_unchanged": _string_list(block.get("columns_unchanged")),
    }


def panel_meta(db_root: Path, path: str) -> dict[str, Any]:
    """Per-column and panel-level publication meta for one published panel."""
    directory, category = _panel_dir(db_root, path)
    meta_path = directory / "meta.yaml"
    if not meta_path.exists():
        return {
            "path": path,
            "category": category,
            "present": False,
            "columns": [],
            "freshness": [],
            "owed": None,
        }

    meta = _load_sidecar(meta_path)
    columns = []
    for name, entry in _section(meta, "columns").items():
        entry = entry if isinstance(entry, dict) else {}
        coverage = entry.get("coverage") if isinstance(entry.get("coverage"), dict) else {}
        dependencies = entry.get("dependencies")
        columns.append(
            {
                "name": name,
                "formula": entry.get("formula"),
                "unit": entry.get("unit"),
                "dependencies": [str(item) for item in dependencies] if isinstance(dependencies, list) else [],
                "non_null_rows": coverage.get("non_null_rows"),
                "first_non_null": coverage.get("first_non_null"),
                "last_non_null": coverage.get("last_non_null"),
                "by_asset": coverage.get("by_asset") if isinstance(coverage.get("by_asset"), dict) else {},
            }
        )

    freshness = [
        {
            "source": source,
            "path": entry.get("path") if isinstance(entry, dict) else None,
            "present": bool(entry.get("present")) if isinstance(entry, dict) else False,
            "captured_at": entry.get("captured_at") if isinstance(entry, dict) else None,
            "min_available": entry.get("min_available") if isinstance(entry, dict) else None,
            "max_available": entry.get("max_available") if isinstance(entry, dict) else None,
        }
        for source, entry in _section(meta, "freshness").items()
    ]

    return {
        "path": path,
        "category": category,
        "present": True,
        "name": meta.get("name"),
        "description": meta.get("description"),
        "created_at": meta.get("created_at"),
        "created_by": meta.get("created_by"),
        "columns": columns,
        "as_of": _section(meta, "as_of"),
        "scope": _section(meta, "scope"),
        "lineage": _section(meta, "lineage"),
        "freshness": freshness,
        "owed": _owed(meta),
    }


# --------------------------------------------------------------------------- #
# Run report
# --------------------------------------------------------------------------- #


def _source_row(entry: dict[str, Any]) -> dict[str, Any]:
    coverage = entry.get("coverage_after") if isinstance(entry.get("coverage_after"), dict) else {}
    outcome = entry.get("driver_outcome") if isinstance(entry.get("driver_outcome"), dict) else {}
    reason = outcome.get("skipped_reason") or outcome.get("error") or entry.get("note")
    return {
        "id": entry.get("id"),
        "required": bool(entry.get("required")),
        "stage": entry.get("stage"),
        "driver": entry.get("driver"),
        "description": entry.get("description"),
        "status": entry.get("status"),
        "rows": coverage.get("rows_scoped"),
        "coverage_start": coverage.get("min_date"),
        "coverage_end": coverage.get("max_date"),
        "duplicates_added": entry.get("duplicates_added"),
        "conflicts_added": entry.get("conflicts_added"),
        "missing_sessions": _int_or_none(entry.get("missing_session_count")),
        "rewrote_files": entry.get("rewrote_files"),
        "duration_seconds": outcome.get("duration_seconds"),
        "reason": reason,
    }


def _integrity(report: dict[str, Any], sources: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Run-wide data-integrity counters, or None when the report records none.

    A refresh that leaves trading sessions unlanded, finds raw duplicates, or records a
    publish diagnostic counter is still reported as UNCHANGED per source, so those counts are
    surfaced beside the sources instead of staying buried in the JSON. ``conflicts_added`` is
    summed alongside them but, being shown per source already, never opens the block alone. ``diagnostics`` carries
    every integer counter the producer wrote under ``publish.diagnostics``, by its own name.
    """
    publish_diagnostics = _section(_section(report, "publish"), "diagnostics")
    duplicates = _section(report, "raw_duplicates")
    gaps = {
        str(source["id"]): int(source["missing_sessions"])
        for source in sources
        if source.get("missing_sessions")
    }
    diagnostics = {
        str(key): value
        for key, value in publish_diagnostics.items()
        if isinstance(value, int) and not isinstance(value, bool)
    }
    counters = {
        "missing_session_total": sum(gaps.values()),
        "sources_with_missing_sessions": gaps,
        "conflicts_added": sum(int(source["conflicts_added"] or 0) for source in sources),
        "raw_duplicate_rows": _int_or_none(duplicates.get("raw_total")),
        "diagnostics": diagnostics,
    }
    if not diagnostics and counters["raw_duplicate_rows"] is None and not gaps:
        return None
    return counters


def panel_run_report(db_root: Path, path: str) -> dict[str, Any]:
    """Per-source refresh status recorded beside one published panel."""
    directory, category = _panel_dir(db_root, path)
    report_path = next(
        (directory / name for name in RUN_REPORT_FILENAMES if (directory / name).exists()),
        None,
    )
    if report_path is None:
        return {
            "path": path,
            "category": category,
            "present": False,
            "sources": [],
            "integrity": None,
        }

    report = _load_sidecar(report_path)
    entries = report.get("sources")
    sources = [
        _source_row(entry) for entry in (entries if isinstance(entries, list) else []) if isinstance(entry, dict)
    ]
    publish = _section(report, "publish")
    return {
        "path": path,
        "category": category,
        "present": True,
        "report_file": report_path.name,
        "generated_at": report.get("generated_at"),
        "completed_at": report.get("completed_at"),
        "mode": report.get("mode"),
        "publish": {
            "gate_open": publish.get("gate_open"),
            "gate_reason": publish.get("gate_reason"),
            "published": publish.get("published"),
            "preset": publish.get("preset"),
            "rows": publish.get("rows"),
            "columns": publish.get("columns"),
            "assets": publish.get("assets") if isinstance(publish.get("assets"), list) else [],
            "start": publish.get("start"),
            "end": publish.get("end"),
        },
        "sources": sources,
        "integrity": _integrity(report, sources),
    }
