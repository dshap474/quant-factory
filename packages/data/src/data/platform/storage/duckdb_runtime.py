"""DuckDB connections sized to the refresh step's memory cap, spilling to disk instead of failing.

USAGE:
    from data.platform.storage.duckdb_runtime import duckdb_connect
    with duckdb_connect(spill_dir) as con:          # memory_limit = 0.7 x $QF_STEP_MEMORY_MB
        con.execute("SELECT ...")
    duckdb_connect(spill_dir, share=0.5)            # leave more of the cap to Polars/Arrow in the same step

Insertion order is kept (DuckDB's default); a caller that never relies on it may
``SET preserve_insertion_order=false`` to save memory.

The refresh runner passes each step its cap as ``QF_STEP_MEMORY_MB``; outside a refresh (tests, ad
hoc runs) the cap defaults to ``DEFAULT_STEP_MEMORY_MB``. DuckDB gets ``share`` of it, the rest is
headroom for Python, Arrow buffers and operators DuckDB cannot spill (``list()``, ``string_agg``).
Threads scale with the limit (one per 512 MB, 2 to 8) because each thread holds its own buffers.
"""

from __future__ import annotations

import os
from pathlib import Path

import duckdb

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

STEP_MEMORY_ENV = "QF_STEP_MEMORY_MB"  # same name the refresh runner sets
DEFAULT_STEP_MEMORY_MB = 7 * 1024
DEFAULT_SHARE = 0.7
MB_PER_THREAD = 512
MIN_THREADS, MAX_THREADS = 2, 8

# --------------------------------------------------------------------------- #
# Connection
# --------------------------------------------------------------------------- #


def step_memory_mb() -> int:
    """This step's memory cap in MB: ``QF_STEP_MEMORY_MB`` when set, else ``DEFAULT_STEP_MEMORY_MB``."""
    value = os.environ.get(STEP_MEMORY_ENV, "").strip()
    return int(float(value)) if value else DEFAULT_STEP_MEMORY_MB


def duckdb_connect(
    temp_dir: Path, *, database: str = ":memory:", read_only: bool = False, share: float = DEFAULT_SHARE
) -> duckdb.DuckDBPyConnection:
    """A connection with ``memory_limit`` = ``share`` x the step cap, scaled threads, and spill to ``temp_dir``."""
    limit_mb = max(256, int(step_memory_mb() * share))
    threads = max(MIN_THREADS, min(limit_mb // MB_PER_THREAD, MAX_THREADS, os.cpu_count() or MIN_THREADS))
    temp_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(database, read_only=read_only)
    con.execute(f"SET memory_limit='{limit_mb}MB'")
    con.execute(f"SET threads={threads}")
    con.execute("SET temp_directory=?", [str(temp_dir)])
    return con


__all__ = ["DEFAULT_STEP_MEMORY_MB", "STEP_MEMORY_ENV", "duckdb_connect", "step_memory_mb"]
