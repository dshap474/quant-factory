"""OS advisory run-lock (fcntl.flock) held for the executor's full runtime.

Purpose: single-instance live executor per lock path. No stale-lock deletion —
the OS releases the advisory lock on process exit (including SIGKILL).

USAGE:
    from execution.locking import RunLock, RunLockError
    with RunLock(path).hold() as _:
        ...
"""

from __future__ import annotations

import fcntl
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, TextIO

from execution.journal import fsync_dir

# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #


class RunLockError(Exception):
    """Raised when the run lock cannot be acquired (another holder)."""


# --------------------------------------------------------------------------- #
# Lock
# --------------------------------------------------------------------------- #


class RunLock:
    """Non-blocking exclusive flock on a persistent marker file."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._fh: TextIO | None = None

    @contextmanager
    def hold(self) -> Iterator["RunLock"]:
        self.acquire()
        try:
            yield self
        finally:
            self.release()

    def acquire(self) -> None:
        if self._fh is not None:
            raise RuntimeError("run lock already held by this instance")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fsync_dir(self.path.parent)
        fh: TextIO = open(self.path, "a+", encoding="utf-8")
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            fh.close()
            raise RunLockError(f"live executor run lock already held: {self.path}") from exc
        # Record pid for operators (not used for stale deletion)
        fh.seek(0)
        fh.truncate()
        fh.write(f"pid={os.getpid()}\n")
        fh.flush()
        os.fsync(fh.fileno())
        self._fh = fh

    def release(self) -> None:
        fh = self._fh
        if fh is None:
            return
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        finally:
            fh.close()
            self._fh = None

    @property
    def held(self) -> bool:
        return self._fh is not None
