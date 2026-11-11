"""Unit-level fixtures for API/CLI command tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from data.api import IngestResult
from data.api.contracts import DatasetKind, StorageTarget


@pytest.fixture
def sample_ingest_result(tmp_path: Path) -> IngestResult:
    """Canonical ingest result used by dataset API/CLI tests."""
    return IngestResult(
        status="success",
        operation="sync",
        dataset_id="example.market.sync",
        family="example_raw",
        kind=DatasetKind.DATA_RAW,
        target=StorageTarget.CANONICAL_DATA_RAW,
        batch_id="20240101-000000",
        written_artifacts=[str(tmp_path / "example_market.parquet")],
        row_counts={"rows": 42},
        checks_passed=["canonical-write"],
    )
