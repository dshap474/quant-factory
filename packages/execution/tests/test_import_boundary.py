"""Hermetic import-boundary tests for the public Execution core.

USAGE: ``uv run --project packages/execution pytest packages/execution/tests/test_import_boundary.py -v``.
"""

from __future__ import annotations

import ast
import importlib.util
import subprocess
import sys
from pathlib import Path

# --------------------------------------------------------------------------- #
# Paths and allowlists
# --------------------------------------------------------------------------- #

PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "src" / "execution"
ALLOWED_TOP_LEVEL = frozenset({"execution", *sys.stdlib_module_names})


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _iter_python_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if path.is_file())


def _imported_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None and not node.level:
            names.add(node.module)
    return names


# --------------------------------------------------------------------------- #
# Public-core boundary
# --------------------------------------------------------------------------- #


def test_public_core_imports_only_stdlib_and_execution() -> None:
    """Keep provider clients, extensions, and upstream packages out of core."""
    assert PACKAGE_ROOT.is_dir(), f"missing package root: {PACKAGE_ROOT}"
    violations: list[str] = []
    for path in _iter_python_files(PACKAGE_ROOT):
        for name in sorted(_imported_names(path)):
            if name.split(".", 1)[0] not in ALLOWED_TOP_LEVEL:
                violations.append(f"{path.relative_to(PACKAGE_ROOT)} imports {name!r}")
    assert not violations, "public Execution core import violations:\n" + "\n".join(violations)


def test_provider_packages_are_not_nested_under_execution() -> None:
    """Old provider-owned module trees must not return as compatibility shims."""
    assert not (PACKAGE_ROOT / "live").exists()
    assert not (PACKAGE_ROOT / "venues").exists()
    assert importlib.util.find_spec("execution.live") is None
    assert importlib.util.find_spec("execution.venues") is None


def test_execution_modules_import_cleanly() -> None:
    """Import every public core submodule without loading a private venue."""
    import execution.accounting
    import execution.events
    import execution.instruments
    import execution.journal
    import execution.locking
    import execution.ownership
    import execution.policies
    import execution.sizing
    import execution.targets

    import execution

    assert execution.__version__ == "0.1.0"
    assert not hasattr(execution.instruments, "SUPPORTED_VENUE")

    result = subprocess.run(
        [sys.executable, "-c", "import execution, sys; assert 'venues' not in sys.modules"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_core_init_does_not_import_extensions_or_provider_clients() -> None:
    """The root public import stays valid when the extension overlay is absent."""
    names = _imported_names(PACKAGE_ROOT / "__init__.py")
    forbidden = {
        name
        for name in names
        if name.split(".", 1)[0]
        in {
            "venues",
            "ccxt",
            "coinbase",
            "coinbase_advanced_client",
            "hyperliquid",
            "hyperliquid_client",
        }
    }
    assert not forbidden, f"execution/__init__.py imports extension or provider surfaces: {sorted(forbidden)}"
