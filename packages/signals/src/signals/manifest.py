"""Signal catalog helpers backed by registered runner metadata.

USAGE: ``get_signal_info("family")`` returns catalog metadata and its README path.
"""

from __future__ import annotations

from typing import Any

import yaml

from signals.registry import SignalRegistry

_DEFAULT_MANIFEST = {"version": 2, "signals": {}}
_ALLOWED_STATUSES = {"active", "planned"}
_CANONICAL_PACKAGE_ROOT = "extensions/lib/"

# --------------------------------------------------------------------------- #
# Catalog readers
# --------------------------------------------------------------------------- #


def load_manifest() -> dict[str, Any]:
    """Return the catalog payload built from ``SignalRegistry.register(...)`` decorators."""
    return {**_DEFAULT_MANIFEST, "signals": SignalRegistry.catalog()}


def list_signals(*, include_planned: bool = True) -> list[str]:
    """List signal types from registered runner metadata."""
    return [signal_type for signal_type, _ in iter_signal_entries(include_planned=include_planned)]


def iter_signal_entries(*, include_planned: bool = True) -> list[tuple[str, dict[str, Any]]]:
    """Return signal catalog entries as ``(signal_type, info)`` tuples."""
    return [(name, info) for name, info in SignalRegistry.catalog().items()
            if include_planned or info.get("status") != "planned"]


def is_allowed_status(value: str) -> bool:
    """Return whether ``value`` is a supported lifecycle status."""
    return value in _ALLOWED_STATUSES


def is_canonical_package_path(value: str) -> bool:
    """Return whether a catalog path uses the canonical family extension root."""
    return value.startswith(_CANONICAL_PACKAGE_ROOT)


def get_signal_info(signal_type: str) -> dict[str, Any] | None:
    """Return the catalog entry for ``signal_type``."""
    return SignalRegistry.info(signal_type)


def get_presets_for_signal(signal_type: str) -> list[str]:
    """List preset names for a registered signal."""
    return SignalRegistry.presets(signal_type)


def get_signal_ids(signal_type: str) -> list[str]:
    """Persisted signal ids (each preset's ``name``) for a registered signal."""
    presets_dir = SignalRegistry.get_presets_dir(signal_type)
    if presets_dir is None or not presets_dir.is_dir():
        return []
    names = (yaml.safe_load(path.read_text(encoding="utf-8")) or {} for path in sorted(presets_dir.glob("*.yaml")))
    return sorted({str(data["name"]) for data in names if isinstance(data, dict) and data.get("name")})


def get_default_preset(signal_type: str) -> str | None:
    """Return the registered default preset for ``signal_type`` when valid."""
    return SignalRegistry.default_preset(signal_type)


def get_all_presets(*, include_planned: bool = True) -> dict[str, list[str]]:
    """Return preset names grouped by signal type."""
    return {
        signal_type: get_presets_for_signal(signal_type)
        for signal_type in list_signals(include_planned=include_planned)
    }


def list_signal_catalog(*, include_planned: bool = False) -> list[dict[str, Any]]:
    """Return flat catalog rows for CLI display."""
    rows: list[dict[str, Any]] = []
    for signal_type, info in iter_signal_entries(include_planned=include_planned):
        engine_version = info.get("engine_version")
        rows.append(
            {
                "signal_type": signal_type,
                "status": str(info.get("status", "active")),
                "description": str(info.get("description", "")),
                "output_type": str(info.get("output_type", "")),
                "runner_module": str(info.get("runner_module", "")),
                "runner_class": str(info.get("runner_class", "")),
                "default_preset": str(info.get("default_preset", "")),
                "presets": get_presets_for_signal(signal_type),
                "signal_ids": get_signal_ids(signal_type),
                "engine_version": engine_version if isinstance(engine_version, int) else None,
            }
        )
    return rows
