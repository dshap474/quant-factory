"""Table-aware read helpers for walkers and readers that predate Delta tables.

Walkers that list parquet files call ``walk_lake`` (or ``collapse``) so a Delta table counts once
as its directory and its ``_delta_log``/``_qf`` internals are never listed. Readers call
``delta_ref`` to learn whether a lake key resolves to a Delta table (directly or through the
legacy-key mapping at ``<db_root>/_qf/key_mapping.parquet``) and then read through
``delta_tables``. Readers that walk a table directory file by file (per-coin venue files) list
``live_files``/``member_files`` and scan them with ``scan_live`` (or ``member_scan`` for one member),
which reads a Delta table's files with the table schema so a later ``add_columns`` neither breaks nor
drops a column. On a lake with no ``_delta_log`` directory and no mapping file every helper
returns the legacy answer without importing ``deltalake``.

USAGE:
    from data.platform.storage import delta_read

    files, tables = delta_read.walk_lake(db_root / "data" / "raw" / "1m")
    ref = delta_read.delta_ref(db_root, "data/raw/1d/example/bars")   # TableRef | None
    frame = delta_read.lake_scan(path).select("time").collect()               # Delta dir or file
    version, size = delta_read.fingerprint(path)                              # (version|mtime_ns, bytes)
    files = delta_read.live_files(venue_dir)                                  # Delta live files or top-level *.parquet
    files = delta_read.member_files(venue_dir, "btc_*.parquet", column="coin", values=["BTC"])
    scan = delta_read.member_scan(venue_dir / "btc_example_1m.parquet", column="coin", value="BTC")
    scan = delta_read.scan_live([spot_dir, perp_dir], "btc_*.parquet", column="coin", values=["BTC"])
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from fnmatch import fnmatchcase
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

import polars as pl

if TYPE_CHECKING:
    from data.platform.storage.delta_tables import TableRef

# --------------------------------------------------------------------------- #
# Layout constants
# --------------------------------------------------------------------------- #

DELTA_LOG = "_delta_log"
SIDECAR = "_qf"
INTERNAL_DIRS = frozenset({DELTA_LOG, SIDECAR})
KEY_MAPPING = Path(SIDECAR) / "key_mapping.parquet"  # relative to the db root


def is_delta_dir(path: Path) -> bool:
    return (Path(path) / DELTA_LOG).is_dir()


def is_table_internal(path: Path | str) -> bool:
    """True for anything inside a ``_delta_log`` or ``_qf`` directory."""
    return any(part in INTERNAL_DIRS for part in Path(path).parts)


def key_mapping_path(db_root: Path) -> Path:
    return Path(db_root) / KEY_MAPPING


def enclosing_delta(path: Path, stop: Path) -> Path | None:
    """The Delta table directory holding ``path`` (or ``path`` itself), searching up to ``stop``."""
    path, stop = Path(path), Path(stop)
    for candidate in (path, *path.parents):
        if candidate == stop or stop not in candidate.parents:
            return None
        if is_delta_dir(candidate):
            return candidate
    return None


# --------------------------------------------------------------------------- #
# Walking
# --------------------------------------------------------------------------- #


def walk_lake(start: Path) -> tuple[list[Path], list[Path]]:
    """Sorted parquet files and Delta table directories at or under ``start``.

    Same files as ``start.rglob("*.parquet")`` except that a Delta table yields once as its
    directory and is never descended into, and ``_delta_log``/``_qf`` are skipped.
    """
    start = Path(start)
    if is_delta_dir(start):
        return [], [start]
    if start.is_file():
        return ([start] if start.suffix == ".parquet" else []), []
    files: list[Path] = []
    tables: list[Path] = []
    for current, dirs, names in os.walk(start):
        here = Path(current)
        keep = []
        for name in dirs:
            if name in INTERNAL_DIRS:
                continue
            if is_delta_dir(here / name):
                tables.append(here / name)
            else:
                keep.append(name)
        dirs[:] = keep
        files.extend(here / name for name in names if name.endswith(".parquet") and (here / name).is_file())
    return sorted(files), sorted(tables)


def collapse(paths: Iterable[Path], stop: Path) -> list[Path]:
    """Replace paths inside a Delta table by the table directory (once) and drop table internals.

    Order is preserved; legacy paths pass through untouched.
    """
    out: list[Path] = []
    seen: set[Path] = set()
    cache: dict[Path, Path | None] = {}
    for path in paths:
        path = Path(path)
        parent = path.parent
        if parent not in cache:
            cache[parent] = enclosing_delta(parent, stop)
        root = path if is_delta_dir(path) else cache[parent]
        if root is None:
            out.append(path)
            continue
        if root not in seen:
            seen.add(root)
            out.append(root)
    return out


# --------------------------------------------------------------------------- #
# Resolution and reads
# --------------------------------------------------------------------------- #


def delta_ref(db_root: Path, key: str | Path) -> TableRef | None:
    """The Delta ``TableRef`` for a lake key (relative to ``db_root`` or absolute under it), else None.

    Without a mapping file and a ``_delta_log`` at the key this returns None without importing
    ``deltalake``; legacy keys keep their legacy read path.
    """
    db_root = Path(db_root)
    key_path = Path(key)
    path = key_path if key_path.is_absolute() else db_root / key_path.as_posix().strip("/")
    mapping = key_mapping_path(db_root)
    if not mapping.exists() and not is_delta_dir(path):
        return None
    from data.platform.storage import delta_tables as dtab

    try:
        ref = dtab.table_ref(db_root, path.absolute(), mapping=mapping)
    except ValueError:  # outside the db root
        return None
    return ref if ref.kind == "delta" else None


def _glob_match(key: str, pattern: str) -> bool:
    """``Path.glob`` semantics for one key: ``*``/``?``/``[]`` match within a path segment, ``**`` any depth."""
    return _match_parts(key.strip("/").split("/"), pattern.strip("/").split("/"))


def _match_parts(keys: list[str], parts: list[str]) -> bool:
    if not parts:
        return not keys
    if parts[0] == "**":
        return any(_match_parts(keys[i:], parts[1:]) for i in range(len(keys) + 1))
    return bool(keys) and fnmatchcase(keys[0], parts[0]) and _match_parts(keys[1:], parts[1:])


def mapped_refs(db_root: Path, pattern: str) -> list[tuple[Path, TableRef]]:
    """``(legacy key path, Delta ref with the key's row filter)`` for each mapped legacy key matching the
    db-relative glob ``pattern``, so globs over cut-over legacy files keep matching; empty without a mapping."""
    mapping = key_mapping_path(db_root)
    if not mapping.exists():
        return []
    from data.platform.storage import delta_tables as dtab

    out = []
    for key in sorted(dtab.load_key_mapping(mapping)):
        if _glob_match(key, pattern):
            ref = dtab.table_ref(db_root, key, mapping=mapping)
            if ref.kind == "delta":
                out.append((Path(db_root) / key, ref))
    return out


def mapped_tables(db_root: Path, pattern: str) -> list[Path]:
    """Delta tables whose mapped legacy keys match the db-relative glob ``pattern`` (for surfaces that
    still name legacy files); empty without a mapping file."""
    return sorted({Path(db_root) / ref.key for _, ref in mapped_refs(db_root, pattern)})


def partition_ref(table: Path, inner: Path, *, db_root: Path | None = None) -> TableRef:
    """The ref of Delta table ``table`` filtered to the partition directory ``inner`` (``<col>=<value>``).

    Raises ``ValueError`` when ``inner`` is not a partition directory of the table.
    """
    from dataclasses import replace

    from data.platform.storage import delta_tables as dtab

    ref = path_ref(table) if db_root is None else dtab.table_ref(db_root, Path(table).absolute())
    parts = Path(inner).relative_to(table).parts
    layout = dtab.read_layout(ref)
    if len(parts) != 1 or layout is None or layout.partition is None or "=" not in parts[0]:
        raise ValueError(f"{inner} is inside Delta table {ref.key} but is not one of its partition directories")
    column, value = parts[0].split("=", 1)
    if column != layout.partition:
        raise ValueError(f"{inner}: {ref.key} is partitioned by {layout.partition}, not {column}")
    dtype = dtab.scan_table(ref).collect_schema()[column]
    typed: Any = int(value) if dtype.is_integer() else value
    return replace(ref, filters=(*ref.filters, (column, typed)))


def meta_path(data_path: Path) -> Path:
    """A dataset's ``meta.yaml``: ``<table>/_qf/meta.yaml`` for a Delta table, else beside the file."""
    data_path = Path(data_path)
    return data_path / SIDECAR / "meta.yaml" if is_delta_dir(data_path) else data_path.parent / "meta.yaml"


def analysis_dir(data_path: Path, features_root: Path) -> Path:
    """Where a feature panel's analysis artifacts live: beside ``data.parquet``, or for a Delta table
    (which owns its directory) ``<features_root>/_analysis/<table relative to features_root>``."""
    data_path = Path(data_path)
    if not is_delta_dir(data_path):
        return data_path.parent
    return Path(features_root) / "_analysis" / data_path.relative_to(features_root)


def path_ref(path: Path) -> TableRef:
    """A ``TableRef`` for a Delta table directory given only its path (read-only uses)."""
    from data.platform.storage import delta_tables as dtab

    path = Path(path).resolve()
    return dtab.table_ref(path.parent, path.name)


@lru_cache(maxsize=32)
def _live_actions(table: str, log_token: str) -> tuple[tuple[str, int, dict[str, Any], dict[str, Any]], ...]:
    """``(relative path, size, min stats, max stats)`` per live data file, sorted by path."""
    del log_token  # cache key only: the newest log entry changes with every commit
    import pyarrow as pa
    from deltalake import DeltaTable

    actions = pl.DataFrame(pa.table(DeltaTable(table).get_add_actions(flatten=True)))
    stats = [c for c in actions.columns if c.startswith(("min.", "max."))]
    out = []
    for row in actions.select("path", "size_bytes", *stats).sort("path").iter_rows(named=True):
        lows = {c[4:]: row[c] for c in stats if c.startswith("min.") and row[c] is not None}
        highs = {c[4:]: row[c] for c in stats if c.startswith("max.") and row[c] is not None}
        out.append((row["path"], int(row["size_bytes"]), lows, highs))
    return tuple(out)


@lru_cache(maxsize=32)
def _live_file_schema(table: str, log_token: str) -> pl.Schema:
    """The table schema without its partition columns: the columns a live data file can carry."""
    del log_token  # cache key only
    import pyarrow as pa
    from deltalake import DeltaTable

    dt = DeltaTable(table)
    schema = pa.schema(dt.schema().to_arrow())
    partitions = set(dt.metadata().partition_columns)
    return pl.DataFrame(pa.schema([f for f in schema if f.name not in partitions]).empty_table()).schema


def _log_token(table: Path) -> str:
    """Cache key of a table's current state: the newest commit's name, mtime and inode, plus the log
    directory's inode, so a table re-created at the same path and version is never served stale."""
    log = Path(table) / DELTA_LOG
    newest = max((e for e in os.scandir(log) if e.name.endswith(".json")), key=lambda e: e.name, default=None)
    head = "" if newest is None else f"{newest.name}:{newest.stat().st_mtime_ns}:{newest.stat().st_ino}"
    return f"{log.stat().st_ino}:{head}"


def _actions(table: Path) -> tuple[tuple[str, int, dict[str, Any], dict[str, Any]], ...]:
    return _live_actions(str(Path(table).resolve()), _log_token(table))


def live_files(path: Path, pattern: str = "*.parquet") -> list[Path]:
    """Parquet files holding the rows of table directory ``path``, sorted by path.

    A Delta table yields its live data files (tombstoned files are never listed). They carry every
    column except the partition columns, whose values live only in the directory names, so their
    rows read like the legacy per-member files. Any other directory yields its top-level ``pattern``
    matches, so legacy readers keep their exact file list; a missing path yields ``[]``.
    """
    path = Path(path)
    if is_delta_dir(path):
        return [path / rel for rel, _size, _lo, _hi in _actions(path)]
    return sorted(p for p in path.glob(pattern) if p.is_file()) if path.is_dir() else []


def member_files(path: Path, pattern: str, *, column: str, values: Iterable[Any]) -> list[Path]:
    """Files that can hold the legacy member files of ``path`` matching ``pattern``, sorted by path.

    Legacy members are one file per ``column`` value (``btc_example_1m.parquet``) and yield
    ``live_files(path, pattern)``. In a Delta table those rows share files, so this yields the live
    files whose ``column`` min/max stats admit one of ``values`` (files without stats are kept); the
    caller keeps only rows with ``column`` in ``values`` (``member_scan`` does).
    """
    path = Path(path)
    if not is_delta_dir(path):
        return live_files(path, pattern)
    wanted = sorted(set(values))
    out = []
    for rel, _size, lows, highs in _actions(path):
        lo, hi = lows.get(column), highs.get(column)
        if lo is None or hi is None or any(lo <= value <= hi for value in wanted):
            out.append(path / rel)
    return out


def member_token(path: Path, pattern: str, *, column: str, values: Iterable[Any]) -> str | None:
    """Change token of the rows ``member_files`` covers in a Delta table, else None.

    Delta data files are immutable and uniquely named, so the token (their relative paths and
    sizes) changes whenever a commit adds or removes a file that can hold those rows. It may also
    change when only neighbouring members were rewritten (a seal, another coin's append), never the
    other way round.
    """
    path = Path(path)
    if not is_delta_dir(path):
        return None
    files = {p.relative_to(path).as_posix() for p in member_files(path, pattern, column=column, values=values)}
    return "\n".join(f"{rel}:{size}" for rel, size, _lo, _hi in _actions(path) if rel in files)


def member_scan(path: Path, *, column: str, value: Any, **scan_parquet_kwargs: Any) -> pl.LazyFrame | None:
    """Lazy scan of one legacy member file ``path``, or of its rows once its directory is a Delta table.

    An existing file scans as ``pl.scan_parquet(path, **kwargs)``. When ``path.parent`` is a Delta
    table the scan covers ``member_files`` filtered to ``column == value`` (row-group stats prune the
    other members). Returns None when no file can hold the member; a Delta file range that admits
    ``value`` without holding it yields an empty frame. A Delta scan carries the table's columns, in
    table order: a column the member's legacy file never had reads as all-null.
    """
    path = Path(path)
    if path.is_file():
        return pl.scan_parquet(path, **scan_parquet_kwargs)
    if not is_delta_dir(path.parent):
        return None
    files = member_files(path.parent, path.name, column=column, values=[value])
    if not files:
        return None
    # The table schema reads files written before an ``add_columns`` (their new columns read as null).
    schema = _live_file_schema(str(path.parent.resolve()), _log_token(path.parent))
    scan = pl.scan_parquet(files, schema=schema, missing_columns="insert", **scan_parquet_kwargs)
    return scan.filter(pl.col(column) == value)


def scan_live(
    path: Path | Iterable[Path],
    pattern: str = "*.parquet",
    *,
    column: str | None = None,
    values: Iterable[Any] | None = None,
    **scan_parquet_kwargs: Any,
) -> pl.LazyFrame | None:
    """Lazy scan of the files of one or more table directories (``live_files``, or ``member_files``
    when ``column``/``values`` are given); None when no directory has a file.

    When no directory is a Delta table this is exactly ``pl.scan_parquet(<all files>, **kwargs)``, so
    legacy readers keep their schema and row order. A Delta directory scans with the table schema
    (``missing_columns="insert"``): files sealed before an ``add_columns`` read the new column as
    null instead of setting the scan schema from the oldest file, and with ``column`` its rows are
    kept to ``values``. Several directories then concatenate diagonally in the given order.
    """
    dirs = [Path(path)] if isinstance(path, (str, os.PathLike)) else [Path(p) for p in path]
    wanted = None if values is None else sorted(set(values))

    def files_of(directory: Path) -> list[str]:
        if column is None:
            return [str(p) for p in live_files(directory, pattern)]
        return [str(p) for p in member_files(directory, pattern, column=column, values=wanted or [])]

    if not any(is_delta_dir(d) for d in dirs):
        files = [f for d in dirs for f in files_of(d)]
        return pl.scan_parquet(files, **scan_parquet_kwargs) if files else None
    scans = []
    for directory in dirs:
        files = files_of(directory)
        if not files:
            continue
        if not is_delta_dir(directory):
            scans.append(pl.scan_parquet(files, **scan_parquet_kwargs))
            continue
        schema = _live_file_schema(str(directory.resolve()), _log_token(directory))
        kwargs = {**scan_parquet_kwargs, "schema": schema, "missing_columns": "insert"}
        scan = pl.scan_parquet(files, **kwargs)
        scans.append(scan.filter(pl.col(column).is_in(wanted or [])) if column is not None else scan)
    if not scans:
        return None
    return scans[0] if len(scans) == 1 else pl.concat(scans, how="diagonal_relaxed")


def lake_scan(path: Path, **scan_parquet_kwargs: Any) -> pl.LazyFrame:
    """Lazy scan of a Delta table directory or a parquet file/glob."""
    if is_delta_dir(path):
        from data.platform.storage import delta_tables as dtab

        return dtab.scan_table(path_ref(path))
    return pl.scan_parquet(path, **scan_parquet_kwargs)


def lake_schema(path: Path) -> dict[str, pl.DataType]:
    if is_delta_dir(path):
        return dict(lake_scan(path).collect_schema())
    return dict(pl.read_parquet_schema(path))


def fingerprint(path: Path) -> tuple[int, int]:
    """Change token: ``(table version, live bytes)`` for a Delta table, ``(mtime_ns, size)`` for a file."""
    if is_delta_dir(path):
        from data.platform.storage import delta_tables as dtab

        stats = dtab.table_stats(path_ref(path))
        return int(stats.version or 0), stats.bytes
    stat = Path(path).stat()
    return stat.st_mtime_ns, stat.st_size


def duckdb_from(path: Path, ref: TableRef | None = None) -> str:
    """DuckDB ``FROM`` source: ``delta_scan`` for a Delta table (or ``ref``), else ``read_parquet``."""
    if ref is not None or is_delta_dir(path):
        from data.platform.storage import delta_tables as dtab

        return dtab.duckdb_source(ref or path_ref(path))
    return "read_parquet('" + str(path).replace("'", "''") + "')"


def load_delta_extension(con: Any) -> None:
    """Load DuckDB's ``delta`` extension, installing it on first use."""
    import duckdb

    try:
        con.execute("LOAD delta")
    except duckdb.Error:
        con.execute("INSTALL delta; LOAD delta")


__all__ = [
    "INTERNAL_DIRS",
    "KEY_MAPPING",
    "collapse",
    "delta_ref",
    "duckdb_from",
    "enclosing_delta",
    "fingerprint",
    "is_delta_dir",
    "is_table_internal",
    "key_mapping_path",
    "lake_scan",
    "lake_schema",
    "live_files",
    "member_files",
    "member_scan",
    "member_token",
    "analysis_dir",
    "load_delta_extension",
    "mapped_refs",
    "mapped_tables",
    "meta_path",
    "partition_ref",
    "path_ref",
    "scan_live",
    "walk_lake",
]
