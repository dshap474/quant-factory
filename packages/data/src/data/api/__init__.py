"""Curated dataset-oriented public API for the data package."""

from __future__ import annotations

from pathlib import Path

from data.config.paths import QUANT_DB_ROOT, resolve_db_root

from .availability import (
    AVAILABLE_AT_COLUMN,
    add_available_at,
    filter_available_as_of,
    validate_information_set,
)
from .contracts import (
    DatasetKind,
    DatasetSpec,
    IngestResult,
    StorageTarget,
    SyncMode,
    WriteDisposition,
)
from .dataset import (
    get_dataset_status,
    ingest_dataset,
    materialize_dataset,
    reconcile_dataset,
    sync_dataset,
    validate_dataset,
)
from .identity import resolve_asset_ids
from .schema import (
    SchemaLoader,
    SchemaValidationError,
    SchemaValidationMode,
    SchemaValidator,
    ValidationResult,
    generate_initial_schemas,
    validate_schema,
)
from .storage import (
    FeatureCatalogValidation,
    FeatureMigrationResult,
    FeatureStore,
    FeatureStoreConfig,
    FeatureVersion,
    ensure_feature_meta_viz,
    list_feature_catalog,
    migrate_feature_catalog,
    validate_feature_catalog,
)
from .surface import (
    DEFAULT_JOBS,
    DEFAULT_MEMORY_GB,
    STEP_TIMEOUT_SECONDS,
    DataOperationalSurfaceValidation,
    RefreshStep,
    SurfaceStatus,
    budget_mb,
    collect_surface_status,
    default_memory_gb,
    memory_cap_available,
    refresh_command,
    refresh_plan,
    resolve_needs,
    run_refresh,
    step_estimates,
    validate_data_operational_surface,
)


def collect_data_surface_status(*, db_root: str | Path | None = None) -> list[SurfaceStatus]:
    """Report parquet footprint, data freshness, and quality issues per db-writing pipeline."""
    return collect_surface_status(resolve_db_root(db_root))


def generate_schema_files(*, db_root: str | Path | None = None) -> None:
    """Generate master and layer SCHEMA.yaml files from current parquet footprints."""
    generate_initial_schemas(db_root=db_root)


__all__ = [
    "AVAILABLE_AT_COLUMN",
    "DatasetKind",
    "DatasetSpec",
    "DataOperationalSurfaceValidation",
    "FeatureCatalogValidation",
    "FeatureMigrationResult",
    "FeatureStore",
    "FeatureStoreConfig",
    "FeatureVersion",
    "IngestResult",
    "QUANT_DB_ROOT",
    "RefreshStep",
    "SchemaLoader",
    "SchemaValidationError",
    "SchemaValidationMode",
    "SchemaValidator",
    "StorageTarget",
    "SurfaceStatus",
    "SyncMode",
    "ValidationResult",
    "WriteDisposition",
    "add_available_at",
    "collect_data_surface_status",
    "ensure_feature_meta_viz",
    "filter_available_as_of",
    "generate_schema_files",
    "get_dataset_status",
    "ingest_dataset",
    "list_feature_catalog",
    "materialize_dataset",
    "migrate_feature_catalog",
    "reconcile_dataset",
    "refresh_command",
    "STEP_TIMEOUT_SECONDS",
    "DEFAULT_JOBS",
    "DEFAULT_MEMORY_GB",
    "budget_mb",
    "default_memory_gb",
    "memory_cap_available",
    "refresh_plan",
    "resolve_asset_ids",
    "resolve_needs",
    "run_refresh",
    "step_estimates",
    "sync_dataset",
    "validate_data_operational_surface",
    "validate_feature_catalog",
    "validate_information_set",
    "validate_dataset",
    "validate_schema",
]
