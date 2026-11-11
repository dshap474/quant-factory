"""Shared dataset handler registry and control-plane protocol."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from data.platform.contracts import DatasetSpec, IngestResult
from data.platform.errors import DatasetContractError


class DatasetHandler(Protocol):
    family: str

    def validate_spec(self, spec: DatasetSpec) -> None: ...
    def ingest(self, spec: DatasetSpec) -> IngestResult: ...
    def sync(self, spec: DatasetSpec) -> IngestResult: ...
    def materialize(self, spec: DatasetSpec) -> IngestResult: ...
    def validate(self, spec: DatasetSpec, *, mode: str) -> IngestResult: ...
    def status(self, spec: DatasetSpec) -> IngestResult: ...
    def reconcile(self, spec: DatasetSpec) -> IngestResult: ...


class DatasetHandlerRegistry:
    _registry: dict[str, DatasetHandler] = {}

    @classmethod
    def register(cls, family: str) -> Callable[[type[DatasetHandler]], type[DatasetHandler]]:
        def decorator(handler_cls: type[DatasetHandler]) -> type[DatasetHandler]:
            existing = cls._registry.get(family)
            if existing is not None:
                existing_type = type(existing)
                if (
                    existing_type.__module__,
                    existing_type.__qualname__,
                ) == (handler_cls.__module__, handler_cls.__qualname__):
                    return handler_cls
                raise DatasetContractError(
                    f"Dataset family '{family}' is already registered",
                    family=family,
                    existing=f"{existing_type.__module__}.{existing_type.__qualname__}",
                    duplicate=f"{handler_cls.__module__}.{handler_cls.__qualname__}",
                )
            handler = handler_cls()
            cls._registry[family] = handler
            return handler_cls

        return decorator

    @classmethod
    def get(cls, family: str) -> DatasetHandler:
        try:
            return cls._registry[family]
        except KeyError as exc:
            raise DatasetContractError(
                f"Unknown dataset family '{family}'",
                family=family,
                available=sorted(cls._registry.keys()),
            ) from exc

    @classmethod
    def list(cls) -> list[str]:
        return sorted(cls._registry.keys())


__all__ = ["DatasetHandler", "DatasetHandlerRegistry"]
