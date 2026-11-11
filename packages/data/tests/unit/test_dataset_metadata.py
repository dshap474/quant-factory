"""Tests for raw and derived dataset metadata emission."""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest
import yaml
from data.platform.storage.dataset_metadata import write_dataset_metadata


def test_write_dataset_metadata_records_schema_and_rows(tmp_path: Path) -> None:
    dataset_root = tmp_path / "data/raw/1d/example/filings"
    dataset_root.mkdir(parents=True)
    table_path = dataset_root / "submission.parquet"
    pl.DataFrame({"cik": ["1"], "value": [2.0]}).write_parquet(table_path)

    meta_path = write_dataset_metadata(
        dataset_root,
        layer="data/raw",
        family="example_filings",
        resolution="1d",
        dataset_id="example.filings.sync",
        kind="table_pack",
        source="sec",
        implementation_path="data.features.example_filings",
        written_paths=[table_path],
        row_counts={"submission": 1},
        description="test metadata",
    )

    payload = yaml.safe_load(meta_path.read_text(encoding="utf-8"))
    assert payload["dataset_id"] == "example.filings.sync"
    assert payload["artifacts"]["parquet_files"] == ["submission.parquet"]
    assert payload["stats"]["row_counts"] == {"submission": 1}
    assert payload["schema"]["tables"]["submission"]["rows"] == 1
    assert payload["schema"]["tables"]["submission"]["columns"][0]["name"] == "cik"


def test_write_dataset_metadata_rewrites_without_mutating_parquet(tmp_path: Path) -> None:
    dataset_root = tmp_path / "data/raw/1d/example/rates"
    dataset_root.mkdir(parents=True)
    table_path = dataset_root / "macro.parquet"
    frame = pl.DataFrame({"series_id": ["DGS10"]})
    frame.write_parquet(table_path)
    before = table_path.read_bytes()

    for description in ("first", "second"):
        write_dataset_metadata(
            dataset_root,
            layer="data/raw",
            family="example_rates",
            resolution="1d",
            dataset_id="example.rates.sync",
            kind="table_pack",
            source="fred",
            implementation_path="data.features.example_rates",
            written_paths=[table_path],
            row_counts={"macro": 1},
            description=description,
        )

    payload = yaml.safe_load((dataset_root / "meta.yaml").read_text(encoding="utf-8"))
    assert payload["description"] == "second"
    assert table_path.read_bytes() == before


@pytest.mark.parametrize("c_extension", [True, False])
def test_metadata_safe_serializer_roundtrip_and_object_rejection(tmp_path: Path, monkeypatch, c_extension) -> None:
    if not c_extension:
        monkeypatch.delattr(yaml, "CSafeDumper", raising=False)
    metadata = {"reconciliation": {"asset.parquet": {"probes": [
        {"start": 1704067200000, "reason": "provider_empty", "fields": ["close_price"],
         "checked_at": "2024-01-01T00:00:00+00:00", "nullable": None, "active": False,
         "quoted_boolean": "yes", "unicode": "é", "infinity": float("inf")}
    ]}}}
    kwargs = dict(layer="data/raw", family="example", resolution="1d", dataset_id="example.sync",
        kind="homogeneous_collection", source="example", implementation_path="example",
        written_paths=[], row_counts={})
    path = write_dataset_metadata(tmp_path, **kwargs, metadata=metadata)
    original = path.read_bytes()
    assert yaml.safe_load(original)["metadata"] == metadata
    with pytest.raises(yaml.representer.RepresenterError):
        write_dataset_metadata(tmp_path, **kwargs, metadata={"object": object()})
    assert path.read_bytes() == original
