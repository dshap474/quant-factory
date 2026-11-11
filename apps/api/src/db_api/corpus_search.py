"""Full-text search over the corpus sources.

An in-memory SQLite FTS5 index holds every wiki note and every chapter (or a work's one text
when it has no chapters) as plain text, ranked by BM25 with titles weighted above bodies and stemmed so
"trading" finds "trade". It is built on the first search and rebuilt when a file changes;
nothing is written to disk.

USAGE::

    search = CorpusSearch()
    search.search(documents, "kelly criterion", limit=40)
    # {"total": <hits>, "matched": [path, ...],
    #  "results": [{"path": ..., "title": ..., "work": ... | None, "snippet": ...}]}
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports
# --------------------------------------------------------------------------- #
import re
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------- #
# Documents
# --------------------------------------------------------------------------- #

# Snippet match markers: control characters that never occur in the text, so the client
# can split on them without parsing markup.
MATCH_START = "\u0002"
MATCH_END = "\u0003"
_SNIPPET_TOKENS = 18
_TITLE_WEIGHT = 5.0


@dataclass(frozen=True)
class SearchDocument:
    """One searchable text: a wiki note, a chapter, or a work's single text."""

    path: str
    title: str
    work: str | None  # the source work a chapter belongs to; None for a wiki note
    file: Path


_FRONTMATTER = re.compile(r"\A---[ \t]*\r?\n.*?\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL)
_MARKDOWN = (
    (re.compile(r"!\[[^\]]*\]\([^)]*\)"), " "),  # images
    (re.compile(r"\[[\w-]+:[\w.-]+\]"), ""),  # wiki citation keys, [work-slug:AB-01]
    (re.compile(r"\[([^\]]*)\]\([^)]*\)"), r"\1"),  # links keep their text
    (re.compile(r"<[^>]+>"), " "),  # html tags
    (re.compile(r"^[ \t]*(?:#{1,6}|>|[-*+]|\d+[.)])[ \t]+", re.MULTILINE), ""),  # block marks
    (re.compile(r"(?<!\\)(?:\*+|`+|~~|(?<!\w)_+|_+(?!\w))"), ""),  # emphasis and code
    (re.compile(r"\\(.)"), r"\1"),  # escapes
    (re.compile(r"[ \t]*\|[ \t]*"), " "),  # table cells
)


def plain_text(markdown: str) -> str:
    """Markdown as the words a reader sees, for indexing and snippets."""
    text = _FRONTMATTER.sub("", markdown)
    for pattern, replacement in _MARKDOWN:
        text = pattern.sub(replacement, text)
    return text


# --------------------------------------------------------------------------- #
# Queries
# --------------------------------------------------------------------------- #

_TERM = re.compile(r'"([^"]*)"|(\S+)')
_WORD = re.compile(r"\w+")


def match_expression(query: str) -> str:
    """A user's query as an FTS5 expression: every word or "quoted phrase" must match, and
    the last bare word matches as a prefix so results follow typing."""
    parts: list[str] = []
    prefix = False
    for phrase, word in _TERM.findall(query):
        tokens = _WORD.findall(phrase or word)
        if tokens:
            parts.append('"' + " ".join(tokens) + '"')
            prefix = not phrase
    if parts and prefix:
        parts[-1] += "*"
    return " ".join(parts)


# --------------------------------------------------------------------------- #
# Index
# --------------------------------------------------------------------------- #


class CorpusSearch:
    """A lazily built FTS5 index, shared across request threads behind one lock."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._connection: sqlite3.Connection | None = None
        self._signature: tuple[tuple[str, float], ...] = ()
        self._documents: list[SearchDocument] = []

    def _build(self, documents: list[SearchDocument]) -> None:
        connection = sqlite3.connect(":memory:", check_same_thread=False)
        connection.execute(
            "CREATE VIRTUAL TABLE docs USING fts5(title, body, tokenize = 'porter unicode61 remove_diacritics 2')"
        )
        rows = []
        for rowid, document in enumerate(documents):
            try:
                body = plain_text(document.file.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                body = ""
            rows.append((rowid, document.title, body))
        connection.executemany("INSERT INTO docs (rowid, title, body) VALUES (?, ?, ?)", rows)
        if self._connection is not None:
            self._connection.close()
        self._connection = connection
        self._documents = documents

    def _current(self, documents: list[SearchDocument]) -> sqlite3.Connection:
        signature = tuple(
            (document.path, document.file.stat().st_mtime if document.file.is_file() else 0.0) for document in documents
        )
        if self._connection is None or signature != self._signature:
            self._build(documents)
            self._signature = signature
        assert self._connection is not None
        return self._connection

    def search(self, documents: list[SearchDocument], query: str, limit: int) -> dict[str, Any]:
        """The best `limit` matches for `query`, with a highlighted snippet each, and every
        match's path and work path (`matched`), so a tree can be filtered to all of them."""
        expression = match_expression(query)
        if not expression:
            return {"total": 0, "matched": [], "results": []}
        with self._lock:
            connection = self._current(documents)
            every = [
                self._documents[rowid]
                for (rowid,) in connection.execute("SELECT rowid FROM docs WHERE docs MATCH ?", (expression,))
            ]
            rows = connection.execute(
                "SELECT rowid, snippet(docs, 1, ?, ?, '…', ?) FROM docs WHERE docs MATCH ? "
                "ORDER BY bm25(docs, ?, 1.0) LIMIT ?",
                (MATCH_START, MATCH_END, _SNIPPET_TOKENS, expression, _TITLE_WEIGHT, limit),
            ).fetchall()
            hits = [(self._documents[rowid], snippet) for rowid, snippet in rows]
        matched = {document.path for document in every} | {document.work for document in every if document.work}
        return {
            "total": len(every),
            "matched": sorted(matched),
            "results": [
                {
                    "path": document.path,
                    "title": document.title,
                    "work": document.work,
                    "snippet": " ".join(snippet.split()),
                }
                for document, snippet in hits
            ],
        }
