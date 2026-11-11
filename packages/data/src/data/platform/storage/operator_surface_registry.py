"""Contracts and optional registry loading for Data operator surfaces.

USAGE: import ``OPERATOR_SCRIPTS`` or run ``uv run qf-data surface-validate``.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from typing import Literal, get_args

from data.extensions import EXTENSIONS_ROOT
from data.platform.errors import DatasetContractError

# --------------------------------------------------------------------------- #
# Contracts
# --------------------------------------------------------------------------- #

Cadence = Literal["daily", "weekly", "on_demand"]
OperatorContract = Literal["control_plane", "analysis_only", "maintenance"]
OperatorRoot = Literal["pipelines", "scripts"]
Freshness = Literal["data", "weekdays", "write"]

SUPPORTED_CADENCES = frozenset(get_args(Cadence))
SUPPORTED_OPERATOR_CONTRACTS = frozenset(get_args(OperatorContract))
SUPPORTED_OPERATOR_ROOTS = frozenset(get_args(OperatorRoot))
SUPPORTED_FRESHNESS = frozenset(get_args(Freshness))


@dataclass(frozen=True, slots=True)
class OperatorScript:
    """Supported operator wrapper metadata validated by ``surface-validate``."""

    path: str
    role: str
    example: str
    cadence: Cadence
    primary_write_surface: str
    notes: str
    contract: OperatorContract = "control_plane"
    root: OperatorRoot = "pipelines"
    refresh: str | None = None
    """Arguments for the routine ``qf-data refresh`` run; ``None`` keeps the pipeline out of it."""
    needs: tuple[str, ...] | None = None
    """Pipeline paths (registry ``path``) this refresh step must wait for. ``None`` = undeclared: wait for
    every step before it in plan order (today's sequential behavior). ``()`` = no dependencies."""
    group: str | None = None
    """Steps sharing a group never run at the same time (one provider API, one shared output)."""
    freshness: Freshness = "data"
    """How ``surface-status`` ages the surface: newest date in the data, the same skipping weekends
    (market-calendar data), or the newest write/refresh stamp (monthly or quarterly releases)."""
    keys: tuple[str, ...] = ()
    """Columns unique per row; ``surface-status`` flags duplicates in every file that has them all."""
    quality_exempt: tuple[str, ...] = ()
    """db-relative globs of files whose values are legitimately future or non-positive (schedules, WTI 2020)."""


# --------------------------------------------------------------------------- #
# Extension loading
# --------------------------------------------------------------------------- #


def _load_operator_scripts() -> tuple[OperatorScript, ...]:
    registry_path = EXTENSIONS_ROOT / "pipelines" / "_operator_surface_registry.py"
    if not registry_path.is_file():
        return ()

    spec = importlib.util.spec_from_file_location("_qf_data_operator_extensions", registry_path)
    if spec is None or spec.loader is None:
        raise DatasetContractError(f"Unable to load operator extensions from '{registry_path}'")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    entries = tuple(module.OPERATOR_SCRIPTS)

    seen: set[tuple[str, str]] = set()
    for entry in entries:
        key = (entry.root, entry.path)
        if key in seen:
            raise DatasetContractError(f"Operator script '{entry.root}/{entry.path}' is already registered")
        if entry.refresh is not None and entry.root != "pipelines":
            raise DatasetContractError(f"Operator script '{entry.root}/{entry.path}': only pipelines take a refresh")
        seen.add(key)
    _validate_refresh_dependencies(entries)
    return entries


def _validate_refresh_dependencies(entries: tuple[OperatorScript, ...]) -> None:
    """``needs``/``group`` only on refresh steps; every ``needs`` path is another refresh pipeline."""
    refreshable = {entry.path for entry in entries if entry.root == "pipelines" and entry.refresh is not None}
    for entry in entries:
        name = f"{entry.root}/{entry.path}"
        if entry.refresh is None and (entry.needs is not None or entry.group is not None):
            raise DatasetContractError(f"Operator script '{name}': needs/group require a refresh")
        if entry.needs is None:
            continue
        if not isinstance(entry.needs, tuple):
            raise DatasetContractError(f"Operator script '{name}': needs must be a tuple of pipeline paths")
        for need in entry.needs:
            if need == entry.path:
                raise DatasetContractError(f"Operator script '{name}': needs itself")
            if need not in refreshable:
                raise DatasetContractError(
                    f"Operator script '{name}': needs '{need}', which is not a registered pipeline with a refresh"
                )


OPERATOR_SCRIPTS = _load_operator_scripts()

__all__ = [
    "Cadence",
    "Freshness",
    "OPERATOR_SCRIPTS",
    "OperatorContract",
    "OperatorRoot",
    "OperatorScript",
    "SUPPORTED_CADENCES",
    "SUPPORTED_FRESHNESS",
    "SUPPORTED_OPERATOR_CONTRACTS",
    "SUPPORTED_OPERATOR_ROOTS",
]
