"""Reusable parquet query surface for canonical quant-factory lake datasets."""

from .collections import (
    aggregate_parquet_collection,
    explain_parquet_collection,
    get_parquet_collection_metadata,
    numeric_stats_collection,
    query_parquet_collection,
    resolve_parquet_collection,
)
from .engine import (
    count_parquet_rows,
    get_parquet_metadata,
    numeric_stats,
    preview_parquet,
    query_parquet,
    resolve_parquet_path,
    to_arrow_ipc_bytes,
)
from .errors import QueryError, QueryPathError, QueryValidationError
from .models import (
    AggregationSpec,
    ColumnInfo,
    DatasetScope,
    ParquetCollectionMetadata,
    ParquetCollectionQuery,
    ParquetFileInfo,
    ParquetMetadata,
    ParquetQuery,
    QueryEngineSettings,
    QueryResult,
)
from .session import DuckDBQuerySession

__all__ = [
    "AggregationSpec",
    "ColumnInfo",
    "DatasetScope",
    "DuckDBQuerySession",
    "ParquetCollectionMetadata",
    "ParquetCollectionQuery",
    "ParquetFileInfo",
    "ParquetMetadata",
    "ParquetQuery",
    "QueryEngineSettings",
    "QueryError",
    "QueryPathError",
    "QueryResult",
    "QueryValidationError",
    "aggregate_parquet_collection",
    "count_parquet_rows",
    "explain_parquet_collection",
    "get_parquet_collection_metadata",
    "get_parquet_metadata",
    "numeric_stats",
    "numeric_stats_collection",
    "preview_parquet",
    "query_parquet",
    "query_parquet_collection",
    "resolve_parquet_collection",
    "resolve_parquet_path",
    "to_arrow_ipc_bytes",
]
