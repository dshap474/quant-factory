"""Public import contract tests for the canonical data package."""

from __future__ import annotations

import importlib
from pathlib import Path

import data.api as data_api
import pytest

import data

PUBLIC_SYMBOLS = [
    "DataOperationalSurfaceValidation",
    "SchemaLoader",
    "SchemaValidationError",
    "SchemaValidator",
    "ValidationResult",
    "FeatureStore",
    "FeatureStoreConfig",
    "FeatureVersion",
    "DatasetSpec",
    "DatasetKind",
    "StorageTarget",
    "SyncMode",
    "WriteDisposition",
    "IngestResult",
]

API_FUNCTIONS = [
    "validate_data_operational_surface",
    "validate_schema",
    "ingest_dataset",
    "sync_dataset",
    "materialize_dataset",
    "validate_dataset",
    "get_dataset_status",
    "reconcile_dataset",
    "resolve_asset_ids",
]


def test_data_root_package_is_minimal():
    assert data.__all__ == ["__version__"]
    assert hasattr(data, "__version__")


def test_data_api_exposes_control_plane_symbols():
    for symbol in PUBLIC_SYMBOLS:
        assert hasattr(data_api, symbol), f"Missing api symbol: {symbol}"


def test_data_api_exposes_control_plane_functions():
    for fn in API_FUNCTIONS:
        assert hasattr(data_api, fn), f"Missing API function: {fn}"
        assert callable(getattr(data_api, fn))


def test_control_plane_symbols_are_in_api_dunder_all():
    for symbol in PUBLIC_SYMBOLS + API_FUNCTIONS:
        assert symbol in data_api.__all__




def test_query_symbols_are_not_on_data_api():
    for symbol in [
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
    ]:
        assert not hasattr(data_api, symbol), f"query symbol should not be exposed: {symbol}"


def test_canonical_data_package_tree_exists_for_operator_surface():
    package_root = Path(__file__).resolve().parents[2]
    assert (package_root / "__init__.py").exists()
    assert (package_root / "src" / "data" / "__init__.py").exists()
    assert (package_root / "src" / "data" / "api" / "__init__.py").exists()
    assert (package_root / "src" / "data" / "cli" / "__init__.py").exists()


def test_removed_legacy_package_tree_is_absent():
    legacy_root = Path(__file__).resolve().parents[4] / "core" / ("data" + "-manager")
    assert not legacy_root.exists()


def test_removed_legacy_module_is_not_importable():
    try:
        importlib.import_module("data" + "_manager")
    except ModuleNotFoundError:
        return
    raise AssertionError("removed legacy module should not be importable")


def test_removed_legacy_api_acquisition_module_is_not_importable():
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("data.api.acquisition")
