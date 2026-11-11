"""Data control-plane handler for the credential-free Yahoo Finance example.

USAGE:
    qf-data dataset sync --spec-json '{"dataset_id":"example.prices.sync_1d","family":"example",
        "kind":"data/raw","target":"canonical_data_raw"}'
    qf-data dataset sync --spec-json '{"dataset_id":"example.prices.derived_1d","family":"example",
        "kind":"data/derived","target":"canonical_data_derived"}'
"""

from __future__ import annotations

from data.platform.contracts import DatasetKind, DatasetSpec, IngestResult, StorageTarget, WriteDisposition
from data.platform.errors import DatasetContractError
from data.platform.ingestion.control_plane import DatasetHandlerRegistry
from data.platform.ingestion.raw_service import build_result as _result

from .client import DEFAULT_SYMBOLS, build_raw_prices, derive_prices
from .repo import DERIVED, RAW, RESOLUTION, Surface, read_frame, read_meta, write_frame

# --------------------------------------------------------------------------- #
# Contract
# --------------------------------------------------------------------------- #

FAMILY = "example"
RAW_DATASET_ID = "example.prices.sync_1d"
DERIVED_DATASET_ID = "example.prices.derived_1d"
DATASETS: dict[str, tuple[DatasetKind, StorageTarget, Surface]] = {
    RAW_DATASET_ID: (DatasetKind.DATA_RAW, StorageTarget.CANONICAL_DATA_RAW, RAW),
    DERIVED_DATASET_ID: (DatasetKind.DATA_DERIVED, StorageTarget.CANONICAL_DATA_DERIVED, DERIVED),
}


# --------------------------------------------------------------------------- #
# Handler
# --------------------------------------------------------------------------- #


@DatasetHandlerRegistry.register(FAMILY)
class ExampleDatasetHandler:
    """Raw Yahoo daily bars for BTC and four ETFs, and the derived ``[timestamp, asset, close]`` panel."""

    family = FAMILY

    def validate_spec(self, spec: DatasetSpec) -> None:
        if spec.dataset_id not in DATASETS:
            raise DatasetContractError("Unsupported example dataset_id", dataset_id=spec.dataset_id)
        kind, target, _ = DATASETS[spec.dataset_id]
        if spec.kind != kind or spec.target != target:
            raise DatasetContractError(
                "example dataset kind/target mismatch", expected_kind=kind.value, expected_target=target.value
            )
        if spec.resolution not in {None, RESOLUTION}:
            raise DatasetContractError("example supports only 1d resolution", resolution=spec.resolution)
        if spec.write_disposition not in {WriteDisposition.MERGE, WriteDisposition.OVERWRITE}:
            raise DatasetContractError("example supports merge or overwrite")

    def ingest(self, spec: DatasetSpec) -> IngestResult:
        return self.sync(spec)

    def sync(self, spec: DatasetSpec) -> IngestResult:
        if spec.dataset_id == DERIVED_DATASET_ID:
            return self.materialize(spec)
        symbols = list(spec.assets or DEFAULT_SYMBOLS)
        frame = build_raw_prices(symbols)
        if frame.is_empty():
            return _result(spec, "sync", status="noop", warnings=["Yahoo Finance returned no completed bars"])
        metadata = {
            "layer": "data/raw",
            "family": FAMILY,
            "dataset_id": RAW_DATASET_ID,
            "source": "yahoo_finance",
            "description": "Yahoo Finance daily bars (auto-adjusted), current UTC day excluded",
            "lineage": {"symbols": symbols, "history_mode": "provider_full_history_not_point_in_time"},
        }
        return self._write(spec, "sync", RAW, frame, metadata)

    def materialize(self, spec: DatasetSpec) -> IngestResult:
        if spec.dataset_id != DERIVED_DATASET_ID:
            raise DatasetContractError("example raw datasets do not support materialize")
        raw = read_frame(spec.resolved_db_root(), RAW)
        if raw is None or raw.is_empty():
            return _result(spec, "materialize", status="error", errors=[f"Sync {RAW_DATASET_ID} first"])
        metadata = {
            "layer": "data/derived",
            "family": FAMILY,
            "dataset_id": DERIVED_DATASET_ID,
            "description": "Daily close per canonical asset id (crypto:BTC, us:SPY, ...)",
            "lineage": {"inputs": [RAW_DATASET_ID]},
        }
        return self._write(spec, "materialize", DERIVED, derive_prices(raw), metadata)

    def validate(self, spec: DatasetSpec, *, mode: str) -> IngestResult:
        _, _, surface = DATASETS[spec.dataset_id]
        frame = read_frame(spec.resolved_db_root(), surface)
        errors = []
        if frame is None:
            errors.append(f"{spec.dataset_id} not found")
        elif frame.select(surface.keys).is_duplicated().any():
            errors.append(f"{spec.dataset_id} has duplicate {surface.keys} rows")
        return _result(
            spec,
            "validate",
            status="error" if errors else "success",
            checks=[] if errors else ["exists", "unique-keys"],
            errors=errors,
        )

    def status(self, spec: DatasetSpec) -> IngestResult:
        _, _, surface = DATASETS[spec.dataset_id]
        db_root = spec.resolved_db_root()
        meta = read_meta(db_root, surface) or {}
        written = [path for path in (surface.data_path(db_root), surface.meta_path(db_root)) if path.exists()]
        return _result(
            spec,
            "status",
            status="success" if written else "noop",
            written=written,
            row_counts={"rows": int(meta.get("stats", {}).get("row_count", 0))},
            warnings=[] if written else [f"{spec.dataset_id} not found"],
            metadata=meta,
        )

    def reconcile(self, spec: DatasetSpec) -> IngestResult:
        return self.sync(spec)

    def _write(self, spec: DatasetSpec, operation: str, surface: Surface, frame, metadata: dict) -> IngestResult:
        written, stored_rows = write_frame(
            spec.resolved_db_root(),
            surface,
            frame,
            metadata=metadata,
            overwrite=spec.write_disposition == WriteDisposition.OVERWRITE,
        )
        return _result(
            spec,
            operation,
            status="success",
            written=written,
            row_counts={"rows": stored_rows, "fetched_rows": frame.height},
            metadata=read_meta(spec.resolved_db_root(), surface) or metadata,
        )


# --------------------------------------------------------------------------- #
# Public exports
# --------------------------------------------------------------------------- #

__all__ = ["DERIVED_DATASET_ID", "ExampleDatasetHandler", "FAMILY", "RAW_DATASET_ID"]
