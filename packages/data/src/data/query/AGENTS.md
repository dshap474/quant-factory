# Data Query

## What
- Read-only parquet access for the canonical lake. One engine per shape: single-file reads (`query_parquet`, `preview_parquet`, `count_parquet_rows`, `numeric_stats`) run as Polars lazy scans; multi-file collections and their aggregations run on DuckDB. Callers never choose the engine; `QueryResult.backend` reports it.
- Both engines share one filter contract: `_sql.temporal_bound` normalizes start/end bounds and entity values compare as text, so a query selects the same rows either way. Change filter semantics in both `engine._filters` and `_sql.duckdb_where` together.
- Hive partitioning is off by default in both engines: a `key=value` directory never adds a column the file schema lacks. A collection query that wants the partition as a column sets `hive_partitioning=True`.
- A plain folder of parquet files with one shared schema, up to `MAX_DIRECTORY_BYTES`, reads as one dataset through the single-file functions; anything else is rejected, so a folder of unrelated tables never unions.
- Public surface is `data.query`, not `data.api`.
- Supported scopes are `data`, `features`, `research`, `signals`, and `strategies`; all paths are relative to `QUANT_DB_ROOT/<scope>/`.

## Use
- Single file: `ParquetQuery` with `query_parquet`, `preview_parquet`, `get_parquet_metadata`, or `numeric_stats`.
- Multi-file lake scans: `ParquetCollectionQuery` with `query_parquet_collection`, `aggregate_parquet_collection`, `get_parquet_collection_metadata`, `numeric_stats_collection`, or `explain_parquet_collection`.
- Resolve collections with exact parquet files, directories, `*` globs, or recursive `**` globs.
- For a committed publication snapshot, pass `paths=("relative/part.parquet", ...)` instead of `path_glob`; only those files are read. Empty lists, duplicates, traversal, symlink escapes, and globs in explicit lists are rejected.
- Use `integer_column` with inclusive `integer_min`/`integer_max` for a publication sequence cutoff; filters run before aggregation and limiting.
- Reuse a `DuckDBQuerySession` across several collection queries in one request, and pass `metadata=` from `get_parquet_collection_metadata` when repeating queries over the same collection; both skip repeated setup. Leave `preserve_insertion_order` on: turning it off made LIMIT previews ~3x slower.

## Rules
- Keep this package read-only. Never add canonical writes, cache-table creation, migrations, or arbitrary public SQL execution here.
- Reject absolute paths, traversal, non-parquet matches, empty collections, and files outside the requested scope.
- Prefer structured query fields over string SQL: `columns`, `start`, `end`, `entity_column`, `entity_values`, `order_by`, `group_by`, `aggregations`, and `time_bucket`.
- Use `union_by_name=True` only when metadata shows schema drift requires it.
- Use `include_filename=True` when provenance matters; it returns `_source_file`.
- Reuse `metadata=` only when it was produced for the same `scope` and `path_glob`; helpers revalidate it.

## Pattern
```python
from data.query import AggregationSpec, ParquetCollectionQuery, aggregate_parquet_collection

result = aggregate_parquet_collection(
    ParquetCollectionQuery(
        scope="data",
        path_glob="raw/1m/example/futures/*/*.parquet",
        group_by=("exchange",),
        aggregations=(AggregationSpec("count_star", alias="rows"),),
        limit=None,
    )
)
```

## Avoid
- Do not import from internals like `data.query.collections`; use `data.query`.
- Do not hand-roll ad hoc SQL or glob readers in serving surfaces or shared tooling when this package covers the need; family-local Polars reads of canonical inputs are sanctioned and stay outside this package.
- Do not expose raw DuckDB connections or `.execute()` as public API.
