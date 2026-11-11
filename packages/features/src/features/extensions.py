"""Mount and load the optional Features extension overlay.

USAGE: ``bootstrap_feature_extensions(PUBLISHABLE_FAMILIES)`` mounts installed
family sources and populates the public catalog without requiring an overlay.
"""

from __future__ import annotations

import sys
from collections.abc import MutableMapping
from dataclasses import dataclass
from pathlib import Path

from features.blocks import FeatureBlocks

# --------------------------------------------------------------------------- #
# Extension paths
# --------------------------------------------------------------------------- #

FEATURES_ROOT = Path(__file__).resolve().parents[2]
EXTENSIONS_ROOT = FEATURES_ROOT / "extensions"
FAMILIES_ROOT = EXTENSIONS_ROOT / "lib"


# --------------------------------------------------------------------------- #
# Extension loading
# --------------------------------------------------------------------------- #

class FeatureExtensionError(RuntimeError):
    """Raised when the installed Features extension overlay is invalid."""


@dataclass(frozen=True)
class FeatureFamily:
    """Explicit publishable feature family entry."""

    category: str
    runner_module: str
    runner_class: str
    resolutions: tuple[str, ...] = ("1d",)
    asset_column: bool = False
    description: str = ""
    presets_dir: Path | None = None
    feature_blocks: FeatureBlocks | None = None


def mount_feature_extensions() -> tuple[str, ...]:
    """Append installed family ``src`` roots in deterministic order."""
    mounted: list[str] = []
    if not FAMILIES_ROOT.is_dir():
        return ()

    for family_root in sorted(FAMILIES_ROOT.iterdir()):
        if not family_root.is_dir() or family_root.name.startswith("_"):
            continue
        src_root = family_root / "src"
        if not src_root.is_dir():
            continue
        src_path = str(src_root)
        if src_path in sys.path:
            continue
        sys.path.append(src_path)
        mounted.append(src_path)
    return tuple(mounted)


def bootstrap_feature_extensions(catalog: MutableMapping[str, FeatureFamily]) -> None:
    """Mount extensions and merge every registered family into ``catalog`` idempotently."""
    from features.registry import FeatureRegistry

    mount_feature_extensions()
    for category, meta in FeatureRegistry.catalog().items():
        presets_dir = FeatureRegistry.get_presets_dir(category)
        family = FeatureFamily(
            category=category,
            runner_module=meta["runner_module"],
            runner_class=meta["runner_class"],
            resolutions=tuple(meta["resolutions"]),
            asset_column=meta["asset_column"],
            description=meta["description"],
            presets_dir=presets_dir,
            feature_blocks=meta.get("feature_blocks"),
        )
        existing = catalog.get(category)
        if existing is None:
            catalog[category] = family
        elif existing != family:
            raise FeatureExtensionError(f"Duplicate feature category registration: {category}")


__all__ = [
    "EXTENSIONS_ROOT",
    "FAMILIES_ROOT",
    "FEATURES_ROOT",
    "FeatureExtensionError",
    "FeatureFamily",
    "bootstrap_feature_extensions",
    "mount_feature_extensions",
]
