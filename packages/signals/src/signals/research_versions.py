"""Discover immutable signal research attempts and canonical lifecycle versions.

USAGE::
    versions = discover_signal_research_versions(db_root)
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports and constants
# --------------------------------------------------------------------------- #
import contextlib
import json
import re
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .registry import SIGNALS_ROOT
from .research_surface import load_research_surface

EXTENSIONS_ROOT = SIGNALS_ROOT / "extensions"
FAMILIES_ROOT = EXTENSIONS_ROOT / "lib"
_VERSION_PATTERN = re.compile(r"^v[0-9]{3}$")
_RUN_TIMESTAMP_PATTERN = re.compile(r"(?P<stamp>[0-9]{8}T[0-9]{6}(?:[0-9]{6})?Z)")


# --------------------------------------------------------------------------- #
# Sealed attempt discovery
# --------------------------------------------------------------------------- #


def _read_object(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _run_timestamp(run_id: str) -> str | None:
    match = _RUN_TIMESTAMP_PATTERN.search(run_id)
    if match is None:
        return None
    stamp = match.group("stamp")
    date_format = "%Y%m%dT%H%M%S%fZ" if len(stamp) == 22 else "%Y%m%dT%H%M%SZ"
    try:
        value = datetime.strptime(stamp, date_format).replace(tzinfo=UTC)
    except ValueError:
        return None
    return value.isoformat().replace("+00:00", "Z")


def _not_tested(run_root: Path) -> dict[str, Any] | None:
    payload = _read_object(run_root / "NOT_TESTED.json")
    if payload is None:
        return None
    status = payload.get("classification") or payload.get("status")
    normalized = str(status).lower().replace(" ", "_") if isinstance(status, str) else ""
    return payload if normalized == "not_tested" else None


def _latest_research_attempt(version_root: Path) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    for experiment_root in sorted(path for path in version_root.iterdir() if path.is_dir()):
        if experiment_root.name.startswith("_"):
            continue
        for run_root in sorted(path for path in experiment_root.iterdir() if path.is_dir()):
            if run_root.name.startswith("_"):
                continue
            manifest = _read_object(run_root / "manifest.json")
            if manifest is None:
                continue
            run_id = manifest.get("run_id")
            if not isinstance(run_id, str) or not run_id:
                continue
            experiment = manifest.get("experiment")
            if not isinstance(experiment, str) or not experiment:
                experiment = experiment_root.name

            disposition = _not_tested(run_root)
            recorded_at = None
            status = None
            reason = None
            if disposition is not None:
                raw_recorded_at = disposition.get("recorded_at") or disposition.get("detected_at_utc")
                recorded_at = raw_recorded_at if isinstance(raw_recorded_at, str) else None
                raw_status = disposition.get("classification") or disposition.get("status")
                status = raw_status if isinstance(raw_status, str) else None
                raw_reason = disposition.get("reason") or disposition.get("error")
                reason = raw_reason if isinstance(raw_reason, str) else None

            observed_at = recorded_at or _run_timestamp(run_id)
            attempts.append(
                {
                    "ordering": (observed_at or "", run_id),
                    "run_id": run_id,
                    "experiment": experiment,
                    "recorded_at": observed_at,
                    "status": status,
                    "reason": reason,
                }
            )

    if not attempts:
        return {"count": 0}
    latest = max(attempts, key=lambda attempt: attempt["ordering"])
    return {"count": len(attempts), **latest}


# --------------------------------------------------------------------------- #
# Lifecycle merge
# --------------------------------------------------------------------------- #


def discover_signal_research_versions(
    db_root: Path,
    families_root: Path | None = None,
) -> list[dict[str, Any]]:
    """Merge persisted attempts with canonical ``VERSION.toml`` lifecycle records."""
    research_root = Path(db_root) / "research" / "signals"
    library_root = families_root or FAMILIES_ROOT
    family_names = (
        {path.name for path in research_root.iterdir() if path.is_dir() and not path.name.startswith("_")}
        if research_root.exists()
        else set()
    )
    if library_root.exists():
        family_names.update(
            path.name
            for path in library_root.iterdir()
            if path.is_dir()
            and not path.name.startswith("_")
            and path.name != "example"
            and any((path / "optimization").glob("**/VERSION.toml"))
        )

    discovered: list[dict[str, Any]] = []
    for family in sorted(family_names):
        versions: dict[str, dict[str, Any]] = {}
        family_research_root = research_root / family
        if family_research_root.exists():
            for version_root in sorted(path for path in family_research_root.iterdir() if path.is_dir()):
                if _VERSION_PATTERN.fullmatch(version_root.name) is None:
                    continue
                attempt = _latest_research_attempt(version_root)
                normalized_status = str(attempt.get("status") or "").lower().replace(" ", "_")
                invalidated = normalized_status == "not_tested"
                # A published surface is the operator's explicit selection; it wins over recency.
                surface = None
                with contextlib.suppress(OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
                    surface = load_research_surface(db_root, family, version_root.name)
                if surface is not None:
                    attempt = {
                        **attempt,
                        "run_id": surface["run_id"],
                        "experiment": surface["experiment"],
                        "recorded_at": _run_timestamp(surface["run_id"]) or attempt.get("recorded_at"),
                    }
                versions[version_root.name] = {
                    "signal_family": family,
                    "memory_version": version_root.name,
                    "total_runs": int(attempt.get("count") or 0),
                    "run_count": int(attempt.get("count") or 0),
                    "latest_run": attempt.get("recorded_at"),
                    "state": "invalidated" if invalidated else "candidate",
                    "display_state": "invalidated" if invalidated else "candidate",
                    "source": "research",
                    "selected_run_id": attempt.get("run_id"),
                    "experiment": attempt.get("experiment"),
                    "has_surface": surface is not None,
                    "surface_state": surface["state"] if surface is not None else None,
                    "lifecycle_phase": None,
                    "lifecycle_status": normalized_status or None,
                    "invalidation_reason": attempt.get("reason"),
                }

        optimization_root = library_root / family / "optimization"
        if optimization_root.exists():
            for version_path in sorted(optimization_root.glob("**/VERSION.toml")):
                memory_version = version_path.parent.name
                if _VERSION_PATTERN.fullmatch(memory_version) is None:
                    continue
                try:
                    payload = tomllib.loads(version_path.read_text(encoding="utf-8"))
                except (OSError, tomllib.TOMLDecodeError):
                    continue
                phase = payload.get("phase")
                status = payload.get("status")
                if (
                    payload.get("version") != int(memory_version[1:])
                    or not isinstance(phase, str)
                    or not phase
                    or not isinstance(status, str)
                    or not status
                ):
                    continue
                invalidated = status == "not_tested"
                row = versions.setdefault(
                    memory_version,
                    {
                        "signal_family": family,
                        "memory_version": memory_version,
                        "total_runs": 0,
                        "run_count": 0,
                        "latest_run": None,
                        "source": "research",
                        "selected_run_id": None,
                        "experiment": None,
                        "has_surface": False,
                        "surface_state": None,
                        "invalidation_reason": None,
                    },
                )
                row.update(
                    {
                        "state": "invalidated" if invalidated else "candidate",
                        "display_state": "invalidated" if invalidated else "candidate",
                        "lifecycle_phase": phase,
                        "lifecycle_status": status,
                    }
                )
        discovered.extend(versions.values())
    return sorted(discovered, key=lambda row: (row["signal_family"], row["memory_version"]))
