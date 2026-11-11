"""Docs API router - package docs discovery and markdown delivery."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from fastapi import APIRouter, HTTPException

from ..config import settings
from ..responses import ttl_cache

router = APIRouter()

_DOCS_ROOT_REL = Path("docs") / "quant-factory"
_FEATURES_MANIFEST_REL = Path("packages") / "features" / "FEATURES.yaml"
_GENERATED_FEATURE_DOC_PATH = "reference/feature-catalog-generated.md"


def _package_root(db_root: Path) -> Path:
    del db_root  # packages live in the repository checkout, not beside the lake
    return Path(settings.repo_root)


def _docs_root(db_root: Path) -> Path:
    package_root = _package_root(db_root)
    preferred = package_root / _DOCS_ROOT_REL
    if preferred.exists():
        return preferred
    return package_root / "docs"


def _humanize_name(value: str) -> str:
    return value.replace("_", " ").replace("-", " ").strip().title()


# A leading YAML block fenced by '---' lines.
_FRONTMATTER = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL)


def _split_frontmatter(markdown: str) -> tuple[dict[str, Any], str]:
    """Return (frontmatter mapping, body); an absent or malformed block reads as empty."""
    match = _FRONTMATTER.match(markdown)
    if not match:
        return {}, markdown
    try:
        loaded = yaml.safe_load(match.group(1))
    except yaml.YAMLError:
        loaded = None
    return (loaded if isinstance(loaded, dict) else {}), markdown[match.end() :]


def _extract_markdown_title(markdown: str, fallback: str) -> str:
    meta, markdown = _split_frontmatter(markdown)
    if isinstance(meta.get("title"), str) and meta["title"].strip():
        return meta["title"].strip()
    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            return re.sub(r"<[^>]+>", "", stripped.lstrip("#")).strip() or fallback
        break
    return fallback


def _normalize_doc_path(doc_path: str) -> str:
    candidate = doc_path.strip().strip("/")
    if not candidate:
        raise HTTPException(status_code=400, detail="doc_path is required")

    parsed = PurePosixPath(candidate)
    if parsed.is_absolute() or any(part in {"", ".", ".."} for part in parsed.parts):
        raise HTTPException(status_code=400, detail="Invalid doc_path")

    return "/".join(parsed.parts)


def _resolve_doc_file(db_root: Path, doc_path: str) -> tuple[Path, str]:
    normalized = _normalize_doc_path(doc_path)
    docs_root = _docs_root(db_root)
    target = docs_root / Path(*normalized.split("/"))

    if target.is_dir():
        target = target / "index.md"
        normalized = f"{normalized}/index.md"

    try:
        target.resolve().relative_to(docs_root.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Access denied") from exc

    return target, normalized


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with open(path) as file_handle:
            loaded = yaml.safe_load(file_handle) or {}
    except yaml.YAMLError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _render_feature_catalog_markdown(db_root: Path) -> str:
    package_root = _package_root(db_root)
    manifest = _load_yaml(package_root / _FEATURES_MANIFEST_REL)
    registry = _load_yaml(db_root / "features" / "REGISTRY.yaml")

    manifest_features = manifest.get("features", {})
    registry_features = registry.get("features", {})

    if not isinstance(manifest_features, dict):
        manifest_features = {}
    if not isinstance(registry_features, dict):
        registry_features = {}

    total_categories = len(manifest_features)
    active_categories = sum(
        1 for info in manifest_features.values() if isinstance(info, dict) and info.get("status", "active") == "active"
    )
    realized_datasets = len(registry_features)

    generated_at = datetime.now(timezone.utc).isoformat()

    lines: list[str] = [
        "# Feature Catalog (Auto-Generated)",
        "",
        f"Generated at: `{generated_at}`",
        "",
        "This page is generated from:",
        "",
        "- `packages/features/FEATURES.yaml`",
        "- `db/features/REGISTRY.yaml`",
        "",
        f"- Manifest categories: **{total_categories}**",
        f"- Active categories: **{active_categories}**",
        f"- Realized datasets in registry: **{realized_datasets}**",
        "",
        "## Categories",
        "",
        "| Category | Status | Resolutions | Realized Dataset(s) | Docs |",
        "|---|---|---|---|---|",
    ]

    for category, info in sorted(manifest_features.items()):
        if not isinstance(info, dict):
            continue

        status = str(info.get("status", "active"))
        resolutions = info.get("resolutions", [])
        if not isinstance(resolutions, list):
            resolutions = []
        resolution_text = ", ".join(str(res) for res in resolutions) or "-"

        realized_parts: list[str] = []
        for resolution in resolutions:
            key = f"{resolution}/{category}"
            realized = "-"
            registry_entry = registry_features.get(key, {})
            if isinstance(registry_entry, dict):
                realized = str(registry_entry.get("data_path", "-"))
            realized_parts.append(f"{resolution}: {realized}")
        latest_text = ", ".join(realized_parts) or "-"

        docs_path = str(info.get("docs", "")) or "-"

        def escape_cell(value: str) -> str:
            return value.replace("|", "\\|")

        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{escape_cell(str(category))}`",
                    escape_cell(status),
                    f"`{escape_cell(resolution_text)}`" if resolution_text != "-" else "-",
                    f"`{escape_cell(latest_text)}`" if latest_text != "-" else "-",
                    f"`{escape_cell(docs_path)}`" if docs_path != "-" else "-",
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- Categories in `_experiments` are not part of this canonical catalog.",
            "- A feature is effectively graduated when manifest, category package, and DB registry are aligned.",
        ]
    )

    return "\n".join(lines) + "\n"


_GENERATED_DOCS: dict[str, dict[str, Any]] = {
    _GENERATED_FEATURE_DOC_PATH: {
        "title": "Feature Catalog (Auto-Generated)",
        "builder": _render_feature_catalog_markdown,
    }
}


def _parse_index(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    loaded = _load_yaml(path)
    return loaded if isinstance(loaded, dict) else {}


def _build_dir_node(db_root: Path, current_dir: Path, rel_dir: str) -> dict[str, Any]:
    index = _parse_index(current_dir / "_index.yaml")
    title = str(index.get("title", "")).strip() if isinstance(index.get("title"), str) else ""

    node_title = title or (_humanize_name(current_dir.name) if rel_dir else "quant-factory Docs")

    children_by_key: dict[str, dict[str, Any]] = {}

    for child in sorted(current_dir.iterdir(), key=lambda item: item.name.lower()):
        if child.name.startswith("."):
            continue
        if child.name == "_index.yaml":
            continue

        if child.is_dir():
            child_rel = f"{rel_dir}/{child.name}" if rel_dir else child.name
            child_node = _build_dir_node(db_root, child, child_rel)
            if child_node["children"]:
                children_by_key[child.name] = child_node
            continue

        if child.is_file() and child.suffix.lower() == ".md":
            file_rel = f"{rel_dir}/{child.name}" if rel_dir else child.name
            children_by_key[child.name] = {
                "type": "file",
                "path": file_rel,
                "title": _humanize_name(child.stem),
                "generated": False,
            }

    for generated_path, generated_meta in _GENERATED_DOCS.items():
        generated_parent = PurePosixPath(generated_path).parent
        generated_parent_str = "" if str(generated_parent) == "." else str(generated_parent)
        if generated_parent_str != rel_dir:
            continue

        generated_name = PurePosixPath(generated_path).name
        if generated_name in children_by_key:
            continue

        children_by_key[generated_name] = {
            "type": "file",
            "path": generated_path,
            "title": str(generated_meta.get("title", _humanize_name(PurePosixPath(generated_path).stem))),
            "generated": True,
        }

    ordered_children: list[dict[str, Any]] = []
    consumed_keys: set[str] = set()

    raw_items = index.get("items", [])
    if isinstance(raw_items, list):
        for item in raw_items:
            item_path = ""
            item_title: str | None = None
            hidden = False

            if isinstance(item, str):
                item_path = item.strip().strip("/")
            elif isinstance(item, dict):
                item_path = str(item.get("path", "")).strip().strip("/")
                title_value = item.get("title")
                if isinstance(title_value, str) and title_value.strip():
                    item_title = title_value.strip()
                hidden = bool(item.get("hidden", False))

            if not item_path or "/" in item_path:
                continue

            child_node = children_by_key.get(item_path)
            if child_node is None:
                continue

            consumed_keys.add(item_path)
            if hidden:
                continue

            if item_title:
                child_node = {**child_node, "title": item_title}

            ordered_children.append(child_node)

    remaining = [child for key, child in children_by_key.items() if key not in consumed_keys]
    remaining.sort(key=lambda child: (0 if child["type"] == "dir" else 1, child["title"].lower()))
    ordered_children.extend(remaining)

    return {
        "type": "dir",
        "path": rel_dir,
        "title": node_title,
        "children": ordered_children,
    }


def _first_doc_path(node: dict[str, Any]) -> str | None:
    for child in node.get("children", []):
        if child.get("type") == "file":
            return child.get("path")
        if child.get("type") == "dir":
            nested = _first_doc_path(child)
            if nested:
                return nested
    return None


@ttl_cache(seconds=30)
def _cached_docs_tree(db_root: Path) -> dict[str, Any]:
    docs_root = _docs_root(db_root)
    if not docs_root.exists() or not docs_root.is_dir():
        raise HTTPException(status_code=404, detail="Docs root not found")

    tree = _build_dir_node(db_root, docs_root, "")
    default_path = "index.md" if (docs_root / "index.md").exists() else _first_doc_path(tree)

    return {
        "root": tree,
        "default_path": default_path,
    }


@router.get("/tree")
def get_docs_tree() -> dict[str, Any]:
    """Return docs tree metadata for docs navigation."""
    return _cached_docs_tree(settings.db_root)


@ttl_cache(seconds=30)
def _cached_doc_page(db_root: Path, doc_path: str) -> dict[str, Any]:
    normalized = _normalize_doc_path(doc_path)

    generated = _GENERATED_DOCS.get(normalized)
    if generated is not None:
        builder = generated["builder"]
        markdown = builder(db_root)
        title = str(generated.get("title", _humanize_name(PurePosixPath(normalized).stem)))
        return {
            "path": normalized,
            "title": title,
            "markdown": markdown,
            "modified": None,
            "generated": True,
        }

    target_file, normalized_path = _resolve_doc_file(db_root, normalized)

    if not target_file.exists() or not target_file.is_file():
        raise HTTPException(status_code=404, detail=f"Document '{normalized_path}' not found")

    if target_file.suffix.lower() != ".md":
        raise HTTPException(status_code=400, detail="Only markdown files are supported")

    markdown = target_file.read_text(encoding="utf-8")
    title = _extract_markdown_title(markdown, _humanize_name(target_file.stem))

    return {
        "path": normalized_path,
        "title": title,
        "markdown": markdown,
        "modified": target_file.stat().st_mtime,
        "generated": False,
    }


@router.get("/page/{doc_path:path}")
def get_doc_page(doc_path: str) -> dict[str, Any]:
    """Return markdown content + metadata for one doc page."""
    return _cached_doc_page(settings.db_root, doc_path)
