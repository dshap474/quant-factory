"""Execution helpers for bounded single-file parquet queries over the quant-factory lake.

Single-file reads run as Polars lazy scans: on wide files they are several times faster than
DuckDB for small previews. Filters
reuse the bounds `_sql.duckdb_where` binds, so both engines select the same rows. Multi-file
collections and their aggregations stay on DuckDB in `collections.py`. A path that resolves to a
Delta table (its directory, or a legacy key mapped onto it) reads through `delta_tables.scan_table`.
A plain folder of same-schema parquet files, up to `MAX_DIRECTORY_BYTES`, reads as one dataset.

USAGE:
    from data.query import ParquetQuery, preview_parquet, query_parquet
    page = preview_parquet(scope="features", path="example/panel/data.parquet", page_size=100)
    rows = query_parquet(ParquetQuery(scope="data", path="raw/1d/x/data.parquet", start="2026-01-01"))
    every_asset = get_parquet_metadata(scope="data", path="raw/1d/example/bars")
"""

from __future__ import annotations

from functools import lru_cache
from io import BytesIO
from math import ceil
from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl
import pyarrow.parquet as pq

from data.config.paths import QUANT_DB_ROOT, resolve_db_root
from data.platform.storage import delta_read

from ._sql import NUMERIC_DTYPES, temporal_bound, validate_scope
from ._sql import (
    SUPPORTED_SCOPES as SUPPORTED_SCOPES,
)
from ._stats import empty_numeric_stats_frame, numeric_stats_exprs, stats_frame_from_row
from .errors import QueryError as QueryError
from .errors import QueryPathError, QueryValidationError
from .models import ColumnInfo, DatasetScope, ParquetMetadata, ParquetQuery, QueryResult

if TYPE_CHECKING:
    from data.platform.storage.delta_tables import TableRef


# One folder read as one dataset stays small enough for the API's bounded memory.
MAX_DIRECTORY_BYTES = 256 * 1024**2


def resolve_parquet_path(
    *,
    scope: DatasetScope,
    path: str,
    db_root: str | Path | None = None,
) -> Path:
    """Resolve a lake-relative parquet path and reject traversal.

    A key that resolves to a Delta table returns the table directory, or the requested key path
    when the table ref carries a row filter (so raw reads of it fail instead of reading every row).
    """
    target, ref = _resolve(scope=scope, path=path, db_root=db_root)
    return target


def _resolve(
    *,
    scope: DatasetScope,
    path: str,
    db_root: str | Path | None,
) -> tuple[Path, TableRef | None]:
    validate_scope(scope)

    root = resolve_db_root(db_root) if db_root is not None else QUANT_DB_ROOT
    scope_root = root / scope
    if not scope_root.exists():
        raise QueryPathError(f"Dataset scope root not found: {scope}")

    target = scope_root / path.strip("/")
    try:
        target.resolve().relative_to(scope_root.resolve())
    except ValueError as exc:
        raise QueryPathError("Access denied") from exc

    ref = delta_read.delta_ref(root, target)
    if ref is not None:
        # The table directory under the caller's (unresolved) root, or the requested key when filtered.
        return (target if ref.filters else root / ref.key), ref
    if not target.exists():
        raise QueryPathError(f"Dataset path not found: {path}")
    table = delta_read.enclosing_delta(target.resolve(), scope_root.resolve())
    if table is not None:  # only the log knows which files inside a table are live
        if not target.is_dir():
            raise QueryPathError(
                f"{path!r} is a file inside a Delta table; query the table or one of its partition directories"
            )
        try:
            return target, delta_read.partition_ref(table, target.resolve(), db_root=root)
        except ValueError as exc:
            raise QueryPathError(str(exc)) from exc
    if target.suffix != ".parquet" and not target.is_dir():
        raise QueryPathError("Only parquet files are supported")
    return target, None


def get_parquet_metadata(
    *,
    scope: DatasetScope,
    path: str,
    db_root: str | Path | None = None,
) -> ParquetMetadata:
    """Read schema and row metadata without loading the dataset."""
    target, ref = _resolve(scope=scope, path=path, db_root=db_root)
    if ref is not None:
        return _delta_metadata(scope, path, target, ref)
    if target.is_dir():
        schema, total_rows = _directory_footers(target, target.stat().st_mtime_ns)
    else:
        schema = pl.read_parquet_schema(target)
        total_rows = pq.ParquetFile(target).metadata.num_rows
    return ParquetMetadata(
        scope=scope,
        path=path.strip("/"),
        absolute_path=str(target),
        total_rows=total_rows,
        columns=tuple(ColumnInfo(name=name, dtype=str(dtype)) for name, dtype in schema.items()),
        typed_schema=dict(schema),
    )


@lru_cache(maxsize=64)
def _directory_footers(target: Path, mtime_ns: int) -> tuple[dict[str, pl.DataType], int]:
    """Shared schema and total rows of a folder's parquet files; replacing a file changes ``mtime_ns``."""
    del mtime_ns  # cache key only
    files = sorted(target.glob("*.parquet"))
    if not files:
        raise QueryPathError("Only parquet files are supported")
    if sum(file.stat().st_size for file in files) > MAX_DIRECTORY_BYTES:
        raise QueryPathError("Folder is too large to read as one dataset")
    schema = dict(pl.read_parquet_schema(files[0]))
    if any(dict(pl.read_parquet_schema(file)) != schema for file in files[1:]):
        raise QueryPathError("Folder files do not share one schema")
    return schema, sum(pq.ParquetFile(file).metadata.num_rows for file in files)


def _delta_metadata(scope: DatasetScope, path: str, target: Path, ref: TableRef) -> ParquetMetadata:
    from data.platform.storage import delta_tables as dtab

    lazy = dtab.scan_table(ref)
    schema = dict(lazy.collect_schema())
    total_rows = int(lazy.select(pl.len()).collect().item()) if ref.filters else dtab.table_stats(ref).rows
    return ParquetMetadata(
        scope=scope,
        path=path.strip("/"),
        absolute_path=str(target),
        total_rows=total_rows,
        columns=tuple(ColumnInfo(name=name, dtype=str(dtype)) for name, dtype in schema.items()),
        typed_schema=schema,
        table=ref,
    )


def preview_parquet(
    *,
    scope: DatasetScope,
    path: str,
    page: int = 1,
    page_size: int = 100,
    db_root: str | Path | None = None,
) -> QueryResult:
    """Return one 1-based page from a parquet dataset."""
    if page < 1:
        raise QueryValidationError("page must be >= 1")
    if page_size < 1:
        raise QueryValidationError("page_size must be >= 1")

    metadata = get_parquet_metadata(scope=scope, path=path, db_root=db_root)
    total_pages = max(1, ceil(metadata.total_rows / page_size)) if metadata.total_rows else 1
    page = min(page, total_pages)
    query = ParquetQuery(
        scope=scope,
        path=path,
        limit=page_size,
        offset=(page - 1) * page_size,
    )
    return query_parquet(query, db_root=db_root, metadata=metadata)


def query_parquet(
    query: ParquetQuery,
    *,
    db_root: str | Path | None = None,
    metadata: ParquetMetadata | None = None,
) -> QueryResult:
    """Run a bounded parquet query and return a Polars dataframe."""
    metadata = metadata or get_parquet_metadata(scope=query.scope, path=query.path, db_root=db_root)
    typed_schema = _typed_schema(metadata)
    _validate_query(query, typed_schema)
    lazy = _filtered_scan(metadata, query, typed_schema)
    if query.order_by is not None:
        # DuckDB's default: nulls last in both directions.
        lazy = lazy.sort(query.order_by, descending=query.descending, nulls_last=True, maintain_order=True)
    lazy = lazy.slice(query.offset, query.limit)
    if query.columns:
        lazy = lazy.select(query.columns)
    return QueryResult(metadata=metadata, frame=lazy.collect(), backend="polars")


def count_parquet_rows(
    query: ParquetQuery,
    *,
    db_root: str | Path | None = None,
    metadata: ParquetMetadata | None = None,
) -> int:
    """Count rows matching a query's time and entity filters, ignoring limit/offset."""
    metadata = metadata or get_parquet_metadata(scope=query.scope, path=query.path, db_root=db_root)
    typed_schema = _typed_schema(metadata)
    _validate_query(query, typed_schema)
    if not _filters(query, typed_schema):
        return metadata.total_rows
    lazy = _filtered_scan(metadata, query, typed_schema)
    return int(lazy.select(pl.len()).collect().item())


def numeric_stats(
    *,
    scope: DatasetScope,
    path: str,
    columns: tuple[str, ...] | None = None,
    db_root: str | Path | None = None,
) -> QueryResult:
    """Compute count/null/mean/std/min/max/median for numeric columns."""
    metadata = get_parquet_metadata(scope=scope, path=path, db_root=db_root)
    schema = _typed_schema(metadata)
    numeric_columns = [
        name for name, dtype in schema.items()
        if dtype in NUMERIC_DTYPES and (columns is None or name in columns)
    ]
    if columns is not None:
        missing = [column for column in columns if column not in schema]
        if missing:
            raise QueryValidationError(f"Unknown columns: {', '.join(missing)}")
    if not numeric_columns:
        return QueryResult(metadata=metadata, frame=empty_numeric_stats_frame())

    row = _scan(metadata).select(numeric_stats_exprs(numeric_columns, schema)).collect()
    return QueryResult(metadata=metadata, frame=stats_frame_from_row(row, numeric_columns), backend="polars")


def to_arrow_ipc_bytes(frame: pl.DataFrame) -> bytes:
    """Serialize a dataframe as Arrow IPC bytes."""
    buffer = BytesIO()
    frame.write_ipc(buffer)
    return buffer.getvalue()


def _validate_query(query: ParquetQuery, schema: dict[str, pl.DataType]) -> None:
    if query.limit is not None and query.limit < 0:
        raise QueryValidationError("limit must be >= 0")
    if query.offset < 0:
        raise QueryValidationError("offset must be >= 0")

    requested = set(query.columns or ())
    needed = set(requested)
    if query.start is not None or query.end is not None:
        needed.add(query.time_column)
    if query.entity_values:
        if query.entity_column is None:
            raise QueryValidationError("entity_column is required when entity_values are provided")
        needed.add(query.entity_column)
    if query.order_by is not None:
        needed.add(query.order_by)

    missing = sorted(column for column in needed if column not in schema)
    if missing:
        raise QueryValidationError(f"Unknown columns: {', '.join(missing)}")


def _typed_schema(metadata: ParquetMetadata) -> dict[str, pl.DataType]:
    """The schema read with the metadata; only hand-built metadata needs a second footer read."""
    return metadata.typed_schema or dict(pl.read_parquet_schema(metadata.absolute_path))


def _scan(metadata: ParquetMetadata) -> pl.LazyFrame:
    if metadata.table is not None:
        from data.platform.storage import delta_tables as dtab

        return dtab.scan_table(metadata.table)
    # Hive auto-detection would add a column per `key=value` directory that the file lacks.
    target = Path(metadata.absolute_path)
    return pl.scan_parquet(target / "*.parquet" if target.is_dir() else target, hive_partitioning=False)


def _filters(query: ParquetQuery, typed_schema: dict[str, pl.DataType]) -> list[pl.Expr]:
    """The time and entity filters, matching the WHERE clause `_sql.duckdb_where` builds."""
    filters: list[pl.Expr] = []
    for value, is_end in ((query.start, False), (query.end, True)):
        if value is None:
            continue
        bound = temporal_bound(value, query.time_column, typed_schema, is_end=is_end)
        dtype = typed_schema[query.time_column]
        literal = pl.lit(bound) if dtype == pl.String else pl.lit(bound, dtype=dtype)
        column = pl.col(query.time_column)
        filters.append(column <= literal if is_end else column >= literal)
    if query.entity_values:
        filters.append(pl.col(query.entity_column).cast(pl.String).is_in(list(query.entity_values)))
    return filters


def _filtered_scan(
    metadata: ParquetMetadata,
    query: ParquetQuery,
    typed_schema: dict[str, pl.DataType],
) -> pl.LazyFrame:
    lazy = _scan(metadata)
    filters = _filters(query, typed_schema)
    return lazy.filter(*filters) if filters else lazy
