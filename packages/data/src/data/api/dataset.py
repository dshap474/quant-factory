"""Dataset-oriented control plane for canonical data operations."""

from __future__ import annotations

from data.extensions import load_dataset_extensions
from data.platform.contracts import DatasetSpec, IngestResult
from data.platform.ingestion.control_plane import DatasetHandlerRegistry

load_dataset_extensions()


def _revalidated(result: IngestResult) -> IngestResult:
    """Re-run result validation so a status/errors change made after construction still
    turns a partial run into an error before any wrapper reads it."""
    checked = IngestResult.model_validate(result.model_dump())
    return result if checked == result else checked


def ingest_dataset(spec: DatasetSpec) -> IngestResult:
    handler = DatasetHandlerRegistry.get(spec.family)
    handler.validate_spec(spec)
    return _revalidated(handler.ingest(spec))


def sync_dataset(spec: DatasetSpec) -> IngestResult:
    handler = DatasetHandlerRegistry.get(spec.family)
    handler.validate_spec(spec)
    return _revalidated(handler.sync(spec))


def materialize_dataset(spec: DatasetSpec) -> IngestResult:
    handler = DatasetHandlerRegistry.get(spec.family)
    handler.validate_spec(spec)
    return _revalidated(handler.materialize(spec))


def validate_dataset(spec: DatasetSpec, *, mode: str = "warn") -> IngestResult:
    handler = DatasetHandlerRegistry.get(spec.family)
    handler.validate_spec(spec)
    return handler.validate(spec, mode=mode)


def get_dataset_status(spec: DatasetSpec) -> IngestResult:
    handler = DatasetHandlerRegistry.get(spec.family)
    handler.validate_spec(spec)
    return handler.status(spec)


def reconcile_dataset(spec: DatasetSpec) -> IngestResult:
    handler = DatasetHandlerRegistry.get(spec.family)
    handler.validate_spec(spec)
    return handler.reconcile(spec)


__all__ = [
    "get_dataset_status",
    "ingest_dataset",
    "materialize_dataset",
    "reconcile_dataset",
    "sync_dataset",
    "validate_dataset",
]
