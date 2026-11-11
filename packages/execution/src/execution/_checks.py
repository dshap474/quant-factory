"""Shared validation primitives for engine-neutral execution contracts.

Purpose: centralize UTC, Decimal, and identity checks used by immutable DTOs
and pure planning/accounting functions.

USAGE:
    >>> from datetime import datetime, timezone
    >>> from decimal import Decimal
    >>> from execution._checks import require_utc, require_finite_decimal
    >>> require_utc(datetime(2024, 1, 1, tzinfo=timezone.utc), "decision_at")
    >>> require_finite_decimal(Decimal("1.5"), "price", positive=True)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Iterable

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

WEIGHT_SUM_TOLERANCE = Decimal("0.000001")
UTC = timezone.utc

# --------------------------------------------------------------------------- #
# Timestamp checks
# --------------------------------------------------------------------------- #


def require_utc(value: datetime, name: str) -> None:
    """Reject naive or non-UTC timestamps."""
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be datetime, got {type(value).__name__}")
    if value.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware UTC")
    offset = value.utcoffset()
    if offset is None or offset != timedelta(0):
        raise ValueError(f"{name} must be UTC (offset zero), got {value.tzinfo!r}")


# --------------------------------------------------------------------------- #
# Decimal checks
# --------------------------------------------------------------------------- #


def require_decimal(value: object, name: str) -> Decimal:
    """Coerce ints to Decimal; reject floats and non-finite values."""
    if isinstance(value, float):
        raise TypeError(f"{name} must be Decimal (float is forbidden)")
    if isinstance(value, int) and not isinstance(value, bool):
        value = Decimal(value)
    if not isinstance(value, Decimal):
        raise TypeError(f"{name} must be Decimal, got {type(value).__name__}")
    if not value.is_finite():
        raise ValueError(f"{name} must be finite Decimal, got {value}")
    return value


def require_finite_decimal(
    value: object,
    name: str,
    *,
    positive: bool = False,
    non_negative: bool = False,
    non_zero: bool = False,
) -> Decimal:
    """Validate a finite Decimal with optional sign constraints."""
    decimal_value = require_decimal(value, name)
    if positive and decimal_value <= 0:
        raise ValueError(f"{name} must be positive, got {decimal_value}")
    if non_negative and decimal_value < 0:
        raise ValueError(f"{name} must be non-negative, got {decimal_value}")
    if non_zero and decimal_value == 0:
        raise ValueError(f"{name} must be non-zero")
    return decimal_value


def require_non_empty_str(value: object, name: str) -> str:
    """Require a non-empty stripped string identity."""
    if not isinstance(value, str):
        raise TypeError(f"{name} must be str, got {type(value).__name__}")
    if not value or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


# --------------------------------------------------------------------------- #
# Collection uniqueness
# --------------------------------------------------------------------------- #


def require_unique_ids(ids: Iterable[str], name: str) -> None:
    """Reject duplicate string identifiers."""
    seen: set[str] = set()
    for item in ids:
        if item in seen:
            raise ValueError(f"duplicate {name}: {item!r}")
        seen.add(item)
