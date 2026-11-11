"""Unit tests for the public data.api facade."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from data.api import (
    AVAILABLE_AT_COLUMN,
    QUANT_DB_ROOT,
    DatasetKind,
    DatasetSpec,
    StorageTarget,
    get_dataset_status,
    ingest_dataset,
    materialize_dataset,
    reconcile_dataset,
    sync_dataset,
    validate_dataset,
    validate_schema,
)
from data.platform.schema import ValidationResult


def _make_spec() -> DatasetSpec:
    return DatasetSpec(
        dataset_id="example.market.sync",
        family="example_raw",
        kind=DatasetKind.DATA_RAW,
        target=StorageTarget.CANONICAL_DATA_RAW,
        product_type="futures",
        exchange="example_venue",
        resolution="1h",
        start_time="2024-01-01T00:00:00Z",
        end_time="2024-01-02T00:00:00Z",
    )


def test_information_availability_public_imports() -> None:
    from data.api import add_available_at, filter_available_as_of, validate_information_set

    assert AVAILABLE_AT_COLUMN == "available_at"
    assert callable(add_available_at)
    assert callable(filter_available_as_of)
    assert callable(validate_information_set)


def test_validate_schema_delegates_to_validator(tmp_path: Path):
    fake_result = ValidationResult(valid=True)

    with patch("data.api.schema.SchemaValidator") as mock_validator_cls:
        mock_validator = MagicMock()
        mock_validator.validate.return_value = fake_result
        mock_validator_cls.return_value = mock_validator

        result = validate_schema(mode="warn", layer="data/raw", db_root=tmp_path)

    mock_validator_cls.assert_called_once_with(tmp_path)
    mock_validator.validate.assert_called_once_with(mode="warn", layer="data/raw")
    assert result is fake_result


def test_validate_schema_uses_default_db_root_when_none():
    fake_result = ValidationResult(valid=True)

    with patch("data.api.schema.SchemaValidator") as mock_validator_cls:
        mock_validator = MagicMock()
        mock_validator.validate.return_value = fake_result
        mock_validator_cls.return_value = mock_validator

        result = validate_schema()

    mock_validator_cls.assert_called_once_with(QUANT_DB_ROOT)
    mock_validator.validate.assert_called_once_with(mode="warn", layer=None)
    assert result is fake_result


def test_validate_schema_converts_string_db_root(tmp_path: Path):
    fake_result = ValidationResult(valid=True)

    with patch("data.api.schema.SchemaValidator") as mock_validator_cls:
        mock_validator = MagicMock()
        mock_validator.validate.return_value = fake_result
        mock_validator_cls.return_value = mock_validator

        validate_schema(db_root=str(tmp_path))

    mock_validator_cls.assert_called_once_with(tmp_path)


def test_ingest_dataset_dispatches_to_registered_handler(sample_ingest_result):
    spec = _make_spec()
    handler = MagicMock()
    handler.ingest.return_value = sample_ingest_result

    with patch("data.api.dataset.DatasetHandlerRegistry.get", return_value=handler) as mock_get:
        result = ingest_dataset(spec)

    mock_get.assert_called_once_with("example_raw")
    handler.validate_spec.assert_called_once_with(spec)
    handler.ingest.assert_called_once_with(spec)
    assert result is sample_ingest_result


def test_sync_dataset_dispatches_to_registered_handler(sample_ingest_result):
    spec = _make_spec()
    handler = MagicMock()
    handler.sync.return_value = sample_ingest_result

    with patch("data.api.dataset.DatasetHandlerRegistry.get", return_value=handler):
        result = sync_dataset(spec)

    handler.validate_spec.assert_called_once_with(spec)
    handler.sync.assert_called_once_with(spec)
    assert result is sample_ingest_result


def test_materialize_dataset_dispatches_to_registered_handler(sample_ingest_result):
    spec = DatasetSpec(
        dataset_id="example.derived.materialize",
        family="example_derived",
        kind=DatasetKind.DATA_DERIVED,
        target=StorageTarget.CANONICAL_DATA_DERIVED,
        resolution="1d",
    )
    handler = MagicMock()
    handler.materialize.return_value = sample_ingest_result

    with patch("data.api.dataset.DatasetHandlerRegistry.get", return_value=handler):
        result = materialize_dataset(spec)

    handler.validate_spec.assert_called_once_with(spec)
    handler.materialize.assert_called_once_with(spec)
    assert result is sample_ingest_result


def test_validate_dataset_passes_mode(sample_ingest_result):
    spec = _make_spec()
    handler = MagicMock()
    handler.validate.return_value = sample_ingest_result

    with patch("data.api.dataset.DatasetHandlerRegistry.get", return_value=handler):
        result = validate_dataset(spec, mode="strict")

    handler.validate_spec.assert_called_once_with(spec)
    handler.validate.assert_called_once_with(spec, mode="strict")
    assert result is sample_ingest_result


def test_get_dataset_status_dispatches_to_registered_handler(sample_ingest_result):
    spec = _make_spec()
    handler = MagicMock()
    handler.status.return_value = sample_ingest_result

    with patch("data.api.dataset.DatasetHandlerRegistry.get", return_value=handler):
        result = get_dataset_status(spec)

    handler.validate_spec.assert_called_once_with(spec)
    handler.status.assert_called_once_with(spec)
    assert result is sample_ingest_result


def test_reconcile_dataset_dispatches_to_registered_handler(sample_ingest_result):
    spec = _make_spec()
    handler = MagicMock()
    handler.reconcile.return_value = sample_ingest_result

    with patch("data.api.dataset.DatasetHandlerRegistry.get", return_value=handler):
        result = reconcile_dataset(spec)

    handler.validate_spec.assert_called_once_with(spec)
    handler.reconcile.assert_called_once_with(spec)
    assert result is sample_ingest_result


def test_partial_results_are_errors() -> None:
    from data.platform.contracts import DatasetKind, IngestResult, StorageTarget

    base = {
        "operation": "sync",
        "dataset_id": "family.raw.sync",
        "family": "family",
        "kind": DatasetKind.DATA_RAW,
        "target": StorageTarget.CANONICAL_DATA_RAW,
        "batch_id": "batch",
    }
    assert IngestResult(**base, status="success").status == "success"
    assert IngestResult(**base, status="noop", warnings=["provider gap"]).status == "noop"

    partials = [
        IngestResult(**base, status="success", errors=["symbol AAA failed"]),
        IngestResult(**base, status="partial"),
    ]
    for result in partials:
        assert result.status == "error"
        assert not result.success
        assert result.errors[-1].startswith("partial result:")
        assert IngestResult.model_validate(result.model_dump()) == result


def test_sync_dataset_turns_post_construction_partial_into_error(sample_ingest_result):
    sample_ingest_result.status = "success"
    sample_ingest_result.errors.append("asset BBB failed")
    handler = MagicMock()
    handler.sync.return_value = sample_ingest_result
    with patch("data.api.dataset.DatasetHandlerRegistry.get", return_value=handler):
        result = sync_dataset(MagicMock())
    assert result.status == "error"
    assert result.errors == ["asset BBB failed", "partial result: success reported with 1 error(s)"]
