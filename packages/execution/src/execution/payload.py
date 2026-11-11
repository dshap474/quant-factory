"""Fail-closed readers for untyped venue payloads.

Purpose: one place where venue plug-ins turn provider JSON and SDK objects into
typed values. Every reader names the field it rejects, so a
malformed payload fails with a precise ``ValueError`` instead of a silent
default. Venue-specific shapes (amounts, product facts) stay in the venue.

USAGE:
    from execution.payload import attr, decimal, mapping, sequence

    row = mapping(response, "order")
    filled = decimal(row.get("filled_size"), "order.filled_size", non_negative=True)
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from typing import Any, cast

from execution._checks import require_finite_decimal

# --------------------------------------------------------------------------- #
# Containers
# --------------------------------------------------------------------------- #


def plain(value: object) -> object:
    """Return ``value.to_dict()`` for SDK response objects, else ``value`` unchanged."""
    to_dict = getattr(value, "to_dict", None)
    return to_dict() if callable(to_dict) else value


def attr(obj: Any, name: str, default: Any = None) -> Any:
    """Read ``name`` from a mapping key or an object attribute."""
    if obj is None:
        return default
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def mapping(value: object, name: str) -> Mapping[str, Any]:
    """Require a mapping (SDK objects are converted through ``to_dict``)."""
    value = plain(value)
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return cast(Mapping[str, Any], value)


def sequence(value: object, name: str) -> Sequence[Any]:
    """Require a non-string sequence (SDK objects are converted through ``to_dict``)."""
    value = plain(value)
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{name} must be a sequence")
    return value


# --------------------------------------------------------------------------- #
# Numbers
# --------------------------------------------------------------------------- #


def decimal(
    value: object,
    name: str,
    *,
    default: str | None = None,
    positive: bool = False,
    non_negative: bool = False,
) -> Decimal:
    """Parse one finite Decimal; ``default`` applies only to ``None`` or ``""``."""
    if default is not None and (value is None or value == ""):
        value = default
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be Decimal-compatible, got {value!r}") from exc
    if not parsed.is_finite():
        raise ValueError(f"{name} must be finite, got {value!r}")
    return require_finite_decimal(parsed, name, positive=positive, non_negative=non_negative)


def integer(value: object, name: str) -> int:
    """Parse one exact whole number (``"2"`` or ``"2.0"``, never ``"2.5"``)."""
    parsed = decimal(value, name)
    if parsed != parsed.to_integral_value():
        raise ValueError(f"{name} must be a whole number, got {value!r}")
    return int(parsed)


__all__ = ["attr", "decimal", "integer", "mapping", "plain", "sequence"]
