"""General research discovery, navigation, documents, and assets.

USAGE::

    GET /api/research/packages            sandbox packages and the Sandbox / Source tree
    GET /api/research/docs                the packages/research/docs tree
    GET /api/research/corpus/wiki         wiki notes with their links and citations
    GET /api/research/corpus/sources      every corpus work with its texts and chapters
    GET /api/research/corpus/search?q=kelly+criterion   full-text search over the wiki and sources
    GET /api/research/doc/corpus/topic.md
    GET /api/research/asset/corpus/topic.assets/figure.png
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports
# --------------------------------------------------------------------------- #
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable

import yaml
from fastapi import APIRouter, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse

from ..config import settings
from ..corpus_search import CorpusSearch, SearchDocument
from ..responses import ttl_cache
from .docs import _extract_markdown_title, _humanize_name, _normalize_doc_path, _split_frontmatter

# --------------------------------------------------------------------------- #
# Constants and extension catalog
# --------------------------------------------------------------------------- #

router = APIRouter()
_DISCLAIMER = "Research only. Results and markers are not approved or executed trades."
_RESEARCH_REL = Path("packages/research")
_SANDBOX_REL = _RESEARCH_REL / "sandbox"
_RESEARCH_DOC_ROOTS = ("corpus", "sandbox", "src", "docs")
_SOURCE_DOC_PREFERENCE = ("README.md", "AGENTS.md")
_RESEARCH_ASSET_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"})
_SOURCE_KINDS = ("books", "papers", "references")
# Inline markdown link targets: [text](target "optional title").
_MARKDOWN_LINK = re.compile(r"\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
# Corpus claim citations, e.g. [example-source:C01].
_CITATION = re.compile(r"\s*\[[a-z0-9][a-z0-9-]*:[A-Za-z0-9-]+\]")
_SUMMARY_CHARS = 360


def _note_summary(meta: dict[str, Any], body: str) -> str:
    """A note's lead: its frontmatter summary, else its first prose paragraph, as plain text."""
    for key in ("summary", "description"):
        if isinstance(meta.get(key), str) and meta[key].strip():
            return " ".join(meta[key].split())
    for block in re.split(r"\n\s*\n", body):
        text = block.strip()
        if not text or text[0] in "#|>-*<`" or text[:2].rstrip(".").isdigit():
            continue
        text = _CITATION.sub("", " ".join(text.split()))
        text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)
        text = re.sub(r"[*_`]", "", text)
        if len(text) <= _SUMMARY_CHARS:
            return text
        cut = text[:_SUMMARY_CHARS]
        end = cut.rfind(". ")
        return cut[: end + 1] if end > _SUMMARY_CHARS // 2 else cut.rstrip() + "…"
    return ""


@dataclass(frozen=True, slots=True)
class ResearchCatalogEntry:
    extension_id: str
    order: int
    summary: Callable[[], dict[str, Any]]
    sandbox_directory: str | None
    include_without_manifest: bool
    disclaimer: str | None


def register_research_catalog_entry(
    app: FastAPI,
    *,
    extension_id: str,
    order: int,
    summary: Callable[[], dict[str, Any]],
    sandbox_directory: str | None = None,
    include_without_manifest: bool = False,
    disclaimer: str | None = None,
) -> None:
    """Register one extension-owned research summary on this app instance."""
    entries = getattr(app.state, "research_catalog_entries", None)
    if entries is None:
        entries = {}
        app.state.research_catalog_entries = entries
    if extension_id in entries:
        raise RuntimeError(f"Duplicate research catalog extension ID: {extension_id}")
    entries[extension_id] = ResearchCatalogEntry(
        extension_id=extension_id,
        order=order,
        summary=summary,
        sandbox_directory=sandbox_directory,
        include_without_manifest=include_without_manifest,
        disclaimer=disclaimer,
    )


def _catalog_disclaimer(app: FastAPI) -> str:
    entries = getattr(app.state, "research_catalog_entries", {})
    overrides = [entry for entry in entries.values() if entry.disclaimer is not None]
    if not overrides:
        return _DISCLAIMER
    return min(overrides, key=lambda entry: (entry.order, entry.extension_id)).disclaimer or _DISCLAIMER


# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #


def _db_root() -> Path:
    return Path(settings.db_root)


def _repo_root() -> Path:
    return Path(settings.repo_root).resolve()


def _research_root() -> Path:
    return _repo_root() / _RESEARCH_REL


def _sandbox_root() -> Path:
    return _repo_root() / _SANDBOX_REL


def _source_root() -> Path:
    return _research_root() / "src"


def _corpus_root() -> Path:
    return _research_root() / "corpus"


def _docs_root() -> Path:
    return _research_root() / "docs"


# --------------------------------------------------------------------------- #
# Discovery and routes
# --------------------------------------------------------------------------- #


def _sandbox_manifest_summary(manifest: Path) -> dict[str, Any] | None:
    """Build a minimal package summary from a sandbox project's viz.json."""
    try:
        data = json.loads(manifest.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    project_id = data.get("id") or manifest.parent.name
    return {
        "id": project_id,
        "title": data.get("title", project_id),
        "subtitle": data.get("subtitle"),
        "route": f"/sandbox/{project_id}",
        "nav_path": ["Sandbox", project_id],
        "surface": data.get("surface"),
        "disclaimer": _DISCLAIMER,
        "package_path": (_SANDBOX_REL / manifest.parent.name).as_posix(),
        "package_exists": True,
    }


def _research_packages(app: FastAPI) -> list[dict[str, Any]]:
    """Return public manifests plus summaries registered by installed extensions."""
    entries = sorted(
        getattr(app.state, "research_catalog_entries", {}).values(),
        key=lambda entry: (entry.order, entry.extension_id),
    )
    packages = [entry.summary() for entry in entries if entry.include_without_manifest]
    entries_by_directory = {
        entry.sandbox_directory: entry
        for entry in entries
        if entry.sandbox_directory is not None and not entry.include_without_manifest
    }
    for manifest in sorted(_sandbox_root().glob("*/viz.json")):
        registered = entries_by_directory.get(manifest.parent.name)
        summary = registered.summary() if registered is not None else _sandbox_manifest_summary(manifest)
        if summary is not None:
            packages.append(summary)
    return packages


def _nav_folder(node_id: str, title: str, children: list[dict[str, Any]]) -> dict[str, Any]:
    return {"id": node_id, "title": title, "kind": "folder", "children": children}


def _nav_package_leaf(pkg: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": pkg["id"],
        "title": pkg["title"],
        "kind": "package",
        "route": pkg["route"],
        "subtitle": pkg.get("subtitle"),
        "surface": pkg.get("surface"),
    }


def _nav_doc_leaf(doc_path: str, title: str, route_prefix: str = "/sandbox/doc") -> dict[str, Any]:
    """Read-only markdown leaf; `doc_path` is POSIX relative to packages/research."""
    return {
        "id": f"doc:{doc_path}",
        "title": title,
        "kind": "doc",
        "route": f"{route_prefix}/{doc_path}",
        "doc_path": doc_path,
        "subtitle": None,
    }


def _markdown_tree(directory: Path, rel_dir: str, route_prefix: str) -> list[dict[str, Any]]:
    """Recursive markdown tree; directories without any markdown are dropped."""
    folders: list[dict[str, Any]] = []
    files: list[dict[str, Any]] = []

    for child in sorted(directory.iterdir(), key=lambda item: item.name.lower()):
        if child.name.startswith("."):
            continue
        child_rel = f"{rel_dir}/{child.name}"
        if child.is_dir():
            nested = _markdown_tree(child, child_rel, route_prefix)
            if nested:
                folders.append(_nav_folder(f"dir:{child_rel}", child.name, nested))
            continue
        if child.is_file() and child.suffix.lower() == ".md":
            files.append(_nav_doc_leaf(child_rel, child.stem, route_prefix))

    return folders + files


def _docs_nav() -> list[dict[str, Any]]:
    root = _docs_root()
    if not root.is_dir():
        return []
    return _markdown_tree(root, "docs", "/research/doc")


def _package_dir_name(pkg: dict[str, Any]) -> str | None:
    """Sandbox directory a wired package belongs to."""
    package_path = pkg.get("package_path")
    if isinstance(package_path, str) and package_path:
        return PurePosixPath(package_path).name
    nav_path = pkg.get("nav_path")
    if isinstance(nav_path, list) and len(nav_path) > 1 and isinstance(nav_path[-1], str):
        return nav_path[-1]
    return None


def _sandbox_nav(packages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One entry per sandbox project: wired projects become folders, others README leaves."""
    root = _sandbox_root()
    if not root.is_dir():
        return []

    leaves_by_dir: dict[str, list[dict[str, Any]]] = {}
    for pkg in packages:
        dir_name = _package_dir_name(pkg)
        if dir_name:
            leaves_by_dir.setdefault(dir_name, []).append(_nav_package_leaf(pkg))

    nodes: list[dict[str, Any]] = []
    for child in sorted(root.iterdir(), key=lambda item: item.name.lower()):
        if child.name.startswith(".") or not child.is_dir():
            continue
        readme = child / "README.md"
        readme_rel = f"sandbox/{child.name}/README.md"
        wired = leaves_by_dir.get(child.name)
        if wired:
            children = list(wired)
            if readme.is_file():
                children.append(_nav_doc_leaf(readme_rel, "README"))
            nodes.append(_nav_folder(f"sandbox:{child.name}", child.name, children))
            continue
        if readme.is_file():
            nodes.append(_nav_doc_leaf(readme_rel, child.name))

    return nodes


def _source_doc_name(directory: Path) -> str | None:
    """README, else AGENTS, else the alphabetically first top-level markdown file."""
    for preferred in _SOURCE_DOC_PREFERENCE:
        if (directory / preferred).is_file():
            return preferred
    markdown = sorted(
        (item.name for item in directory.iterdir() if item.is_file() and item.suffix.lower() == ".md"),
        key=str.lower,
    )
    return markdown[0] if markdown else None


def _source_nav() -> list[dict[str, Any]]:
    root = _source_root()
    if not root.is_dir():
        return []

    nodes: list[dict[str, Any]] = []
    for child in sorted(root.iterdir(), key=lambda item: item.name.lower()):
        if child.name.startswith(".") or not child.is_dir():
            continue
        doc_name = _source_doc_name(child)
        if doc_name is None:
            continue
        nodes.append(_nav_doc_leaf(f"src/{child.name}/{doc_name}", child.name))

    return nodes


def _research_nav(packages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sandbox surface skeleton: sandbox projects, then the research source tools."""
    return [
        _nav_folder("sandbox", "Sandbox", _sandbox_nav(packages)),
        _nav_folder("src", "Source", _source_nav()),
    ]


# --------------------------------------------------------------------------- #
# Corpus
# --------------------------------------------------------------------------- #


def _corpus_link_targets(markdown: str, note_rel: str) -> list[str]:
    """Corpus-relative paths of a note's relative markdown links (anchors and URLs dropped)."""
    base = PurePosixPath(note_rel).parent
    targets: list[str] = []
    for raw in _MARKDOWN_LINK.findall(markdown):
        target = raw.split("#", 1)[0]
        if not target or "://" in target or target.startswith(("/", "mailto:")):
            continue
        parts: list[str] = []
        for part in (base / target).parts:
            if part == "..":
                if not parts:
                    break
                parts.pop()
            elif part not in ("", "."):
                parts.append(part)
        else:
            if parts:
                targets.append("/".join(parts).replace("%20", " "))
    return targets


@ttl_cache(seconds=30)
def _cached_corpus_wiki(db_root: Path) -> dict[str, Any]:
    root = _corpus_root()
    wiki = root / "wiki"
    notes: list[dict[str, Any]] = []
    if wiki.is_dir():
        for path in sorted(wiki.rglob("*.md"), key=lambda item: item.as_posix().lower()):
            rel = path.relative_to(root)
            if any(part.startswith(".") for part in rel.parts):
                continue
            markdown = path.read_text(encoding="utf-8", errors="replace")
            targets = _corpus_link_targets(markdown, rel.as_posix())
            meta, body = _split_frontmatter(markdown)
            notes.append(
                {
                    "path": rel.as_posix(),
                    "title": _extract_markdown_title(markdown, _humanize_name(path.stem)),
                    "folder": rel.parent.relative_to("wiki").as_posix() if len(rel.parts) > 2 else "",
                    "links": sorted({t for t in targets if t.startswith("wiki/") and t.endswith(".md")}),
                    "sources": sorted({"/".join(t.split("/")[:3]) for t in targets if t.startswith("sources/")}),
                    "summary": _note_summary(meta, body),
                }
            )
    known = {note["path"] for note in notes}
    for note in notes:
        note["links"] = [link for link in note["links"] if link in known and link != note["path"]]
    return {"notes": notes}


# A chapter file's own title is its first heading near the top; split files open with "## Chapter 3: …".
_CHAPTER_HEADING = re.compile(r"^#{1,3}[ \t]+(.+?)[ \t#]*$", re.MULTILINE)
_CHAPTER_HEAD_BYTES = 4096
_ORDER_PREFIX = re.compile(r"^\d+[-_]")
# Emphasis and code markers, but not an escaped character or an underscore inside a word.
_TITLE_MARKUP = re.compile(r"(?<!\\)(?:\*+|`|(?<!\w)_+|_+(?!\w))")
# Inline HTML, such as a converted document's link anchor (`## Chapter 3 <a id="ch03"></a>`).
_HTML_TAG = re.compile(r"<[^>]+>")


def _plain_title(text: str) -> str:
    """A heading as plain text: `***Index***` and `activity\\_regularizer` read as written, and
    a converted document's trailing hard-break backslash (`CHAPTER 1\\`) and anchors are dropped."""
    text = _TITLE_MARKUP.sub("", _HTML_TAG.sub("", text))
    return re.sub(r"\\(.)", r"\1", text).rstrip("\\ \t").strip()


def _stem_title(path: Path) -> str:
    """A file name as a title, without its ordering prefix (`015-index.md` is "Index")."""
    return _humanize_name(_ORDER_PREFIX.sub("", path.stem))


def _chapter_title(path: Path) -> str:
    """The chapter's first heading, else its file name without the ordering prefix."""
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            head = handle.read(_CHAPTER_HEAD_BYTES)
    except OSError:
        head = ""
    meta, body = _split_frontmatter(head)
    if isinstance(meta.get("title"), str) and meta["title"].strip():
        return meta["title"].strip()
    match = _CHAPTER_HEADING.search(body)
    if match:
        return _plain_title(match.group(1))
    return _stem_title(path)


def _source_work(kind: str, directory: Path) -> dict[str, Any]:
    name = directory.name
    meta: dict[str, Any] = {}
    meta_file = directory / "metadata.yaml"
    if meta_file.is_file():
        try:
            loaded = yaml.safe_load(meta_file.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            loaded = None
        if isinstance(loaded, dict):
            meta = loaded
    chapters_dir = directory / "chapters"
    chapters = (
        [
            {"path": f"sources/{kind}/{name}/chapters/{item.name}", "title": _chapter_title(item)}
            for item in sorted(chapters_dir.glob("*.md"), key=lambda item: item.name.lower())
        ]
        if chapters_dir.is_dir()
        else []
    )
    text = directory / f"{name}.md"
    authors = meta.get("authors")
    topics = meta.get("topics")
    year = meta.get("year")
    return {
        "kind": kind.removesuffix("s"),
        "name": name,
        "path": f"sources/{kind}/{name}",
        "title": str(meta.get("title") or _humanize_name(name)),
        "authors": [str(author) for author in authors] if isinstance(authors, list) else [],
        "year": year if isinstance(year, int) else None,
        "category": str(meta["category"]) if meta.get("category") else None,
        "topics": [str(topic) for topic in topics] if isinstance(topics, list) else [],
        "text": f"sources/{kind}/{name}/{name}.md" if text.is_file() else None,
        "chapters": chapters,
        "compressed": (directory / "compressed").is_dir(),
    }


@ttl_cache(seconds=30)
def _cached_corpus_sources(db_root: Path) -> dict[str, Any]:
    root = _corpus_root() / "sources"
    works: list[dict[str, Any]] = []
    for kind in _SOURCE_KINDS:
        kind_root = root / kind
        if not kind_root.is_dir():
            continue
        for directory in sorted(kind_root.iterdir(), key=lambda item: item.name.lower()):
            if directory.is_dir() and not directory.name.startswith("."):
                works.append(_source_work(kind, directory))
    return {"works": works}


_SEARCH = CorpusSearch()
_SEARCH_LIMIT = 40
# Indexes, contents, reference lists and figure lists are keyword lists that outrank the
# prose they point to.
_NOT_SEARCHED = re.compile(
    r"\b(?:index|contents|references|bibliography|list of (?:figures|tables))\W*$", re.IGNORECASE
)


def _search_documents() -> list[SearchDocument]:
    """Every wiki note, and every chapter or a work's one text when it has no chapters."""
    root = _corpus_root()
    documents = [
        SearchDocument(note["path"], _plain_title(note["title"]), None, root / note["path"])
        for note in _cached_corpus_wiki(_db_root())["notes"]
    ]
    for work in _cached_corpus_sources(_db_root())["works"]:
        texts = work["chapters"] or ([{"path": work["text"], "title": work["title"]}] if work["text"] else [])
        documents.extend(
            SearchDocument(text["path"], text["title"], work["path"], root / text["path"])
            for text in texts
            if not _NOT_SEARCHED.search(text["title"])
        )
    return documents


# --------------------------------------------------------------------------- #
# Research documents
# --------------------------------------------------------------------------- #


def _resolve_research_path(raw_path: str) -> tuple[Path, str]:
    """Map a stable logical research path to its canonical physical root."""
    normalized = _normalize_doc_path(raw_path)

    if normalized.split("/")[0] not in _RESEARCH_DOC_ROOTS:
        raise HTTPException(status_code=403, detail="Access denied")

    root_name, *relative_parts = normalized.split("/")
    physical_roots = {
        "corpus": _corpus_root(),
        "sandbox": _sandbox_root(),
        "src": _source_root(),
        "docs": _docs_root(),
    }
    physical_root = physical_roots[root_name]
    target = physical_root / Path(*relative_parts)
    try:
        target.resolve().relative_to(physical_root.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Access denied") from exc

    return target, normalized


@ttl_cache(seconds=30)
def _cached_research_doc(db_root: Path, doc_path: str) -> dict[str, Any]:
    target, normalized = _resolve_research_path(doc_path)

    if target.suffix.lower() != ".md":
        raise HTTPException(status_code=400, detail="Only markdown files are supported")
    if not target.is_file():
        raise HTTPException(status_code=404, detail=f"Document '{normalized}' not found")

    markdown = target.read_text(encoding="utf-8", errors="replace")

    return {
        "path": normalized,
        "title": _plain_title(_extract_markdown_title(markdown, _stem_title(target))),
        "markdown": markdown,
        "modified": target.stat().st_mtime,
        "generated": False,
    }


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #


@router.get("/packages")
def list_research_packages(request: Request) -> dict[str, Any]:
    """Return wired sandbox packages and the Sandbox/Source nav skeleton."""
    packages = _research_packages(request.app)
    return {
        "packages": packages,
        "nav": _research_nav(packages),
        "disclaimer": _catalog_disclaimer(request.app),
    }


@router.get("/docs")
def list_research_docs() -> dict[str, Any]:
    """Return the packages/research/docs markdown tree."""
    return {"nav": _docs_nav()}


@router.get("/corpus/wiki")
def list_corpus_wiki() -> dict[str, Any]:
    """Return every wiki note with its resolved wiki links and the works it cites."""
    return _cached_corpus_wiki(_db_root())


@router.get("/corpus/sources")
def list_corpus_sources() -> dict[str, Any]:
    """Return every corpus work (books, papers, references) with its texts and chapters."""
    return _cached_corpus_sources(_db_root())


@router.get("/corpus/search")
def search_corpus(
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(_SEARCH_LIMIT, ge=1, le=200),
) -> dict[str, Any]:
    """Rank the corpus wiki notes and source chapters against `q`, with a snippet around each match."""
    return {"query": q, **_SEARCH.search(_search_documents(), q, limit)}


@router.get("/doc/{doc_path:path}")
def get_research_doc(doc_path: str) -> dict[str, Any]:
    """Return markdown content + metadata for one packages/research document."""
    return _cached_research_doc(_db_root(), doc_path)


@router.get("/asset/{asset_path:path}")
def get_research_asset(asset_path: str) -> FileResponse:
    """Return one image asset referenced by a packages/research document."""
    target, normalized = _resolve_research_path(asset_path)

    if target.suffix.lower() not in _RESEARCH_ASSET_SUFFIXES:
        raise HTTPException(status_code=400, detail="Unsupported asset type")
    if not target.is_file():
        raise HTTPException(status_code=404, detail=f"Asset '{normalized}' not found")

    return FileResponse(target)
