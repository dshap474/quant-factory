"""Shared bounded parquet-path index for catalog and scope statistics.

A Delta table is one entry (its directory, live bytes from its add actions); its data files,
``_delta_log`` and ``_qf`` are never listed.

USAGE:
    entries = get_parquet_index(db_root, "data")
    refresh_parquet_indexes(db_root)
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports
# --------------------------------------------------------------------------- #
import time
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Literal

from data.platform.storage import delta_read

Scope = Literal["data", "features"]

# --------------------------------------------------------------------------- #
# Models and state
# --------------------------------------------------------------------------- #

_INDEX_TTL_SECONDS = 300
_MAX_INDEXES = 4
_LOCK = RLock()


@dataclass(frozen=True)
class ParquetIndexEntry:
    """One parquet path plus metadata needed by catalog summaries."""

    path: Path
    relative_path: Path
    size_bytes: int
    is_table: bool = False


_CACHE: OrderedDict[tuple[Path, Scope], tuple[float, tuple[ParquetIndexEntry, ...]]] = OrderedDict()

# --------------------------------------------------------------------------- #
# Index lifecycle
# --------------------------------------------------------------------------- #


def _build_index(db_root: Path, scope: Scope) -> tuple[ParquetIndexEntry, ...]:
    scope_root = db_root / scope
    if not scope_root.exists():
        return ()
    entries: list[ParquetIndexEntry] = []
    files, tables = delta_read.walk_lake(scope_root)
    for path in files:
        if any(part.startswith((".", "_")) for part in path.relative_to(scope_root).parts):
            continue
        entries.append(
            ParquetIndexEntry(
                path=path,
                relative_path=path.relative_to(scope_root),
                size_bytes=path.stat().st_size,
            )
        )
    for path in tables:
        if any(part.startswith((".", "_")) for part in path.relative_to(scope_root).parts):
            continue
        entries.append(
            ParquetIndexEntry(
                path=path,
                relative_path=path.relative_to(scope_root),
                size_bytes=delta_read.fingerprint(path)[1],
                is_table=True,
            )
        )
    entries.sort(key=lambda entry: entry.relative_path.parts)
    return tuple(entries)


def get_parquet_index(
    db_root: Path,
    scope: Scope,
    *,
    refresh: bool = False,
) -> tuple[ParquetIndexEntry, ...]:
    """Return one cached scope index, rebuilding at most once per expiry."""
    key = (db_root.resolve(), scope)
    with _LOCK:
        now = time.monotonic()
        cached = _CACHE.get(key)
        if not refresh and cached is not None and cached[0] > now:
            _CACHE.move_to_end(key)
            return cached[1]

        entries = _build_index(db_root, scope)
        _CACHE[key] = (now + _INDEX_TTL_SECONDS, entries)
        _CACHE.move_to_end(key)
        while len(_CACHE) > _MAX_INDEXES:
            _CACHE.popitem(last=False)
        return entries


def clear_parquet_indexes() -> None:
    """Drop all in-memory scope indexes."""
    with _LOCK:
        _CACHE.clear()


def refresh_parquet_indexes(db_root: Path) -> dict[Scope, int]:
    """Rebuild both operator-visible scope indexes immediately."""
    clear_parquet_indexes()
    return {scope: len(get_parquet_index(db_root, scope, refresh=True)) for scope in ("data", "features")}


def prewarm_parquet_indexes(db_root: Path) -> None:
    """Populate both indexes during API startup."""
    for scope in ("data", "features"):
        get_parquet_index(db_root, scope)
