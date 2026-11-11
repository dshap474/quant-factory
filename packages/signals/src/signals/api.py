"""Stable public API for the signals control plane."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from signals.bootstrap import (
    import_active_runner_modules,
    import_runner_module,
    populate_signal_registry,
    resolve_signal_runner,
)
from signals.manifest import (
    get_all_presets,
    get_default_preset,
    get_presets_for_signal,
    get_signal_info,
    list_signal_catalog,
    list_signals,
    load_manifest,
)
from signals.prediction_store import PredictionStore
from signals.publish import (
    SignalPublishReport,
)
from signals.publish import (
    publish_catalog as _publish_catalog,
)
from signals.validators import (
    SignalCatalogValidation,
    SignalSmokeReport,
    smoke_signal_catalog,
    smoke_signals,
    validate_signal_catalog,
)


@dataclass
class SignalsApiError(Exception):
    """Boundary error for signals API consumers."""

    code: str
    details: str

    def __str__(self) -> str:
        return f"{self.code}: {self.details}"


def list_catalog(*, include_planned: bool = False) -> list[dict[str, Any]]:
    """List registry-derived signal catalog rows."""
    return list_signal_catalog(include_planned=include_planned)


def validate_catalog() -> SignalCatalogValidation:
    """Validate registry/catalog/runtime/disk consistency for active signals."""
    try:
        return validate_signal_catalog()
    except Exception as exc:  # pragma: no cover - explicit boundary conversion
        raise SignalsApiError("validate_catalog_failed", str(exc)) from exc


def smoke_catalog(*, signal_type: str | None = None) -> SignalSmokeReport:
    """Run smoke execution for active signals using ``save=False``."""
    try:
        return smoke_signals(signal_type=signal_type)
    except Exception as exc:  # pragma: no cover - explicit boundary conversion
        raise SignalsApiError("smoke_catalog_failed", str(exc)) from exc


def publish_catalog(
    *,
    signal_types: Sequence[str] | None = None,
    preset: str | None = None,
    all_presets: bool = False,
    db_root: Path | None = None,
    dry_run: bool = False,
    fail_fast: bool = False,
) -> SignalPublishReport:
    """Run selected active signal families with ``save=True``.

    Selection is registry-driven: an empty ``signal_types`` publishes every
    ``status == "active"`` catalog entry with its registered default preset.
    Individual runner failures are recorded, not raised; usage errors are.
    """
    try:
        return _publish_catalog(
            signal_types=signal_types,
            preset=preset,
            all_presets=all_presets,
            db_root=db_root,
            dry_run=dry_run,
            fail_fast=fail_fast,
        )
    except ValueError as exc:
        raise SignalsApiError("publish_catalog_invalid_selection", str(exc)) from exc


__all__ = [
    "SignalsApiError",
    "SignalCatalogValidation",
    "SignalPublishReport",
    "SignalSmokeReport",
    "PredictionStore",
    "get_all_presets",
    "get_default_preset",
    "get_presets_for_signal",
    "get_signal_info",
    "import_active_runner_modules",
    "import_runner_module",
    "list_catalog",
    "list_signal_catalog",
    "list_signals",
    "load_manifest",
    "populate_signal_registry",
    "publish_catalog",
    "resolve_signal_runner",
    "smoke_catalog",
    "smoke_signal_catalog",
    "smoke_signals",
    "validate_catalog",
    "validate_signal_catalog",
]
