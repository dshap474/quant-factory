"""Shared result and validation helpers for simple canonical raw families.

Usage: import these helpers from a family ``service.py``; provider behavior stays family-local.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, cast

from data.platform.contracts import DatasetKind, DatasetSpec, IngestResult, StorageTarget
from data.platform.errors import DatasetContractError
from data.platform.schema import SchemaValidator
from data.platform.storage.parquet_runtime import new_batch_id

# --------------------------------------------------------------------------- #
# Results
# --------------------------------------------------------------------------- #


def build_result(
    spec: DatasetSpec,
    operation: str,
    *,
    status: str,
    written: list[Path] | None = None,
    row_counts: dict[str, int] | None = None,
    checks: list[str] | None = None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
    metadata: dict[str, object] | None = None,
) -> IngestResult:
    return IngestResult(
        status=status,
        operation=operation,
        dataset_id=spec.dataset_id,
        family=spec.family,
        kind=spec.kind,
        target=spec.target,
        batch_id=new_batch_id(),
        written_artifacts=[str(path) for path in written or []],
        row_counts=row_counts or {},
        checks_passed=checks or [],
        warnings=warnings or [],
        errors=errors or [],
        metadata=metadata or {},
    )


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #


def validate_raw_1d_spec(spec: DatasetSpec, *, family: str, supported_dataset_ids: set[str]) -> None:
    if spec.dataset_id not in supported_dataset_ids:
        raise DatasetContractError(f"Unsupported {family} dataset_id", dataset_id=spec.dataset_id)
    if spec.kind != DatasetKind.DATA_RAW:
        raise DatasetContractError(f"{family} datasets must use kind=data/raw", kind=spec.kind.value)
    if spec.target != StorageTarget.CANONICAL_DATA_RAW:
        raise DatasetContractError(f"{family} datasets must target canonical_data_raw", target=spec.target.value)
    if spec.resolution not in {None, "1d"}:
        raise DatasetContractError(f"{family} datasets must use resolution=1d", resolution=spec.resolution)


def validate_raw_schema(spec: DatasetSpec, *, mode: str, layer: str = "data/raw") -> IngestResult:
    if mode not in {"strict", "repair", "warn"}:
        raise DatasetContractError("Unsupported schema validation mode", mode=mode)
    validation_mode = cast(Literal["strict", "repair", "warn"], mode)
    result = SchemaValidator(spec.resolved_db_root()).validate(mode=validation_mode, layer=layer)
    if result.valid:
        return build_result(
            spec,
            "validate",
            status="success",
            checks=[f"schema:{layer.removeprefix('data/')}:{mode}"],
            metadata={"validation": str(result)},
        )
    return build_result(spec, "validate", status="error", errors=[str(result)], metadata={"validation": str(result)})


__all__ = ["build_result", "validate_raw_1d_spec", "validate_raw_schema"]
