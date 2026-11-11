"""Runtime registry for publishable feature families.

Each family registers its runner where it lives, under the published category name.
``Runner.from_preset()`` with no name builds the family's full panel from its config
defaults; a named preset (``presets_dir``) is an optional curated subset.
One runner may serve several categories (one decorator per category).

USAGE:
    @FeatureRegistry.register(
        "example/daily",
        presets_dir="extensions/lib/example/presets",
        asset_column=True,
        description="Example daily feature panel",
    )
    class ExampleRunner: ...

    FeatureRegistry.catalog()   # {category: metadata}; imports every family runner once
"""

from __future__ import annotations

from pathlib import Path

from family_registry import FamilyRegistry

FEATURES_ROOT = Path(__file__).resolve().parents[2]

# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #


class FeatureRegistry(FamilyRegistry):
    """Registry of feature-family runners mounted as bare ``<package>.runner`` modules."""

    label = "Feature family"
    package_root = FEATURES_ROOT
    defaults = {"resolutions": ("1d",), "asset_column": False}


__all__ = ["FEATURES_ROOT", "FeatureRegistry"]
