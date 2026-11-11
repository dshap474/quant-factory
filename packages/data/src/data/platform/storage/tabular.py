"""Shared prepared-table and parquet helpers for raw/derived families."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import date, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq

from data.platform.storage.parquet_runtime import refuse_delta_target, write_polars_parquet_atomic


@dataclass(frozen=True)
class PreparedTable:
    """Normalized parquet-ready table plus merge metadata."""

    name: str
    frame: pl.DataFrame
    key_columns: tuple[str, ...]
    sort_columns: tuple[str, ...] = ()

    def is_empty(self) -> bool:
        return self.frame.is_empty()


def as_date(value: str | date | datetime) -> date:
    """Normalize an ISO-like value to a calendar date."""

    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def read_frame(path: Path) -> pl.DataFrame | None:
    if not path.exists():
        return None
    return pl.read_parquet(path)


def write_frame(frame: pl.DataFrame, path: Path) -> Path:
    return write_polars_parquet_atomic(frame, path)


def merge_frame(existing: pl.DataFrame | None, table: PreparedTable) -> pl.DataFrame:
    if existing is None:
        merged = table.frame
    else:
        merged = pl.concat([existing, table.frame], how="diagonal_relaxed")

    subset = [column for column in table.key_columns if column in merged.columns]
    if subset:
        merged = merged.unique(subset=subset, keep="last", maintain_order=True)

    sort_columns = [column for column in table.sort_columns if column in merged.columns]
    if sort_columns:
        merged = merged.sort(sort_columns)
    return merged


def merge_into_parquet(path: Path, table: PreparedTable) -> int:
    """Merge ``table`` into the stored parquet at ``path`` without loading the stored rows; return the row count.

    Matches ``merge_frame(read_frame(path), table)`` when the stored file is sorted by ``table.sort_columns``
    (every merge-written file is): stored rows whose key the update replaces are filtered out while streaming,
    and the deduplicated update is merge-sorted back in. An update that would widen or retype the stored
    schema falls back to the in-memory merge.
    """
    refuse_delta_target(path)
    schema = pl.scan_parquet(path).collect_schema()
    columns = [*table.key_columns, *table.sort_columns]
    if not set(columns) <= set(table.frame.columns) or any(
        column not in schema or dtype not in (schema[column], pl.Null) for column, dtype in table.frame.schema.items()
    ):
        frame = merge_frame(read_frame(path), table)
        write_frame(frame, path)
        return frame.height

    update = table.frame.select(
        pl.col(column).cast(dtype) if column in table.frame.columns else pl.lit(None, dtype).alias(column)
        for column, dtype in schema.items()
    )
    stored = pl.scan_parquet(path)
    if table.key_columns:
        keys = list(table.key_columns)
        update = update.unique(subset=keys, keep="last", maintain_order=True)
        stored = stored.filter(~pl.struct(keys).is_in(update.select(pl.struct(keys)).to_series().implode()))
    if table.sort_columns:
        order = pl.struct(list(table.sort_columns)).alias("__merge_order")
        update = update.sort(table.sort_columns).with_columns(order)
        merged = stored.with_columns(order).merge_sorted(update.lazy(), key="__merge_order").drop("__merge_order")
    else:
        merged = pl.concat([stored, update.lazy()])
    tmp_path = path.with_name(f"{path.name}.tmp-{uuid4().hex}")
    merged.sink_parquet(tmp_path, compression="zstd", compression_level=3)
    tmp_path.replace(path)
    return pq.ParquetFile(path).metadata.num_rows


def _rows_differing_from_stored(path: Path, table: PreparedTable, stamp_columns: tuple[str, ...]) -> PreparedTable:
    """Drop update rows already stored with the same values, comparing everything but ``stamp_columns``.

    Those rows keep their stored stamps. The stored file is only streamed. An update whose columns or
    types differ from the stored file comes back whole, so the merge handles it as before.
    """
    schema = pl.scan_parquet(path).collect_schema()
    frame = table.frame
    if set(frame.columns) != set(schema) or any(dtype not in (schema[name], pl.Null) for name, dtype in frame.schema.items()):
        return table
    if table.key_columns:
        frame = frame.unique(subset=list(table.key_columns), keep="last", maintain_order=True)
    frame = frame.select(pl.col(name).cast(dtype) for name, dtype in schema.items())
    compared = [name for name in schema if name not in stamp_columns]
    stored_matches = (
        pl.scan_parquet(path)
        .select(compared)
        .join(frame.lazy().select(compared), on=compared, how="semi", nulls_equal=True)
        .collect(engine="streaming")
    )
    return replace(table, frame=frame.join(stored_matches, on=compared, how="anti", nulls_equal=True, maintain_order="left"))


def write_tables(
    tables: list[PreparedTable],
    *,
    path_resolver,
    overwrite: bool,
    stamp_columns: tuple[str, ...] = (),
) -> tuple[list[Path], dict[str, int]]:
    """Write ``tables``; with ``stamp_columns``, a merge that would only refresh those columns writes nothing.

    A table left unchanged while another changes is still returned, so metadata lists every artifact.
    Returns nothing written when no table changed, so callers can report a noop.
    """
    written: list[Path] = []
    row_counts: dict[str, int] = {}
    changed = False
    for table in tables:
        if table.is_empty():
            continue
        path = path_resolver(table.name)
        written.append(path)
        if overwrite or not path.exists():
            frame = table.frame if overwrite else merge_frame(None, table)
            write_frame(frame, path)
            row_counts[table.name] = frame.height
            changed = True
            continue
        update = _rows_differing_from_stored(path, table, stamp_columns) if stamp_columns else table
        if update.is_empty():
            row_counts[table.name] = pq.ParquetFile(path).metadata.num_rows
            continue
        row_counts[table.name] = merge_into_parquet(path, update)
        changed = True
    return (written, row_counts) if changed else ([], {})


def write_changed_tables(
    tables: list[PreparedTable],
    *,
    path_resolver,
    overwrite: bool,
) -> tuple[list[Path], dict[str, int]]:
    """Like ``write_tables``, but skip a table whose result equals what is stored (schema and values).

    An unchanged rerun therefore writes nothing, so callers can report it as a noop.
    """
    written: list[Path] = []
    row_counts: dict[str, int] = {}
    for table in tables:
        if table.is_empty():
            continue
        path = path_resolver(table.name)
        refuse_delta_target(path)
        existing = read_frame(path)
        frame = merge_frame(None if overwrite else existing, table)
        if existing is not None and existing.schema == frame.schema and existing.equals(frame):
            continue
        write_frame(frame, path)
        written.append(path)
        row_counts[table.name] = frame.height
    return written, row_counts


def raw_row_counts(paths: list[Path]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in paths:
        if path.suffix == ".parquet":
            counts[path.stem] = pl.read_parquet(path).height
    return counts


class DynamicStringParquetWriter:
    """Streaming parquet writer with string schema inferred from the first row."""

    def __init__(self, path: Path, *, batch_size: int = 25000) -> None:
        refuse_delta_target(path)
        self.path = path
        self.batch_size = batch_size
        self.columns: tuple[str, ...] | None = None
        self._schema: pa.Schema | None = None
        self._rows: list[dict[str, str | None]] = []
        self._row_count = 0
        self._tmp_path = path.with_name(f"{path.name}.tmp")
        self._writer: pq.ParquetWriter | None = None

    def write_rows(self, rows: list[dict[str, Any]]) -> None:
        for row in rows:
            if self.columns is None:
                self.columns = tuple(row.keys())
                self._schema = pa.schema([(column, pa.string()) for column in self.columns])
            assert self.columns is not None
            self._rows.append({column: _stringify(row.get(column)) for column in self.columns})
            self._row_count += 1
            if len(self._rows) >= self.batch_size:
                self._flush()

    def close(self) -> int:
        self._flush()
        if self._writer is not None:
            self._writer.close()
            refuse_delta_target(self.path)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._tmp_path.replace(self.path)
        return self._row_count

    def _flush(self) -> None:
        if not self._rows:
            return
        assert self._schema is not None
        table = pa.Table.from_pylist(self._rows, schema=self._schema)
        if self._writer is None:
            self._tmp_path.parent.mkdir(parents=True, exist_ok=True)
            self._writer = pq.ParquetWriter(self._tmp_path, self._schema, compression="zstd")
        self._writer.write_table(table)
        self._rows = []


class FrameChunkParquetWriter:
    """Write one parquet file from DataFrame chunks in order; the file appears atomically on ``close``.

    The first chunk fixes the schema. Use it when the whole frame would not fit in memory
    but its chunks arrive in final sort order (a date-chunked build).
    """

    def __init__(self, path: Path) -> None:
        refuse_delta_target(path)
        self.path = path
        self._tmp_path = path.with_name(f"{path.name}.tmp-{uuid4().hex}")
        self._writer: pq.ParquetWriter | None = None
        self._schema: pa.Schema | None = None
        self._row_count = 0

    def write(self, frame: pl.DataFrame) -> None:
        if frame.is_empty():
            return
        table = frame.to_arrow(compat_level=pl.CompatLevel.oldest())
        if self._writer is None:
            self._schema = table.schema
            self._tmp_path.parent.mkdir(parents=True, exist_ok=True)
            self._writer = pq.ParquetWriter(self._tmp_path, self._schema, compression="zstd", compression_level=3)
        self._writer.write_table(table.cast(self._schema))
        self._row_count += frame.height

    def close(self) -> int:
        """Publish the file and return its row count (0 and no file when nothing was written)."""
        if self._writer is not None:
            self._writer.close()
            refuse_delta_target(self.path)
            self._tmp_path.replace(self.path)
        return self._row_count

    def abort(self) -> None:
        if self._writer is not None:
            self._writer.close()
        self._tmp_path.unlink(missing_ok=True)


def _stringify(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True)
    return str(value)


__all__ = [
    "DynamicStringParquetWriter",
    "FrameChunkParquetWriter",
    "PreparedTable",
    "as_date",
    "merge_frame",
    "raw_row_counts",
    "read_frame",
    "write_changed_tables",
    "write_frame",
    "write_tables",
]
