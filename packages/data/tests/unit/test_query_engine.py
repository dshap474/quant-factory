"""Tests for the reusable parquet query runtime."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import get_args

import polars as pl
import pytest
from data.query import (
    AggregationSpec,
    DatasetScope,
    DuckDBQuerySession,
    ParquetCollectionQuery,
    ParquetQuery,
    QueryEngineSettings,
    QueryPathError,
    QueryValidationError,
    aggregate_parquet_collection,
    count_parquet_rows,
    explain_parquet_collection,
    get_parquet_collection_metadata,
    get_parquet_metadata,
    numeric_stats,
    numeric_stats_collection,
    preview_parquet,
    query_parquet,
    query_parquet_collection,
    resolve_parquet_collection,
    resolve_parquet_path,
    to_arrow_ipc_bytes,
)


@pytest.fixture
def query_db_root(tmp_path: Path) -> Path:
    db_root = tmp_path / "db"
    target = db_root / "data" / "raw" / "1d"
    target.mkdir(parents=True)
    pl.DataFrame(
        {
            "timestamp": [datetime(2024, 1, 1) + timedelta(days=i) for i in range(5)],
            "asset": ["BTC", "ETH", "BTC", "SOL", "BTC"],
            "observation_date": [
                (datetime(2024, 1, 1) + timedelta(days=i)).date().isoformat()
                for i in range(5)
            ],
            "close": [10.0, 20.0, 11.0, 30.0, 12.0],
            "volume": [100, 200, 110, 300, 120],
        }
    ).write_parquet(target / "panel.parquet")
    pl.DataFrame(
        {
            "timestamp": [
                "2024-01-01T09:30:00",
                "2024-01-02T10:15:00",
                "2024-01-02T15:45:00",
                "2024-01-03T09:30:00",
            ],
            "asset": ["BTC", "ETH", "SOL", "BTC"],
            "close": [10.0, 20.0, 30.0, 11.0],
        }
    ).write_parquet(target / "string_times.parquet")

    collection = db_root / "data" / "raw" / "1m" / "collection"
    collection.mkdir(parents=True)
    pl.DataFrame(
        {
            "timestamp": [
                datetime(2024, 1, 1, 0),
                datetime(2024, 1, 1, 1),
                datetime(2024, 1, 2, 0),
            ],
            "exchange": ["binance", "binance", "binance"],
            "asset": ["BTC", "ETH", "BTC"],
            "price": [10.0, 20.0, 11.0],
            "volume": [100.0, 200.0, 110.0],
        }
    ).write_parquet(collection / "binance.parquet")
    pl.DataFrame(
        {
            "timestamp": [datetime(2024, 1, 1, 0), datetime(2024, 1, 2, 0)],
            "exchange": ["coinbase", "coinbase"],
            "asset": ["BTC", "SOL"],
            "price": [10.5, 30.0],
            "volume": [90.0, 300.0],
        }
    ).write_parquet(collection / "coinbase.parquet")
    nested = collection / "nested"
    nested.mkdir()
    pl.DataFrame(
        {
            "timestamp": [datetime(2024, 1, 1, 0)],
            "exchange": ["kraken"],
            "asset": ["BTC"],
            "price": [10.25],
            "volume": [80.0],
        }
    ).write_parquet(nested / "kraken.parquet")
    (collection / "notes.txt").write_text("not parquet")

    research = db_root / "research" / "strategies" / "candidate"
    research.mkdir(parents=True)
    pl.DataFrame({"date": ["2024-01-01"], "daily_return": [0.01]}).write_parquet(
        research / "path.parquet"
    )

    drift = db_root / "data" / "raw" / "1m" / "schema_drift"
    drift.mkdir(parents=True)
    pl.DataFrame(
        {"timestamp": [datetime(2024, 1, 1)], "asset": ["BTC"], "price": [10.0]}
    ).write_parquet(drift / "a.parquet")
    pl.DataFrame(
        {
            "timestamp": [datetime(2024, 1, 2)],
            "asset": ["ETH"],
            "price": [20.0],
            "extra_factor": [1.0],
        }
    ).write_parquet(drift / "b.parquet")

    filename_dir = db_root / "data" / "raw" / "1m" / "filename_columns"
    filename_dir.mkdir(parents=True)
    pl.DataFrame(
        {
            "timestamp": [datetime(2024, 1, 1)],
            "filename": ["provider-file-name"],
            "value": [1.0],
        }
    ).write_parquet(filename_dir / "real_filename.parquet")
    pl.DataFrame(
        {
            "timestamp": [datetime(2024, 1, 1)],
            "_source_file": ["already-present"],
            "value": [2.0],
        }
    ).write_parquet(filename_dir / "source_file.parquet")
    return db_root


def test_query_parquet_projects_filters_and_orders(query_db_root: Path):
    result = query_parquet(
        ParquetQuery(
            scope="data",
            path="raw/1d/panel.parquet",
            columns=("timestamp", "asset", "close"),
            start="2024-01-02",
            entity_column="asset",
            entity_values=("BTC",),
            order_by="timestamp",
            descending=True,
            limit=2,
        ),
        db_root=query_db_root,
    )

    assert result.backend == "polars"
    assert result.metadata.total_rows == 5
    assert result.frame["asset"].to_list() == ["BTC", "BTC"]
    assert result.frame["close"].to_list() == [12.0, 11.0]
    assert result.frame.columns == ["timestamp", "asset", "close"]


def test_count_parquet_rows_applies_filters_and_ignores_paging(query_db_root: Path):
    base = ParquetQuery(scope="data", path="raw/1d/panel.parquet", limit=1, offset=3)

    assert count_parquet_rows(base, db_root=query_db_root) == 5
    btc = replace(base, entity_column="asset", entity_values=("BTC",))
    assert count_parquet_rows(btc, db_root=query_db_root) == 3
    assert count_parquet_rows(replace(btc, start="2024-01-02"), db_root=query_db_root) == 2


def test_preview_and_metadata_do_not_require_full_query(query_db_root: Path):
    metadata = get_parquet_metadata(scope="data", path="raw/1d/panel.parquet", db_root=query_db_root)
    page = preview_parquet(
        scope="data",
        path="raw/1d/panel.parquet",
        page=2,
        page_size=2,
        db_root=query_db_root,
    )

    assert metadata.total_rows == 5
    assert [column.name for column in metadata.columns] == [
        "timestamp",
        "asset",
        "observation_date",
        "close",
        "volume",
    ]
    assert page.frame["asset"].to_list() == ["BTC", "SOL"]


def test_datetime_filters_accept_z_suffix_for_naive_columns(query_db_root: Path):
    result = query_parquet(
        ParquetQuery(
            scope="data",
            path="raw/1d/panel.parquet",
            columns=("timestamp", "asset"),
            start="2024-01-02T00:00:00Z",
        ),
        db_root=query_db_root,
    )

    assert result.backend == "polars"
    assert result.frame["asset"].to_list() == ["ETH", "BTC", "SOL", "BTC"]


def test_string_date_filters_compare_normalized_dates(query_db_root: Path):
    result = query_parquet(
        ParquetQuery(
            scope="data",
            path="raw/1d/panel.parquet",
            columns=("observation_date", "asset"),
            time_column="observation_date",
            start="2024-01-02",
            end="2024-01-04T00:00:00Z",
        ),
        db_root=query_db_root,
    )

    assert result.backend == "polars"
    assert result.frame["asset"].to_list() == ["ETH", "BTC", "SOL"]


def test_string_iso_datetime_end_date_includes_same_day_rows(query_db_root: Path):
    result = query_parquet(
        ParquetQuery(
            scope="data",
            path="raw/1d/string_times.parquet",
            columns=("timestamp", "asset"),
            time_column="timestamp",
            end="2024-01-02",
            order_by="timestamp",
        ),
        db_root=query_db_root,
    )

    assert result.backend == "polars"
    assert result.frame["asset"].to_list() == ["BTC", "ETH", "SOL"]


def test_invalid_temporal_bound_raises_validation_error(query_db_root: Path):
    with pytest.raises(QueryValidationError, match="Invalid temporal bound"):
        query_parquet(
            ParquetQuery(scope="data", path="raw/1d/panel.parquet", start="not-a-date"),
            db_root=query_db_root,
        )


def test_numeric_stats_and_arrow_serialization(query_db_root: Path):
    result = numeric_stats(
        scope="data",
        path="raw/1d/panel.parquet",
        columns=("close",),
        db_root=query_db_root,
    )
    row = result.frame.row(0, named=True)

    assert row["column"] == "close"
    assert row["count"] == 5
    assert row["null_count"] == 0
    assert row["max"] == 30.0
    assert to_arrow_ipc_bytes(result.frame).startswith(b"ARROW")


def test_query_rejects_unknown_columns(query_db_root: Path):
    with pytest.raises(QueryValidationError, match="Unknown columns"):
        query_parquet(
            ParquetQuery(scope="data", path="raw/1d/panel.parquet", columns=("missing",)),
            db_root=query_db_root,
        )


def test_resolve_parquet_path_rejects_traversal(query_db_root: Path):
    with pytest.raises(QueryPathError, match="Access denied"):
        resolve_parquet_path(scope="data", path="../outside.parquet", db_root=query_db_root)


def test_resolve_parquet_collection_accepts_file_directory_and_globs(query_db_root: Path):
    exact = resolve_parquet_collection(
        scope="data",
        path_glob="raw/1m/collection/binance.parquet",
        db_root=query_db_root,
    )
    directory = resolve_parquet_collection(
        scope="data",
        path_glob="raw/1m/collection",
        db_root=query_db_root,
    )
    globbed = resolve_parquet_collection(
        scope="data",
        path_glob="raw/1m/collection/*.parquet",
        db_root=query_db_root,
    )
    recursive = resolve_parquet_collection(
        scope="data",
        path_glob="raw/1m/collection/**/*.parquet",
        db_root=query_db_root,
    )

    assert len(exact) == 1
    assert len(directory) == 3
    assert len(globbed) == 2
    assert len(recursive) == 3


def test_resolve_parquet_collection_rejects_unsafe_or_bad_matches(query_db_root: Path):
    with pytest.raises(QueryPathError, match="Access denied"):
        resolve_parquet_collection(scope="data", path_glob="../*.parquet", db_root=query_db_root)
    with pytest.raises(QueryPathError, match="lake-relative"):
        resolve_parquet_collection(
            scope="data",
            path_glob=str(query_db_root / "data" / "raw" / "1m" / "collection" / "binance.parquet"),
            db_root=query_db_root,
        )
    with pytest.raises(QueryPathError, match="Only parquet"):
        resolve_parquet_collection(
            scope="data",
            path_glob="raw/1m/collection/*",
            db_root=query_db_root,
        )
    with pytest.raises(QueryPathError, match="No parquet files"):
        resolve_parquet_collection(
            scope="data",
            path_glob="raw/1m/collection/missing/*.parquet",
            db_root=query_db_root,
        )


def test_collection_metadata_reports_counts_and_schema_drift(query_db_root: Path):
    metadata = get_parquet_collection_metadata(
        scope="data",
        path_glob="raw/1m/schema_drift/*.parquet",
        db_root=query_db_root,
    )

    assert metadata.file_count == 2
    assert metadata.total_rows == 2
    assert metadata.total_row_groups == 2
    assert metadata.total_size_bytes > 0
    assert metadata.requires_union_by_name is True
    assert {column.name for column in metadata.columns} == {
        "timestamp",
        "asset",
        "price",
        "extra_factor",
    }
    assert {column.name for column in metadata.common_columns} == {"timestamp", "asset", "price"}


def test_query_parquet_collection_projects_filters_and_source_file(query_db_root: Path):
    result = query_parquet_collection(
        ParquetCollectionQuery(
            scope="data",
            path_glob="raw/1m/collection/*.parquet",
            columns=("timestamp", "exchange", "asset", "price"),
            start="2024-01-01",
            end="2024-01-01",
            entity_column="asset",
            entity_values=("BTC",),
            include_filename=True,
            order_by="exchange",
            limit=None,
        ),
        db_root=query_db_root,
    )

    assert result.metadata.total_rows == 5
    assert result.frame["exchange"].to_list() == ["binance", "coinbase"]
    assert result.frame["asset"].to_list() == ["BTC", "BTC"]
    assert "_source_file" in result.frame.columns
    assert all(path.endswith(".parquet") for path in result.frame["_source_file"].to_list())


def test_collection_datetime_end_date_includes_full_day(query_db_root: Path):
    result = query_parquet_collection(
        ParquetCollectionQuery(
            scope="data",
            path_glob="raw/1m/collection/binance.parquet",
            columns=("timestamp", "asset"),
            end="2024-01-01",
            order_by="timestamp",
            limit=None,
        ),
        db_root=query_db_root,
    )

    assert result.frame["asset"].to_list() == ["BTC", "ETH"]


def test_collection_empty_columns_defaults_to_all_columns(query_db_root: Path):
    result = query_parquet_collection(
        ParquetCollectionQuery(
            scope="data",
            path_glob="raw/1m/collection/binance.parquet",
            columns=(),
            limit=1,
        ),
        db_root=query_db_root,
    )

    assert result.frame.columns == ["timestamp", "exchange", "asset", "price", "volume"]


def test_collection_include_filename_with_star_returns_one_source_column(query_db_root: Path):
    result = query_parquet_collection(
        ParquetCollectionQuery(
            scope="data",
            path_glob="raw/1m/collection/binance.parquet",
            include_filename=True,
            limit=1,
        ),
        db_root=query_db_root,
    )

    assert "_source_file" in result.frame.columns
    assert "filename" not in result.frame.columns


def test_collection_include_filename_allows_real_filename_column(query_db_root: Path):
    result = query_parquet_collection(
        ParquetCollectionQuery(
            scope="data",
            path_glob="raw/1m/filename_columns/real_filename.parquet",
            columns=("filename", "value"),
            include_filename=True,
            limit=1,
        ),
        db_root=query_db_root,
    )

    assert result.frame.columns == ["filename", "value", "_source_file"]
    assert result.frame["filename"].to_list() == ["provider-file-name"]
    assert result.frame["_source_file"].to_list()[0].endswith("real_filename.parquet")


def test_collection_include_filename_rejects_source_file_collision(query_db_root: Path):
    with pytest.raises(QueryValidationError, match="_source_file"):
        query_parquet_collection(
            ParquetCollectionQuery(
                scope="data",
                path_glob="raw/1m/filename_columns/source_file.parquet",
                include_filename=True,
                limit=1,
            ),
            db_root=query_db_root,
        )


def test_collection_query_rejects_group_by_without_aggregations(query_db_root: Path):
    with pytest.raises(QueryValidationError, match="group_by requires aggregations"):
        query_parquet_collection(
            ParquetCollectionQuery(
                scope="data",
                path_glob="raw/1m/collection/*.parquet",
                group_by=("exchange",),
                limit=None,
            ),
            db_root=query_db_root,
        )


def test_collection_query_requires_union_by_name_for_schema_drift(query_db_root: Path):
    query = ParquetCollectionQuery(
        scope="data",
        path_glob="raw/1m/schema_drift/*.parquet",
        columns=("asset", "price", "extra_factor"),
        order_by="timestamp",
        limit=None,
    )

    with pytest.raises(QueryValidationError, match="union_by_name"):
        query_parquet_collection(query, db_root=query_db_root)

    result = query_parquet_collection(
        replace(query, union_by_name=True),
        db_root=query_db_root,
    )
    assert result.frame["asset"].to_list() == ["BTC", "ETH"]
    assert result.frame["extra_factor"].to_list()[0] is None


def test_collection_query_revalidates_supplied_metadata_path(query_db_root: Path):
    metadata = get_parquet_collection_metadata(
        scope="data",
        path_glob="raw/1m/collection/*.parquet",
        db_root=query_db_root,
    )

    with pytest.raises(QueryValidationError, match="path_glob"):
        query_parquet_collection(
            ParquetCollectionQuery(
                scope="data",
                path_glob="raw/1m/schema_drift/*.parquet",
                columns=("asset",),
                union_by_name=True,
                limit=1,
            ),
            db_root=query_db_root,
            metadata=metadata,
        )


def test_collection_helpers_reject_fabricated_metadata_files(query_db_root: Path):
    metadata = get_parquet_collection_metadata(
        scope="data",
        path_glob="raw/1m/collection/*.parquet",
        db_root=query_db_root,
    )
    outside = query_db_root.parent / "outside.parquet"
    pl.DataFrame({"asset": ["BTC"], "price": [1.0]}).write_parquet(outside)
    bad_file = replace(metadata.files[0], absolute_path=str(outside))
    bad_metadata = replace(metadata, files=(bad_file, *metadata.files[1:]))
    query = ParquetCollectionQuery(
        scope="data",
        path_glob="raw/1m/collection/*.parquet",
        columns=("asset",),
        limit=1,
    )

    with pytest.raises(QueryValidationError, match="metadata files"):
        query_parquet_collection(query, db_root=query_db_root, metadata=bad_metadata)
    with pytest.raises(QueryValidationError, match="metadata files"):
        explain_parquet_collection(query, db_root=query_db_root, metadata=bad_metadata)
    with pytest.raises(QueryValidationError, match="metadata files"):
        aggregate_parquet_collection(
            replace(
                query,
                columns=None,
                group_by=("exchange",),
                aggregations=(AggregationSpec(function="count_star", alias="rows"),),
                limit=None,
            ),
            db_root=query_db_root,
            metadata=bad_metadata,
        )


def test_aggregate_parquet_collection_groups_and_time_buckets(query_db_root: Path):
    result = aggregate_parquet_collection(
        ParquetCollectionQuery(
            scope="data",
            path_glob="raw/1m/collection/*.parquet",
            group_by=("exchange",),
            aggregations=(
                AggregationSpec(function="count_star", alias="rows"),
                AggregationSpec(function="mean", column="volume", alias="mean_volume"),
            ),
            time_bucket="day",
            order_by="exchange",
            limit=None,
        ),
        db_root=query_db_root,
    )
    rows = result.frame.rows(named=True)
    totals = {}
    for row in rows:
        totals[row["exchange"]] = totals.get(row["exchange"], 0) + row["rows"]

    assert totals["binance"] == 3
    assert totals["coinbase"] == 2
    assert any(row["mean_volume"] == pytest.approx(150.0) for row in rows)
    assert "_time_bucket" in result.frame.columns


def test_numeric_stats_collection_uses_validated_file_list(query_db_root: Path):
    result = numeric_stats_collection(
        scope="data",
        path_glob="raw/1m/collection/*.parquet",
        columns=("price",),
        db_root=query_db_root,
    )
    row = result.frame.row(0, named=True)

    assert row["column"] == "price"
    assert row["count"] == 5
    assert row["max"] == 30.0


def test_duckdb_query_session_applies_validated_settings(tmp_path: Path):
    settings = QueryEngineSettings(
        threads=2,
        memory_limit="1GB",
        temp_directory=tmp_path / "duckdb",
        preserve_insertion_order=False,
    )

    with DuckDBQuerySession(settings) as session:
        current_settings = session.current_settings()

    assert current_settings["threads"] == 2
    assert str(current_settings["temp_directory"]).endswith("duckdb")
    assert current_settings["preserve_insertion_order"] is False


def test_duckdb_query_session_does_not_expose_public_raw_sql_execution():
    session = DuckDBQuerySession()

    assert not hasattr(session, "execute")
    assert not hasattr(session, "connection")


@pytest.mark.parametrize(
    "sql",
    [
        "CREATE TABLE t (x INTEGER)",
        "COPY (SELECT 1) TO 'out.parquet'",
        "ATTACH 'other.duckdb'",
        "INSTALL httpfs",
        "LOAD httpfs",
        "SELECT 1; CREATE TABLE t (x INTEGER)",
    ],
)
def test_duckdb_query_session_rejects_non_read_generated_sql(sql: str):
    with DuckDBQuerySession() as session:
        with pytest.raises(QueryValidationError, match="read-only|single statement"):
            session._execute_generated(sql)


def test_public_collection_query_can_reuse_session(query_db_root: Path):
    with DuckDBQuerySession() as session:
        result = query_parquet_collection(
            ParquetCollectionQuery(
                scope="data",
                path_glob="raw/1m/collection/binance.parquet",
                columns=("asset", "price"),
                limit=1,
            ),
            db_root=query_db_root,
            session=session,
        )

    assert result.frame.columns == ["asset", "price"]
    assert result.frame["asset"].to_list() == ["BTC"]


def test_explain_parquet_collection_returns_duckdb_plan(query_db_root: Path):
    plan = explain_parquet_collection(
        ParquetCollectionQuery(
            scope="data",
            path_glob="raw/1m/collection/*.parquet",
            columns=("timestamp", "asset"),
            limit=1,
        ),
        db_root=query_db_root,
    )

    assert "read_parquet" in plan.lower() or "physical_plan" in plan.lower()


def test_query_package_exports_shared_literals():
    assert set(get_args(DatasetScope)) == {
        "data",
        "features",
        "research",
        "signals",
        "strategies",
    }


def test_query_parquet_supports_read_only_research_artifacts(query_db_root: Path):
    result = query_parquet(
        ParquetQuery(
            scope="research",
            path="strategies/candidate/path.parquet",
            columns=("date", "daily_return"),
        ),
        db_root=query_db_root,
    )

    assert result.frame.to_dicts() == [{"date": "2024-01-01", "daily_return": 0.01}]
