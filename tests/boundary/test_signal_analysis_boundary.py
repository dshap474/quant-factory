"""Keep the installed signal-analysis library independent of repository domains.

Usage: uv run pytest tests/boundary/test_signal_analysis_boundary.py
"""

from __future__ import annotations

import ast
import importlib.metadata
import subprocess
import sys
from pathlib import Path

import pytest
from packaging.requirements import Requirement

# --------------------------------------------------------------------------- #
# Dependency and executable example boundaries
# --------------------------------------------------------------------------- #

pytestmark = pytest.mark.boundary
_PACKAGE = Path(__file__).resolve().parents[2] / "packages/platform/signal-analysis"


def test_analysis_imports_only_standard_library_and_declared_dependencies():
    allowed = sys.stdlib_module_names | {"signal_analysis", "numpy", "polars", "scipy", "__future__"}
    for source in (_PACKAGE / "src/signal_analysis").rglob("*.py"):
        for node in ast.walk(ast.parse(source.read_text())):
            if isinstance(node, ast.Import):
                assert {alias.name.split(".")[0] for alias in node.names} <= allowed, source
            elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
                assert node.module.split(".")[0] in allowed, source


def test_declared_runtime_dependencies_are_only_numerical_libraries():
    requirements = importlib.metadata.requires("quant-factory-signal-analysis") or []
    assert {Requirement(requirement).name for requirement in requirements} == {"numpy", "polars", "scipy"}


def test_readme_example_runs_from_installed_package_outside_checkout(tmp_path):
    example = (_PACKAGE / "README.md").read_text().split("```python\n", 1)[1].split("```", 1)[0]
    code = (
        example
        + "\nimport sys\nassert not ({'features', 'signals', 'strategies', 'research', 'ml_engine', 'backtest'} & set(sys.modules))\n"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", code], cwd=tmp_path, capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stderr
