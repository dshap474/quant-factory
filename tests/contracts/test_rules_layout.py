"""Contracts for the rules-file system layout.

Enforces the structure of the rules system itself (the rules about rules):
every package root carries its rules in `AGENTS.md`; no live AGENTS.md
reintroduces an append-only memory section; and every
`AGENTS.md` path a package's rules point at actually exists.

USAGE: uv run pytest tests/contracts/test_rules_layout.py -q
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# --------------------------------------------------------------------------- #
# Package roots
# --------------------------------------------------------------------------- #


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _package_roots() -> list[Path]:
    root = _repo_root()
    return [d for d in sorted((root / "packages").iterdir()) if d.is_dir()]


def _rules_path(pkg_root: Path) -> Path:
    return pkg_root / "AGENTS.md"


PACKAGE_ROOTS = _package_roots()
PACKAGE_IDS = [p.name for p in PACKAGE_ROOTS]

# --------------------------------------------------------------------------- #
# Structure: rules live in the package AGENTS.md
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("pkg_root", PACKAGE_ROOTS, ids=PACKAGE_IDS)
def test_package_has_rules_file(pkg_root: Path) -> None:
    rules = _rules_path(pkg_root)
    assert rules.is_file(), f"missing package rules: {rules}"


# --------------------------------------------------------------------------- #
# No memory sections in live agent docs
# --------------------------------------------------------------------------- #

_MEMORY_HEADER = re.compile(r"^#+ .*(?:Project|Package) Memory", re.MULTILINE)
_SKIP_PARTS = {".worktrees", "runs", "optimization", "_archive", "node_modules", ".venv"}


def test_no_memory_sections_in_agents_files() -> None:
    root = _repo_root()
    offenders = []
    for f in root.rglob("AGENTS.md"):
        parts = f.relative_to(root).parts
        if _SKIP_PARTS & set(parts) or any(p.startswith(".") for p in parts):
            continue
        if _MEMORY_HEADER.search(f.read_text()):
            offenders.append(str(f.relative_to(root)))
    assert not offenders, (
        "append-only memory sections are not allowed; "
        f"found reintroduced headers in: {offenders}"
    )


# --------------------------------------------------------------------------- #
# Pointer integrity: AGENTS.md paths named in package rules must exist
# --------------------------------------------------------------------------- #

_AGENTS_REF = re.compile(r"`([^`<>]*AGENTS\.md)`")


@pytest.mark.parametrize("pkg_root", PACKAGE_ROOTS, ids=PACKAGE_IDS)
def test_rules_agents_pointers_exist(pkg_root: Path) -> None:
    root = _repo_root()
    text = _rules_path(pkg_root).read_text()
    broken = []
    for ref in _AGENTS_REF.findall(text):
        candidates = (root / ref, pkg_root / ref)
        if not any(c.is_file() for c in candidates):
            broken.append(ref)
    assert not broken, f"{_rules_path(pkg_root)} points at missing AGENTS.md files: {broken}"
