"""Naming helpers for canonical signal families and presets."""

from __future__ import annotations

import re

VALID_SIGNAL_TOKEN = r"[a-z0-9]+(?:-[a-z0-9]+)*"
# Optional asset-class prefix joined by one underscore, as in strategies: ``equities_index-trend``.
ASSET_CLASS_PREFIX = rf"(?:{VALID_SIGNAL_TOKEN}_)?"
SIGNAL_TYPE_RE = re.compile(rf"^{ASSET_CLASS_PREFIX}{VALID_SIGNAL_TOKEN}$")
PRESET_NAME_RE = re.compile(rf"^(default|{ASSET_CLASS_PREFIX}{VALID_SIGNAL_TOKEN})$")


def is_valid_signal_type_name(value: str) -> bool:
    """Return whether ``value`` is a canonical signal family name."""
    return bool(SIGNAL_TYPE_RE.fullmatch(value))


def validate_signal_type_name(value: str) -> None:
    """Validate canonical signal family naming."""
    if not is_valid_signal_type_name(value):
        raise ValueError(
            "signal_type must be lowercase kebab-case, optionally prefixed '<asset-class>_', and "
            "should encode scope + semantic meaning, for example 'equities_index-trend'"
        )


def is_valid_preset_name(value: str) -> bool:
    """Return whether ``value`` is a canonical preset name."""
    return bool(PRESET_NAME_RE.fullmatch(value))


def validate_preset_name(value: str) -> None:
    """Validate canonical preset naming."""
    if not is_valid_preset_name(value):
        raise ValueError(
            "preset name must be 'default' or lowercase kebab-case, optionally prefixed '<asset-class>_'"
        )


def naming_guidance(signal_type: str) -> str | None:
    """Return a human-readable warning when a signal family name is off-contract."""
    if is_valid_signal_type_name(signal_type):
        return None
    return (
        "Naming warning: signal name should be lowercase kebab-case, optionally prefixed "
        "'<asset-class>_', and encode scope first, "
        "then predictive meaning, for example 'trend-score', 'momentum-rank', or "
        "'equities_index-trend'."
    )
