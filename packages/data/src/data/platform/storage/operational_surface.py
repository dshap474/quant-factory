"""Validation helpers for the ``packages/data`` operational surface."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from data.extensions import EXTENSIONS_ROOT

from .operator_surface_registry import (
    OPERATOR_SCRIPTS,
    SUPPORTED_CADENCES,
    SUPPORTED_FRESHNESS,
    SUPPORTED_OPERATOR_CONTRACTS,
    SUPPORTED_OPERATOR_ROOTS,
)

DATA_ROOT = EXTENSIONS_ROOT.parent
PIPELINES_ROOT = EXTENSIONS_ROOT / "pipelines"
SCRIPTS_ROOT = EXTENSIONS_ROOT / "scripts"
REQUIRED_DOCS = (
    DATA_ROOT / "AGENTS.md",
    DATA_ROOT / "README.md",
)


@dataclass
class DataOperationalSurfaceValidation:
    """Validation report for the ``packages/data`` package surface."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors

    def __str__(self) -> str:
        lines = [f"Valid: {self.valid}"]
        if self.errors:
            lines.append(f"Errors ({len(self.errors)}):")
            lines.extend(f"  - {error}" for error in self.errors)
        if self.warnings:
            lines.append(f"Warnings ({len(self.warnings)}):")
            lines.extend(f"  - {warning}" for warning in self.warnings)
        if self.info:
            lines.append(f"Info ({len(self.info)}):")
            lines.extend(f"  - {row}" for row in self.info)
        return "\n".join(lines)


def _list_scripts(root: Path) -> list[str]:
    return sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*.py")
        if path.name != "__init__.py" and not path.name.startswith("_")
    )


def _script_text(root: Path, relpath: str) -> str:
    return (root / relpath).read_text(encoding="utf-8")


def _calls_data_api(text: str) -> bool:
    return "from data.api import" in text or "import data.api" in text


def _builds_dataset_spec(text: str) -> bool:
    return "DatasetSpec" in text or "build_raw_spec" in text or "build_derived_spec" in text


def _uses_any_api_operation(text: str) -> bool:
    operations = (
        "ingest_dataset(",
        "sync_dataset(",
        "materialize_dataset(",
        "validate_dataset(",
        "get_dataset_status(",
        "reconcile_dataset(",
    )
    return any(operation in text for operation in operations)


def _uses_validate_api_operation(text: str) -> bool:
    operations = ("validate_dataset(", "get_dataset_status(", "reconcile_dataset(")
    return any(operation in text for operation in operations)


def _uses_mutating_api_operation(text: str) -> bool:
    operations = ("ingest_dataset(", "sync_dataset(", "materialize_dataset(")
    return any(operation in text for operation in operations)


def _imports_forbidden_active_surface(text: str) -> bool:
    forbidden_fragments = (
        "from data.features",
        "import data.features",
        "from data.platform.storage",
        "import data.platform.storage",
        "import boto3",
        "import psycopg2",
        "from psycopg2",
        "import pyarrow",
        "from pyarrow",
    )
    return any(fragment in text for fragment in forbidden_fragments)


def validate_data_operational_surface() -> DataOperationalSurfaceValidation:
    """Validate package docs and registry-listed operational entrypoints."""
    result = DataOperationalSurfaceValidation()

    if not DATA_ROOT.exists():
        result.errors.append(f"Missing data package root: {DATA_ROOT}")
        return result

    if EXTENSIONS_ROOT.is_dir():
        for doc_path in REQUIRED_DOCS:
            if not doc_path.exists():
                result.errors.append(f"Missing required data operational doc: {doc_path}")

    actual_pipeline_scripts = _list_scripts(PIPELINES_ROOT) if PIPELINES_ROOT.exists() else []
    actual_utility_scripts = _list_scripts(SCRIPTS_ROOT) if SCRIPTS_ROOT.exists() else []
    actual_scripts_by_root = {
        "pipelines": actual_pipeline_scripts,
        "scripts": actual_utility_scripts,
    }
    registry_entries = list(OPERATOR_SCRIPTS)
    registry_paths = [(entry.root, entry.path) for entry in registry_entries]

    for entry in registry_entries:
        if entry.root not in SUPPORTED_OPERATOR_ROOTS:
            result.errors.append(f"operator registry: unsupported root '{entry.root}' for {entry.path}")
        if entry.cadence not in SUPPORTED_CADENCES:
            result.errors.append(f"operator registry: unsupported cadence '{entry.cadence}' for {entry.path}")
        if entry.contract not in SUPPORTED_OPERATOR_CONTRACTS:
            result.errors.append(f"operator registry: unsupported contract '{entry.contract}' for {entry.path}")
        if entry.freshness not in SUPPORTED_FRESHNESS:
            result.errors.append(f"operator registry: unsupported freshness '{entry.freshness}' for {entry.path}")
        if not entry.path.endswith(".py"):
            result.errors.append(f"operator registry: path is not a Python script: {entry.path}")
        root_dir = PIPELINES_ROOT if entry.root == "pipelines" else SCRIPTS_ROOT
        root_label = entry.root
        if f"packages/data/extensions/{root_label}/{entry.path}" not in entry.example:
            result.errors.append(f"operator registry: example does not reference script path: {entry.path}")
        if entry.path not in actual_scripts_by_root.get(entry.root, []):
            result.errors.append(f"operator registry: listed script does not exist in {root_label}/: {entry.path}")
            continue

        text = _script_text(root_dir, entry.path)
        if entry.root == "pipelines":
            if not entry.path.startswith(("raw/", "corrected/", "derived/")):
                result.errors.append(f"operator registry: lib pipeline outside raw/, corrected/ or derived/: {entry.path}")
            if not entry.primary_write_surface.startswith(("db/data/raw/", "db/data/corrected/", "db/data/derived/")):
                result.errors.append(f"operator registry: lib pipeline does not write db/data: {entry.path}")

        if not _calls_data_api(text):
            result.errors.append(f"{root_label}/ active wrapper does not import data.api: {entry.path}")
        if not _builds_dataset_spec(text):
            result.errors.append(f"{root_label}/ active wrapper does not build DatasetSpec: {entry.path}")
        if not _uses_any_api_operation(text):
            result.errors.append(f"{root_label}/ active wrapper does not call a data.api operation: {entry.path}")
        if entry.root == "pipelines" and _imports_forbidden_active_surface(text):
            result.errors.append(f"pipelines/ active wrapper imports forbidden active runtime surface: {entry.path}")

        if entry.contract == "analysis_only":
            if "StorageTarget.EXTERNAL" not in text:
                result.errors.append(f"{root_label}/ analysis wrapper does not target StorageTarget.EXTERNAL: {entry.path}")
            if not _uses_validate_api_operation(text):
                result.errors.append(f"{root_label}/ analysis wrapper does not use a validation/status API: {entry.path}")
            if _uses_mutating_api_operation(text):
                result.errors.append(f"{root_label}/ analysis wrapper uses a mutating API operation: {entry.path}")

    for name in actual_pipeline_scripts:
        if ("pipelines", name) not in registry_paths:
            result.errors.append(f"pipelines/ script missing from operator registry: {name}")
    for name in actual_utility_scripts:
        if ("scripts", name) not in registry_paths:
            result.errors.append(f"scripts/ utility missing from operator registry: {name}")

    result.info.append(f"extension pipelines: {len(actual_pipeline_scripts)}")
    result.info.append(f"script utilities: {len(actual_utility_scripts)}")
    result.info.append(f"registered scripts: {len(registry_entries)}")
    return result


__all__ = ["DataOperationalSurfaceValidation", "validate_data_operational_surface"]
