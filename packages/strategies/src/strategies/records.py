"""Read a strategy version's records: ``VERSION.toml`` and its markdown documents.

Every version of an active family carries the same record files (AGENTS.md §5), so this
reader needs no per-family code.

USAGE:
    from strategies.records import load_version_records
    records = load_version_records("example", "v002")
    records["record"]["status"], [doc["name"] for doc in records["documents"]]

    from strategies.records import family_versions
    rows = family_versions("example")  # one lineage row per version, oldest first
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports
# --------------------------------------------------------------------------- #
import datetime as dt
import tomllib
from pathlib import Path
from typing import Any

from .paths import FAMILIES_ROOT

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

DOCUMENTS = ("SPEC.md", "HYPOTHESIS_OUTCOME.md", "REVIEW.md", "CHANGELOG.md")

# --------------------------------------------------------------------------- #
# Records
# --------------------------------------------------------------------------- #


def version_dir(family: str, version: str, *, root: Path = FAMILIES_ROOT) -> Path | None:
    """The active folder holding ``<family>/<version>/VERSION.toml``, or None."""
    for path in sorted((root / family / "optimization").glob(f"**/{version}/VERSION.toml")):
        if ".dev" not in path.parts:
            return path.parent
    return None


def load_version_records(family: str, version: str, *, root: Path = FAMILIES_ROOT) -> dict[str, Any] | None:
    """``VERSION.toml`` as JSON-safe values plus each record document present, or None."""
    folder = version_dir(family, version, root=root)
    if folder is None:
        return None
    record = tomllib.loads((folder / "VERSION.toml").read_text())
    documents = [
        {"name": name, "markdown": (folder / name).read_text()}
        for name in DOCUMENTS
        if (folder / name).is_file()
    ]
    return {
        "strategy_type": family,
        "memory_version": version,
        "path": folder.relative_to(root / family).as_posix(),
        "record": _json_safe(record),
        "documents": documents,
    }


def family_versions(family: str, *, root: Path = FAMILIES_ROOT) -> list[dict[str, Any]]:
    """One row per active version of ``family``, oldest first: the lineage and outcome fields."""
    rows = []
    for path in (root / family / "optimization").glob("**/v[0-9][0-9][0-9]/VERSION.toml"):
        if ".dev" in path.parts:
            continue
        record = _json_safe(tomllib.loads(path.read_text()))
        rows.append({
            "version": path.parent.name,
            "status": record.get("status"),
            "phase": record.get("phase"),
            "parent": record.get("parent"),
            "question": record.get("question"),
            "finding": record.get("finding"),
            "backtest_run_at": record.get("backtest_run_at"),
            "baseline_selected_at": record.get("baseline_selected_at"),
            "headline": record.get("headline"),
        })
    return sorted(rows, key=lambda row: row["version"])


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return value.isoformat()
    return value
