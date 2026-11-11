"""Tests for docs API endpoints."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def docs_db_root() -> Path:
    with tempfile.TemporaryDirectory() as tmp_dir:
        repo_root = Path(tmp_dir)
        db_root = repo_root / "db"
        db_root.mkdir(parents=True)

        docs_root = repo_root / "docs" / "quant-factory"
        reference_dir = docs_root / "reference"
        reference_dir.mkdir(parents=True)

        (docs_root / "_index.yaml").write_text(
            "title: Test Docs\n"
            "items:\n"
            "  - path: index.md\n"
            "    title: Home\n"
            "  - path: architecture.md\n"
            "  - path: reference\n"
        )
        (reference_dir / "_index.yaml").write_text(
            "title: Reference\n"
            "items:\n"
            "  - path: guide.md\n"
            "  - path: feature-catalog-generated.md\n"
        )

        (docs_root / "index.md").write_text("# Index\n\nWelcome.\n")
        (docs_root / "architecture.md").write_text("# Architecture\n\nSystem map.\n")
        (reference_dir / "guide.md").write_text("# Guide\n\nReference content.\n")
        (reference_dir / "raw.yaml").write_text("name: not-markdown\n")

        manifest_root = repo_root / "packages" / "features"
        manifest_root.mkdir(parents=True)
        (manifest_root / "FEATURES.yaml").write_text(
            "version: 2\n"
            "features:\n"
            "  macro:\n"
            "    status: active\n"
            "    description: Macro features\n"
            "    resolutions: [\"1d\"]\n"
            "    docs: _/macro/README.md\n"
            "  btc/futures:\n"
            "    status: planned\n"
            "    description: Futures features\n"
            "    resolutions: [\"1d\", \"5m\"]\n"
            "    docs: _/btc-futures/README.md\n"
        )

        registry_root = db_root / "features"
        registry_root.mkdir(parents=True)
        (registry_root / "REGISTRY.yaml").write_text(
            "version: 5\n"
            "features:\n"
            "  1d/macro:\n"
            "    data_path: features/1d/macro/data.parquet\n"
            "  1d/btc/futures:\n"
            "    data_path: features/1d/btc/futures/data.parquet\n"
        )

        yield db_root


def test_docs_tree_returns_ordered_nodes(client, set_db_root, docs_db_root):
    set_db_root(docs_db_root)

    response = client.get("/api/docs/tree")
    assert response.status_code == 200

    payload = response.json()
    assert payload["default_path"] == "index.md"
    assert payload["root"]["title"] == "Test Docs"

    children = payload["root"]["children"]
    assert [item["path"] for item in children] == ["index.md", "architecture.md", "reference"]

    reference = next(item for item in children if item["type"] == "dir" and item["path"] == "reference")
    reference_files = [item["path"] for item in reference["children"] if item["type"] == "file"]
    assert "reference/guide.md" in reference_files
    assert "reference/feature-catalog-generated.md" in reference_files


def test_docs_page_returns_markdown(client, set_db_root, docs_db_root):
    set_db_root(docs_db_root)

    response = client.get("/api/docs/page/reference/guide.md")
    assert response.status_code == 200

    payload = response.json()
    assert payload["path"] == "reference/guide.md"
    assert payload["title"] == "Guide"
    assert "Reference content" in payload["markdown"]
    assert payload["generated"] is False


def test_docs_page_returns_generated_feature_catalog(client, set_db_root, docs_db_root):
    set_db_root(docs_db_root)

    response = client.get("/api/docs/page/reference/feature-catalog-generated.md")
    assert response.status_code == 200

    payload = response.json()
    assert payload["generated"] is True
    assert payload["path"] == "reference/feature-catalog-generated.md"
    assert "Feature Catalog (Auto-Generated)" in payload["markdown"]
    assert "`macro`" in payload["markdown"]
    assert "1d: features/1d/macro/data.parquet" in payload["markdown"]


def test_docs_page_rejects_non_markdown(client, set_db_root, docs_db_root):
    set_db_root(docs_db_root)

    response = client.get("/api/docs/page/reference/raw.yaml")
    assert response.status_code == 400
    assert "Only markdown files" in response.json()["detail"]


def test_docs_page_rejects_path_traversal(client, set_db_root, docs_db_root):
    set_db_root(docs_db_root)

    response = client.get("/api/docs/page/%2E%2E%2Fsecret.md")
    assert response.status_code == 400
    assert "Invalid doc_path" in response.json()["detail"]


def test_docs_page_missing_document(client, set_db_root, docs_db_root):
    set_db_root(docs_db_root)

    response = client.get("/api/docs/page/does-not-exist.md")
    assert response.status_code == 404
