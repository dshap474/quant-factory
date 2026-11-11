"""Every version of every active strategy family has the AGENTS.md §5/§6 shape.

Records, a parseable VERSION.toml with the paper split time, the shared phase/status
vocabulary and the lineage fields the Viz Evolution view draws, and a rerun.py exposing
``PRESETS`` and ``build``. rerun.py is checked by parsing, not importing, so a version whose
dependencies are missing still counts its shape. `example` is the reference to copy.

USAGE: uv run pytest packages/strategies/tests/test_version_conformance.py -q
"""

from __future__ import annotations

import ast
import datetime as dt
import re
import tomllib
from pathlib import Path

import pytest

# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #
LIB = Path(__file__).resolve().parents[1] / "extensions/lib"
RECORDS = ("SPEC.md", "CHANGELOG.md", "REVIEW.md", "HYPOTHESIS_OUTCOME.md")
VERSION_KEYS = ("phase", "status", "backtest_run_at", "backtest_run_at_source")
PHASES = {"preregistered", "implemented", "audited", "run", "recorded"}
STATUSES = {"active", "supported", "falsified", "inconclusive", "descriptive", "not_tested"}


def families() -> list[Path]:
    return sorted(p for p in LIB.iterdir()
                  if p.is_dir() and not p.name.startswith(("_", ".")) and (p / "optimization").is_dir())


def versions() -> list[Path]:
    found = []
    for family in families():
        opt = family / "optimization"
        found += [toml.parent for toml in opt.rglob("VERSION.toml") if re.fullmatch(r"v\d{3}", toml.parent.name)
                  and not any(part.startswith((".", "_")) for part in toml.relative_to(opt).parts)]
    return sorted(found)


VERSIONS = versions()


def label(path: Path) -> str:
    return str(path.relative_to(LIB))


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("family", families(), ids=lambda p: p.name)
def test_family_registers_a_runner(family: Path) -> None:
    assert any((family / "src").glob("*/runner.py")), f"{family.name} has no src/<pkg>/runner.py (AGENTS.md §6)"


@pytest.mark.parametrize("version", VERSIONS, ids=label)
def test_version_has_records(version: Path) -> None:
    missing = [name for name in RECORDS if not (version / name).is_file()]
    assert not missing, f"{label(version)} is missing {missing}; stub unrecorded ones honestly (AGENTS.md §5)"


@pytest.mark.parametrize("version", VERSIONS, ids=label)
def test_version_toml(version: Path) -> None:
    meta = tomllib.loads((version / "VERSION.toml").read_text())
    missing = [key for key in VERSION_KEYS if key not in meta]
    assert not missing, f"{label(version)}/VERSION.toml lacks {missing}"
    assert meta["phase"] in PHASES, f"{label(version)}/VERSION.toml phase {meta['phase']!r} not in {sorted(PHASES)}"
    assert meta["status"] in STATUSES, f"{label(version)}/VERSION.toml status {meta['status']!r} not in {sorted(STATUSES)}"


@pytest.mark.parametrize("version", VERSIONS, ids=label)
def test_version_lineage(version: Path) -> None:
    meta = tomllib.loads((version / "VERSION.toml").read_text())
    family = version.relative_to(LIB).parts[0]
    siblings = {path.name for path in VERSIONS if path.relative_to(LIB).parts[0] == family}
    for key in ("parent", "question") + (("finding",) if meta["phase"] == "recorded" else ()):
        assert isinstance(meta.get(key), str) and meta[key].strip(), f"{label(version)}/VERSION.toml needs a one-line {key} (AGENTS.md §5)"
    assert meta["parent"] == "none" or meta["parent"] in siblings - {version.name}, (
        f"{label(version)}/VERSION.toml parent {meta['parent']!r} is not another version of the family")
    selected = meta.get("baseline_selected_at")
    if selected is not None:
        stamp = selected if isinstance(selected, dt.datetime) else dt.datetime.fromisoformat(str(selected))
        assert stamp.utcoffset() == dt.timedelta(0), (
            f"{label(version)}/VERSION.toml baseline_selected_at {selected!r} is not a UTC timestamp")


def baselines() -> dict[str, str]:
    """Family -> the version with the latest baseline_selected_at, for families that have one."""
    latest: dict[str, tuple[dt.datetime, str]] = {}
    for version in VERSIONS:
        selected = tomllib.loads((version / "VERSION.toml").read_text()).get("baseline_selected_at")
        if selected is None:
            continue
        stamp = selected if isinstance(selected, dt.datetime) else dt.datetime.fromisoformat(str(selected))
        family = version.relative_to(LIB).parts[0]
        latest[family] = max(latest.get(family, (stamp, version.name)), (stamp, version.name))
    return {family: name for family, (_, name) in sorted(latest.items())}


@pytest.mark.parametrize(("family", "baseline"), baselines().items())
def test_baseline_diagrams(family: str, baseline: str) -> None:
    path = LIB / family / "docs/ARCHITECTURE.md"
    assert path.is_file(), f"{family} has baseline {baseline} but no docs/ARCHITECTURE.md (AGENTS.md §5)"
    text = path.read_text()
    title = re.search(r"^# Architecture — baseline (v\d{3})$", text, re.M)
    assert title and title[1] == baseline, (
        f"{family}/docs/ARCHITECTURE.md must be titled '# Architecture — baseline {baseline}' (the latest baseline)")
    sections = dict(re.findall(r"^## (.+)\n([\s\S]*?)(?=^## |\Z)", text, re.M))
    optional = ["Alpha model", "Risk model"]
    assert list(sections)[:2] == ["Pipeline", "State"] and all(
        name in optional for name in list(sections)[2:]) and list(sections)[2:] == sorted(
        list(sections)[2:], key=optional.index), (
        f"{family}/docs/ARCHITECTURE.md must have ## Pipeline, ## State, then optionally "
        f"## Alpha model and ## Risk model, not {list(sections)}")
    for name, body in sections.items():
        assert "```mermaid\n" in body, f"{family}/docs/ARCHITECTURE.md needs a ## {name} mermaid diagram"


DIMENSIONS_HEAD = "| Dimension | Status | Current choice or what was ruled out | Deciding versions |"
QUESTIONS_HEAD = "| Question | Evidence so far | What would distinguish the explanations |"


def cited(text: str) -> set[str]:
    """`v002–v004, v007` -> {v002, v003, v004, v007}."""
    found = set()
    for start, end in re.findall(r"v(\d{3})(?:\s*[–-]\s*v?(\d{3}))?", text):
        found |= {f"v{n:03d}" for n in range(int(start), int(end or start) + 1)}
    return found


@pytest.mark.parametrize("family", families(), ids=lambda p: p.name)
def test_design_space(family: Path) -> None:
    path = family / "optimization/DESIGN-SPACE.md"
    assert path.is_file(), f"{family.name} has no optimization/DESIGN-SPACE.md (AGENTS.md §5)"
    sections = dict(re.findall(r"^## (.+)\n([\s\S]*?)(?=^## |\Z)", path.read_text(), re.M))
    assert list(sections) == ["Dimensions", "Open questions"], (
        f"{family.name}/optimization/DESIGN-SPACE.md must have exactly ## Dimensions then ## Open questions, "
        f"not {list(sections)}")
    for name, head in (("Dimensions", DIMENSIONS_HEAD), ("Open questions", QUESTIONS_HEAD)):
        assert head in sections[name], f"{family.name} design space ## {name} needs the table {head}"
    siblings = {v.name for v in VERSIONS if v.relative_to(LIB).parts[0] == family.name}
    rows = [line for line in sections["Dimensions"].splitlines() if line.startswith("|")][2:]
    assert rows, f"{family.name} design space has no dimensions"
    for row in rows:
        cells = [cell.strip() for cell in row.strip("|").split(" | ")]
        assert len(cells) == 4, f"{family.name} design space row needs 4 cells: {row[:80]}"
        assert cells[1].startswith(("locked", "closed", "open")), (
            f"{family.name} dimension {cells[0]!r} status {cells[1]!r} must start with locked, closed or open")
        missing = cited(cells[3]) - siblings
        assert not missing, f"{family.name} dimension {cells[0]!r} cites unknown versions {sorted(missing)}"


@pytest.mark.parametrize("version", VERSIONS, ids=label)
def test_version_has_rerun(version: Path) -> None:
    path = version / "rerun.py"
    assert path.is_file(), f"{label(version)} has no rerun.py; use PRESETS = () with the reason if it can't rebuild"
    tree = ast.parse(path.read_text())
    assert ast.get_docstring(tree), f"{label(version)}/rerun.py needs a docstring (and the reason when PRESETS is empty)"
    names = {t.id for node in tree.body if isinstance(node, (ast.Assign, ast.AnnAssign))
             for t in (node.targets if isinstance(node, ast.Assign) else [node.target]) if isinstance(t, ast.Name)}
    names |= {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
    names |= {a.asname or a.name for node in tree.body if isinstance(node, ast.ImportFrom) for a in node.names}
    assert {"PRESETS", "build"} <= names, f"{label(version)}/rerun.py must define PRESETS and build"
