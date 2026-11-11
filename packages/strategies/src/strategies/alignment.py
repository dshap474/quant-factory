"""Validate selected presets and their strategy memory versions.

USAGE: ``validate_strategy_alignment("family")`` checks the packaged preset without
requiring a master document. Existing legacy declarations remain readable during migration.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import yaml

from .manifest import get_strategy_info, iter_strategy_entries
from .paths import STRATEGIES_ROOT, resolve_strategy_path

# --------------------------------------------------------------------------- #
# Version declarations and reports
# --------------------------------------------------------------------------- #

_ACTIVE_VERSION_RE = re.compile(r"(?m)^- Active memory version: `(?P<version>v\d{3})`\s*$")
_BEST_CONFIG_RE = re.compile(r"(?im)^- Best [^\n`]*configuration[^\n`]*: `(?P<preset>[^`]+)`\.")
_STALE_PRESET_PATTERNS = (
    re.compile(r"(?i)packaged presets are stale"),
    re.compile(r"(?i)canonical preset is stale"),
    re.compile(r"(?i)default preset is stale"),
)


@dataclass
class StrategyAlignmentValidation:
    """Validation report for registry, preset and memory-version alignment."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors


def resolve_active_memory_version(strategy_type: str) -> str | None:
    """Read the registered default preset's explicit ``memory_version``.

    An existing legacy master declaration is a read-only fallback for an unmigrated
    preset. Missing declarations return None; malformed explicit declarations fail
    instead of falling back or inferring a version from research recency or performance.
    """
    info = get_strategy_info(strategy_type)
    if info is None or not info.get("presets_dir") or not info.get("default_preset"):
        return None
    presets_dir = resolve_strategy_path(str(info["presets_dir"]), STRATEGIES_ROOT)
    preset_path = presets_dir / f"{info['default_preset']}.yaml"
    if not preset_path.is_file():
        return None
    config = yaml.safe_load(preset_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError(f"{strategy_type}: default preset must be a YAML mapping")
    if "memory_version" in config:
        version = config["memory_version"]
        if not isinstance(version, str) or re.fullmatch(r"v\d{3}", version) is None:
            raise ValueError(f"{strategy_type}: default preset memory_version must be vNNN")
        return version

    legacy_path = presets_dir.parent / "optimization" / "STRATEGY_MASTER_DOC.md"
    if legacy_path.is_file():
        match = _ACTIVE_VERSION_RE.search(legacy_path.read_text(encoding="utf-8"))
        return match.group("version") if match else None
    return None


# --------------------------------------------------------------------------- #
# Alignment checks
# --------------------------------------------------------------------------- #


def _validate_strategy_alignment(
    strategy_type: str,
    result: StrategyAlignmentValidation,
) -> None:
    info = get_strategy_info(strategy_type)
    if info is None:
        result.errors.append(f"{strategy_type}: strategy type not found in registry-derived catalog")
        return
    canonical_preset = info.get("default_preset")
    presets_rel = info.get("presets_dir")
    if not canonical_preset and not presets_rel:
        result.info.append(f"{strategy_type}: built from explicit inputs; no preset alignment to check")
        return
    if not canonical_preset or not presets_rel:
        result.errors.append(f"{strategy_type}: missing registered default preset or presets directory")
        return
    presets_dir = resolve_strategy_path(str(presets_rel), STRATEGIES_ROOT)
    if not (presets_dir / f"{canonical_preset}.yaml").is_file():
        result.errors.append(f"{strategy_type}: missing registered default preset '{canonical_preset}'")
        return
    try:
        version = resolve_active_memory_version(strategy_type)
    except (ValueError, yaml.YAMLError) as exc:
        result.errors.append(f"{strategy_type}: invalid version declaration: {exc}")
        return
    if version is None:
        if info.get("status") == "planned":
            result.info.append(f"{strategy_type}: planned family has no selected memory version")
        else:
            result.errors.append(f"{strategy_type}: default preset must declare memory_version")
        return

    optimization_root = presets_dir.parent / "optimization"
    version_dir = optimization_root / version
    if not version_dir.is_dir():
        version_dir = optimization_root / "version" / version
    if not version_dir.is_dir():
        result.errors.append(f"{strategy_type}: selected version '{version}' has no version directory")
        return

    version_md = version_dir / "VERSION.md"
    if version_md.is_file():
        version_text = version_md.read_text(encoding="utf-8")
        if any(pattern.search(version_text) for pattern in _STALE_PRESET_PATTERNS):
            best_config = _BEST_CONFIG_RE.search(version_text)
            if best_config is None:
                result.warnings.append(
                    f"{strategy_type}: active version doc marks presets stale but does not declare "
                    "a best configuration preset"
                )
            elif canonical_preset != best_config.group("preset"):
                result.errors.append(
                    f"{strategy_type}: active version doc recommends preset '{best_config.group('preset')}' "
                    f"while canonical preset remains '{canonical_preset}'"
                )
    result.info.append(
        f"{strategy_type}: alignment checked against canonical preset '{canonical_preset}' "
        f"and active version '{version}'"
    )


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #


def validate_strategy_alignment(
    strategy_type: str | None = None,
    *,
    include_planned: bool = False,
) -> StrategyAlignmentValidation:
    """Validate registered presets and selected memory versions without required prose."""
    result = StrategyAlignmentValidation()
    entries = (
        [(strategy_type, get_strategy_info(strategy_type) or {})]
        if strategy_type
        else iter_strategy_entries(include_planned=include_planned)
    )
    if not entries:
        result.warnings.append("No strategy entries available for alignment validation")
        return result
    for current_strategy_type, _ in entries:
        _validate_strategy_alignment(current_strategy_type, result)
    return result
