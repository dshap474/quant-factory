"""Read a family's curated presets without constructing or running producers.

The full panel is not a preset: it is the family config's defaults.

USAGE: ``list_feature_presets("my/category")``.
"""

from __future__ import annotations

from typing import Any

import yaml

# --------------------------------------------------------------------------- #
# Read-only preset discovery
# --------------------------------------------------------------------------- #


def list_feature_presets(category: str) -> list[dict[str, Any]]:
    """Read the curated presets belonging to the explicit family catalog."""
    from features.api import PUBLISHABLE_FAMILIES

    family = PUBLISHABLE_FAMILIES.get(category)
    if family is None or family.presets_dir is None:
        return []
    # A family whose presets mirror the lake keeps them under ``<presets_dir>/<resolution>/``;
    # otherwise its presets sit flat in ``presets_dir``.
    resolution_dirs = [family.presets_dir / res for res in family.resolutions if (family.presets_dir / res).is_dir()]
    paths = [path for folder in resolution_dirs or [family.presets_dir] for path in sorted(folder.glob("*.yaml"))]
    results = []
    for path in paths:
        payload = yaml.safe_load(path.read_text()) or {}
        if not isinstance(payload, dict) or payload.get("category") != category:
            continue
        columns = payload.get("feature_columns")
        if columns is not None and (
            not isinstance(columns, list) or not all(isinstance(column, str) for column in columns)
        ):
            raise ValueError(f"Invalid feature_columns in preset {path.stem}")
        results.append({
            "name": path.stem,
            "description": str(payload.get("description", "")),
            "resolution": path.parent.name if resolution_dirs else str(payload.get("resolution", "1d")),
            "columns": columns,
            "blocks": [key.removeprefix("include_") for key, value in payload.items()
                       if key.startswith("include_") and value is True],
            "parameters": {key: value for key, value in payload.items()
                           if key.startswith("include_") or key == "baseline_windows"},
        })
    return sorted(results, key=lambda item: (item["resolution"], item["name"]))
