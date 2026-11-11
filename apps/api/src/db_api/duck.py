"""One shared, memory-capped DuckDB connection for the DB API's own aggregations.

Every request takes a cursor (its own session on the same database), so concurrent requests are
thread-safe while sharing one buffer pool: ``threads=8``, ``memory_limit=5GB`` and spilling to an
on-disk temp directory under the user cache (never ``/tmp``, which may be RAM-backed). That
keeps the API within an 8 GB memory budget however many profile requests run at once.

USAGE:
    from db_api.duck import cursor

    with cursor() as conn:
        rows = conn.execute("SELECT count(*) FROM read_parquet('x.parquet')").fetchall()
    with cursor(delta=True) as conn:                  # loads DuckDB's delta extension once
        conn.execute("SELECT count(*) FROM delta_scan('/db/data/raw/1d/example/bars')")
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from threading import Lock

import duckdb
from data.platform.storage import delta_read

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

THREADS = 8
MEMORY_LIMIT = "5GB"


def temp_directory() -> Path:
    cache_home = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return cache_home / "quant-factory" / "db-api-duckdb"


# --------------------------------------------------------------------------- #
# Shared connection
# --------------------------------------------------------------------------- #

_LOCK = Lock()  # guards creating/dropping the shared connection (held only briefly)
_DELTA_LOCK = Lock()  # serializes the one-time delta extension load; never held with _LOCK
_STATE: dict[str, object] = {}
# Errors after which DuckDB invalidates the database instance: every later use would fail too.
_FATAL = (duckdb.FatalException, duckdb.InternalException)


def _connection() -> duckdb.DuckDBPyConnection:
    with _LOCK:
        connection = _STATE.get("connection")
        if connection is None:
            spill = temp_directory()
            spill.mkdir(parents=True, exist_ok=True)
            connection = duckdb.connect(
                ":memory:",
                config={"threads": THREADS, "memory_limit": MEMORY_LIMIT, "temp_directory": str(spill)},
            )
            _STATE["connection"] = connection
            _STATE.pop("delta", None)
        return connection  # type: ignore[return-value]


def _drop(connection: duckdb.DuckDBPyConnection) -> None:
    """Forget a connection DuckDB invalidated so the next request opens a fresh one."""
    with _LOCK:
        if _STATE.get("connection") is connection:
            _STATE.pop("connection", None)
            _STATE.pop("delta", None)
    with suppress(duckdb.Error):
        connection.close()


def _ensure_delta(parent: duckdb.DuckDBPyConnection) -> None:
    """Load the delta extension once per connection; a failure is cached and re-raised fast."""
    state = _STATE.get("delta")
    if state is None:
        with _DELTA_LOCK:
            state = _STATE.get("delta")
            if state is None:
                try:
                    delta_read.load_delta_extension(parent)
                    state = True
                except duckdb.Error as exc:
                    state = exc
                if _STATE.get("connection") is parent:
                    _STATE["delta"] = state
    if isinstance(state, BaseException):
        raise RuntimeError(f"DuckDB delta extension unavailable: {state}") from state


@contextmanager
def cursor(*, delta: bool = False) -> Iterator[duckdb.DuckDBPyConnection]:
    """A per-request cursor on the shared connection, session time zone UTC.

    A fatal or internal DuckDB error drops the shared connection, so the API recovers on the next
    request instead of failing every request until restart.
    """
    parent = _connection()
    try:
        if delta:
            _ensure_delta(parent)
        conn = parent.cursor()
    except _FATAL:
        _drop(parent)
        raise
    try:
        conn.execute("SET TimeZone = 'UTC'")
        yield conn
    except _FATAL:
        _drop(parent)
        raise
    finally:
        with suppress(duckdb.Error):  # the parent may already be closed after a fatal error
            conn.close()


def close() -> None:
    """Close the shared connection (tests and shutdown)."""
    with _LOCK:
        connection = _STATE.pop("connection", None)
        _STATE.pop("delta", None)
    if connection is not None:
        connection.close()  # type: ignore[attr-defined]
