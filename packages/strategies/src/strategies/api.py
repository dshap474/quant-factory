"""Stable API surface for strategy control-plane operations.

USAGE: ``validate_strategy_catalog()`` checks installed families;
``scaffold("new-family")`` creates a family with README and a design-space map.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from config import QUANT_DB_ROOT
from family_registry import is_historical_module

from .alignment import (
    StrategyAlignmentValidation,
    resolve_active_memory_version,
    validate_strategy_alignment,
)
from .bootstrap import populate_strategy_registry
from .manifest import (
    get_default_preset,
    get_presets_for_type,
    get_strategy_info,
    list_strategy_catalog,
    list_strategy_types,
    load_manifest,
)
from .paths import FAMILIES_ROOT, STRATEGIES_ROOT, resolve_strategy_path
from .registry import StrategyRegistry
from .versioned import promote_run

# --------------------------------------------------------------------------- #
# Reports and version identifiers
# --------------------------------------------------------------------------- #


_VERSION_DIR_RE = re.compile(r"^v\d{3}$")


@dataclass
class StrategyCatalogValidation:
    """Validation report for catalog/registry/on-disk consistency."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors


@dataclass
class StrategySmokeReport:
    """Smoke report for registered strategies."""

    passed: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)
    info: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return not self.failed


@dataclass(frozen=True)
class StrategyRunHandle:
    """Lightweight run handle returned by ``run``."""

    strategy_type: str
    preset: str
    memory_version: str | None
    run_id: str | None
    run_dir: Path | None
    metrics: dict[str, float]


# --------------------------------------------------------------------------- #
# Catalog validation
# --------------------------------------------------------------------------- #


def _check_archived_runners_registered(result: StrategyCatalogValidation) -> None:
    """Assert no registered runner resolves to a sealed-version module.

    Discovery imports only family ``src/`` runners; this fails loudly if a runner from
    ``optimization/version/`` ever leaks into the live registry.
    """
    for strategy_type in sorted(StrategyRegistry.list()):
        runner_cls = StrategyRegistry.get(strategy_type)
        if is_historical_module(runner_cls):
            result.errors.append(
                f"{strategy_type}: registered runner '{runner_cls.__module__}' resolves to an archived module"
            )


def _check_canonical_preset_durability(
    result: StrategyCatalogValidation,
    *,
    strategy_type: str,
    presets_dir: str,
    default_preset: str,
    version: str,
    strategies_root: Path = STRATEGIES_ROOT,
) -> None:
    """Assert the default preset has a byte-identical frozen copy in its version pack.

    Durability: ``optimization/<version>/presets/<default>.yaml`` must exist.
    Mirror: that frozen copy must match the live ``presets/<default>.yaml`` bytes.
    """
    live_preset = resolve_strategy_path(presets_dir, strategies_root) / f"{default_preset}.yaml"
    family_root = resolve_strategy_path(presets_dir, strategies_root).parent
    frozen_preset = family_root / "optimization" / version / "presets" / f"{default_preset}.yaml"
    if not frozen_preset.exists():
        archived = family_root / "optimization" / "version" / version / "presets" / f"{default_preset}.yaml"
        if archived.exists():
            frozen_preset = archived
    rel_frozen = (
        frozen_preset.relative_to(strategies_root) if frozen_preset.is_relative_to(strategies_root) else frozen_preset
    )
    if not frozen_preset.exists():
        result.errors.append(f"{strategy_type}: canonical preset '{default_preset}' has no frozen copy at {rel_frozen}")
        return
    if live_preset.exists() and frozen_preset.read_bytes() != live_preset.read_bytes():
        result.errors.append(
            f"{strategy_type}: frozen preset {rel_frozen} differs from live {presets_dir}/{default_preset}.yaml"
        )


def _check_output_metadata(
    result: StrategyCatalogValidation,
    *,
    active_types: list[str],
    strategies_dir: Path,
) -> None:
    """Warn when a promoted ``final/meta.json`` carries a foreign family label."""
    for strategy_type in sorted(active_types):
        for meta_path in sorted((strategies_dir / strategy_type / "versions").glob("v*/final/meta.json")):
            if not _VERSION_DIR_RE.match(meta_path.parents[1].name):
                continue
            try:
                label = json.loads(meta_path.read_text()).get("strategy_type")
            except (OSError, ValueError, AttributeError):
                continue
            if label and label != strategy_type:
                result.warnings.append(
                    f"{strategy_type}: versions/{meta_path.parents[1].name}/final/meta.json "
                    f"strategy_type '{label}' != '{strategy_type}'"
                )


def _validate_strategy_catalog_internal() -> StrategyCatalogValidation:
    required_fields = ("status", "description", "runner_module", "runner_class", "output_type", "docs")
    result = StrategyCatalogValidation()

    manifest = load_manifest()
    strategies = manifest.get("strategies", {})
    if not isinstance(strategies, dict):
        result.errors.append("Strategy catalog is invalid")
        return result
    if not strategies:
        result.info.append("No strategy extensions installed")
        return result

    for strategy_type, info in sorted(strategies.items()):
        if not isinstance(info, dict):
            result.errors.append(f"{strategy_type}: catalog entry is not a mapping")
            continue
        for field_name in required_fields:
            value = info.get(field_name)
            if value in (None, "", []):
                result.errors.append(f"{strategy_type}: missing catalog field '{field_name}'")

        # Presets are optional: a family built from explicit inputs declares none.
        if info.get("presets_dir") or info.get("default_preset"):
            if not get_presets_for_type(strategy_type):
                result.errors.append(f"{strategy_type}: no presets found under {info.get('presets_dir')}")
            if get_default_preset(strategy_type) is None:
                result.errors.append(
                    f"{strategy_type}: default_preset '{info.get('default_preset')}' is not present on disk"
                )

        docs_path = info.get("docs")
        if (
            isinstance(docs_path, str)
            and docs_path
            and not resolve_strategy_path(docs_path, STRATEGIES_ROOT).exists()
        ):
            result.warnings.append(f"{strategy_type}: docs path missing from installed layout: {docs_path}")

    if result.errors:
        return result

    try:
        StrategyRegistry.clear()
        imported = populate_strategy_registry(include_planned=False)
        result.info.append(f"Imported active strategies: {', '.join(imported)}")
    except Exception as exc:
        result.errors.append(f"Active strategy bootstrap failed: {exc}")
        return result

    expected = set(list_strategy_types(include_planned=False))
    registered = set(StrategyRegistry.list())
    if registered != expected:
        result.errors.append(f"StrategyRegistry mismatch: expected {sorted(expected)}, got {sorted(registered)}")
        return result

    active_types = sorted(expected)
    for strategy_type in active_types:
        info = get_strategy_info(strategy_type)
        if info is None:
            result.errors.append(f"{strategy_type}: missing catalog metadata")
            continue
        metadata = StrategyRegistry.get_metadata(strategy_type)
        for field_name in (
            "description",
            "presets_dir",
            "default_preset",
            "output_type",
            "runner_module",
            "runner_class",
        ):
            if metadata.get(field_name) != info.get(field_name):
                result.errors.append(
                    f"{strategy_type}: catalog {field_name} '{info.get(field_name)}' != runtime '{metadata.get(field_name)}'"
                )

        # Canonical preset durability + mirror: the registered default preset must
        # have a byte-identical frozen copy in the selected memory-version pack.
        default_preset = get_default_preset(strategy_type)
        presets_dir = info.get("presets_dir")
        if not presets_dir:
            continue
        try:
            version = resolve_active_memory_version(strategy_type)
        except (ValueError, yaml.YAMLError) as exc:
            result.errors.append(f"{strategy_type}: invalid version declaration: {exc}")
            continue
        if version is None:
            result.errors.append(f"{strategy_type}: default preset must declare memory_version")
            continue
        if default_preset and isinstance(presets_dir, str) and presets_dir and version:
            _check_canonical_preset_durability(
                result,
                strategy_type=strategy_type,
                presets_dir=presets_dir,
                default_preset=default_preset,
                version=version,
            )

    # No registered runner may resolve to a sealed-version module.
    _check_archived_runners_registered(result)

    # Output-metadata correctness (warnings): persisted labels match producing family.
    _check_output_metadata(
        result,
        active_types=active_types,
        strategies_dir=Path(QUANT_DB_ROOT) / "strategies",
    )

    return result


# --------------------------------------------------------------------------- #
# Public operator API
# --------------------------------------------------------------------------- #


def validate_strategy_catalog() -> StrategyCatalogValidation:
    """Validate catalog, package surfaces, imports, and registry coherence."""
    return _validate_strategy_catalog_internal()


def smoke_strategies(
    *,
    strategy_type: str | None = None,
    execute: bool = False,
) -> StrategySmokeReport:
    """Smoke strategy presets from catalog defaults."""
    report = StrategySmokeReport()
    try:
        StrategyRegistry.clear()
        populate_strategy_registry(include_planned=False)
    except Exception as exc:
        report.failed["catalog"] = str(exc)
        return report

    target_types = [strategy_type] if strategy_type else list_strategy_types(include_planned=False)
    for current_strategy_type in target_types:
        preset_name = get_default_preset(current_strategy_type)
        if preset_name is None and not get_strategy_info(current_strategy_type).get("presets_dir"):
            report.info.append(f"{current_strategy_type}: built from explicit inputs; no preset to smoke")
            continue
        if preset_name is None:
            report.failed[current_strategy_type] = "missing or invalid catalog default_preset"
            continue
        try:
            runner_cls = StrategyRegistry.get(current_strategy_type)
            runner = runner_cls.from_preset(preset_name, save=False)
            if execute:
                result = runner.run()
                report.info.append(
                    f"{current_strategy_type}: execute smoke passed with {len(result.weights.weights)} weight rows"
                )
            else:
                report.info.append(
                    f"{current_strategy_type}: preset smoke passed via {runner_cls.__name__}.from_preset('{preset_name}', save=False)"
                )
        except Exception as exc:
            report.failed[current_strategy_type] = str(exc)
            continue
        report.passed.append(current_strategy_type)
    return report


def list_families(*, include_planned: bool = False) -> list[str]:
    """List strategy families (catalog strategy types)."""
    return list_strategy_types(include_planned=include_planned)


def list_presets(family: str) -> list[str]:
    """List package-level runnable preset aliases for a family."""
    return get_presets_for_type(family)


def get_active_preset(family: str) -> str | None:
    """Return the registered default runnable preset for a family."""
    return get_default_preset(family)


def list_catalog(*, include_planned: bool = False) -> list[dict[str, Any]]:
    """Return flat control-plane catalog rows."""
    return list_strategy_catalog(include_planned=include_planned)


def validate_catalog() -> StrategyCatalogValidation:
    """Validate catalog, package surfaces, imports, and registry coherence."""
    return validate_strategy_catalog()


def validate_alignment(
    family: str | None = None,
    *,
    include_planned: bool = False,
) -> StrategyAlignmentValidation:
    """Validate registered preset and selected-version alignment."""
    return validate_strategy_alignment(
        strategy_type=family,
        include_planned=include_planned,
    )


def smoke(
    family: str | None = None,
    *,
    execute: bool = False,
) -> StrategySmokeReport:
    """Smoke strategy presets from catalog defaults."""
    return smoke_strategies(strategy_type=family, execute=execute)


def run(
    family: str,
    *,
    preset: str | None = None,
    memory_version: str | None = None,
    save: bool = True,
) -> StrategyRunHandle:
    """Run a family preset; saved runs land in the version's research directory."""
    populate_strategy_registry(include_planned=False)

    info = get_strategy_info(family)
    if info is None:
        raise KeyError(f"Unknown strategy family: {family}")

    preset_name = preset or get_default_preset(family)
    if preset_name is None:
        raise ValueError(f"Family '{family}' has no valid default_preset and no explicit preset was provided.")
    if save and memory_version is None:
        raise ValueError("memory_version is required for persisted strategy runs")

    runner = StrategyRegistry.get(family).from_preset(preset_name, save=save, memory_version=memory_version)
    runner.run_config.preset_name = preset_name
    result = runner.run()
    return StrategyRunHandle(
        strategy_type=family,
        preset=preset_name,
        memory_version=memory_version,
        run_id=result.run_id,
        run_dir=result.run_dir,
        metrics=result.metrics,
    )


def finalize(
    family: str,
    *,
    memory_version: str,
    run_id: str,
) -> StrategyRunHandle:
    """Promote one operator-chosen saved run into the version's ``final/`` artifact."""
    final_dir = promote_run(QUANT_DB_ROOT, family, memory_version, run_id)
    meta = json.loads((final_dir / "meta.json").read_text())
    return StrategyRunHandle(
        strategy_type=family,
        preset=meta.get("preset"),
        memory_version=memory_version,
        run_id=run_id,
        run_dir=final_dir,
        metrics=meta.get("metrics", {}),
    )


# --------------------------------------------------------------------------- #
# Family creation and scaffolding
# --------------------------------------------------------------------------- #


def scaffold(
    family: str,
    *,
    archetype: str = "directional",
    description: str = "",
) -> dict[str, Any]:
    """Scaffold a new strategy family package under ``extensions/lib/``."""
    _assert_slug(family, label="family")
    module = family.replace("-", "_")
    package_root = FAMILIES_ROOT / family
    src_root = package_root / "src" / module
    presets_dir = package_root / "presets"
    tests_dir = package_root / "tests"
    optimization_root = package_root / "optimization"

    if package_root.exists():
        raise FileExistsError(f"Strategy package already exists: {package_root}")

    src_root.mkdir(parents=True, exist_ok=False)
    presets_dir.mkdir(parents=True, exist_ok=True)
    tests_dir.mkdir(parents=True, exist_ok=True)
    optimization_root.mkdir(parents=True, exist_ok=True)

    output_type = "market_neutral" if archetype == "market_neutral" else "directional"
    runner_class = _runner_class_name(family)

    (package_root / "README.md").write_text(
        f"# {family}\n\n{description or 'Strategy package scaffold.'}\n",
        encoding="utf-8",
    )
    (package_root / "AGENTS.md").write_text(
        f"# {family} Local Memory\n\n"
        "- Active memory version: none recorded.\n"
        "- Canonical runnable preset: `default`.\n"
        "- Keep only strategy-local memory and gotchas here. Broader strategy-system rules live in parent AGENTS files.\n"
        "- Saved runs land in `db/research/strategies/<strategy_type>/<vNNN>/<preset>/<run_id>/`; "
        "promoted finals in `db/strategies/<strategy_type>/versions/<vNNN>/final/`.\n",
        encoding="utf-8",
    )
    (optimization_root / "DESIGN-SPACE.md").write_text(
        f"# {family} design space\n\n"
        "No experiments recorded. Maintain a concise synthesis of findings and open questions,\n"
        "with links to version-local specifications, changelogs and outcomes.\n",
        encoding="utf-8",
    )
    (presets_dir / "default.yaml").write_text(
        "name: default\ndescription: Default scaffold preset\ndata: {}\nstrategy: {}\nbacktest: {}\n",
        encoding="utf-8",
    )
    (src_root / "__init__.py").write_text(
        "from .runner import " + runner_class + '\n\n__all__ = ["' + runner_class + '"]\n',
        encoding="utf-8",
    )
    (src_root / "preset.py").write_text(
        _preset_module_template(),
        encoding="utf-8",
    )
    (src_root / "runner.py").write_text(
        _runner_module_template(
            family=family,
            module=module,
            runner_class=runner_class,
            description=description or f"{family} strategy runner",
            output_type=output_type,
        ),
        encoding="utf-8",
    )
    (tests_dir / "test_runner_smoke.py").write_text(
        "from " + module + ".runner import " + runner_class + "\n\n"
        "def test_runner_class_exists() -> None:\n"
        "    assert " + runner_class + " is not None\n",
        encoding="utf-8",
    )

    return {"family": family, "package_root": str(package_root)}


# --------------------------------------------------------------------------- #
# Scaffold template helpers
# --------------------------------------------------------------------------- #


def _apply_dot_overrides(config: dict[str, Any], overrides: dict[str, Any]) -> None:
    for key, value in overrides.items():
        target = config
        parts = key.split(".")
        for part in parts[:-1]:
            existing = target.get(part)
            if not isinstance(existing, dict):
                target[part] = {}
            target = target[part]
        target[parts[-1]] = value


def _assert_slug(value: str, *, label: str) -> None:
    if not value:
        raise ValueError(f"{label} must not be empty")
    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789-_")
    if any(ch not in allowed for ch in value):
        raise ValueError(f"{label} must use lowercase slug characters [a-z0-9-_]")


def _runner_class_name(family: str) -> str:
    parts = [p.capitalize() for p in family.replace("_", "-").split("-") if p]
    return "".join(parts) + "Runner"


def _preset_module_template() -> str:
    return (
        '"""Preset loader scaffold."""\n\n'
        "from __future__ import annotations\n\n"
        "from pathlib import Path\n"
        "from typing import Any\n\n"
        "import yaml\n\n"
        'PRESET_DIR = Path(__file__).resolve().parents[2] / "presets"\n\n\n'
        "def load_preset(name: str, overrides: dict[str, Any] | None = None) -> dict[str, Any]:\n"
        "    preset_name = name if name.endswith('.yaml') else f'{name}.yaml'\n"
        "    path = PRESET_DIR / preset_name\n"
        "    if not path.exists():\n"
        "        raise FileNotFoundError(f'Preset not found: {path}')\n"
        "    with path.open(encoding='utf-8') as handle:\n"
        "        config = yaml.safe_load(handle) or {}\n"
        "    if not isinstance(config, dict):\n"
        "        raise ValueError(f'Preset must be a YAML object: {path}')\n"
        "    if overrides:\n"
        "        for key, value in overrides.items():\n"
        "            target = config\n"
        "            parts = key.split('.')\n"
        "            for part in parts[:-1]:\n"
        "                existing = target.get(part)\n"
        "                if not isinstance(existing, dict):\n"
        "                    target[part] = {}\n"
        "                target = target[part]\n"
        "            target[parts[-1]] = value\n"
        "    return config\n\n\n"
        "def list_presets() -> list[str]:\n"
        "    if not PRESET_DIR.exists():\n"
        "        return []\n"
        "    return sorted(p.stem for p in PRESET_DIR.glob('*.yaml'))\n"
    )


def _runner_module_template(
    *,
    family: str,
    module: str,
    runner_class: str,
    description: str,
    output_type: str,
) -> str:
    return (
        '"""Strategy runner scaffold."""\n\n'
        "from __future__ import annotations\n\n"
        "from typing import Any\n\n"
        "import polars as pl\n\n"
        "from config import QUANT_DB_ROOT\n"
        "from strategies import StrategyRegistry, StrategyRunConfig, StrategyRunner, StrategyWeights\n\n"
        f"from {module}.preset import load_preset\n\n\n"
        "@StrategyRegistry.register(\n"
        f'    "{family}",\n'
        f"    description={description!r},\n"
        f'    runner_module="{module}.runner",\n'
        f'    presets_dir="lib/{family}/presets",\n'
        f'    docs="lib/{family}/README.md",\n'
        '    default_preset="default",\n'
        f'    output_type="{output_type}",\n'
        ")\n"
        f"class {runner_class}(StrategyRunner):\n"
        "    def __init__(self, config: dict[str, Any], save: bool = True, memory_version: str | None = None) -> None:\n"
        "        super().__init__(\n"
        "            StrategyRunConfig(\n"
        f"                strategy_id=str(config.get('name', '{family}')),\n"
        f'                strategy_type="{family}",\n'
        "                save=save,\n"
        "                db_root=QUANT_DB_ROOT,\n"
        "                memory_version=memory_version,\n"
        "            )\n"
        "        )\n"
        "        self.config = config\n\n"
        "    @classmethod\n"
        "    def from_preset(\n"
        "        cls,\n"
        "        name: str,\n"
        "        overrides: dict[str, Any] | None = None,\n"
        "        save: bool = True,\n"
        "        memory_version: str | None = None,\n"
        f'    ) -> "{runner_class}":\n'
        "        config = load_preset(name, overrides=overrides)\n"
        "        return cls(config=config, save=save, memory_version=memory_version)\n\n"
        "    def load_data(self) -> pl.DataFrame:\n"
        "        raise NotImplementedError('Implement data loading from local db parquet sources.')\n\n"
        "    def generate_weights(self, data: pl.DataFrame) -> StrategyWeights:\n"
        "        raise NotImplementedError('Implement strategy logic that returns StrategyWeights.')\n\n"
        "    def get_config_dict(self) -> dict[str, Any]:\n"
        "        return dict(self.config)\n"
    )
