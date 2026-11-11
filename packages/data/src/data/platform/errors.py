"""Stable package-facing errors for the data control plane."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DataPackageError(Exception):
    """Base error with stable machine-readable code and details."""

    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        super().__init__(self.message)


class DatasetContractError(DataPackageError):
    def __init__(self, message: str, **details: Any) -> None:
        super().__init__("dataset_contract_error", message, details)


class CanonicalRoutingError(DataPackageError):
    def __init__(self, message: str, **details: Any) -> None:
        super().__init__("canonical_routing_error", message, details)


class SchemaContractError(DataPackageError):
    def __init__(self, message: str, **details: Any) -> None:
        super().__init__("schema_contract_error", message, details)


class IngestionConflictError(DataPackageError):
    def __init__(self, message: str, **details: Any) -> None:
        super().__init__("ingestion_conflict_error", message, details)


class SourceAdapterError(DataPackageError):
    def __init__(self, message: str, **details: Any) -> None:
        super().__init__("source_adapter_error", message, details)


class ExternalTargetError(DataPackageError):
    def __init__(self, message: str, **details: Any) -> None:
        super().__init__("external_target_error", message, details)


__all__ = [
    "CanonicalRoutingError",
    "DataPackageError",
    "DatasetContractError",
    "ExternalTargetError",
    "IngestionConflictError",
    "SchemaContractError",
    "SourceAdapterError",
]
