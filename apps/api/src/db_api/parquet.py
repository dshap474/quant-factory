"""Read lake parquet files by absolute path through `data.query`.

Routers hold absolute paths under `settings.db_root`; this maps each to its lake scope and
relative path so every read gets `data.query`'s path checks, Polars engine and filters. The
quote, source and fingerprint helpers serve the profile modules that build their own DuckDB
aggregations: a Delta table is one source (``delta_scan``) whose fingerprint is its table version.

USAGE:
    frame = read_parquet_frame(path, columns=["timestamp", "close"], limit=100)
    rows = count_parquet_rows(path)
    schema = read_parquet_schema(path)
    source, delta = source_sql(path)        # "read_parquet('...')" or "delta_scan('...')"
    token = fingerprint(path)                # (mtime_ns, size) or (table version, bytes)
    lake_path_exists(path)                   # file, Delta table, or legacy key mapped onto one
    is_parquet_directory(path)               # plain folder of parquet files, read as one dataset
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl
from data.platform.storage import delta_read
from data.query import ParquetMetadata, ParquetQuery, get_parquet_metadata, query_parquet

from .config import settings

if TYPE_CHECKING:
    from data.platform.storage.delta_tables import TableRef

# --------------------------------------------------------------------------- #
# Reads
# --------------------------------------------------------------------------- #


def read_parquet_frame(
    path: Path,
    *,
    columns: list[str] | tuple[str, ...] | None = None,
    limit: int | None = None,
    offset: int = 0,
    order_by: str | None = None,
    descending: bool = False,
    equals: tuple[str, str] | None = None,
    db_root: Path | None = None,
) -> pl.DataFrame:
    """Read rows from one lake parquet file.

    ``equals=(column, value)`` keeps only rows whose column, cast to text, equals value;
    the filter runs inside the scan so unmatched rows are never materialized.
    """
    metadata = _metadata(path, db_root)
    query = ParquetQuery(
        scope=metadata.scope,
        path=metadata.path,
        columns=tuple(columns) if columns else None,
        entity_column=equals[0] if equals else None,
        entity_values=(equals[1],) if equals else (),
        limit=limit,
        offset=offset,
        order_by=order_by,
        descending=descending,
    )
    return query_parquet(query, metadata=metadata).frame


def count_parquet_rows(path: Path, *, db_root: Path | None = None) -> int:
    """Row count from the parquet footer."""
    return _metadata(path, db_root).total_rows


def read_parquet_schema(path: Path, *, db_root: Path | None = None) -> dict[str, pl.DataType]:
    """Polars schema from the parquet footer."""
    return dict(_metadata(path, db_root).typed_schema)


def _metadata(path: Path, db_root: Path | None) -> ParquetMetadata:
    # Callers build paths from their lake root (settings.db_root unless given), so compare
    # unresolved; data.query then resolves symlinks and rejects anything escaping the scope.
    root = Path(db_root if db_root is not None else settings.db_root).absolute()
    relative = Path(path).absolute().relative_to(root)
    scope, rest = relative.parts[0], Path(*relative.parts[1:]).as_posix()
    return get_parquet_metadata(scope=scope, path=rest, db_root=root)


# --------------------------------------------------------------------------- #
# Sources, fingerprints and SQL quoting for the profile modules' DuckDB aggregations
# --------------------------------------------------------------------------- #


def _delta(path: Path, db_root: Path | None) -> TableRef | None:
    if delta_read.is_delta_dir(path):
        return delta_read.path_ref(path)
    if Path(path).exists():
        return None
    return delta_read.delta_ref(Path(db_root if db_root is not None else settings.db_root), path)


def lake_path_exists(path: Path, *, db_root: Path | None = None) -> bool:
    """A parquet file, a Delta table, or a legacy key mapped onto a Delta table exists at ``path``."""
    return Path(path).is_file() or _delta(path, db_root) is not None


def is_parquet_directory(path: Path, *, db_root: Path | None = None) -> bool:
    """A plain folder of parquet files; a Delta table or a partition inside one is not."""
    root = Path(db_root if db_root is not None else settings.db_root).resolve()
    return (
        path.is_dir()
        and _delta(path, db_root) is None
        and delta_read.enclosing_delta(path.resolve(), root) is None
        and any(path.glob("*.parquet"))
    )


def source_sql(path: Path, *, db_root: Path | None = None) -> tuple[str, bool]:
    """DuckDB ``FROM`` source for a lake path and whether it needs the ``delta`` extension."""
    ref = _delta(path, db_root)
    if ref is None and path.is_dir():
        files = _quote_literal(str(path / "*.parquet"))
        return f"read_parquet({files}, union_by_name = true, hive_partitioning = false)", False
    return delta_read.duckdb_from(path, ref), ref is not None


def fingerprint(path: Path, *, db_root: Path | None = None) -> tuple[int, int]:
    """Cache token: ``(mtime_ns, size)`` for a file; ``(table version, live bytes)`` for a Delta table."""
    ref = _delta(path, db_root)
    return delta_read.fingerprint(ref.path if ref is not None else path)


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _quote_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"
