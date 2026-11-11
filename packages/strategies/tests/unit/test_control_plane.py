"""Verify hermetic Strategies core discovery, resolver, and validation mechanics.

USAGE: ``uv run pytest packages/strategies/tests/unit/test_control_plane.py -q``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import ModuleType

import strategies.api as api
import strategies.bootstrap as bootstrap

from strategies import StrategyRegistry

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


# --------------------------------------------------------------------------- #
# Discovery and archive isolation
# --------------------------------------------------------------------------- #


def test_strategy_package_discovery_ignores_archive_dirs(tmp_path: Path, monkeypatch) -> None:
    families_root = tmp_path / "extensions" / "lib"
    (families_root / "active-family" / "src").mkdir(parents=True)
    (families_root / "_archive").mkdir()
    (families_root / "_template").mkdir()
    monkeypatch.setattr(StrategyRegistry, "package_root", tmp_path)

    assert [path.name for path in bootstrap.iter_strategy_package_dirs()] == ["active-family"]


def test_strategy_registry_ignores_manual_archive_imports(tmp_path: Path, monkeypatch) -> None:
    module_name = "strategies.archived_family.runner"
    module = ModuleType(module_name)
    archive_file = tmp_path / "extensions/lib/_archive/archived-family/src/archived_family/runner.py"
    archive_file.parent.mkdir(parents=True)
    archive_file.touch()
    module.__file__ = str(archive_file)
    monkeypatch.setitem(sys.modules, module_name, module)

    StrategyRegistry.clear()
    runner_cls = type("ArchivedRunner", (), {"__module__": module_name})
    StrategyRegistry.register("archived-family")(runner_cls)

    assert StrategyRegistry.list() == []


def test_archive_isolation_flags_registered_archive_runner(tmp_path: Path, monkeypatch) -> None:
    module_name = "strategies.leaked_archive.runner"
    module = ModuleType(module_name)
    archive_file = tmp_path / "extensions/lib/_archive/leaked/src/leaked/runner.py"
    archive_file.parent.mkdir(parents=True)
    archive_file.touch()
    module.__file__ = str(archive_file)
    monkeypatch.setitem(sys.modules, module_name, module)

    StrategyRegistry.clear()
    try:
        runner_cls = type("LeakedRunner", (), {"__module__": module_name})
        StrategyRegistry._registry["leaked-archive"] = runner_cls
        result = api.StrategyCatalogValidation()
        api._check_archived_runners_registered(result)
        assert any("archived module" in error for error in result.errors)
    finally:
        StrategyRegistry.clear()


# --------------------------------------------------------------------------- #
# Scaffold and legacy metadata resolution
# --------------------------------------------------------------------------- #


def test_scaffold_does_not_create_legacy_strategy_directory(tmp_path: Path, monkeypatch) -> None:
    families_root = tmp_path / "extensions" / "lib"
    monkeypatch.setattr(api, "FAMILIES_ROOT", families_root)

    api.scaffold("demo", description="Demo strategy")

    family_root = families_root / "demo"
    assert (family_root / "optimization/DESIGN-SPACE.md").exists()
    assert (family_root / "README.md").exists()
    assert not (family_root / "optimization/CHANGELOG.md").exists()
    assert not (family_root / "optimization/STRATEGY_MASTER_DOC.md").exists()
    assert not (family_root / ".strategy").exists()


def test_canonical_preset_durability_passes_when_frozen_copy_matches(tmp_path: Path) -> None:
    _write(tmp_path / "extensions/lib/fam/presets/def.yaml", "a: 1\n")
    _write(tmp_path / "extensions/lib/fam/optimization/v001/presets/def.yaml", "a: 1\n")
    result = api.StrategyCatalogValidation()

    api._check_canonical_preset_durability(
        result,
        strategy_type="fam",
        presets_dir="lib/fam/presets",
        default_preset="def",
        version="v001",
        strategies_root=tmp_path,
    )

    assert result.errors == []


def test_canonical_preset_durability_flags_missing_frozen_copy(tmp_path: Path) -> None:
    _write(tmp_path / "extensions/lib/fam/presets/def.yaml", "a: 1\n")
    result = api.StrategyCatalogValidation()

    api._check_canonical_preset_durability(
        result,
        strategy_type="fam",
        presets_dir="lib/fam/presets",
        default_preset="def",
        version="v001",
        strategies_root=tmp_path,
    )

    assert any("no frozen copy" in error for error in result.errors)


def test_canonical_preset_durability_flags_drifted_frozen_copy(tmp_path: Path) -> None:
    _write(tmp_path / "extensions/lib/fam/presets/def.yaml", "a: 1\n")
    _write(tmp_path / "extensions/lib/fam/optimization/v001/presets/def.yaml", "a: 2\n")
    result = api.StrategyCatalogValidation()

    api._check_canonical_preset_durability(
        result,
        strategy_type="fam",
        presets_dir="lib/fam/presets",
        default_preset="def",
        version="v001",
        strategies_root=tmp_path,
    )

    assert any("differs from live" in error for error in result.errors)


# --------------------------------------------------------------------------- #
# Output metadata
# --------------------------------------------------------------------------- #


def test_output_metadata_flags_foreign_strategy_type_label(tmp_path: Path) -> None:
    meta_path = tmp_path / "fam/versions/v001/final/meta.json"
    _write(meta_path, json.dumps({"strategy_type": "other-fam"}))
    result = api.StrategyCatalogValidation()

    api._check_output_metadata(result, active_types=["fam"], strategies_dir=tmp_path)

    assert any("other-fam" in warning for warning in result.warnings)


def test_output_metadata_silent_when_label_matches(tmp_path: Path) -> None:
    meta_path = tmp_path / "fam/versions/v001/final/meta.json"
    _write(meta_path, json.dumps({"strategy_type": "fam"}))
    result = api.StrategyCatalogValidation()

    api._check_output_metadata(result, active_types=["fam"], strategies_dir=tmp_path)

    assert result.warnings == []
