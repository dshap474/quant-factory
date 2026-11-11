"""Lake and per-table write locks: fcntl flock files under ``<db_root>/.locks/``.

``lake_lock`` takes the same ``db/.locks/lake-write.lock`` that a lake refresh holds exclusively
and queued run jobs hold shared. Inside a process that runs under one
of those holders a conflicting request would wait for its own parent, so ``lake_lock`` detects
them (``QF_LAKE_LOCK_HELD`` from a refresh, ``QF_RUN_PROGRESS`` from a run job) and raises
``LakeLockHeldByParent`` at once. ``table_lock`` serializes the Delta writers of
one table (``write_slice``, ``seal_partition``, ``maintain``). Both are re-entrant per thread.

USAGE:
    from data.platform.storage.locks import lake_lock, table_lock

    with lake_lock("exclusive", wait_seconds=600):   # cut-over: bounded wait, LockTimeout on expiry
        ...
    with table_lock(ref):                            # ref: delta_tables.TableRef
        ...
"""

from __future__ import annotations

import fcntl
import os
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Literal

from data.config.paths import resolve_db_root

# --------------------------------------------------------------------------- #
# Paths and errors
# --------------------------------------------------------------------------- #

LAKE_LOCK = Path(".locks") / "lake-write.lock"
TABLE_LOCKS = Path(".locks") / "tables"


class LockTimeout(TimeoutError):
    """The lock was still held by someone else when the wait ran out."""


class LakeLockHeldByParent(RuntimeError):
    """This process runs under a holder of the lake lock, so taking it here would wait on itself."""


def _parent_lake_lock() -> str | None:
    """The lake-lock mode a parent already holds: a refresh exports ``QF_LAKE_LOCK_HELD``;
    a run job holds it shared and sets ``QF_RUN_PROGRESS`` for its child."""
    if held := os.environ.get("QF_LAKE_LOCK_HELD"):
        return held
    return "shared" if os.environ.get("QF_RUN_PROGRESS") else None


def lake_lock_path(db_root: Path | None = None) -> Path:
    return resolve_db_root(db_root) / LAKE_LOCK


def table_lock_path(db_root: Path, key: str) -> Path:
    return db_root / TABLE_LOCKS / f"{key.strip('/').replace('/', '__')}.lock"


# --------------------------------------------------------------------------- #
# flock with a bounded wait, re-entrant per thread
# --------------------------------------------------------------------------- #

_held = threading.local()


@contextmanager
def _flock(path: Path, *, exclusive: bool, wait_seconds: float | None) -> Iterator[None]:
    held: dict[Path, list[Any]] = _held.__dict__.setdefault("locks", {})
    path = path.resolve()
    if path in held:
        entry = held[path]
        if exclusive and not entry[1]:
            raise RuntimeError(f"cannot upgrade a held shared lock to exclusive: {path}")
        entry[2] += 1
        try:
            yield
        finally:
            entry[2] -= 1
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a")
    op = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
    try:
        if wait_seconds is None:
            fcntl.flock(handle, op)
        else:
            deadline = time.monotonic() + wait_seconds
            while True:
                try:
                    fcntl.flock(handle, op | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise LockTimeout(f"{path} still held after {wait_seconds:g}s") from None
                    time.sleep(0.2)
        held[path] = [handle, exclusive, 1]
        try:
            yield
        finally:
            del held[path]
            fcntl.flock(handle, fcntl.LOCK_UN)
    finally:
        handle.close()


# --------------------------------------------------------------------------- #
# Public locks
# --------------------------------------------------------------------------- #


@contextmanager
def lake_lock(
    mode: Literal["shared", "exclusive"],
    wait_seconds: float | None = None,
    *,
    db_root: Path | None = None,
) -> Iterator[Path]:
    """Hold the lake-write lock; ``wait_seconds=None`` waits forever, otherwise raises ``LockTimeout``."""
    if mode not in ("shared", "exclusive"):
        raise ValueError(f"mode must be 'shared' or 'exclusive', got {mode!r}")
    parent = _parent_lake_lock()
    if parent == "exclusive" or (parent == "shared" and mode == "exclusive"):
        raise LakeLockHeldByParent(
            f"a parent process already holds the lake lock {parent} (a refresh / a queued run job); "
            f"a {mode} request here would wait on its own parent. Run this outside them."
        )
    path = lake_lock_path(db_root)
    with _flock(path, exclusive=mode == "exclusive", wait_seconds=wait_seconds):
        yield path


@contextmanager
def table_lock(ref: Any, wait_seconds: float | None = None) -> Iterator[Path]:
    """Hold the exclusive per-table lock for ``ref`` (a ``TableRef``: ``db_root`` and ``key``)."""
    path = table_lock_path(Path(ref.db_root), str(ref.key))
    with _flock(path, exclusive=True, wait_seconds=wait_seconds):
        yield path


__all__ = ["LakeLockHeldByParent", "LockTimeout", "lake_lock", "lake_lock_path", "table_lock", "table_lock_path"]
