"""Version storage: research runs saved by the runner and operator-promoted finals.

A saved run lives at ``research/strategies/<family>/<version>/<preset>/<run_id>/``
(``decisions.parquet``, ``backtest.parquet``, ``meta.json``). Promotion copies one
chosen run into ``strategies/<family>/versions/<version>/final/`` by explicit operator
action; nothing is ever selected by metrics.

USAGE:
    runs = load_version_runs(db_root, "my-family", "v001")
    final_dir = promote_run(db_root, "my-family", "v001", run_id)
    rows = discover_strategy_versions(db_root)
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import polars as pl

from .contracts import validate_identifier, validate_memory_version

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #


def get_version_dir(db_root: Path, strategy_type: str, memory_version: str) -> Path:
    """Return the canonical (promoted) version directory."""
    validate_identifier(strategy_type, "strategy_type")
    validate_memory_version(memory_version)
    return Path(db_root) / "strategies" / strategy_type / "versions" / memory_version


def get_version_final_dir(db_root: Path, strategy_type: str, memory_version: str) -> Path:
    return get_version_dir(db_root, strategy_type, memory_version) / "final"


def get_research_version_dir(db_root: Path, strategy_type: str, memory_version: str) -> Path:
    validate_identifier(strategy_type, "strategy_type")
    validate_memory_version(memory_version)
    return Path(db_root) / "research" / "strategies" / strategy_type / memory_version


# --------------------------------------------------------------------------- #
# Saved runs
# --------------------------------------------------------------------------- #


def _saved_run_dirs(db_root: Path, strategy_type: str, memory_version: str) -> list[Path]:
    """Runner-saved run directories (all three artifacts present) for one version."""
    root = get_research_version_dir(db_root, strategy_type, memory_version)
    return sorted(
        meta.parent
        for meta in root.glob("*/*/meta.json")
        if (meta.parent / "backtest.parquet").exists() and (meta.parent / "decisions.parquet").exists()
    )


def load_version_runs(db_root: Path, strategy_type: str, memory_version: str) -> pl.DataFrame:
    """One row per saved run: identity, data range, config and scalar metrics."""
    rows = []
    for run_dir in _saved_run_dirs(db_root, strategy_type, memory_version):
        meta = json.loads((run_dir / "meta.json").read_text())
        data_range = meta.get("data_range") or {}
        metrics = {k: float(v) for k, v in (meta.get("metrics") or {}).items() if isinstance(v, (int, float))}
        rows.append({
            "run_id": run_dir.name,
            "created_at": meta.get("created_at"),
            "preset": meta.get("preset") or run_dir.parent.name,
            "config_json": json.dumps(meta.get("config", {}), sort_keys=True, default=str),
            "data_start": data_range.get("start"),
            "data_end": data_range.get("end"),
            **metrics,
        })
    if not rows:
        return pl.DataFrame(schema={"run_id": pl.Utf8, "created_at": pl.Utf8, "preset": pl.Utf8})
    return pl.DataFrame(rows, infer_schema_length=None)


# --------------------------------------------------------------------------- #
# Promotion
# --------------------------------------------------------------------------- #


def promote_run(db_root: Path, strategy_type: str, memory_version: str, run_id: str) -> Path:
    """Copy one saved research run into the version's ``final/``; never overwrites."""
    validate_identifier(run_id, "run_id")
    matches = [d for d in _saved_run_dirs(db_root, strategy_type, memory_version) if d.name == run_id]
    if len(matches) != 1:
        raise FileNotFoundError(f"Saved run '{run_id}' not found for {strategy_type}/{memory_version}")
    final_dir = get_version_final_dir(db_root, strategy_type, memory_version)
    if final_dir.exists():
        raise FileExistsError(f"{final_dir} already holds a promoted run; record a correction explicitly")
    shutil.copytree(matches[0], final_dir)
    meta = json.loads((final_dir / "meta.json").read_text())
    meta.update(selected_run_id=run_id, source_run_dir=str(matches[0]))
    (final_dir / "meta.json").write_text(json.dumps(meta, indent=2, default=str))
    return final_dir


def load_version_final_artifact(
    db_root: Path,
    strategy_type: str,
    memory_version: str,
) -> tuple[pl.DataFrame, dict[str, Any]] | None:
    """Load the promoted backtest and meta for one memory version."""
    final_dir = get_version_final_dir(db_root, strategy_type, memory_version)
    parquet_path = final_dir / "backtest.parquet"
    meta_path = final_dir / "meta.json"
    if not parquet_path.exists() or not meta_path.exists():
        return None
    return pl.read_parquet(parquet_path), json.loads(meta_path.read_text())


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #


def discover_strategy_versions(db_root: Path) -> list[dict[str, Any]]:
    """Discover promoted versions: every ``versions/<vNNN>/final/meta.json``."""
    discovered: list[dict[str, Any]] = []
    for meta_path in sorted((Path(db_root) / "strategies").glob("[!_]*/versions/v*/final/meta.json")):
        version_dir = meta_path.parents[1]
        strategy_type, memory_version = version_dir.parents[1].name, version_dir.name
        try:
            meta = json.loads(meta_path.read_text())
            total_runs = load_version_runs(db_root, strategy_type, memory_version).height
        except (OSError, ValueError):
            continue
        metrics = meta.get("metrics") or {}
        discovered.append({
            "strategy_type": strategy_type,
            "memory_version": memory_version,
            "total_runs": total_runs,
            "has_final": True,
            "best_sharpe": metrics.get("sharpe"),
            "best_return": metrics.get("total_return"),
            "final_run_id": meta.get("selected_run_id") or meta.get("run_id"),
            "latest_run": meta.get("created_at"),
        })
    return discovered
