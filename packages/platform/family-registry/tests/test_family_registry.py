"""Behavior of the shared family registry: registration, discovery, and catalog reads.

USAGE: ``uv run pytest packages/platform/family-registry -q``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from family_registry import FamilyRegistry

# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


def _write_family(root: Path, family: str, package: str, *, status: str = "active") -> None:
    src = root / "extensions" / "lib" / family / "src" / package
    src.mkdir(parents=True)
    (src / "runner.py").write_text(
        "from conftest_registry import DemoRegistry\n"
        f"@DemoRegistry.register({family!r}, status={status!r}, presets_dir='extensions/lib/{family}/presets',"
        " default_preset='default')\n"
        "class Runner:\n"
        "    pass\n"
    )
    presets = root / "extensions" / "lib" / family / "presets"
    presets.mkdir()
    (presets / "default.yaml").write_text("name: default\n")


@pytest.fixture
def registry(tmp_path, monkeypatch):
    class DemoRegistry(FamilyRegistry):
        label = "Demo"
        package_root = tmp_path
        defaults = {"output_type": "demo"}

    shim = type(sys)("conftest_registry")
    shim.DemoRegistry = DemoRegistry
    monkeypatch.setitem(sys.modules, "conftest_registry", shim)
    _write_family(tmp_path, "alpha-fam", "alpha_fam")
    _write_family(tmp_path, "beta-fam", "beta_fam", status="planned")
    (tmp_path / "extensions" / "lib" / "_archive" / "src").mkdir(parents=True)
    for family in ("alpha-fam", "beta-fam"):
        monkeypatch.syspath_prepend(str(tmp_path / "extensions" / "lib" / family / "src"))
    yield DemoRegistry
    for module in ("alpha_fam", "alpha_fam.runner", "beta_fam", "beta_fam.runner"):
        sys.modules.pop(module, None)


# --------------------------------------------------------------------------- #
# Registration
# --------------------------------------------------------------------------- #


def test_subclasses_keep_separate_tables():
    class One(FamilyRegistry):
        pass

    class Two(FamilyRegistry):
        pass

    One.register("x")(type("R", (), {"__module__": __name__}))
    assert One.list() == ["x"] and Two.list() == []


def test_register_fills_defaults_and_rejects_a_second_class(registry):
    first = type("First", (), {"__module__": __name__})
    registry.register("demo", description="d")(first)
    registry.register("demo", description="d")(first)
    meta = registry.get_metadata("demo")
    assert meta == {
        "name": "demo",
        "status": "active",
        "description": "d",
        "presets_dir": "",
        "output_type": "demo",
        "runner_module": __name__,
        "runner_class": "First",
    }
    with pytest.raises(ValueError, match="already registered"):
        registry.register("demo")(type("Second", (), {"__module__": __name__}))
    with pytest.raises(KeyError):
        registry.get("missing")


def test_historical_copies_never_register(registry, tmp_path):
    source = tmp_path / "optimization" / "version" / "v001" / "runner.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        "from conftest_registry import DemoRegistry\n"
        "@DemoRegistry.register('old')\n"
        "class Old:\n"
        "    def marker(self):\n"
        "        return 1\n"
    )
    exec(compile(source.read_text(), str(source), "exec"), {"__name__": "untracked_copy"})
    assert "old" not in registry.list()


# --------------------------------------------------------------------------- #
# Discovery and catalog
# --------------------------------------------------------------------------- #


def test_populate_imports_families_and_drops_planned(registry):
    assert [p.name for p in registry.package_dirs()] == ["alpha-fam", "beta-fam"]
    assert registry.runner_modules() == ["alpha_fam.runner", "beta_fam.runner"]
    assert registry.populate() == ["alpha-fam"]
    assert registry.populate(include_planned=True) == ["alpha-fam", "beta-fam"]


def test_catalog_discovers_on_first_read(registry, tmp_path):
    catalog = registry.catalog()
    assert sorted(catalog) == ["alpha-fam", "beta-fam"]
    assert catalog["alpha-fam"]["docs"] == "extensions/lib/alpha-fam/README.md"
    assert "name" not in catalog["alpha-fam"]
    assert registry.presets("alpha-fam") == ["default"]
    assert registry.default_preset("alpha-fam") == "default"
    assert registry.get_presets_dir("alpha-fam") == tmp_path / "extensions/lib/alpha-fam/presets"
    assert registry.import_runner_module("alpha-fam").Runner is registry.get("alpha-fam")


def test_missing_extensions_root_discovers_nothing(tmp_path):
    class Empty(FamilyRegistry):
        package_root = tmp_path / "absent"

    assert Empty.populate() == [] and Empty.catalog() == {}
