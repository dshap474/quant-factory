"""Layer-boundary guard: ``data.platform`` (shared mechanics) must never import ``data.features`` (family slices).

USAGE:
    uv run pytest packages/data/tests/unit/test_layer_boundaries.py -q
"""

from __future__ import annotations

import ast
from pathlib import Path

import data

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

PLATFORM_ROOT = Path(data.__file__).parent / "platform"


def _feature_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("data.features"):
            hits.append(f"{path}:{node.lineno} from {node.module}")
        elif isinstance(node, ast.Import):
            hits.extend(
                f"{path}:{node.lineno} import {a.name}" for a in node.names if a.name.startswith("data.features")
            )
    return hits


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


def test_platform_never_imports_features() -> None:
    offenders = [hit for path in sorted(PLATFORM_ROOT.rglob("*.py")) for hit in _feature_imports(path)]
    assert not offenders, "data.platform must stay family-agnostic:\n" + "\n".join(offenders)
