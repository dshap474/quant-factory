"""Verify Data's optional extension loading boundary.

USAGE: ``uv run pytest packages/data/tests/unit/test_extension_loading.py -q``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import data.platform.storage.operator_surface_registry as operator_registry
import pytest
from data.platform.errors import DatasetContractError
from data.platform.ingestion.control_plane import DatasetHandlerRegistry

# --------------------------------------------------------------------------- #
# Dataset registry
# --------------------------------------------------------------------------- #


def test_core_imports_and_cli_work_without_extensions(tmp_path: Path) -> None:
    source_root = tmp_path / "src"
    shutil.copytree(Path(__file__).resolve().parents[2] / "src" / "data", source_root / "data")
    script = """
import data
import data.api
import data.query
from data.cli import app
from data.platform.errors import DatasetContractError
from data.platform.ingestion.control_plane import DatasetHandlerRegistry
from data.platform.storage.operator_surface_registry import OPERATOR_SCRIPTS
from typer.testing import CliRunner

assert DatasetHandlerRegistry.list() == []
assert OPERATOR_SCRIPTS == ()
try:
    DatasetHandlerRegistry.get("missing")
except DatasetContractError as exc:
    assert exc.code == "dataset_contract_error"
else:
    raise AssertionError("missing extension did not return the typed registry error")
assert CliRunner().invoke(app, ["--help"]).exit_code == 0
"""
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(source_root)
    subprocess.run([sys.executable, "-c", script], cwd=tmp_path, env=environment, check=True)


def test_dataset_registration_is_idempotent_for_the_same_handler() -> None:
    family = "extension_loading_idempotent"

    @DatasetHandlerRegistry.register(family)
    class DemoHandler:
        pass

    DatasetHandlerRegistry.register(family)(DemoHandler)
    DatasetHandlerRegistry._registry.pop(family)


def test_dataset_registration_rejects_duplicate_family() -> None:
    family = "extension_loading_duplicate"

    @DatasetHandlerRegistry.register(family)
    class FirstHandler:
        pass

    class SecondHandler:
        pass

    with pytest.raises(DatasetContractError, match="already registered"):
        DatasetHandlerRegistry.register(family)(SecondHandler)
    DatasetHandlerRegistry._registry.pop(family)


# --------------------------------------------------------------------------- #
# Operator registry
# --------------------------------------------------------------------------- #


def test_operator_registry_accepts_an_absent_extension_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(operator_registry, "EXTENSIONS_ROOT", tmp_path / "missing")
    assert operator_registry._load_operator_scripts() == ()


def test_operator_registry_rejects_duplicate_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pipelines_root = tmp_path / "pipelines"
    pipelines_root.mkdir()
    (pipelines_root / "_operator_surface_registry.py").write_text(
        """from data.platform.storage.operator_surface_registry import OperatorScript
entry = OperatorScript(path='raw/demo.py', role='demo', example='demo', cadence='on_demand', primary_write_surface='db/data/raw/demo', notes='demo')
OPERATOR_SCRIPTS = (entry, entry)
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(operator_registry, "EXTENSIONS_ROOT", tmp_path)
    with pytest.raises(DatasetContractError, match="already registered"):
        operator_registry._load_operator_scripts()
