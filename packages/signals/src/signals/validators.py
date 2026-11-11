"""Validation surfaces for the signals control plane."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from signals.bootstrap import (
    FAMILIES_ROOT,
    import_runner_module,
    iter_signal_package_dirs,
    populate_signal_registry,
    qualify_runner_module,
    resolve_signal_runner,
)
from signals.contracts import validate_prediction_frame
from signals.manifest import (
    get_default_preset,
    get_presets_for_signal,
    get_signal_info,
    is_allowed_status,
    is_canonical_package_path,
    iter_signal_entries,
    list_signals,
    load_manifest,
)
from signals.naming import is_valid_preset_name, is_valid_signal_type_name
from signals.registry import SIGNALS_ROOT, SignalRegistry

REQUIRED_FIELDS = (
    "status",
    "description",
    "runner_module",
    "runner_class",
    "presets_dir",
    "default_preset",
    "output_type",
    "docs",
)
LIGHTWEIGHT_MEMORY_FILES = (
    "_signal/CHANGELOG.md",
)


@dataclass
class SignalCatalogValidation:
    """Validation report for catalog/registry/on-disk consistency."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors

    def __str__(self) -> str:
        lines = [f"Signal catalog valid: {self.valid}"]
        if self.errors:
            lines.append(f"errors ({len(self.errors)}):")
            lines.extend(f"  - {err}" for err in self.errors)
        if self.warnings:
            lines.append(f"warnings ({len(self.warnings)}):")
            lines.extend(f"  - {warn}" for warn in self.warnings)
        if self.info:
            lines.append(f"info ({len(self.info)}):")
            lines.extend(f"  - {row}" for row in self.info)
        return "\n".join(lines)


@dataclass
class SignalSmokeReport:
    """Smoke-run report for active signals."""

    passed: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)
    info: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return not self.failed


def _require_string(info: dict[str, Any], signal_type: str, field: str, result: SignalCatalogValidation) -> None:
    value = info.get(field)
    if not isinstance(value, str) or not value.strip():
        result.errors.append(f"{signal_type}: missing required catalog field '{field}'")


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    return loaded if isinstance(loaded, dict) else {}


def _validate_memory_contract(
    package_root: Path,
    signal_type: str,
    result: SignalCatalogValidation,
) -> None:
    signal_memory = package_root / "_signal"
    if not signal_memory.exists():
        result.warnings.append(f"{signal_type}: optional _signal memory directory is missing")
        return

    for rel_path in LIGHTWEIGHT_MEMORY_FILES:
        path = package_root / rel_path
        if not path.exists():
            result.warnings.append(f"{signal_type}: optional memory file missing: {path}")


def _validate_presets(
    package_root: Path,
    signal_type: str,
    result: SignalCatalogValidation,
) -> None:
    presets_dir = package_root / "presets"
    if not presets_dir.exists():
        return

    for preset_path in sorted(presets_dir.glob("*.yaml")):
        stem = preset_path.stem
        if not is_valid_preset_name(stem):
            result.errors.append(f"{signal_type}: preset filename '{stem}' must be 'default' or lowercase kebab-case")

        data = _load_yaml_mapping(preset_path)
        preset_name = str(data.get("name", "")).strip()
        preset_signal_type = str(data.get("signal_type", "")).strip()

        if not preset_name:
            result.errors.append(f"{signal_type}: preset {preset_path.name} missing 'name'")
        elif not is_valid_preset_name(preset_name):
            result.errors.append(
                f"{signal_type}: preset name '{preset_name}' in {preset_path.name} must be lowercase kebab-case"
            )

        if not preset_signal_type:
            result.errors.append(f"{signal_type}: preset {preset_path.name} missing 'signal_type'")
        elif preset_signal_type != signal_type:
            result.errors.append(
                f"{signal_type}: preset {preset_path.name} declares signal_type '{preset_signal_type}'"
            )


def validate_signal_catalog() -> SignalCatalogValidation:
    """Validate registry-derived catalog, package files, imports, and runner coherence."""
    result = SignalCatalogValidation()
    manifest = load_manifest()
    version = manifest.get("version")
    if version != 2:
        result.errors.append(f"Signal catalog compatibility payload must declare version: 2 (found {version!r})")

    entries = iter_signal_entries(include_planned=True)
    if not entries:
        result.warnings.append("Signal catalog has no signal entries")
        return result

    entry_by_type = {signal_type: info for signal_type, info in entries if isinstance(info, dict)}
    known_package_dirs = {path.name for path in iter_signal_package_dirs()}

    for signal_type, info in entries:
        if not isinstance(info, dict):
            result.errors.append(f"{signal_type}: catalog entry must be a mapping")
            continue

        for field_name in REQUIRED_FIELDS:
            _require_string(info, signal_type, field_name, result)

        if not is_valid_signal_type_name(signal_type):
            result.errors.append(f"{signal_type}: signal_type must be lowercase kebab-case and naming-semantic")

        status = str(info.get("status", "active"))
        if not is_allowed_status(status):
            result.errors.append(f"{signal_type}: invalid status '{status}' (expected active or planned)")

        docs_path = SIGNALS_ROOT / str(info.get("docs", ""))
        if not docs_path.exists():
            result.errors.append(f"{signal_type}: missing docs path {docs_path}")

        presets_dir = SIGNALS_ROOT / str(info.get("presets_dir", ""))
        if not presets_dir.exists():
            result.errors.append(f"{signal_type}: missing presets_dir {presets_dir}")
        else:
            preset_names = get_presets_for_signal(signal_type)
            if not preset_names:
                result.errors.append(f"{signal_type}: presets_dir has no YAML presets")
            default_preset = get_default_preset(signal_type)
            if status == "active" and default_preset is None:
                result.errors.append(
                    f"{signal_type}: default_preset '{info.get('default_preset')}' is not present on disk"
                )

        docs_rel = Path(str(info.get("docs", "")))
        presets_rel = str(info.get("presets_dir", ""))
        docs_rel_str = str(info.get("docs", ""))
        if presets_rel and not is_canonical_package_path(presets_rel):
            result.errors.append(
                f"{signal_type}: presets_dir must use canonical 'extensions/lib/' root "
                f"(got '{presets_rel}')"
            )
        if docs_rel_str and not is_canonical_package_path(docs_rel_str):
            result.errors.append(
                f"{signal_type}: docs must use canonical 'extensions/lib/' root "
                f"(got '{docs_rel_str}')"
            )

        if docs_rel.parts[:2] == ("extensions", "lib") and len(docs_rel.parts) > 2:
            package_dir = docs_rel.parts[2]
            if package_dir not in known_package_dirs:
                result.errors.append(f"{signal_type}: docs path points to missing package directory '{package_dir}'")
            else:
                pkg_root = FAMILIES_ROOT / package_dir
                if not (pkg_root / "tests").exists():
                    result.errors.append(f"{signal_type}: package missing tests directory")
                _validate_memory_contract(pkg_root, signal_type, result)
                _validate_presets(pkg_root, signal_type, result)

    if result.errors:
        return result

    try:
        imported = populate_signal_registry(include_planned=False)
    except Exception as exc:
        result.errors.append(f"Active signal bootstrap failed: {exc}")
        return result

    result.info.append(f"Imported active signals: {', '.join(imported)}")
    registered = set(SignalRegistry.list())
    expected = {
        signal_type for signal_type, info in entry_by_type.items() if str(info.get("status", "active")) == "active"
    }
    if set(imported) != expected:
        result.errors.append(f"Active discovery mismatch: expected {sorted(expected)}, got {sorted(imported)}")
        return result
    if registered != set(imported):
        result.errors.append(
            f"SignalRegistry active-only mismatch: expected {sorted(imported)}, got {sorted(registered)}"
        )
        return result

    for signal_type in sorted(imported):
        info = entry_by_type[signal_type]

        try:
            runner_cls = SignalRegistry.get(signal_type)
        except Exception as exc:
            result.errors.append(f"{signal_type}: registry lookup failed: {exc}")
            continue

        expected_runner_class = str(info.get("runner_class"))
        if runner_cls.__name__ != expected_runner_class:
            result.errors.append(
                f"{signal_type}: catalog runner_class '{expected_runner_class}' != runtime '{runner_cls.__name__}'"
            )

        expected_runner_module = qualify_runner_module(str(info.get("runner_module")))
        if runner_cls.__module__ != expected_runner_module:
            result.errors.append(
                f"{signal_type}: catalog runner_module '{expected_runner_module}' != runtime '{runner_cls.__module__}'"
            )

        try:
            import_runner_module(signal_type)
        except Exception as exc:
            result.errors.append(f"{signal_type}: import failed after bootstrap: {exc}")

    root_venv = SIGNALS_ROOT / ".venv"
    if root_venv.exists():
        result.warnings.append(f"Package-local virtualenv present: {root_venv}")
    for package_dir in iter_signal_package_dirs():
        local_venv = package_dir / ".venv"
        if local_venv.exists():
            result.warnings.append(f"Package-local virtualenv present: {local_venv}")

    return result


def smoke_signals(*, signal_type: str | None = None) -> SignalSmokeReport:
    """Run active signal presets with ``save=False`` to prove execution viability."""
    report = SignalSmokeReport()
    target_types = [signal_type] if signal_type else list_signals(include_planned=False)

    populate_signal_registry(include_planned=False)

    for current_signal_type in target_types:
        info = get_signal_info(current_signal_type)
        if info is None:
            report.failed[current_signal_type] = "signal type not found in catalog"
            continue

        preset_name = get_default_preset(current_signal_type)
        if preset_name is None:
            report.failed[current_signal_type] = "missing or invalid default_preset"
            continue

        try:
            runner = resolve_signal_runner(current_signal_type, preset_name, save=False)
            result = runner.run()
            validate_prediction_frame(result.predictions, signal_name=runner.run_config.signal_id)
        except Exception as exc:
            report.failed[current_signal_type] = str(exc)
            continue

        report.passed.append(current_signal_type)
        report.info.append(f"{current_signal_type}: smoke passed with {len(result.predictions)} prediction rows")

    return report


smoke_signal_catalog = smoke_signals
