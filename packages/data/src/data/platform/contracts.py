"""Shared typed contracts for the data control plane."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from data.config.paths import resolve_db_root


class DatasetKind(str, Enum):
    DATA_RAW = "data/raw"
    DATA_CORRECTED = "data/corrected"
    DATA_DERIVED = "data/derived"
    FEATURE = "feature"


class StorageTarget(str, Enum):
    CANONICAL_DATA_RAW = "canonical_data_raw"
    CANONICAL_DATA_CORRECTED = "canonical_data_corrected"
    CANONICAL_DATA_DERIVED = "canonical_data_derived"
    CANONICAL_FEATURE = "canonical_feature"
    EXTERNAL = "external"


class SyncMode(str, Enum):
    SNAPSHOT = "snapshot"
    INCREMENTAL = "incremental"
    BACKFILL = "backfill"


class WriteDisposition(str, Enum):
    FAIL = "fail"
    MERGE = "merge"
    OVERWRITE = "overwrite"
    APPEND = "append"


class TableLayout(BaseModel):
    """How a Delta table is laid out: partition column, sort key, key columns, rows per sealed file.

    Declared once per dataset (``DatasetSpec.layout``) and stored with the table at creation
    (``<table>/_qf/layout.json``). ``key_columns`` get add-action stats; files are sorted by ``sort_key``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    partition: str | None = None
    sort_key: tuple[str, ...]
    key_columns: tuple[str, ...]
    target_file_rows: int = Field(default=3_500_000, gt=0)

    @model_validator(mode="after")
    def _check_columns(self) -> TableLayout:
        if not self.sort_key or not self.key_columns:
            raise ValueError("sort_key and key_columns must not be empty")
        if self.partition is not None and self.partition in self.sort_key:
            raise ValueError("the partition column must not be part of sort_key")
        return self


class TableCommit(BaseModel):
    """One Delta commit made by the write engine (``write_slice``, ``seal_partition``, ``create_table``)."""

    model_config = ConfigDict(extra="forbid")

    table: str
    operation: str
    run_id: str
    version: int | None = None
    slice: str | None = None
    rows_written: int = 0
    rows_deleted: int = 0
    files_added: int = 0
    files_removed: int = 0
    seconds: float = 0.0
    checks_passed: list[str] = Field(default_factory=list)

    @property
    def noop(self) -> bool:
        return self.version is None


class DatasetSpec(BaseModel):
    """Typed dataset contract for all runtime control-plane operations."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    dataset_id: str
    family: str
    kind: DatasetKind
    target: StorageTarget
    sync_mode: SyncMode = SyncMode.INCREMENTAL
    write_disposition: WriteDisposition = WriteDisposition.MERGE
    resolution: str | None = None
    dataset_type: str | None = None
    product_type: str | None = None
    exchange: str | None = None
    assets: list[str] = Field(default_factory=list)
    columns: list[str] = Field(default_factory=list)
    start_time: str | datetime | None = None
    end_time: str | datetime | None = None
    category: str | None = None
    version: str | None = None
    include_levels: bool | None = None
    description: str | None = None
    db_root: Path | None = None
    layout: TableLayout | None = None
    options: dict[str, Any] = Field(default_factory=dict)

    @field_validator("dataset_id", "family")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("assets")
    @classmethod
    def _normalize_assets(cls, value: list[str]) -> list[str]:
        return sorted({item.strip().upper() for item in value if item.strip()})

    def resolved_db_root(self) -> Path:
        return resolve_db_root(self.db_root)


# A partial result is a failed result: wrappers exit non-zero only on "error", and the
# refresh log stamps any zero exit as fresh, so partial runs must never look successful.
SUCCESS_STATUSES = frozenset({"success", "noop"})
PARTIAL_STATUSES = frozenset({"partial"})


class IngestResult(BaseModel):
    """Stable machine-readable result envelope for dataset operations.

    Validation normalizes partial outcomes to ``status="error"``: a ``partial`` status
    or a success/noop that carries errors. Families report per-item failures that
    should fail the run in ``errors``; ``warnings`` never change the status.
    """

    model_config = ConfigDict(extra="forbid")

    status: str
    operation: str
    dataset_id: str
    family: str
    kind: DatasetKind
    target: StorageTarget
    batch_id: str
    written_artifacts: list[str] = Field(default_factory=list)
    row_counts: dict[str, int] = Field(default_factory=dict)
    checks_passed: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    table_commit: TableCommit | None = None

    @model_validator(mode="after")
    def _partial_is_error(self) -> IngestResult:
        reason: str | None = None
        if self.status in PARTIAL_STATUSES:
            reason = f"partial result: status {self.status}"
        elif self.status in SUCCESS_STATUSES and self.errors:
            reason = f"partial result: {self.status} reported with {len(self.errors)} error(s)"
        if reason is not None:
            self.metadata = {**self.metadata, "reported_status": self.status}
            self.errors = [*self.errors, reason]
            self.status = "error"
        return self

    @property
    def success(self) -> bool:
        return self.status in SUCCESS_STATUSES and not self.errors


__all__ = [
    "DatasetKind",
    "DatasetSpec",
    "IngestResult",
    "StorageTarget",
    "SyncMode",
    "TableCommit",
    "TableLayout",
    "WriteDisposition",
]
