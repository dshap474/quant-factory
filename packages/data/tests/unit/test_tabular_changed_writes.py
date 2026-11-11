"""Unit tests for ``write_changed_tables``: merge on keys, skip byte-for-byte unchanged results.

USAGE:
    uv run --project packages/data pytest packages/data/tests/unit/test_tabular_changed_writes.py -q
"""

from __future__ import annotations

from pathlib import Path

import polars as pl
from data.platform.storage.tabular import PreparedTable, write_changed_tables

# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


def _write(tmp_path: Path, frame: pl.DataFrame, *, overwrite: bool = False):
    return write_changed_tables(
        [PreparedTable("t", frame, ("k",), ("k",))],
        path_resolver=lambda name: tmp_path / f"{name}.parquet",
        overwrite=overwrite,
    )


def test_unchanged_rerun_writes_nothing_and_changes_are_merged(tmp_path: Path) -> None:
    base = pl.DataFrame({"k": [1, 2], "v": [1.0, 2.0]})

    first, _ = _write(tmp_path, base)
    again, _ = _write(tmp_path, base)
    revised, counts = _write(tmp_path, pl.DataFrame({"k": [2, 3], "v": [9.0, 3.0]}))

    assert (len(first), again, len(revised)) == (1, [], 1)
    assert counts == {"t": 3}
    assert pl.read_parquet(tmp_path / "t.parquet")["v"].to_list() == [1.0, 9.0, 3.0]


def test_dtype_change_counts_as_a_change(tmp_path: Path) -> None:
    _write(tmp_path, pl.DataFrame({"k": [1], "v": [1]}))

    written, _ = _write(tmp_path, pl.DataFrame({"k": [1], "v": [1.0]}), overwrite=True)

    assert written and pl.read_parquet(tmp_path / "t.parquet").schema["v"] == pl.Float64
