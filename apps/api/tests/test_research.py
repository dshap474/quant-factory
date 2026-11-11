"""Tests for generalized research discovery and document serving.

USAGE: ``uv run pytest apps/api/tests/test_research.py -q``
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_packages_discovers_sandbox_viz_manifests(client, set_db_root, tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    db_root = repo_root / "db"
    db_root.mkdir(parents=True)
    sandbox = repo_root / "packages" / "research" / "sandbox"
    for project, manifest in (
        ("wired-lab", {"id": "wired-lab", "title": "Wired Lab", "subtitle": "Research.", "surface": "lab_db"}),
        ("other-lab", {"id": "other-lab", "title": "Other Lab", "subtitle": "Minimal.", "surface": "lab_db"}),
    ):
        (sandbox / project).mkdir(parents=True)
        (sandbox / project / "viz.json").write_text(json.dumps(manifest))
    (sandbox / "unwired-lab").mkdir(parents=True)  # No viz.json -> not discovered.
    set_db_root(db_root)

    payload = client.get("/api/research/packages").json()
    ids = [item["id"] for item in payload["packages"]]
    assert ids == ["other-lab", "wired-lab"]

    other = next(item for item in payload["packages"] if item["id"] == "other-lab")
    assert other["route"] == "/sandbox/other-lab"
    assert other["nav_path"] == ["Sandbox", "other-lab"]
    assert other["package_path"] == "packages/research/sandbox/other-lab"

    sandbox_node = payload["nav"][0]
    assert sandbox_node["title"] == "Sandbox"
    # Wired projects become folders keyed by their sandbox directory; unwired-lab has no README.
    assert [child["id"] for child in sandbox_node["children"]] == ["sandbox:other-lab", "sandbox:wired-lab"]
    assert [child["id"] for child in sandbox_node["children"][0]["children"]] == ["other-lab"]


# --------------------------------------------------------------------------- #
# Research documents
# --------------------------------------------------------------------------- #


def _write_research_tree(tmp_path: Path) -> Path:
    """Build a minimal packages/research layout and return the lake root."""
    repo_root = tmp_path / "repo"
    db_root = repo_root / "db"
    db_root.mkdir(parents=True)
    research = repo_root / "packages" / "research"

    corpus = research / "corpus"
    (corpus / "wiki" / "factors").mkdir(parents=True)
    (corpus / "wiki" / "factors" / "factors.md").write_text("# Factors\n")
    (corpus / "wiki" / "README.md").write_text("# Wiki\n")
    (corpus / "sources" / "books").mkdir(parents=True)
    (corpus / "sources" / "books" / "example-book.md").write_text("Body only.\n")
    (corpus / "empty-dir").mkdir()
    (corpus / ".hidden").mkdir()
    (corpus / ".hidden" / "secret.md").write_text("# Secret\n")
    (corpus / "top.md").write_text("# Top\n")
    (corpus / "notes.txt").write_text("ignored")

    docs = research / "docs"
    (docs / "models").mkdir(parents=True)
    (docs / "models" / "decision.md").write_text("# Decision\n")
    (docs / "empty-dir").mkdir()
    (docs / "overview.md").write_text("# Overview\n")

    source = research / "src"
    (source / "alpha-tool").mkdir(parents=True)
    (source / "alpha-tool" / "README.md").write_text("# Alpha\n")
    (source / "alpha-tool" / "AGENTS.md").write_text("# Agents\n")
    (source / "beta-tool").mkdir()
    (source / "beta-tool" / "AGENTS.md").write_text("# Beta agents\n")
    (source / "gamma-tool").mkdir()
    (source / "gamma-tool" / "zeta.md").write_text("# Zeta\n")
    (source / "gamma-tool" / "alpha-notes.md").write_text("# Alpha notes\n")
    (source / "delta-tool").mkdir()  # No markdown -> skipped.

    return db_root


def test_docs_tree_nesting_and_sorting(client, set_db_root, tmp_path: Path) -> None:
    set_db_root(_write_research_tree(tmp_path))

    nav = client.get("/api/research/docs").json()["nav"]
    assert [child["id"] for child in nav] == ["dir:docs/models", "doc:docs/overview.md"]
    assert nav[0]["children"][0] == {
        "id": "doc:docs/models/decision.md",
        "title": "decision",
        "kind": "doc",
        "route": "/research/doc/docs/models/decision.md",
        "doc_path": "docs/models/decision.md",
        "subtitle": None,
    }


def test_nav_sandbox_wired_and_unwired_shapes(client, set_db_root, tmp_path: Path) -> None:
    db_root = _write_research_tree(tmp_path)
    sandbox = db_root.parent / "packages" / "research" / "sandbox"

    (sandbox / "readme-only-lab").mkdir(parents=True)
    (sandbox / "readme-only-lab" / "README.md").write_text("# Notes\n")
    (sandbox / "other-lab").mkdir()
    (sandbox / "other-lab" / "viz.json").write_text(json.dumps({"id": "other-lab", "title": "Other Lab"}))
    (sandbox / "plain-lab").mkdir()
    (sandbox / "plain-lab" / "README.md").write_text("# Plain\n")
    (sandbox / "no-readme-lab").mkdir()  # No viz.json and no README -> skipped.
    set_db_root(db_root)

    sandbox_node = client.get("/api/research/packages").json()["nav"][0]
    children = {child["id"]: child for child in sandbox_node["children"]}
    assert list(children) == [
        "sandbox:other-lab",
        "doc:sandbox/plain-lab/README.md",
        "doc:sandbox/readme-only-lab/README.md",
    ]

    # Wired project without a README carries the package leaf only.
    assert [child["kind"] for child in children["sandbox:other-lab"]["children"]] == ["package"]

    plain = children["doc:sandbox/plain-lab/README.md"]
    assert plain["kind"] == "doc"
    assert plain["title"] == "plain-lab"
    assert plain["route"] == "/sandbox/doc/sandbox/plain-lab/README.md"


def test_nav_source_doc_preference_fallback(client, set_db_root, tmp_path: Path) -> None:
    set_db_root(_write_research_tree(tmp_path))

    source = client.get("/api/research/packages").json()["nav"][1]
    assert [(child["title"], child["doc_path"]) for child in source["children"]] == [
        ("alpha-tool", "src/alpha-tool/README.md"),
        ("beta-tool", "src/beta-tool/AGENTS.md"),
        ("gamma-tool", "src/gamma-tool/alpha-notes.md"),
    ]


def test_research_doc_returns_markdown_page(client, set_db_root, tmp_path: Path) -> None:
    set_db_root(_write_research_tree(tmp_path))

    payload = client.get("/api/research/doc/corpus/wiki/factors/factors.md").json()
    assert payload["path"] == "corpus/wiki/factors/factors.md"
    assert payload["title"] == "Factors"
    assert payload["markdown"] == "# Factors\n"
    assert payload["generated"] is False
    assert isinstance(payload["modified"], float)


def test_research_doc_title_falls_back_to_stem(client, set_db_root, tmp_path: Path) -> None:
    set_db_root(_write_research_tree(tmp_path))

    payload = client.get("/api/research/doc/corpus/sources/books/example-book.md").json()
    assert payload["title"] == "Example Book"


def test_research_doc_returns_source_markdown(client, set_db_root, tmp_path: Path) -> None:
    set_db_root(_write_research_tree(tmp_path))

    payload = client.get("/api/research/doc/src/alpha-tool/README.md").json()
    assert payload["path"] == "src/alpha-tool/README.md"
    assert payload["markdown"] == "# Alpha\n"


@pytest.mark.parametrize(
    ("doc_path", "expected_status"),
    [
        ("corpus/%2E%2E/%2E%2E/db/secret.md", 400),  # Encoded traversal reaches the handler unnormalized.
        ("corpus/wiki/factors/factors.txt", 400),  # Non-markdown suffix.
        ("db/secret.md", 403),  # Outside the corpus/sandbox/src roots.
        ("tools/alpha-tool/README.md", 403),  # Renamed root has no compatibility alias.
        ("packages/research/corpus/top.md", 403),
        ("corpus/wiki/missing.md", 404),
    ],
)
def test_research_doc_rejects_bad_paths(
    client,
    set_db_root,
    tmp_path: Path,
    doc_path: str,
    expected_status: int,
) -> None:
    db_root = _write_research_tree(tmp_path)
    (db_root / "secret.md").write_text("# Secret\n")
    (db_root.parent / "packages" / "research" / "corpus" / "wiki" / "factors" / "factors.txt").write_text("plain")
    set_db_root(db_root)

    assert client.get(f"/api/research/doc/{doc_path}").status_code == expected_status


def test_research_doc_empty_path_returns_400(client, set_db_root, tmp_path: Path) -> None:
    set_db_root(_write_research_tree(tmp_path))

    assert client.get("/api/research/doc/").status_code == 400


def test_research_asset_serves_image(client, set_db_root, tmp_path: Path) -> None:
    db_root = _write_research_tree(tmp_path)
    assets = db_root.parent / "packages" / "research" / "corpus" / "sources" / "books" / "book.assets"
    assets.mkdir(parents=True)
    (assets / "figure-1.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    set_db_root(db_root)

    response = client.get("/api/research/asset/corpus/sources/books/book.assets/figure-1.png")
    assert response.status_code == 200
    assert response.content == b"\x89PNG\r\n\x1a\n"


def test_research_asset_rejects_bad_suffix_and_missing(client, set_db_root, tmp_path: Path) -> None:
    set_db_root(_write_research_tree(tmp_path))

    assert client.get("/api/research/asset/corpus/top.md").status_code == 400
    assert client.get("/api/research/asset/corpus/missing.png").status_code == 404
    assert client.get("/api/research/asset/db/secret.png").status_code == 403
