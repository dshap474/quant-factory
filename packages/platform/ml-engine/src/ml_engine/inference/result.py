"""Immutable values returned by the standalone inference boundary.

Usage::

    result = pipeline.predict(frame)
    print(result.row_ids, result.predictions)

The result contains only in-memory prediction data.  It intentionally exposes
no persistence or registry operations.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------- #
# Public result value
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class PredictionResult:
    """Row-aligned predictions and the metadata of the loaded artifact.

    ``predictions`` and ``row_ids`` are copied on construction so callers
    cannot mutate arrays owned by the inference pipeline.  ``base_predictions``
    is a copied dataframe when requested by :meth:`InferencePipeline.predict`.
    """

    predictions: np.ndarray
    row_ids: np.ndarray
    timestamps: np.ndarray | None = None
    entities: np.ndarray | None = None
    base_predictions: pd.DataFrame | None = None
    metadata: Mapping[str, Any] = MappingProxyType({})

    # ------------------------------------------------------------------ #
    # Value validation and defensive copies
    # ------------------------------------------------------------------ #

    def __post_init__(self) -> None:
        final = np.asarray(self.predictions).copy()
        row_ids = np.asarray(self.row_ids).copy()
        if final.ndim != 1:
            raise ValueError("predictions must be one-dimensional")
        if row_ids.ndim != 1:
            raise ValueError("row_ids must be one-dimensional")
        if len(final) != len(row_ids):
            raise ValueError("predictions and row_ids must have equal length")

        final.setflags(write=False)
        row_ids.setflags(write=False)
        object.__setattr__(self, "predictions", final)
        object.__setattr__(self, "row_ids", row_ids)
        for name in ("timestamps", "entities"):
            value = getattr(self, name)
            if value is None:
                continue
            copied = np.asarray(value).copy()
            if copied.ndim != 1 or len(copied) != len(row_ids):
                raise ValueError(f"{name} must be one-dimensional and row-aligned")
            copied.setflags(write=False)
            object.__setattr__(self, name, copied)

        if self.base_predictions is not None:
            base = self.base_predictions.copy(deep=True)
            if len(base) != len(row_ids):
                raise ValueError("base_predictions must be row-aligned")
            object.__setattr__(self, "base_predictions", base)
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    # ------------------------------------------------------------------ #
    # Convenience metadata
    # ------------------------------------------------------------------ #

    @property
    def n_rows(self) -> int:
        """Return the number of predictions."""

        return len(self.predictions)

    @property
    def artifact_schema_version(self) -> Any:
        """Return the artifact schema version recorded by the artifact."""

        return self.metadata.get("artifact_schema_version")


__all__ = ["PredictionResult"]
