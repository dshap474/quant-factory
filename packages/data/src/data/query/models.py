"""Typed contracts for reusable parquet query operations.

USAGE: ParquetCollectionQuery(scope="research", paths=("run/part.parquet",))
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

import polars as pl

# --------------------------------------------------------------------------- #
# Query settings, metadata, requests, and results
# --------------------------------------------------------------------------- #

DatasetScope = Literal["data", "features", "research", "signals", "strategies"]
AggregationFunction = Literal[
    "count_star",
    "count",
    "null_count",
    "count_distinct",
    "sum",
    "mean",
    "stddev_samp",
    "min",
    "max",
    "median",
]
TimeBucket = Literal["hour", "day"]


@dataclass(frozen=True)
class QueryEngineSettings:
    """DuckDB runtime settings for explicit query sessions."""

    threads: int | None = None
    memory_limit: str | None = None
    temp_directory: str | Path | None = None
    preserve_insertion_order: bool | None = None


@dataclass(frozen=True)
class ColumnInfo:
    """Schema entry for a parquet column."""

    name: str
    dtype: str


@dataclass(frozen=True)
class ParquetMetadata:
    """Metadata for one parquet dataset resolved inside the lake root."""

    scope: DatasetScope
    path: str
    absolute_path: str
    total_rows: int
    columns: tuple[ColumnInfo, ...]
    # The Polars schema read with the footer, so queries never re-read it. Not part of equality.
    typed_schema: dict[str, pl.DataType] = field(default_factory=dict, repr=False, compare=False)
    # The Delta ``TableRef`` when the path resolves to a Delta table; None for parquet files.
    table: Any = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class ParquetFileInfo:
    """File-level parquet metadata for one resolved collection member."""

    path: str
    absolute_path: str
    row_count: int
    row_group_count: int
    file_size_bytes: int
    # The Delta ``TableRef`` when this member is a Delta table (row_group_count then counts its files).
    table: Any = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class ParquetCollectionMetadata:
    """Metadata for a validated parquet file collection."""

    scope: DatasetScope
    path_glob: str
    files: tuple[ParquetFileInfo, ...]
    total_rows: int
    total_size_bytes: int
    total_row_groups: int
    columns: tuple[ColumnInfo, ...]
    common_columns: tuple[ColumnInfo, ...]
    schema_mismatches: tuple[str, ...]
    paths: tuple[str, ...] | None = None
    # First-seen Polars dtype per column across files, read once with the footers.
    typed_schema: dict[str, pl.DataType] = field(default_factory=dict, repr=False, compare=False)

    @property
    def file_count(self) -> int:
        return len(self.files)

    @property
    def requires_union_by_name(self) -> bool:
        return bool(self.schema_mismatches)


@dataclass(frozen=True)
class AggregationSpec:
    """Allowlisted aggregation over one optional source column."""

    function: AggregationFunction
    column: str | None = None
    alias: str | None = None

    def __post_init__(self) -> None:
        if self.function == "count_star":
            return
        if self.column is None:
            raise ValueError(f"{self.function} aggregation requires a column")


@dataclass(frozen=True)
class ParquetQuery:
    """Bounded query request for one parquet dataset."""

    scope: DatasetScope
    path: str
    columns: tuple[str, ...] | None = None
    start: str | date | datetime | None = None
    end: str | date | datetime | None = None
    time_column: str = "timestamp"
    entity_column: str | None = None
    entity_values: tuple[str, ...] = ()
    limit: int | None = 1000
    offset: int = 0
    order_by: str | None = None
    descending: bool = False


@dataclass(frozen=True)
class ParquetCollectionQuery:
    """Bounded scan using either path_glob or exact paths inside one lake scope.

    Integer bounds are inclusive and applied before ordering, aggregation, and limit.
    """

    scope: DatasetScope
    path_glob: str = ""
    columns: tuple[str, ...] | None = None
    start: str | date | datetime | None = None
    end: str | date | datetime | None = None
    time_column: str = "timestamp"
    entity_column: str | None = None
    entity_values: tuple[str, ...] = ()
    limit: int | None = 1000
    offset: int = 0
    order_by: str | None = None
    descending: bool = False
    include_filename: bool = False
    union_by_name: bool = False
    # Add a column per `key=value` directory (e.g. `slots=1000-1099` -> `slots`) to `*` reads.
    hive_partitioning: bool = False
    group_by: tuple[str, ...] = ()
    aggregations: tuple[AggregationSpec, ...] = ()
    time_bucket: TimeBucket | None = None
    paths: tuple[str, ...] | None = None
    integer_column: str | None = None
    integer_min: int | None = None
    integer_max: int | None = None


@dataclass(frozen=True)
class QueryResult:
    """Collected dataframe plus provenance for a parquet query."""

    metadata: ParquetMetadata | ParquetCollectionMetadata
    frame: pl.DataFrame
    # Single-file reads run on Polars; collections and their aggregations run on DuckDB.
    backend: Literal["duckdb", "polars"] = "duckdb"

    @property
    def returned_rows(self) -> int:
        return self.frame.height
