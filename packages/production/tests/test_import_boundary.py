"""Hermetic import-boundary tests for the public Production core.

USAGE: ``uv run --package quant-factory-production pytest packages/production/tests/test_import_boundary.py -q``.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

# --------------------------------------------------------------------------- #
# Paths and allowlist
# --------------------------------------------------------------------------- #

PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "src" / "production"
ALLOWED_TOP_LEVEL = frozenset({"production", "strategies", "yaml", *sys.stdlib_module_names})


def _imports(path: Path) -> set[str]:
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


def test_public_core_imports_only_declared_dependencies() -> None:
    violations: list[str] = []
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        for name in sorted(_imports(path)):
            if name.split(".", 1)[0] not in ALLOWED_TOP_LEVEL:
                violations.append(f"{path.relative_to(PACKAGE_ROOT)} imports {name!r}")
    assert not violations, "public Production import violations:\n" + "\n".join(violations)
