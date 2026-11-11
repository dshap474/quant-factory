"""Identifier and run-id helpers local to the signals package."""

from __future__ import annotations

import re
from datetime import datetime

ID_PATTERN = re.compile(r"^[a-z][a-z0-9_\-]{0,127}$")


def validate_identifier(value: str, label: str) -> None:
    """Validate canonical identifier format."""
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    if not ID_PATTERN.match(value):
        raise ValueError(f"{label} must match {ID_PATTERN.pattern}. Got: {value}")


def generate_run_id() -> str:
    """Generate a unique run ID based on timestamp."""
    now = datetime.now()
    return f"run-{now.strftime('%Y%m%d-%H%M%S')}"
