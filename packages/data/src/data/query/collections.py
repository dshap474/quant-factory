"""Safe multi-file DuckDB queries over parquet collections in the lake.

A Delta table inside a collection (its directory, a path inside it, or a legacy key mapped onto it)
is one member read through ``delta_scan``; its data files and ``_delta_log`` are never listed.

USAGE: query_parquet_collection(ParquetCollectionQuery(scope="research", paths=("a.parquet",)))
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

import polars as pl
import pyarrow.parquet as pq

from data.config.paths import QUANT_DB_ROOT, resolve_db_root
from data.platform.storage import delta_read

from ._sql import (
    NUMERIC_DTYPES,
    duckdb_where,
    limit_offset_sql,
    quote_ident,
    quote_literal,
    validate_scope,
)
from ._stats import empty_numeric_stats_frame, numeric_stats_sql, stats_frame_from_row
from .errors import QueryPathError, QueryValidationError
from .models import (
    AggregationSpec,
    ColumnInfo,
    DatasetScope,
    ParquetCollectionMetadata,
    ParquetCollectionQuery,
    ParquetFileInfo,
    QueryEngineSettings,
    QueryResult,
)
from .session import DuckDBQuerySession

if TYPE_CHECKING:
    from data.platform.storage.delta_tables import TableRef

# --------------------------------------------------------------------------- #
# Public collection resolution and query operations
# --------------------------------------------------------------------------- #


def resolve_parquet_collection(
    *,
    scope: DatasetScope,
    path_glob: str = "",
    paths: tuple[str, ...] | None = None,
    db_root: str | Path | None = None,
    max_files: int = 10_000,
) -> tuple[Path, ...]:
    """Resolve a glob/directory or a bounded explicit file set under one lake scope.

    A Delta member resolves to its table directory, or to the requested key when the mapping
    adds a row filter.
    """
    return tuple(
        _resolve_members(scope=scope, path_glob=path_glob, paths=paths, db_root=db_root, max_files=max_files)
    )


def _resolve_members(
    *,
    scope: DatasetScope,
    path_glob: str,
    paths: tuple[str, ...] | None,
    db_root: str | Path | None,
    max_files: int,
) -> dict[Path, TableRef | None]:
    """Ordered collection members: each parquet file maps to None, each Delta member to its ref."""
    validate_scope(scope)
    if max_files < 1:
        raise QueryValidationError("max_files must be >= 1")

    if paths is not None:
        if path_glob or not paths or len(paths) > max_files:
            raise QueryPathError("Provide a nonempty bounded file list without path_glob")
        root = resolve_db_root(db_root) if db_root is not None else QUANT_DB_ROOT
        scope_root = (root / scope).resolve()
        resolved: list[tuple[Path, TableRef | None]] = []
        for name in paths:
            if (not name or Path(name).is_absolute() or "://" in name
                    or ".." in Path(name).parts or any(char in name for char in "*?[]")):
                raise QueryPathError("Explicit files must be exact lake-relative parquet paths")
            ref = delta_read.delta_ref(root, scope_root / name)
            if ref is not None:
                resolved.append((_delta_member(scope_root / name, ref, scope_root), ref))
                continue
            _refuse_inside_table(scope_root / name, scope_root, name)
            target = _validate_collection_file(scope_root / name, scope_root)
            if not target.is_file():
                raise QueryPathError(f"Parquet file not found: {name}")
            resolved.append((target, None))
        members = dict(resolved)
        if len(members) != len(resolved):
            raise QueryPathError("Duplicate explicit parquet files")
        return members

    requested = path_glob.strip()
    if not requested:
        raise QueryPathError("Collection path is required")
    if Path(requested).is_absolute() or "://" in requested:
        raise QueryPathError("Collection paths must be lake-relative")
    if ".." in Path(requested).parts:
        raise QueryPathError("Access denied")

    root = resolve_db_root(db_root) if db_root is not None else QUANT_DB_ROOT
    scope_root = (root / scope).resolve()
    if not scope_root.exists():
        raise QueryPathError(f"Dataset scope root not found: {scope}")

    candidate = scope_root / requested.strip("/")
    ref = delta_read.delta_ref(root, candidate)
    if ref is not None:
        return {_delta_member(candidate, ref, scope_root): ref}
    table = delta_read.enclosing_delta(candidate, scope_root) if candidate.exists() else None
    if table is not None:  # a partition directory reads through the table with a partition filter
        try:
            ref = delta_read.partition_ref(table, candidate, db_root=root)
        except ValueError as exc:
            raise QueryPathError(f"{exc}; query the table or one partition directory") from exc
        return {_delta_member(candidate, ref, scope_root): ref}
    mapped: list[tuple[Path, TableRef]] = []
    if candidate.exists() and candidate.is_dir():
        files, tables = delta_read.walk_lake(candidate)
        matches = sorted([*files, *tables])
    elif candidate.exists():
        matches = [candidate]
    else:
        matches = _glob_members(scope_root, requested.strip("/"), path_glob)
        # Cut-over legacy keys (e.g. per-coin files) keep matching through the key mapping.
        # A key whose table the glob already reads whole (or whose legacy file it matched) is not added twice.
        whole = {path.resolve() for path in matches}
        mapped = [
            (key, mref)
            for key, mref in delta_read.mapped_refs(root, f"{scope}/{requested.strip('/')}")
            if _inside_scope(key, scope_root) and mref.path.resolve() not in whole and key.resolve() not in whole
        ]

    if not matches and not mapped:
        raise QueryPathError(f"No parquet files matched collection path: {path_glob}")
    if len(matches) > max_files:
        raise QueryPathError(f"Collection matched {len(matches)} files; max_files is {max_files}")

    members: dict[Path, TableRef | None] = {}
    for key, mref in mapped:
        members[_delta_member(scope_root / key.relative_to(Path(root) / scope), mref, scope_root)] = mref
    for path in matches:
        if delta_read.is_delta_dir(path):
            table = delta_read.delta_ref(root, path) or delta_read.path_ref(path)
            members[_delta_member(path, table, scope_root)] = table
        else:
            members[_validate_collection_file(path, scope_root)] = None
    return members


def get_parquet_collection_metadata(
    *,
    scope: DatasetScope,
    path_glob: str = "",
    paths: tuple[str, ...] | None = None,
    db_root: str | Path | None = None,
    max_files: int = 10_000,
) -> ParquetCollectionMetadata:
    """Read metadata for a validated parquet collection without loading rows."""
    members = _resolve_members(
        scope=scope,
        path_glob=path_glob,
        paths=paths,
        db_root=db_root,
        max_files=max_files,
    )
    root = resolve_db_root(db_root) if db_root is not None else QUANT_DB_ROOT
    scope_root = (root / scope).resolve()

    file_infos: list[ParquetFileInfo] = []
    schemas: list[dict[str, pl.DataType]] = []
    total_rows = 0
    total_size_bytes = 0
    total_row_groups = 0
    for path, ref in members.items():
        if ref is not None:
            info, schema = _delta_file_info(path, ref, scope_root)
            file_infos.append(info)
            schemas.append(schema)
            total_rows += info.row_count
            total_size_bytes += info.file_size_bytes
            total_row_groups += info.row_group_count
            continue
        parquet_metadata = pq.ParquetFile(path).metadata
        row_count = parquet_metadata.num_rows
        row_group_count = parquet_metadata.num_row_groups
        file_size_bytes = path.stat().st_size
        relative_path = path.relative_to(scope_root).as_posix()

        file_infos.append(
            ParquetFileInfo(
                path=relative_path,
                absolute_path=str(path),
                row_count=row_count,
                row_group_count=row_group_count,
                file_size_bytes=file_size_bytes,
            )
        )
        schemas.append(dict(pl.read_parquet_schema(path)))
        total_rows += row_count
        total_size_bytes += file_size_bytes
        total_row_groups += row_group_count

    columns, common_columns, schema_mismatches = _summarize_schemas(file_infos, schemas)
    return ParquetCollectionMetadata(
        scope=scope,
        path_glob=path_glob.strip("/"),
        files=tuple(file_infos),
        total_rows=total_rows,
        total_size_bytes=total_size_bytes,
        total_row_groups=total_row_groups,
        columns=columns,
        common_columns=common_columns,
        schema_mismatches=schema_mismatches,
        paths=paths,
        typed_schema=_merged_typed_schema(schemas),
    )


def query_parquet_collection(
    query: ParquetCollectionQuery,
    *,
    db_root: str | Path | None = None,
    metadata: ParquetCollectionMetadata | None = None,
    session: DuckDBQuerySession | None = None,
    settings: QueryEngineSettings | None = None,
) -> QueryResult:
    """Run a bounded parquet collection query and return a Polars dataframe."""
    metadata, files = _resolve_metadata_and_files(query=query, metadata=metadata, db_root=db_root)
    typed_schema = _typed_schema(metadata, files)
    _validate_collection_query(query, metadata, typed_schema)

    sql, params = _build_collection_sql(query, files, typed_schema, tables=_tables(metadata))
    frame = _execute_frame(sql, params, session=session, settings=settings)
    return QueryResult(metadata=metadata, frame=frame)


def aggregate_parquet_collection(
    query: ParquetCollectionQuery,
    *,
    db_root: str | Path | None = None,
    metadata: ParquetCollectionMetadata | None = None,
    session: DuckDBQuerySession | None = None,
    settings: QueryEngineSettings | None = None,
) -> QueryResult:
    """Run allowlisted grouped aggregations over a parquet collection."""
    if not query.aggregations:
        raise QueryValidationError("aggregations are required")
    return query_parquet_collection(
        query,
        db_root=db_root,
        metadata=metadata,
        session=session,
        settings=settings,
    )


def numeric_stats_collection(
    *,
    scope: DatasetScope,
    path_glob: str,
    columns: tuple[str, ...] | None = None,
    union_by_name: bool = False,
    db_root: str | Path | None = None,
    session: DuckDBQuerySession | None = None,
    settings: QueryEngineSettings | None = None,
) -> QueryResult:
    """Compute numeric column statistics across a parquet collection."""
    metadata = get_parquet_collection_metadata(scope=scope, path_glob=path_glob, db_root=db_root)
    if metadata.requires_union_by_name and not union_by_name:
        raise QueryValidationError("Collection schemas differ; use union_by_name=True")

    files = tuple(Path(file.absolute_path) for file in metadata.files)
    typed_schema = _typed_schema(metadata, files)
    missing = [column for column in columns or () if column not in typed_schema]
    if missing:
        raise QueryValidationError(f"Unknown columns: {', '.join(missing)}")

    numeric_columns = [
        name
        for name, dtype in typed_schema.items()
        if dtype in NUMERIC_DTYPES and (columns is None or name in columns)
    ]
    if not numeric_columns:
        return QueryResult(metadata=metadata, frame=empty_numeric_stats_frame())

    table_sql = _read_parquet_sql(files, union_by_name=union_by_name, include_filename=False, tables=_tables(metadata))
    row = _execute_frame(
        numeric_stats_sql(table_sql=table_sql, columns=numeric_columns),
        [],
        session=session,
        settings=settings,
    )
    return QueryResult(metadata=metadata, frame=stats_frame_from_row(row, numeric_columns))


def explain_parquet_collection(
    query: ParquetCollectionQuery,
    *,
    analyze: bool = False,
    db_root: str | Path | None = None,
    metadata: ParquetCollectionMetadata | None = None,
    session: DuckDBQuerySession | None = None,
    settings: QueryEngineSettings | None = None,
) -> str:
    """Return DuckDB EXPLAIN text for a generated collection query."""
    metadata, files = _resolve_metadata_and_files(query=query, metadata=metadata, db_root=db_root)
    typed_schema = _typed_schema(metadata, files)
    _validate_collection_query(query, metadata, typed_schema)

    sql, params = _build_collection_sql(query, files, typed_schema, tables=_tables(metadata))
    prefix = "EXPLAIN ANALYZE" if analyze else "EXPLAIN"
    frame = _execute_frame(f"{prefix} {sql}", params, session=session, settings=settings)
    return "\n".join(" | ".join(str(value) for value in row) for row in frame.rows())


# --------------------------------------------------------------------------- #
# Validation and generated read-only SQL
# --------------------------------------------------------------------------- #


def _glob_members(scope_root: Path, pattern: str, requested: str) -> list[Path]:
    """Glob matches as parquet files and whole Delta tables.

    A match inside a Delta table stands for the whole table only when a recursive ``**`` segment reaches
    the table's directory level (the glob covers every file of the table); any narrower glob into a table
    is refused, since its files are not the table's rows (tombstones, partition columns in dir names).
    """
    parts = Path(pattern).parts
    out: list[Path] = []
    seen: set[Path] = set()
    tables: dict[Path, Path | None] = {}
    for path in sorted(scope_root.glob(pattern)):
        if delta_read.is_delta_dir(path):
            table: Path | None = path
        else:
            if path.parent not in tables:
                tables[path.parent] = delta_read.enclosing_delta(path.parent, scope_root)
            table = tables[path.parent]
        if table is None:
            if path.is_file():
                out.append(path)
            continue
        if table != path and "**" not in parts[: len(table.relative_to(scope_root).parts) + 1]:
            _refuse_inside_table(path, scope_root, requested)
        if table not in seen:
            seen.add(table)
            out.append(table)
    return out


def _inside_scope(path: Path, scope_root: Path) -> bool:
    try:
        path.resolve().relative_to(scope_root)
    except ValueError:
        return False
    return True


def _refuse_inside_table(path: Path, scope_root: Path, requested: str) -> None:
    """A file or directory inside a Delta table is never read on its own: only the log knows which
    data files are live, and partition values live in directory names."""
    table = delta_read.enclosing_delta(path, scope_root)
    if table is not None and table != path:
        raise QueryPathError(
            f"{requested!r} reaches inside Delta table {table.relative_to(scope_root).as_posix()}; "
            "query the table or one of its partition directories"
        )


def _delta_member(path: Path, ref: TableRef, scope_root: Path) -> Path:
    """The member path of a Delta ref: the table directory, or the requested key for a filtered ref."""
    member = ref.path if not ref.filters else path
    try:
        member.resolve().relative_to(scope_root)
    except ValueError as exc:
        raise QueryPathError("Access denied") from exc
    return ref.path.resolve() if not ref.filters else path


def _delta_file_info(path: Path, ref: TableRef, scope_root: Path) -> tuple[ParquetFileInfo, dict[str, pl.DataType]]:
    from data.platform.storage import delta_tables as dtab

    lazy = dtab.scan_table(ref)
    stats = dtab.table_stats(ref)
    rows = int(lazy.select(pl.len()).collect().item()) if ref.filters else stats.rows
    info = ParquetFileInfo(
        path=path.relative_to(scope_root).as_posix(),
        absolute_path=str(path),
        row_count=rows,
        row_group_count=stats.files,
        file_size_bytes=stats.bytes,
        table=ref,
    )
    return info, dict(lazy.collect_schema())


def _tables(metadata: ParquetCollectionMetadata) -> dict[Path, TableRef]:
    return {Path(file.absolute_path): file.table for file in metadata.files if file.table is not None}


def _validate_collection_file(path: Path, scope_root: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(scope_root)
    except ValueError as exc:
        raise QueryPathError("Access denied") from exc
    if resolved.suffix != ".parquet":
        raise QueryPathError("Only parquet files are supported")
    return resolved


def _resolve_metadata_and_files(
    *,
    query: ParquetCollectionQuery,
    metadata: ParquetCollectionMetadata | None,
    db_root: str | Path | None,
) -> tuple[ParquetCollectionMetadata, tuple[Path, ...]]:
    if metadata is None:
        metadata = get_parquet_collection_metadata(
            scope=query.scope,
            path_glob=query.path_glob,
            paths=query.paths,
            db_root=db_root,
        )
        return metadata, tuple(Path(file.absolute_path) for file in metadata.files)

    if metadata.scope != query.scope:
        raise QueryValidationError("Collection metadata scope does not match query")
    if metadata.paths != query.paths:
        raise QueryValidationError("Collection metadata paths do not match query")
    if _normalize_collection_path(metadata.path_glob) != _normalize_collection_path(query.path_glob):
        raise QueryValidationError("Collection metadata path_glob does not match query")

    root = resolve_db_root(db_root) if db_root is not None else QUANT_DB_ROOT
    scope_root = (root / query.scope).resolve()
    expected_files = resolve_parquet_collection(
        scope=query.scope,
        path_glob=query.path_glob,
        paths=query.paths,
        db_root=db_root,
    )
    try:
        metadata_files = tuple(
            Path(file.absolute_path) if file.table is not None
            else _validate_collection_file(Path(file.absolute_path), scope_root)
            for file in metadata.files
        )
    except QueryPathError as exc:
        raise QueryValidationError("Collection metadata files do not match query path") from exc
    if metadata_files != expected_files:
        raise QueryValidationError("Collection metadata files do not match query path")
    return metadata, metadata_files


def _normalize_collection_path(path: str) -> str:
    return path.strip().strip("/")


def _summarize_schemas(
    file_infos: Sequence[ParquetFileInfo],
    schemas: Sequence[dict[str, pl.DataType]],
) -> tuple[tuple[ColumnInfo, ...], tuple[ColumnInfo, ...], tuple[str, ...]]:
    ordered_names: list[str] = []
    for schema in schemas:
        for name in schema:
            if name not in ordered_names:
                ordered_names.append(name)

    columns = tuple(ColumnInfo(name=name, dtype=_dtype_summary(name, schemas)) for name in ordered_names)
    common_columns = tuple(
        ColumnInfo(name=name, dtype=_dtype_summary(name, schemas))
        for name in ordered_names
        if all(name in schema for schema in schemas) and len({str(schema[name]) for schema in schemas}) == 1
    )

    mismatches: list[str] = []
    first_schema = tuple((name, str(dtype)) for name, dtype in schemas[0].items())
    for file_info, schema in zip(file_infos[1:], schemas[1:], strict=True):
        signature = tuple((name, str(dtype)) for name, dtype in schema.items())
        if signature != first_schema:
            mismatches.append(f"{file_info.path}: schema differs from first file")
    for name in ordered_names:
        dtypes = {str(schema[name]) for schema in schemas if name in schema}
        present_count = sum(1 for schema in schemas if name in schema)
        if len(dtypes) > 1:
            mismatches.append(f"{name}: dtype mismatch across files")
        elif present_count != len(schemas):
            mismatches.append(f"{name}: missing from {len(schemas) - present_count} file(s)")
    return columns, common_columns, tuple(dict.fromkeys(mismatches))


def _dtype_summary(name: str, schemas: Sequence[dict[str, pl.DataType]]) -> str:
    dtypes = sorted({str(schema[name]) for schema in schemas if name in schema})
    if not dtypes:
        return "missing"
    if len(dtypes) == 1:
        return dtypes[0]
    return "mixed[" + ", ".join(dtypes) + "]"


def _merged_typed_schema(schemas: Sequence[dict[str, pl.DataType]]) -> dict[str, pl.DataType]:
    typed_schema: dict[str, pl.DataType] = {}
    for schema in schemas:
        for name, dtype in schema.items():
            typed_schema.setdefault(name, dtype)
    return typed_schema


def _typed_schema(metadata: ParquetCollectionMetadata, files: Sequence[Path]) -> dict[str, pl.DataType]:
    """The schema read with the metadata; only hand-built metadata needs a second footer pass."""
    return metadata.typed_schema or _merged_typed_schema([pl.read_parquet_schema(path) for path in files])


def _validate_collection_query(
    query: ParquetCollectionQuery,
    metadata: ParquetCollectionMetadata,
    typed_schema: dict[str, pl.DataType],
) -> None:
    if query.limit is not None and query.limit < 0:
        raise QueryValidationError("limit must be >= 0")
    if query.offset < 0:
        raise QueryValidationError("offset must be >= 0")
    if query.integer_min is not None or query.integer_max is not None:
        if query.integer_column not in typed_schema or not typed_schema[query.integer_column].is_integer():
            raise QueryValidationError("Integer bounds require an integer column")
        for bound in (query.integer_min, query.integer_max):
            if bound is not None and (type(bound) is not int or not -(2**63) <= bound < 2**63):
                raise QueryValidationError("Integer bounds must be signed INT64 values")
        if (query.integer_min is not None and query.integer_max is not None
                and query.integer_min > query.integer_max):
            raise QueryValidationError("integer_min exceeds integer_max")
    if query.group_by and not query.aggregations:
        raise QueryValidationError("group_by requires aggregations")
    if metadata.requires_union_by_name and not query.union_by_name:
        raise QueryValidationError("Collection schemas differ; use union_by_name=True")
    if query.include_filename and "_source_file" in typed_schema:
        raise QueryValidationError("include_filename conflicts with existing _source_file column")

    output_aliases = {"_time_bucket"} if query.time_bucket is not None else set()
    output_aliases.update(_aggregation_alias(aggregation) for aggregation in query.aggregations)
    requested = set(query.columns or ())
    needed = set(requested)
    needed.update(query.group_by)
    needed.update(aggregation.column for aggregation in query.aggregations if aggregation.column is not None)
    if query.start is not None or query.end is not None or query.time_bucket is not None:
        needed.add(query.time_column)
    if query.entity_values:
        if query.entity_column is None:
            raise QueryValidationError("entity_column is required when entity_values are provided")
        needed.add(query.entity_column)
    if query.order_by is not None and query.order_by not in output_aliases:
        needed.add(query.order_by)

    missing = sorted(column for column in needed if column not in typed_schema)
    if missing:
        raise QueryValidationError(f"Unknown columns: {', '.join(missing)}")


def _build_collection_sql(
    query: ParquetCollectionQuery,
    files: Sequence[Path],
    typed_schema: dict[str, pl.DataType],
    *,
    tables: Mapping[Path, TableRef] | None = None,
) -> tuple[str, list[object]]:
    table_sql = _read_parquet_sql(
        files,
        union_by_name=query.union_by_name,
        include_filename=query.include_filename,
        hive_partitioning=query.hive_partitioning,
        tables=tables,
    )
    where_sql, params = duckdb_where(query, typed_schema)
    for operator, value in ((">=", query.integer_min), ("<=", query.integer_max)):
        if value is not None:
            where_sql += (" AND " if where_sql else " WHERE ")
            where_sql += f"{quote_ident(query.integer_column)} {operator} ?"
            params.append(value)
    if query.aggregations:
        select_sql, group_sql = _aggregation_select_and_group_sql(query)
    else:
        select_sql = _projection_select_sql(query)
        group_sql = ""

    order_sql = ""
    if query.order_by is not None:
        direction = "DESC" if query.descending else "ASC"
        order_sql = f" ORDER BY {quote_ident(query.order_by)} {direction}"

    sql = (
        f"SELECT {select_sql} "
        f"FROM {table_sql}"
        f"{where_sql}{group_sql}{order_sql}"
        f"{limit_offset_sql(limit=query.limit, offset=query.offset)}"
    )
    return sql, params


def _read_parquet_sql(
    files: Sequence[Path],
    *,
    union_by_name: bool,
    include_filename: bool,
    hive_partitioning: bool = False,
    tables: Mapping[Path, TableRef] | None = None,
) -> str:
    tables = tables or {}
    parquet_files = [path for path in files if path not in tables]
    file_list = ", ".join(quote_literal(str(path)) for path in parquet_files)
    # Off unless asked: auto-detection would add a column per `key=value` directory (e.g.
    # `quarter`) that the file schema, and so validation, never sees.
    options = [
        f"hive_partitioning = {'true' if hive_partitioning else 'false'}",
        f"union_by_name = {'true' if union_by_name else 'false'}",
        f"filename = {quote_literal('_source_file') if include_filename else 'false'}",
    ]
    parquet_sql = f"read_parquet([{file_list}], {', '.join(options)})"
    if not tables:
        return parquet_sql
    from data.platform.storage import delta_tables as dtab

    selects = [
        f"SELECT *{f', {quote_literal(str(path))} AS _source_file' if include_filename else ''} "
        f"FROM {dtab.duckdb_source(ref)}"
        for path, ref in tables.items()
    ]
    if parquet_files:
        selects.insert(0, f"SELECT * FROM {parquet_sql}")
    return "(" + " UNION ALL BY NAME ".join(selects) + ")"


def _projection_select_sql(query: ParquetCollectionQuery) -> str:
    pieces: list[str]
    if not query.columns:
        pieces = ["*"]
    else:
        pieces = [quote_ident(column) for column in query.columns]
    if query.time_bucket is not None:
        pieces.append(f"{_time_bucket_expr(query)} AS _time_bucket")
    if query.include_filename and query.columns:
        pieces.append(quote_ident("_source_file"))
    return ", ".join(pieces)


def _aggregation_select_and_group_sql(query: ParquetCollectionQuery) -> tuple[str, str]:
    select_pieces: list[str] = []
    group_exprs: list[str] = []
    if query.time_bucket is not None:
        bucket_expr = _time_bucket_expr(query)
        select_pieces.append(f"{bucket_expr} AS _time_bucket")
        group_exprs.append(bucket_expr)
    for column in query.group_by:
        select_pieces.append(quote_ident(column))
        group_exprs.append(quote_ident(column))
    for aggregation in query.aggregations:
        select_pieces.append(_aggregation_sql(aggregation))

    group_sql = ""
    if group_exprs:
        group_sql = " GROUP BY " + ", ".join(group_exprs)
    return ", ".join(select_pieces), group_sql


def _time_bucket_expr(query: ParquetCollectionQuery) -> str:
    if query.time_bucket not in {"hour", "day"}:
        raise QueryValidationError("time_bucket must be 'hour' or 'day'")
    return f"date_trunc({quote_literal(query.time_bucket)}, CAST({quote_ident(query.time_column)} AS TIMESTAMP))"


def _aggregation_sql(aggregation: AggregationSpec) -> str:
    alias = quote_ident(_aggregation_alias(aggregation))
    if aggregation.function == "count_star":
        return f"count(*) AS {alias}"

    ident = quote_ident(aggregation.column)
    if aggregation.function == "count":
        expr = f"count({ident})"
    elif aggregation.function == "null_count":
        expr = f"count(*) - count({ident})"
    elif aggregation.function == "count_distinct":
        expr = f"count(DISTINCT {ident})"
    elif aggregation.function == "sum":
        expr = f"sum({ident})"
    elif aggregation.function == "mean":
        expr = f"avg({ident})"
    elif aggregation.function == "stddev_samp":
        expr = f"stddev_samp({ident})"
    elif aggregation.function == "min":
        expr = f"min({ident})"
    elif aggregation.function == "max":
        expr = f"max({ident})"
    elif aggregation.function == "median":
        expr = f"median({ident})"
    else:
        raise QueryValidationError(f"Unsupported aggregation function: {aggregation.function}")
    return f"{expr} AS {alias}"


def _aggregation_alias(aggregation: AggregationSpec) -> str:
    if aggregation.alias is not None:
        return aggregation.alias
    if aggregation.function == "count_star":
        return "count_star"
    return f"{aggregation.function}_{aggregation.column}"


def _execute_frame(
    sql: str,
    params: list[object],
    *,
    session: DuckDBQuerySession | None,
    settings: QueryEngineSettings | None,
) -> pl.DataFrame:
    if session is not None:
        _load_delta_if_needed(session, sql)
        return session._execute_generated(sql, params).pl()
    with DuckDBQuerySession(settings) as managed_session:
        _load_delta_if_needed(managed_session, sql)
        return managed_session._execute_generated(sql, params).pl()


def _load_delta_if_needed(session: DuckDBQuerySession, sql: str) -> None:
    if "delta_scan(" in sql:
        delta_read.load_delta_extension(session._get_connection())
