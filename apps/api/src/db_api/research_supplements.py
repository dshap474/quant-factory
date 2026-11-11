"""Registry of research-surface supplements keyed by a manifest provenance label.

A supplement is an extra, run-local display artifact a research manifest declares in its
``provenance`` list (``{"label": ..., "path": ...}``). An installed extension registers a loader
for a label; the surface route calls it only when the selected manifest declares that label and
returns its JSON under ``supplements[label]``. The core registers none.

Loaders that return a variant matrix use this shape; the Viz renders the first such matrix::

    {"run_id": str, "title": str, "variants": [{"id", "label", "metrics", "data": [{"date",
     "daily_return", "portfolio_value"}], "gross_return"?, "gross_sharpe"?}]}

USAGE:
    register_surface_supplement(app, "my_matrix", my_matrix_loader)  # in an extension
    supplements = load_surface_supplements(app, db_root, manifest, frame, sampled_dates)
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports
# --------------------------------------------------------------------------- #
from collections.abc import Callable
from pathlib import Path
from typing import Any

import polars as pl
from fastapi import FastAPI

# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #

SurfaceSupplementLoader = Callable[[Path, dict, pl.DataFrame, list], dict | None]
"""``(db_root, manifest, full performance frame, sampled display dates)`` -> JSON-ready dict or None.

Raise ``KeyError``/``OSError``/``TypeError``/``ValueError`` when the declared artifact is invalid.
"""


def register_surface_supplement(app: FastAPI, label: str, loader: SurfaceSupplementLoader) -> None:
    """Load ``label`` supplements with ``loader`` on one application."""
    current = registered_surface_supplements(app)
    if not label or label in current:
        raise ValueError(f"Invalid or duplicate surface supplement label: {label!r}")
    app.state.surface_supplements = {**current, label: loader}


def registered_surface_supplements(app: FastAPI) -> dict[str, SurfaceSupplementLoader]:
    """Return the application's supplement loaders; none by default."""
    return getattr(app.state, "surface_supplements", {})


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #


def load_surface_supplements(
    app: FastAPI, db_root: Path, manifest: dict, frame: pl.DataFrame, sampled_dates: list
) -> dict[str, Any]:
    """Run every registered loader whose label the manifest declares; omit labels that return None."""
    declared = {item.get("label") for item in manifest.get("provenance", []) if isinstance(item, dict)}
    supplements: dict[str, Any] = {}
    for label, loader in registered_surface_supplements(app).items():
        if label in declared and (value := loader(db_root, manifest, frame, sampled_dates)) is not None:
            supplements[label] = value
    return supplements
