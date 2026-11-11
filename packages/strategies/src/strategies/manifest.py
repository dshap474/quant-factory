"""Strategy catalog helpers backed by registered runner metadata.

USAGE: ``get_strategy_info("family")`` returns catalog metadata and its README path.
"""

from __future__ import annotations

from typing import Any

from .registry import StrategyRegistry

# --------------------------------------------------------------------------- #
# Catalog metadata
# --------------------------------------------------------------------------- #

_DEFAULT_MANIFEST = {"version": 2, "strategies": {}}
_ALLOWED_STATUSES = {"active", "planned"}


def load_manifest() -> dict[str, Any]:
    """Return the compatibility catalog payload.

    The catalog comes from ``StrategyRegistry.register(...)`` decorators in
    concrete strategy runner modules.
    """
    return {**_DEFAULT_MANIFEST, "strategies": StrategyRegistry.catalog()}


def list_strategy_types(*, include_planned: bool = True) -> list[str]:
    """List strategy types from registered runner metadata."""
    return [strategy_type for strategy_type, _ in iter_strategy_entries(include_planned=include_planned)]


def iter_strategy_entries(*, include_planned: bool = True) -> list[tuple[str, dict[str, Any]]]:
    """Return catalog entries as ``(strategy_type, info)`` tuples."""
    return [(name, info) for name, info in StrategyRegistry.catalog().items()
            if include_planned or info.get("status") != "planned"]


def is_allowed_status(value: str) -> bool:
    """Return whether ``value`` is a supported lifecycle status."""
    return value in _ALLOWED_STATUSES


def get_strategy_info(strategy_type: str) -> dict[str, Any] | None:
    """Return the catalog entry for ``strategy_type``."""
    return StrategyRegistry.info(strategy_type)


def get_presets_for_type(strategy_type: str) -> list[str]:
    """List preset names for a registered strategy."""
    return StrategyRegistry.presets(strategy_type)


def get_default_preset(strategy_type: str) -> str | None:
    """Return the registered default preset for ``strategy_type`` when valid."""
    return StrategyRegistry.default_preset(strategy_type)


def get_all_presets(*, include_planned: bool = True) -> dict[str, list[str]]:
    """Return preset names grouped by strategy type."""
    return {
        strategy_type: get_presets_for_type(strategy_type)
        for strategy_type in list_strategy_types(include_planned=include_planned)
    }


def list_strategy_catalog(*, include_planned: bool = False) -> list[dict[str, Any]]:
    """Return flat catalog rows for CLI display."""
    rows: list[dict[str, Any]] = []
    for strategy_type, info in iter_strategy_entries(include_planned=include_planned):
        rows.append(
            {
                "strategy_type": strategy_type,
                "status": str(info.get("status", "active")),
                "description": str(info.get("description", "")),
                "output_type": str(info.get("output_type", "")),
                "runner_module": str(info.get("runner_module", "")),
                "runner_class": str(info.get("runner_class", "")),
                "default_preset": str(info.get("default_preset", "")),
                "presets": get_presets_for_type(strategy_type),
            }
        )
    return rows
