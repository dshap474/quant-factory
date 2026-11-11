"""Public schema validation surface."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from data.config.paths import resolve_db_root
from data.platform.schema import (
    SchemaLoader,
    SchemaValidationError,
    SchemaValidator,
    ValidationResult,
)

SchemaValidationMode = Literal["strict", "repair", "warn"]


def validate_schema(
    *,
    mode: SchemaValidationMode = "warn",
    layer: str | None = None,
    db_root: str | Path | None = None,
) -> ValidationResult:
    """Validate parquet datasets against SCHEMA.yaml contracts."""
    validator = SchemaValidator(resolve_db_root(db_root))
    return validator.validate(mode=mode, layer=layer)


def generate_initial_schemas(*, db_root: str | Path | None = None) -> None:
    """Generate master and layer SCHEMA.yaml files from current parquet footprints."""
    validator = SchemaValidator(resolve_db_root(db_root))
    validator.generate_initial_schemas()


__all__ = [
    "SchemaLoader",
    "SchemaValidationError",
    "SchemaValidationMode",
    "SchemaValidator",
    "ValidationResult",
    "generate_initial_schemas",
    "validate_schema",
]
