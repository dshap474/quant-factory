"""Shared scalar checks for execution-input preparation.

Purpose: centralize UTC and Decimal boundary conversion used by preparation market-data
and StrategyWeights translation without introducing a validation framework.

USAGE:
    >>> from backtest.preparation.validation import to_decimal  # doctest: +SKIP
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Sequence

from ..errors import BacktestContractError

# --------------------------------------------------------------------------- #
# UTC timestamps
# --------------------------------------------------------------------------- #

UTC = timezone.utc


def require_utc_datetime(value: object, name: str) -> datetime:
    """Return a normalized UTC datetime or raise the public contract error."""
    if not isinstance(value, datetime):
        raise BacktestContractError(f"{name} must be datetime, got {type(value).__name__}")
    if value.tzinfo is None:
        raise BacktestContractError(f"{name} must be timezone-aware UTC")
    offset = value.utcoffset()
    if offset is None or offset != timedelta(0):
        raise BacktestContractError(f"{name} must be UTC (offset zero), got {value.tzinfo!r}")
    return value.astimezone(UTC)


def validate_strictly_increasing_utc(
    values: Sequence[object],
    name: str,
) -> tuple[datetime, ...]:
    """Validate a required, non-empty, strictly increasing UTC sequence."""
    if not values:
        raise BacktestContractError(f"{name} must be non-empty")
    out: list[datetime] = []
    for index, raw in enumerate(values):
        if raw is None:
            raise BacktestContractError(f"{name}[{index}] must not be null")
        timestamp = require_utc_datetime(raw, f"{name}[{index}]")
        if out and timestamp <= out[-1]:
            raise BacktestContractError(
                f"{name} must be strictly increasing; got {out[-1].isoformat()} then {timestamp.isoformat()}"
            )
        out.append(timestamp)
    return tuple(out)


# --------------------------------------------------------------------------- #
# Exact numeric conversion
# --------------------------------------------------------------------------- #


def to_decimal(value: object, name: str) -> Decimal:
    """Convert supported boundary numerics without binary-float artifacts."""
    if value is None:
        raise BacktestContractError(f"{name} must not be null")
    if isinstance(value, bool):
        raise BacktestContractError(f"{name} must be numeric, got bool")
    if isinstance(value, Decimal):
        decimal_value = value
    elif isinstance(value, int):
        decimal_value = Decimal(value)
    elif isinstance(value, float):
        decimal_value = Decimal(str(value))
    elif isinstance(value, str):
        try:
            decimal_value = Decimal(value)
        except InvalidOperation as exc:
            raise BacktestContractError(f"{name} is not a valid decimal: {value!r}") from exc
    else:
        raise BacktestContractError(f"{name} must be numeric, got {type(value).__name__}")
    if not decimal_value.is_finite():
        raise BacktestContractError(f"{name} must be finite, got {decimal_value}")
    return decimal_value
