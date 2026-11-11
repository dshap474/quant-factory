"""Resolve current and legacy package-relative strategy paths.

USAGE: ``resolve_strategy_path("lib/example-family/presets", STRATEGIES_ROOT)``.
"""

from __future__ import annotations

from pathlib import Path

# --------------------------------------------------------------------------- #
# Package roots
# --------------------------------------------------------------------------- #

STRATEGIES_ROOT = Path(__file__).resolve().parents[2]
EXTENSIONS_ROOT = STRATEGIES_ROOT / "extensions"
IMPLEMENTATION_ROOT = "extensions"
FAMILIES_ROOT_NAME = "lib"
FAMILIES_ROOT = EXTENSIONS_ROOT / FAMILIES_ROOT_NAME
LEGACY_IMPLEMENTATION_ROOT = FAMILIES_ROOT_NAME


# --------------------------------------------------------------------------- #
# Physical path resolution
# --------------------------------------------------------------------------- #

def resolve_strategy_path(
    path: str | Path,
    strategies_root: Path = STRATEGIES_ROOT,
) -> Path:
    """Resolve package-relative metadata; a leading ``lib/`` names the family root."""
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    if candidate.parts and candidate.parts[0] == FAMILIES_ROOT_NAME:
        return strategies_root / IMPLEMENTATION_ROOT / candidate
    return strategies_root / candidate


__all__ = [
    "EXTENSIONS_ROOT",
    "FAMILIES_ROOT",
    "FAMILIES_ROOT_NAME",
    "IMPLEMENTATION_ROOT",
    "LEGACY_IMPLEMENTATION_ROOT",
    "STRATEGIES_ROOT",
    "resolve_strategy_path",
]
