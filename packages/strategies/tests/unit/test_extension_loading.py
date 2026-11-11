"""Verify the public Strategies core works without a private overlay.

USAGE: ``uv run pytest packages/strategies/tests/unit/test_extension_loading.py -q``.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from strategies.paths import resolve_strategy_path

from strategies import StrategyRegistry

# --------------------------------------------------------------------------- #
# Zero-extension core
# --------------------------------------------------------------------------- #


def test_core_imports_and_cli_help_work_without_extensions(tmp_path: Path) -> None:
    source_root = tmp_path / "src"
    shutil.copytree(Path(__file__).resolve().parents[2] / "src" / "strategies", source_root / "strategies")
    script = """
import strategies
from strategies import StrategyRegistry
from strategies.api import validate_strategy_catalog
from strategies.cli import app
from strategies.manifest import list_strategy_types
from typer.testing import CliRunner

assert list_strategy_types(include_planned=True) == []
assert StrategyRegistry.list() == []
assert validate_strategy_catalog().valid
try:
    StrategyRegistry.get("missing")
except KeyError:
    pass
else:
    raise AssertionError("missing extension did not return the registry's existing not-found error")
assert CliRunner().invoke(app, ["--help"]).exit_code == 0
"""
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(source_root)
    subprocess.run([sys.executable, "-c", script], cwd=tmp_path, env=environment, check=True)


# --------------------------------------------------------------------------- #
# Path compatibility and registration
# --------------------------------------------------------------------------- #


def test_family_package_path_maps_under_extensions(tmp_path: Path) -> None:
    from strategies.paths import FAMILIES_ROOT
    from strategies.research_surface import STRATEGY_LIBRARY_ROOT

    assert resolve_strategy_path("lib/fam/presets", tmp_path) == tmp_path / "extensions/lib/fam/presets"
    assert resolve_strategy_path("extensions/lib/fam/presets", tmp_path) == tmp_path / "extensions/lib/fam/presets"
    assert STRATEGY_LIBRARY_ROOT == FAMILIES_ROOT


def test_strategy_registration_is_idempotent_for_same_class() -> None:
    name = "extension-loading-idempotent"
    runner_cls = type("DemoRunner", (), {"__module__": __name__})
    try:
        StrategyRegistry.register(name)(runner_cls)
        StrategyRegistry.register(name)(runner_cls)
        assert StrategyRegistry.get(name) is runner_cls
    finally:
        StrategyRegistry.unregister(name)


def test_strategy_registration_rejects_a_second_runner_for_one_name() -> None:
    name = "extension-loading-duplicate"
    first = type("FirstRunner", (), {"__module__": __name__})
    second = type("SecondRunner", (), {"__module__": __name__})
    try:
        StrategyRegistry.register(name)(first)
        with pytest.raises(ValueError, match="already registered"):
            StrategyRegistry.register(name)(second)
        assert StrategyRegistry.get(name) is first
    finally:
        StrategyRegistry.unregister(name)


def test_historical_version_module_cannot_replace_registered_family(tmp_path: Path) -> None:
    """Dynamic archived experiments may import without a sys.modules entry."""
    name = "archive-shadow-test"
    active = type("ActiveRunner", (), {"__module__": __name__})
    source = tmp_path / "optimization" / "version" / "v000" / "run.py"
    source.parent.mkdir(parents=True)
    source.write_text(
        "from strategies import StrategyRegistry\n"
        f"@StrategyRegistry.register({name!r})\n"
        "class HistoricalRunner:\n"
        "    def marker(self):\n"
        "        return 'historical'\n"
    )
    try:
        StrategyRegistry.register(name)(active)
        spec = importlib.util.spec_from_file_location("untracked_historical_run", source)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert "untracked_historical_run" not in sys.modules
        assert StrategyRegistry.get(name) is active
    finally:
        StrategyRegistry.unregister(name)
