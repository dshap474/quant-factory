"""Delta Lake tables for the lake: resolution, reads, stats and the one write engine.

A directory is a Delta table exactly when ``<dir>/_delta_log/`` exists; ``table_ref`` is the only
switch. Every write is "replace slice S with rows R" (``write_slice``): find the live files holding
rows of S, let DuckDB rebuild each one (its rows outside S plus the rows of R in its key range,
sorted by the table's sort key), write leftover rows of R to new files, then make one Delta commit
that removes the old files and adds the new ones. Memory is bounded by the touched files. No
delta-rs MERGE, predicate overwrite or ``write_deltalake`` is used. Add actions carry stats for the
key columns only, computed by DuckDB over each new file. Sidecars live under ``<table>/_qf/``.

USAGE:
    from data.platform.contracts import TableLayout
    from data.platform.storage import delta_tables as dtab

    ref = dtab.table_ref(db_root, "data/raw/1d/example/bars")
    layout = TableLayout(partition="month", sort_key=("coin", "time"), key_columns=("coin", "time"))
    ref = dtab.create_table(ref, schema, layout)                         # pa.Schema incl. "month"
    dtab.write_slice(ref, rows, slice="false", run_id=run_id)            # append
    dtab.write_slice(ref, rows, slice="coin = 'BTC' AND time >= 1790000000000", run_id=run_id)
    dtab.seal_partition(ref, "2026-10", run_id=run_id)
    report = dtab.maintain(ref)                                          # dry run by default
    frame = dtab.scan_table(ref, columns=["coin", "time"]).collect()
    con.sql(f"SELECT count(*) FROM {dtab.duckdb_source(ref)}")
"""

from __future__ import annotations

import json
import math
import os
import shutil
import time
import uuid
from collections.abc import Iterator, Mapping
from contextlib import nullcontext
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import duckdb
import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq
from deltalake import DeltaTable
from deltalake.transaction import AddAction, CommitProperties, RemoveAction

from data.platform.contracts import TableCommit, TableLayout
from data.platform.storage.locks import table_lock

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

SIDECAR_DIR = "_qf"
LAYOUT_FILE = "layout.json"
ROW_GROUP_SIZE = 100_000
DUCKDB_MEMORY_LIMIT = "4GB"
DUCKDB_THREADS = min(8, os.cpu_count() or 1)
SEAL_MIN_FILES = 8
SEAL_QUIET = timedelta(days=3)
VACUUM_RETENTION_HOURS = 7 * 24
STATIC_SUFFIXES = (".parquet",)
DEFAULT_LAYERS = ("data", "features")
_SAFE_PARTITION_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")

Kind = Literal["delta", "static", "legacy"]


class SchemaDriftError(ValueError):
    """Rows do not match the table schema under the dtype policy."""


class ProtocolError(RuntimeError):
    """The table protocol carries a feature outside the allowlist."""


class WriteCheckError(RuntimeError):
    """Row count, checksum or non-null counts disagree before and after a write."""


# --------------------------------------------------------------------------- #
# Table references
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class TableRef:
    """A resolved lake table: ``kind`` decides the read and write paths; ``filters`` select rows."""

    db_root: Path
    key: str
    path: Path
    kind: Kind
    filters: tuple[tuple[str, Any], ...] = ()
    requested_key: str | None = None

    @property
    def sidecar_dir(self) -> Path:
        return self.path / SIDECAR_DIR


def is_delta_dir(path: Path) -> bool:
    return (path / "_delta_log").is_dir()


@lru_cache(maxsize=8)
def _load_mapping_cached(path: str, mtime_ns: int) -> dict[str, dict[str, Any]]:
    del mtime_ns  # cache key only
    if path.endswith(".parquet"):
        records = pl.read_parquet(path).to_dicts()
    else:
        records = json.loads(Path(path).read_text(encoding="utf-8"))
    out: dict[str, dict[str, Any]] = {}
    for record in records:
        filters = record.get("filters") or {}
        if isinstance(filters, str):
            filters = json.loads(filters)
        out[str(record["legacy_key"]).strip("/")] = {
            "table": str(record.get("table") or record["legacy_key"]).strip("/"),
            "filters": dict(filters),
            "kind": record.get("kind"),
        }
    return out


def load_key_mapping(mapping: Path | Mapping[str, Mapping[str, Any]] | None) -> dict[str, dict[str, Any]]:
    """Legacy-key mapping: ``legacy_key -> {table, filters, kind}``, from a JSON list or a parquet table.

    Records have ``legacy_key`` (relative to the db root), ``table`` (target table key), optional
    ``filters`` (a dict or a JSON object string, e.g. ``{"coin": "BTC"}``) and optional
    ``kind`` (``"static"`` marks a plain file or directory kept read-only on purpose).
    """
    if mapping is None:
        return {}
    if isinstance(mapping, Mapping):
        return {str(k).strip("/"): dict(v) for k, v in mapping.items()}
    path = Path(mapping)
    if not path.exists():
        return {}
    return _load_mapping_cached(str(path), path.stat().st_mtime_ns)


def _relative_key(db_root: Path, key: str | Path) -> str:
    candidate = Path(key)
    if candidate.is_absolute():
        return candidate.resolve().relative_to(db_root).as_posix()
    return candidate.as_posix().strip("/")


def table_ref(
    db_root: Path,
    key: str | Path,
    *,
    mapping: Path | Mapping[str, Mapping[str, Any]] | None = None,
) -> TableRef:
    """Resolve ``key`` (relative to ``db_root``, or an absolute path under it) to a ``TableRef``.

    ``delta`` when the target directory holds ``_delta_log/``; ``static`` when the mapping declares
    it; otherwise ``legacy`` (a plain file or a directory of parquet files, or a path not yet written).
    A mapped legacy key whose target table is Delta resolves to that table plus the mapped row filter.
    """
    db_root = Path(db_root).resolve()
    rel = _relative_key(db_root, key)
    entry = load_key_mapping(mapping).get(rel)
    if entry is not None:
        target = db_root / entry["table"]
        if is_delta_dir(target):
            filters = tuple(sorted(entry.get("filters", {}).items()))
            return TableRef(db_root, entry["table"], target, "delta", filters, requested_key=rel)
        kind: Kind = "static" if entry.get("kind") == "static" else "legacy"
        return TableRef(db_root, rel, db_root / rel, kind, requested_key=rel)
    path = db_root / rel
    if is_delta_dir(path):
        return TableRef(db_root, rel, path, "delta", requested_key=rel)
    return TableRef(db_root, rel, path, "legacy", requested_key=rel)


def iter_tables(
    db_root: Path,
    layer: str | None = None,
    *,
    mapping: Path | Mapping[str, Mapping[str, Any]] | None = None,
) -> Iterator[TableRef]:
    """Yield every table under ``layer`` (default ``data`` and ``features``) without listing Delta data files.

    Delta tables yield once and are not descended into; ``_``/``.``-prefixed entries are skipped;
    mapped static directories yield once; other parquet files yield as legacy or static refs.
    """
    db_root = Path(db_root).resolve()
    entries = load_key_mapping(mapping)
    static_keys = {k for k, v in entries.items() if v.get("kind") == "static"}
    for top in [layer] if layer else DEFAULT_LAYERS:
        start = db_root / top
        if not start.is_dir():
            continue
        for current, dirs, files in os.walk(start):
            here = Path(current)
            rel = here.relative_to(db_root).as_posix()
            if is_delta_dir(here):
                dirs[:] = []
                yield TableRef(db_root, rel, here, "delta", requested_key=rel)
                continue
            if rel in static_keys:
                dirs[:] = []
                yield TableRef(db_root, rel, here, "static", requested_key=rel)
                continue
            dirs[:] = sorted(d for d in dirs if not d.startswith(("_", ".")))
            for name in sorted(files):
                if name.startswith(("_", ".")) or not name.endswith(STATIC_SUFFIXES):
                    continue
                file_key = f"{rel}/{name}"
                kind: Kind = "static" if file_key in static_keys else "legacy"
                yield TableRef(db_root, file_key, here / name, kind, requested_key=file_key)


# --------------------------------------------------------------------------- #
# Reads
# --------------------------------------------------------------------------- #


def _sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int | float):
        return repr(value)
    return "'" + str(value).replace("'", "''") + "'"


def _legacy_glob(ref: TableRef) -> str:
    return str(ref.path) if ref.path.is_file() else f"{ref.path}/**/*.parquet"


def scan_table(ref: TableRef, columns: list[str] | None = None, version: int | None = None) -> pl.LazyFrame:
    """Lazy Polars scan of a table, with the ref's row filter applied."""
    if ref.kind == "delta":
        frame = pl.scan_delta(str(ref.path), version=version)
    else:
        if version is not None:
            raise ValueError(f"{ref.key} is {ref.kind}; only Delta tables have versions")
        frame = pl.scan_parquet(_legacy_glob(ref), missing_columns="insert", extra_columns="ignore")
    for column, value in ref.filters:
        frame = frame.filter(pl.col(column) == value)
    return frame.select(columns) if columns else frame


def duckdb_source(ref: TableRef) -> str:
    """A DuckDB ``FROM`` source for the table (needs the ``delta`` extension for Delta tables)."""
    path = str(ref.path).replace("'", "''")
    if ref.kind == "delta":
        source = f"delta_scan('{path}')"
    elif ref.path.is_file():
        source = f"read_parquet('{path}')"
    else:
        source = f"read_parquet('{path}/**/*.parquet', union_by_name=true)"
    if not ref.filters:
        return source
    where = " AND ".join(f'"{c}" = {_sql_literal(v)}' for c, v in ref.filters)
    return f"(SELECT * FROM {source} WHERE {where})"


def _add_actions(dt: DeltaTable) -> pa.Table:
    return pa.table(dt.get_add_actions(flatten=True))


def _legacy_files(ref: TableRef) -> list[Path]:
    if ref.path.is_file():
        return [ref.path]
    return sorted(ref.path.glob("**/*.parquet")) if ref.path.is_dir() else []


@dataclass(frozen=True)
class TableStats:
    rows: int
    files: int
    bytes: int
    key_min: dict[str, Any] = field(default_factory=dict)
    key_max: dict[str, Any] = field(default_factory=dict)
    version: int | None = None


def table_stats(ref: TableRef) -> TableStats:
    """Rows, files, bytes and key min/max from add actions (Delta) or parquet footers; reads no data.

    The ref's row filter is not applied: stats describe the whole table.
    """
    if ref.kind != "delta":
        files = _legacy_files(ref)
        return TableStats(
            rows=sum(pq.ParquetFile(f).metadata.num_rows for f in files),
            files=len(files),
            bytes=sum(f.stat().st_size for f in files),
        )
    dt = DeltaTable(str(ref.path))
    actions = _add_actions(dt)
    names = set(actions.column_names)
    layout = read_layout(ref)
    key_columns = layout.key_columns if layout else ()
    key_min: dict[str, Any] = {}
    key_max: dict[str, Any] = {}
    for column in key_columns:
        lows = (
            [v for v in actions.column(f"min.{column}").to_pylist() if v is not None]
            if f"min.{column}" in names
            else []
        )
        highs = (
            [v for v in actions.column(f"max.{column}").to_pylist() if v is not None]
            if f"max.{column}" in names
            else []
        )
        if lows:
            key_min[column] = min(lows)
        if highs:
            key_max[column] = max(highs)
    records = [n or 0 for n in actions.column("num_records").to_pylist()] if actions.num_rows else []
    return TableStats(
        rows=sum(records),
        files=actions.num_rows,
        bytes=sum(actions.column("size_bytes").to_pylist()) if actions.num_rows else 0,
        key_min=key_min,
        key_max=key_max,
        version=dt.version(),
    )


def table_version(ref: TableRef) -> int | None:
    return DeltaTable(str(ref.path)).version() if ref.kind == "delta" else None


def table_commit_time(ref: TableRef) -> datetime | None:
    """Time of the latest commit (Delta), or the newest file mtime (static/legacy)."""
    if ref.kind == "delta":
        history = DeltaTable(str(ref.path)).history(1)
        return datetime.fromtimestamp(history[0]["timestamp"] / 1000, tz=UTC) if history else None
    files = _legacy_files(ref)
    return datetime.fromtimestamp(max(f.stat().st_mtime for f in files), tz=UTC) if files else None


# --------------------------------------------------------------------------- #
# Protocol, layout sidecar and dtype policy
# --------------------------------------------------------------------------- #


def _has_naive_timestamp(schema: pa.Schema) -> bool:
    def naive(t: pa.DataType) -> bool:
        if pa.types.is_timestamp(t):
            return t.tz is None
        if pa.types.is_struct(t):
            return any(naive(t.field(i).type) for i in range(t.num_fields))
        if pa.types.is_list(t) or pa.types.is_large_list(t) or pa.types.is_fixed_size_list(t):
            return naive(t.value_type)
        if pa.types.is_map(t):
            return naive(t.key_type) or naive(t.item_type)
        return False

    return any(naive(f.type) for f in schema)


def check_protocol(dt: DeltaTable) -> None:
    """Allow reader 1 / writer 2 with no features, or 3 / 7 with exactly ``timestampNtz``."""
    p = dt.protocol()
    plain = (p.min_reader_version, p.min_writer_version) == (1, 2) and not p.reader_features and not p.writer_features
    ntz = (
        (p.min_reader_version, p.min_writer_version) == (3, 7)
        and set(p.reader_features or ()) == {"timestampNtz"}
        and set(p.writer_features or ()) == {"timestampNtz"}
    )
    if not (plain or ntz):
        raise ProtocolError(f"{dt.table_uri}: protocol {p} is outside the allowlist")


def read_layout(ref: TableRef) -> TableLayout | None:
    path = ref.sidecar_dir / LAYOUT_FILE
    return TableLayout.model_validate_json(path.read_text(encoding="utf-8")) if path.exists() else None


def _require_layout(ref: TableRef) -> TableLayout:
    layout = read_layout(ref)
    if layout is None:
        raise FileNotFoundError(f"{ref.key}: missing {SIDECAR_DIR}/{LAYOUT_FILE}; create the table with create_table")
    return layout


def _table_schema(dt: DeltaTable) -> pa.Schema:
    return pa.schema(dt.schema().to_arrow())


def _type_family(t: pa.DataType) -> str:
    """Delta-level type identity: string/binary/list encodings collapse, timestamps keep naive vs aware."""
    if pa.types.is_string(t) or pa.types.is_large_string(t) or pa.types.is_string_view(t):
        return "string"
    if pa.types.is_binary(t) or pa.types.is_large_binary(t) or pa.types.is_binary_view(t):
        return "binary"
    if pa.types.is_timestamp(t):
        return "timestamp_ntz" if t.tz is None else "timestamp"
    if pa.types.is_date(t):
        return "date"
    if pa.types.is_list(t) or pa.types.is_large_list(t) or pa.types.is_list_view(t) or pa.types.is_large_list_view(t):
        return f"list<{_type_family(t.value_type)}>"
    if pa.types.is_struct(t):
        inner = ",".join(f"{t.field(i).name}:{_type_family(t.field(i).type)}" for i in range(t.num_fields))
        return f"struct<{inner}>"
    if pa.types.is_dictionary(t):
        return _type_family(t.value_type)
    return str(t)


def conform_rows(rows: pa.Table, schema: pa.Schema) -> pa.Table:
    """Apply the dtype policy: reject new columns and type drift; cast unsigned to int64, null-typed and
    missing columns to the declared type, timestamp units to the table's unit (raising on lost precision).
    """
    extra = [name for name in rows.column_names if schema.get_field_index(name) < 0]
    if extra:
        raise SchemaDriftError(f"columns not in the table schema: {extra}; add them with add_columns first")
    columns = []
    for target in schema:
        if target.name not in rows.column_names:
            columns.append(pa.nulls(rows.num_rows, target.type))
            continue
        column = rows.column(target.name)
        source = column.type
        if pa.types.is_dictionary(source):
            column, source = column.cast(source.value_type), source.value_type
        if pa.types.is_null(source):
            pass
        elif pa.types.is_unsigned_integer(source):
            if not pa.types.is_int64(target.type):
                raise SchemaDriftError(f"{target.name}: unsigned {source} only casts into an int64 column")
        elif _type_family(source) != _type_family(target.type):
            raise SchemaDriftError(f"{target.name}: {source} does not match the table type {target.type}")
        columns.append(column.cast(target.type, safe=True))
    return pa.Table.from_arrays(columns, schema=schema)


def _to_arrow(rows: Any) -> pa.Table:
    if isinstance(rows, pa.Table):
        return rows
    if isinstance(rows, pl.LazyFrame):
        rows = rows.collect()
    if isinstance(rows, pl.DataFrame):
        return rows.to_arrow()
    raise TypeError(f"rows must be a pyarrow Table or a Polars frame, got {type(rows).__name__}")


# --------------------------------------------------------------------------- #
# DuckDB plumbing
# --------------------------------------------------------------------------- #


class _Duck:
    """One DuckDB connection per write: memory-capped, spilling under ``<db_root>/.tmp``, session time zone
    UTC (so ``TIMESTAMPTZ`` literals in a slice predicate without an offset mean UTC)."""

    def __init__(self, ref: TableRef, schema: pa.Schema, layout: TableLayout) -> None:
        self.tmp = ref.db_root / ".tmp" / f"duckdb-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self.tmp.mkdir(parents=True, exist_ok=True)
        self.con = duckdb.connect()
        self.con.execute(
            f"SET memory_limit='{DUCKDB_MEMORY_LIMIT}'; SET threads={DUCKDB_THREADS}; "
            f"SET temp_directory='{self.tmp}'; SET preserve_insertion_order=true; SET TimeZone='UTC'"
        )
        try:
            self.con.execute("LOAD delta")
        except duckdb.Error:
            self.con.execute("INSTALL delta; LOAD delta")
        self.schema = schema
        self.layout = layout
        self.con.register("__empty", schema.empty_table())
        self.types = {row[0]: row[1] for row in self.con.execute("DESCRIBE SELECT * FROM __empty").fetchall()}
        self.con.unregister("__empty")
        self.partition = layout.partition
        self.columns = [f.name for f in schema]
        self.file_columns = [c for c in self.columns if c != self.partition]
        order = dict.fromkeys(c for c in (*layout.sort_key, *layout.key_columns) if c != layout.partition)
        self.order = ", ".join(_q(c) for c in order)  # full key order: deterministic with sort-key ties

    def close(self) -> None:
        self.con.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def file_select(self, path: str, partition_value: Any) -> str:
        """Full-row select (declared types, partition column restored) over one data file."""
        present = set(pq.read_schema(path).names)
        parts = []
        for column in self.columns:
            if column == self.partition:
                value = _sql_literal(partition_value)
            elif column in present:
                value = _q(column)
            else:
                value = "NULL"
            parts.append(f"CAST({value} AS {self.types[column]}) AS {_q(column)}")
        return f"SELECT {', '.join(parts)} FROM read_parquet('{_esc(path)}')"

    def aggregate(self, source: str) -> dict[str, int]:
        """Row count, whole-row checksum and per-column non-null counts of a full-row source."""
        cols = ", ".join(_q(c) for c in self.columns)
        nonnull = ", ".join(f"count({_q(c)})" for c in self.columns)
        row = self.con.execute(f"SELECT count(*), sum(hash({cols}))::HUGEINT, {nonnull} FROM {source}").fetchone()
        return {
            "rows": row[0],
            "checksum": int(row[1] or 0),
            **{f"nonnull.{c}": row[i + 2] for i, c in enumerate(self.columns)},
        }

    def copy_out(self, select: str, out: Path) -> None:
        cols = ", ".join(_q(c) for c in self.file_columns)
        out.parent.mkdir(parents=True, exist_ok=True)
        self.con.execute(
            f"COPY (SELECT {cols} FROM ({select}) ORDER BY {self.order}) TO '{_esc(str(out))}' "
            f"(FORMAT parquet, COMPRESSION zstd, ROW_GROUP_SIZE {ROW_GROUP_SIZE})"
        )

    def file_stats(self, out: Path) -> tuple[int, str]:
        """numRecords plus min/max/nullCount for the key columns, computed by DuckDB over the file."""
        keys = [c for c in dict.fromkeys((*self.layout.key_columns, *self.layout.sort_key)) if c != self.partition]
        keys = [c for c in keys if _stats_kind(self.schema.field(c).type) is not None]
        exprs = ", ".join(f"min({_q(c)}), max({_q(c)}), count(*) - count({_q(c)})" for c in keys)
        row = self.con.execute(
            f"SELECT count(*){', ' + exprs if exprs else ''} FROM read_parquet('{_esc(str(out))}')"
        ).fetchone()
        mins, maxs, nulls = {}, {}, {}
        for i, column in enumerate(keys):
            lo, hi, nn = row[1 + 3 * i : 4 + 3 * i]
            kind = _stats_kind(self.schema.field(column).type)
            nulls[column] = nn
            if lo is not None:
                mins[column] = _format_stat(lo, kind, upper=False)
                maxs[column] = _format_stat(hi, kind, upper=True)
        return row[0], json.dumps({"numRecords": row[0], "minValues": mins, "maxValues": maxs, "nullCount": nulls})


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _esc(text: str) -> str:
    return text.replace("'", "''")


def _stats_kind(t: pa.DataType) -> str | None:
    if pa.types.is_integer(t):
        return "int"
    if pa.types.is_string(t) or pa.types.is_large_string(t) or pa.types.is_string_view(t):
        return "string"
    if pa.types.is_date(t):
        return "date"
    if pa.types.is_timestamp(t):
        return "timestamp_ntz" if t.tz is None else "timestamp"
    return None


def _format_stat(value: Any, kind: str, *, upper: bool) -> Any:
    """Delta stat values; timestamps go to millisecond precision, the max rounded up so skipping stays safe."""
    if kind in ("int", "string"):
        return value
    if kind == "date":
        return value.isoformat()
    ts: datetime = value
    if ts.tzinfo is not None:
        ts = ts.astimezone(UTC).replace(tzinfo=None)
    floor = ts.replace(microsecond=ts.microsecond // 1000 * 1000)
    if upper and floor != ts:
        floor += timedelta(milliseconds=1)
    text = floor.strftime("%Y-%m-%dT%H:%M:%S.") + f"{floor.microsecond // 1000:03d}"
    return text + "Z" if kind == "timestamp" else text.replace("T", " ")


def _partition_string(value: Any) -> str:
    text = str(value)
    if not text or not set(text) <= _SAFE_PARTITION_CHARS:
        raise ValueError(f"partition value {value!r} must be non-empty and use only [A-Za-z0-9_.-]")
    return text


# --------------------------------------------------------------------------- #
# Table creation
# --------------------------------------------------------------------------- #


def create_table(ref: TableRef, schema: pa.Schema, layout: TableLayout, *, run_id: str = "create") -> TableRef:
    """Create an empty Delta table at ``ref.path`` with protocol 1/2 (3/7 + ``timestampNtz`` only when a
    naive timestamp column exists), and store ``layout`` in ``_qf/layout.json``. Returns the Delta ref.
    """
    if ref.kind == "static":
        raise ValueError(f"{ref.key} is static (read-only)")
    if is_delta_dir(ref.path):
        raise FileExistsError(f"{ref.key} is already a Delta table")
    if ref.path.exists():
        stray = [p.name for p in ref.path.iterdir() if not p.name.startswith(("_", "."))]
        if stray:
            raise FileExistsError(f"{ref.key} holds non-Delta entries {stray[:5]}; convert it, do not create over it")
    names = set(schema.names)
    missing = [c for c in (*layout.sort_key, *layout.key_columns) if c not in names]
    if layout.partition is not None:
        missing += [] if layout.partition in names else [layout.partition]
    if missing:
        raise SchemaDriftError(f"layout columns not in the schema: {missing}")
    for f in schema:
        if pa.types.is_null(f.type):
            raise SchemaDriftError(f"{f.name}: declare a type; null-typed columns are not allowed")
        if pa.types.is_unsigned_integer(f.type):
            raise SchemaDriftError(f"{f.name}: declare unsigned integers as int64")
    if layout.partition is not None:
        part_type = schema.field(layout.partition).type
        if _stats_kind(part_type) not in ("int", "string"):
            raise SchemaDriftError(f"partition column {layout.partition} must be a string or integer column")
    dt = DeltaTable.create(
        str(ref.path),
        schema,
        mode="error",
        partition_by=[layout.partition] if layout.partition else None,
        commit_properties=CommitProperties(custom_metadata={"qf.run_id": run_id, "qf.operation": "create"}),
    )
    check_protocol(dt)
    ntz = "timestampNtz" in (dt.protocol().writer_features or ())
    if ntz != _has_naive_timestamp(schema):
        raise ProtocolError(f"{ref.key}: timestampNtz is {ntz} but naive timestamps present is {not ntz}")
    ref.path.joinpath(SIDECAR_DIR).mkdir(exist_ok=True)
    (ref.sidecar_dir / LAYOUT_FILE).write_text(layout.model_dump_json(indent=2), encoding="utf-8")
    return TableRef(ref.db_root, ref.key, ref.path, "delta", requested_key=ref.requested_key)


def add_columns(ref: TableRef, fields: list[pa.Field], *, run_id: str, allow_timestamp_ntz: bool = False) -> int:
    """Additive schema change: append nullable columns (one commit). Returns the new version.

    A naive timestamp column on a table without ``timestampNtz`` would upgrade the protocol to 3/7;
    that is refused unless ``allow_timestamp_ntz=True``.
    """
    from deltalake.schema import Field as DeltaField

    with table_lock(ref):
        dt = _delta(ref)
        has_ntz = "timestampNtz" in (dt.protocol().writer_features or ())
        if not has_ntz and not allow_timestamp_ntz and _has_naive_timestamp(pa.schema(fields)):
            raise ProtocolError(f"{ref.key}: adding a naive timestamp column would enable timestampNtz")
        dt.alter.add_columns(
            [DeltaField.from_arrow(f.with_nullable(True)) for f in fields],
            commit_properties=CommitProperties(custom_metadata={"qf.run_id": run_id, "qf.operation": "add_columns"}),
        )
        dt = DeltaTable(str(ref.path))
        check_protocol(dt)
        return dt.version()


def _delta(ref: TableRef) -> DeltaTable:
    if ref.kind != "delta":
        raise ValueError(f"{ref.key} is {ref.kind}; only Delta tables are written by this engine")
    if ref.filters:
        raise ValueError(f"{ref.key}: write through the table ref, not a filtered legacy-key ref")
    dt = DeltaTable(str(ref.path))
    check_protocol(dt)
    return dt


# --------------------------------------------------------------------------- #
# Write engine
# --------------------------------------------------------------------------- #


def _file_rows(actions: pa.Table, partition: str | None) -> list[dict[str, Any]]:
    rows = actions.to_pylist()
    for row in rows:
        row["_pv"] = row.get(f"partition.{partition}") if partition else None
    return rows


def _new_path(ref: TableRef, partition: str | None, value: Any, tag: str, i: int) -> Path:
    base = ref.path / f"{partition}={_partition_string(value)}" if partition else ref.path
    return base / f"part-{tag}-{i:04d}.zstd.parquet"


def _add_action(ref: TableRef, duck: _Duck, out: Path, value: Any, now: int) -> tuple[int, AddAction]:
    n, stats = duck.file_stats(out)
    pv = {duck.partition: _partition_string(value)} if duck.partition else {}
    return n, AddAction(out.relative_to(ref.path).as_posix(), out.stat().st_size, pv, now, True, stats)


def _remove_action(row: dict[str, Any], partition: str | None, now: int) -> RemoveAction:
    pv = {partition: None if row["_pv"] is None else str(row["_pv"])} if partition else {}
    return RemoveAction(row["path"], True, now, row["size_bytes"], pv)


def _sum_aggregates(*aggs: dict[str, int]) -> dict[str, int]:
    out: dict[str, int] = {}
    for agg in aggs:
        for k, v in agg.items():
            out[k] = out.get(k, 0) + v
    return out


def _check_equal(label: str, expected: dict[str, int], actual: dict[str, int]) -> None:
    if expected != actual:
        diff = {
            k: (expected.get(k), actual.get(k)) for k in set(expected) | set(actual) if expected.get(k) != actual.get(k)
        }
        raise WriteCheckError(f"{label}: expected vs actual differ {diff}")


def _landed(uri: str, tag: str) -> int | None:
    """Version of the commit carrying ``qf.tag == tag`` among the latest few, or None."""
    for entry in DeltaTable(uri).history(10):
        if entry.get("qf.tag") == tag:
            return int(entry["version"])
    return None


def _commit(dt: DeltaTable, actions: list[Any], *, layout: TableLayout, metadata: dict[str, str], **kwargs: Any) -> int:
    """Commit ``actions`` and return the new version.

    Raises only when the commit did not land: if ``create_write_transaction`` fails after its log entry
    was written (a post-commit hook, say), the tagged entry is found and its version returned.
    """
    metadata = {**metadata, "qf.tag": uuid.uuid4().hex}
    try:
        dt.create_write_transaction(
            actions,
            schema=dt.schema(),
            partition_by=[layout.partition] if layout.partition else None,
            commit_properties=CommitProperties(custom_metadata=metadata),
            **kwargs,
        )
    except BaseException:
        version = _landed(dt.table_uri, metadata["qf.tag"])
        if version is None:
            raise
        return version
    version = _landed(dt.table_uri, metadata["qf.tag"])
    if version is None:
        raise RuntimeError(f"{dt.table_uri}: commit returned but its log entry was not found")
    return version


def _unlink_all(paths: list[Path]) -> None:
    for path in paths:
        path.unlink(missing_ok=True)


def write_slice(
    ref: TableRef,
    rows: Any,
    *,
    slice: str,
    run_id: str,
    source: str | None = None,
    allow_delete: bool = False,
) -> TableCommit:
    """Replace the rows matching SQL predicate ``slice`` with ``rows`` in one commit.

    ``slice="false"`` appends (touches no files); ``"true"`` replaces the whole table. Every row of a
    non-append write must satisfy the slice, and no key may already exist outside the slice. Empty
    ``rows`` make no commit unless ``allow_delete=True``, which deletes the slice. Checks row count,
    whole-row checksum and non-null counts of the rebuilt files before the commit, and the table row
    total and the slice read back through ``delta_scan`` after it; a failed after-check reverts the
    commit (by a new commit) and raises ``WriteCheckError``. Schema and rows are read under the lock.
    """
    started = time.perf_counter()
    arrow = _to_arrow(rows)
    append = slice.strip().lower() == "false"
    commit = TableCommit(table=ref.key, operation="write_slice", run_id=run_id, slice=slice)
    if arrow.num_rows == 0 and (append or not allow_delete):
        commit.seconds = time.perf_counter() - started
        return commit
    with table_lock(ref):
        dt = _delta(ref)
        layout = _require_layout(ref)
        schema = _table_schema(dt)
        table = conform_rows(arrow, schema)
        del arrow
        if layout.partition and table.num_rows and table.column(layout.partition).null_count:
            raise SchemaDriftError(f"partition column {layout.partition} has nulls")
        duck = _Duck(ref, schema, layout)
        try:
            _write_slice_locked(ref, dt, duck, table, layout, slice, append, commit, source)
        finally:
            duck.close()
    commit.seconds = time.perf_counter() - started
    return commit


def _key_box(duck: _Duck, source: str, layout: TableLayout) -> str:
    """A pushdown-able bounding box (partition IN list, key BETWEEN min and max) around ``source``'s keys."""
    con, part = duck.con, layout.partition
    conds: list[str] = []
    if part:
        values = [r[0] for r in con.execute(f"SELECT DISTINCT {_q(part)} FROM {source}").fetchall()]
        if len(values) <= 1000:
            conds.append(f"{_q(part)} IN ({', '.join(_sql_literal(v) for v in values)})")
    for column in layout.key_columns:
        if column == part or _stats_kind(duck.schema.field(column).type) is None:
            continue
        lo, hi = con.execute(f"SELECT min({_q(column)}), max({_q(column)}) FROM {source}").fetchone()
        if lo is not None:
            cast = duck.types[column]
            conds.append(
                f"{_q(column)} BETWEEN CAST({_sql_literal(_lit(lo))} AS {cast}) AND CAST({_sql_literal(_lit(hi))} AS {cast})"
            )
    return " AND ".join(conds) or "TRUE"


def _write_slice_locked(
    ref: TableRef,
    dt: DeltaTable,
    duck: _Duck,
    table: pa.Table,
    layout: TableLayout,
    slice: str,
    append: bool,
    commit: TableCommit,
    source: str | None,
) -> None:
    con, part = duck.con, layout.partition
    bare = f"({slice})"  # WHERE drops NULL; keeps delta_scan file skipping
    kept_filter = f"NOT coalesce(({slice}), false)"
    root = str(ref.path.resolve())
    scan = f"delta_scan('{_esc(root)}')"
    con.register("__rows_in", table)
    new_agg = duck.aggregate("__rows_in")
    if not append:
        outside = con.execute(f"SELECT count(*) FROM __rows_in WHERE {kept_filter}").fetchone()[0]
        if outside:
            raise ValueError(f"{outside} rows fall outside the slice {slice!r}")
    key_cols = list(dict.fromkeys(((part,) if part else ()) + layout.key_columns))
    keys = ", ".join(_q(c) for c in key_cols)
    dupes = con.execute(
        f"SELECT count(*) FROM (SELECT {keys} FROM __rows_in GROUP BY ALL HAVING count(*) > 1)"
    ).fetchone()[0]
    if dupes:
        raise ValueError(f"rows carry {dupes} duplicated keys ({keys})")
    if table.num_rows and slice.strip().lower() != "true":
        box = _key_box(duck, "__rows_in", layout)
        join = " AND ".join(f"e.{_q(c)} IS NOT DISTINCT FROM n.{_q(c)}" for c in key_cols)
        clash = con.execute(
            f"SELECT count(*) FROM (SELECT {keys} FROM {scan} WHERE {box} AND {kept_filter}) e "
            f"JOIN __rows_in n ON {join}"
        ).fetchone()[0]
        if clash:
            raise ValueError(f"{clash} rows carry keys that already exist outside the slice {slice!r}")

    files = _file_rows(_add_actions(dt), part)
    before_records = sum(f["num_records"] or 0 for f in files)
    if append:
        touched: list[dict[str, Any]] = []
    elif slice.strip().lower() == "true":
        touched = files
    else:
        hits = {
            os.path.relpath(row[0], root)
            for row in con.execute(
                f"SELECT DISTINCT filename FROM delta_scan('{_esc(root)}', filename=true) WHERE {bare}"
            ).fetchall()
        }
        touched = [f for f in files if os.path.normpath(f["path"]) in hits]

    # Place each new row once: the first touched file whose partition and key box contain it, else
    # (-1) a new file, chunked by a row number over the full key order computed once.
    boxes = []
    for i, f in enumerate(touched):
        cond = [f"{_q(part)} = {_sql_literal(f['_pv'])}"] if part else []
        for column in layout.key_columns:
            lo, hi = f.get(f"min.{column}"), f.get(f"max.{column}")
            if column != part and lo is not None and hi is not None:
                cast = duck.types[column]
                cond.append(
                    f"{_q(column)} BETWEEN CAST({_sql_literal(_lit(lo))} AS {cast}) "
                    f"AND CAST({_sql_literal(_lit(hi))} AS {cast})"
                )
        boxes.append(f"WHEN {' AND '.join(cond) or 'TRUE'} THEN {i}")
    assign = f"CASE {' '.join(boxes)} ELSE -1 END" if boxes else "-1"
    by = ", ".join([_q(part), "__f"] if part else ["__f"])
    con.execute(
        f"CREATE TEMP TABLE placed AS SELECT *, (row_number() OVER (PARTITION BY {by} ORDER BY {duck.order}) - 1) "
        f"// {layout.target_file_rows} AS __c FROM (SELECT *, {assign} AS __f FROM __rows_in)"
    )
    con.unregister("__rows_in")

    tag = f"v{dt.version() + 1}-{uuid.uuid4().hex[:12]}"
    now = int(time.time() * 1000)
    cols = ", ".join(_q(c) for c in duck.columns)
    actions: list[Any] = []
    adds: list[AddAction] = []
    written: list[Path] = []
    kept_agg: dict[str, int] = {}
    try:
        for i, f in enumerate(touched):
            kept = f"SELECT * FROM ({duck.file_select(str(ref.path / f['path']), f['_pv'])}) WHERE {kept_filter}"
            kept_agg = _sum_aggregates(kept_agg, duck.aggregate(f"({kept})"))
            out = _new_path(ref, part, f["_pv"], tag, i)
            written.append(out)
            duck.copy_out(f"{kept} UNION ALL SELECT {cols} FROM placed WHERE __f = {i}", out)
            actions.append(_remove_action(f, part, now))
            n, add = _add_action(ref, duck, out, f["_pv"], now)
            if n:
                actions.append(add)
                adds.append(add)
            else:
                out.unlink()
        groups = con.execute(
            f"SELECT {_q(part) if part else 'NULL'}, __c FROM placed WHERE __f = -1 GROUP BY ALL ORDER BY ALL"
        ).fetchall()
        for j, (value, chunk) in enumerate(groups, start=len(touched)):
            where = f"__f = -1 AND __c = {chunk}" + (f" AND {_q(part)} = {_sql_literal(value)}" if part else "")
            out = _new_path(ref, part, value, tag, j)
            written.append(out)
            duck.copy_out(f"SELECT {cols} FROM placed WHERE {where}", out)
            _, add = _add_action(ref, duck, out, value, now)
            actions.append(add)
            adds.append(add)
        con.execute("DROP TABLE placed")
        written_agg = _sum_aggregates(
            *(duck.aggregate(f"({duck.file_select(str(ref.path / a.path), _pv_of(a, part))})") for a in adds)
        )
        _check_equal(
            "rebuilt files vs kept rows + new rows", _sum_aggregates(kept_agg, new_agg), written_agg or _zero(duck)
        )
        checks = ["rows_in_slice", "unique_keys", "no_existing_keys", "rebuilt_rows_checksum_nonnull"]
        commit.checks_passed = checks
        if not actions:
            return
        metadata = {"qf.run_id": commit.run_id, "qf.operation": "write_slice", "qf.slice": slice}
        if source:
            metadata["qf.source"] = source
        version = _commit(dt, actions, layout=layout, metadata=metadata, mode="append")
    except BaseException:
        _unlink_all(written)  # nothing committed: _commit raises only when no log entry landed
        raise
    # Committed: the new files belong to the table now. Failures from here revert by commit only.
    deleted = sum(f["num_records"] or 0 for f in touched) - kept_agg.get("rows", 0)
    after = DeltaTable(str(ref.path))
    check_protocol(after)
    after_records = sum(n or 0 for n in _add_actions(after).column("num_records").to_pylist())
    try:
        if after_records != before_records - deleted + new_agg["rows"]:
            raise WriteCheckError(f"table rows {after_records} != {before_records} - {deleted} + {new_agg['rows']}")
        if not append:
            readback = duck.aggregate(f"(SELECT {cols} FROM {scan} WHERE {bare})")
            _check_equal("slice read back through delta_scan vs new rows", new_agg, readback)
    except WriteCheckError:
        _revert(ref, after, duck, actions, layout, commit.run_id, version)
        raise
    commit.version = version
    commit.rows_written = new_agg["rows"]
    commit.rows_deleted = deleted
    commit.files_added = len(adds)
    commit.files_removed = len(touched)
    commit.checks_passed = [*checks, "table_rows", *([] if append else ["slice_readback_checksum_nonnull"]), "protocol"]


def _lit(value: Any) -> Any:
    if isinstance(value, datetime | date):
        return value.isoformat()
    return value


def _pv_of(add: AddAction, partition: str | None) -> Any:
    return add.partition_values.get(partition) if partition else None


def _zero(duck: _Duck) -> dict[str, int]:
    return {"rows": 0, "checksum": 0, **{f"nonnull.{c}": 0 for c in duck.columns}}


def _revert(
    ref: TableRef, dt: DeltaTable, duck: _Duck, actions: list[Any], layout: TableLayout, run_id: str, version: int
) -> None:
    """Undo a commit: remove its adds and re-add the files it removed (still on disk until vacuum)."""
    now = int(time.time() * 1000)
    inverse: list[Any] = []
    for action in actions:
        if isinstance(action, AddAction):
            inverse.append(RemoveAction(action.path, True, now, action.size, dict(action.partition_values)))
        else:
            pv = dict(action.partition_values or {})
            _, add = _add_action(
                ref, duck, ref.path / action.path, pv.get(layout.partition) if layout.partition else None, now
            )
            inverse.append(add)
    metadata = {"qf.run_id": run_id, "qf.operation": "revert", "qf.reverts": str(version)}
    _commit(dt, inverse, layout=layout, metadata=metadata, mode="append")


# --------------------------------------------------------------------------- #
# Seal and maintenance
# --------------------------------------------------------------------------- #


def _cut_ranges(counts: list[tuple[Any, int]], rows_per_file: int) -> list[tuple[Any, Any]]:
    """Greedy cut of sorted (first-key value, rows) into contiguous ranges of about ``rows_per_file`` rows."""
    ranges, start, acc = [], None, 0
    for i, (value, n) in enumerate(counts):
        start = (value,) if start is None else start
        acc += n
        if acc >= rows_per_file or i == len(counts) - 1:
            ranges.append((start[0], value))
            start, acc = None, 0
    return ranges


def seal_partition(ref: TableRef, value: Any = None, *, run_id: str) -> TableCommit:
    """Rebuild one partition (``value``; ``None`` for an unpartitioned table) into sorted files of about
    ``target_file_rows`` rows: one grouped pass for the range cut and the before-checksum, one DuckDB
    ``COPY ... ORDER BY`` per first-sort-key range, then one overwrite commit with ``partition_filters``.
    """
    started = time.perf_counter()
    with table_lock(ref):
        dt = _delta(ref)
        layout = _require_layout(ref)
        part = layout.partition
        if (part is None) != (value is None):
            raise ValueError(f"{ref.key}: pass a partition value exactly when the table is partitioned")
        schema = _table_schema(dt)
        files = [f for f in _file_rows(_add_actions(dt), part) if part is None or str(f["_pv"]) == str(value)]
        commit = TableCommit(
            table=ref.key, operation="seal", run_id=run_id, slice=f"{part} = {value!r}" if part else "true"
        )
        if not files:
            commit.seconds = time.perf_counter() - started
            return commit
        duck = _Duck(ref, schema, layout)
        written: list[Path] = []
        try:
            con = duck.con
            union = " UNION ALL ".join(duck.file_select(str(ref.path / f["path"]), f["_pv"]) for f in files)
            con.execute(f"CREATE TEMP VIEW src AS {union}")
            first = layout.sort_key[0]
            cols = ", ".join(_q(c) for c in duck.columns)
            nonnull = ", ".join(f"count({_q(c)})" for c in duck.columns)
            grouped = con.execute(
                f"SELECT {_q(first)}, count(*), sum(hash({cols}))::HUGEINT, {nonnull} "
                f"FROM src GROUP BY 1 ORDER BY 1 NULLS FIRST"
            ).fetchall()
            before = {"rows": 0, "checksum": 0, **{f"nonnull.{c}": 0 for c in duck.columns}}
            for row in grouped:
                before["rows"] += row[1]
                before["checksum"] += int(row[2] or 0)
                for i, c in enumerate(duck.columns):
                    before[f"nonnull.{c}"] += row[3 + i]
            tag = f"sealed-v{dt.version() + 1}-{uuid.uuid4().hex[:12]}"
            now = int(time.time() * 1000)
            adds = []
            for i, (lo, hi) in enumerate(_cut_ranges([(r[0], r[1]) for r in grouped], layout.target_file_rows)):
                if lo is None:
                    upper = "" if hi is None else f" OR {_q(first)} <= {_sql_literal(_lit(hi))}"
                    where = f"({_q(first)} IS NULL{upper})"
                else:
                    where = f"{_q(first)} BETWEEN {_sql_literal(_lit(lo))} AND {_sql_literal(_lit(hi))}"
                out = _new_path(ref, part, value, tag, i)
                written.append(out)
                duck.copy_out(f"SELECT * FROM src WHERE {where}", out)
                adds.append(_add_action(ref, duck, out, value, now)[1])
            after = _sum_aggregates(
                *(duck.aggregate(f"({duck.file_select(str(ref.path / a.path), value)})") for a in adds)
            )
            _check_equal("sealed files vs source partition", before, after)
            metadata = {"qf.run_id": run_id, "qf.operation": "seal", "qf.slice": commit.slice or ""}
            filters = [(part, "=", _partition_string(value))] if part else None
            commit.version = _commit(
                dt, adds, layout=layout, metadata=metadata, mode="overwrite", partition_filters=filters
            )
        except BaseException:
            _unlink_all(written)  # nothing committed: _commit raises only when no log entry landed
            raise
        finally:
            duck.close()
        check_protocol(DeltaTable(str(ref.path)))
    commit.rows_written = before["rows"]
    commit.rows_deleted = before["rows"]
    commit.files_added = len(adds)
    commit.files_removed = len(files)
    commit.checks_passed = ["sealed_rows_checksum_nonnull", "protocol"]
    commit.seconds = time.perf_counter() - started
    return commit


@dataclass
class MaintenanceReport:
    table: str
    dry_run: bool
    seal: list[Any] = field(default_factory=list)
    sealed: list[TableCommit] = field(default_factory=list)
    vacuum_files: list[str] = field(default_factory=list)
    vacuum_refused: list[str] = field(default_factory=list)
    vacuumed: bool = False
    log_cleaned: bool = False


def _is_data_file(relative: str, partition: str | None) -> bool:
    parts = Path(relative).parts
    if not parts or not parts[-1].endswith(".parquet") or parts[0].startswith(("_", ".")):
        return False
    if len(parts) == 1:
        return True
    return len(parts) == 2 and partition is not None and parts[0].startswith(f"{partition}=")


def _needs_seal(files: list[dict[str, Any]], layout: TableLayout, cutoff_ms: int) -> bool:
    """More files than ``max(8, 1.5 x what a seal would produce)``, quiet for 3 days, not one seal's output."""
    if max(f["modification_time"] for f in files) >= cutoff_ms:
        return False
    rows = sum(f["num_records"] or 0 for f in files)
    if len(files) <= max(SEAL_MIN_FILES, math.ceil(1.5 * math.ceil(rows / layout.target_file_rows))):
        return False
    tags = {Path(f["path"]).name.rsplit("-", 1)[0] for f in files}
    return not (len(tags) == 1 and next(iter(tags)).startswith("part-sealed-"))


def maintain(
    ref: TableRef, *, dry_run: bool = True, run_id: str = "maintain", now: datetime | None = None
) -> MaintenanceReport:
    """Seal every partition that ``_needs_seal`` (too many files, quiet 3 days); vacuum (``full=True``, 7 days),
    refusing when the dry-run list holds anything but this table's data files; clean the log (30 days).
    """
    layout = _require_layout(ref)
    report = MaintenanceReport(table=ref.key, dry_run=dry_run)
    cutoff_ms = int(((now or datetime.now(UTC)) - SEAL_QUIET).timestamp() * 1000)
    with table_lock(ref) if not dry_run else nullcontext():
        dt = _delta(ref)
        groups: dict[Any, list[dict[str, Any]]] = {}
        for f in _file_rows(_add_actions(dt), layout.partition):
            groups.setdefault(f["_pv"], []).append(f)
        report.seal = sorted((pv for pv, fs in groups.items() if _needs_seal(fs, layout, cutoff_ms)), key=str)
        if not dry_run:
            report.sealed = [seal_partition(ref, pv, run_id=run_id) for pv in report.seal]
            dt = DeltaTable(str(ref.path))
        report.vacuum_files = dt.vacuum(retention_hours=VACUUM_RETENTION_HOURS, dry_run=True, full=True)
        report.vacuum_refused = [p for p in report.vacuum_files if not _is_data_file(p, layout.partition)]
        if not dry_run:
            if report.vacuum_refused:
                raise RuntimeError(f"{ref.key}: vacuum would delete non-data files {report.vacuum_refused[:10]}")
            dt.vacuum(retention_hours=VACUUM_RETENTION_HOURS, dry_run=False, full=True)
            report.vacuumed = True
            dt.cleanup_metadata()
            report.log_cleaned = True
    return report


__all__ = [
    "MaintenanceReport",
    "ProtocolError",
    "SchemaDriftError",
    "TableRef",
    "TableStats",
    "WriteCheckError",
    "add_columns",
    "check_protocol",
    "conform_rows",
    "create_table",
    "duckdb_source",
    "is_delta_dir",
    "iter_tables",
    "load_key_mapping",
    "maintain",
    "read_layout",
    "scan_table",
    "seal_partition",
    "table_commit_time",
    "table_ref",
    "table_stats",
    "table_version",
    "write_slice",
]
