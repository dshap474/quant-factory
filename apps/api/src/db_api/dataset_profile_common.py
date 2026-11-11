"""Shared helpers for generic parquet feature profile endpoints."""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import polars as pl
from features.api import FeaturesApiError, family_feature_blocks

FAMILY_LABELS = {
    "ta": "TA",
    "carry_funding": "Carry / funding",
    "open_interest": "Open interest",
    "liquidations": "Liquidations",
    "flow_liquidity": "Flow / liquidity",
    "supply_mcap": "Supply / mcap",
    "coverage_quality": "Coverage / quality",
    "price_volatility": "Price / volatility",
    "other": "Other",
}


def infer_family(column: str) -> str:
    lowered = column.lower()
    if lowered.startswith("ta_"):
        return "ta"
    if any(token in lowered for token in ("funding", "premium", "basis", "carry")):
        return "carry_funding"
    if "open_interest" in lowered or "oi_" in lowered:
        return "open_interest"
    if "liquidation" in lowered:
        return "liquidations"
    if any(token in lowered for token in ("volume", "turnover", "liquidity", "trade", "flow")):
        return "flow_liquidity"
    if any(token in lowered for token in ("mcap", "market_cap", "supply", "fdv")):
        return "supply_mcap"
    if any(token in lowered for token in ("venue", "source_count", "coverage", "availability", "confidence", "missing")):
        return "coverage_quality"
    if any(token in lowered for token in ("ret", "return", "price", "open", "high", "low", "close", "vwap", "range", "volatility")):
        return "price_volatility"
    return "other"


@dataclass(frozen=True)
class ColumnBlocks:
    """Which block each column belongs to, with the blocks' labels in display order."""

    labels: dict[str, str]
    lookup: Callable[[str], str | None]

    def of(self, column: str) -> str:
        return self.lookup(column) or "other"

    def label(self, column: str) -> str:
        block = self.of(column)
        return self.labels.get(block, FAMILY_LABELS.get(block, block))

    def counts(self, columns: Iterable[str]) -> list[dict[str, Any]]:
        """``{id, label, count}`` per block present in ``columns``, in display order."""
        counts: dict[str, int] = {}
        for column in columns:
            block = self.of(column)
            counts[block] = counts.get(block, 0) + 1
        order = [*self.labels, *(block for block in counts if block not in self.labels)]
        return [
            {"id": block, "label": self.labels.get(block, FAMILY_LABELS.get(block, block)), "count": counts[block]}
            for block in order
            if counts.get(block)
        ]


NAME_BLOCKS = ColumnBlocks(FAMILY_LABELS, infer_family)


def column_blocks(scope: str, path: str) -> ColumnBlocks:
    """The feature family's declared blocks for a published panel; name rules for anything else."""
    if scope != "features":
        return NAME_BLOCKS
    # ``<resolution>/<category...>/data.parquet``; a variant panel sits one folder below its family.
    parts = Path(path).parts[1:-1]
    for end in range(len(parts), 0, -1):
        try:
            declared = family_feature_blocks("/".join(parts[:end]))
        except FeaturesApiError:
            continue
        if declared is not None:
            return ColumnBlocks(dict(declared.labels), declared.block)
        break
    return NAME_BLOCKS


ENTITY_COLUMN_PRIORITY = (
    "asset",
    "symbol",
    "ticker",
    "instrument",
    "pair",
    "coin",
    "market",
    "id",
)


def is_entity_column(name: str, distinct_values: int) -> bool:
    """Whether a string column is an entity axis the operator can filter on.

    A varying string column is an entity axis on its own evidence. A column that
    is pinned to one value still is one when its name is a known entity key: a
    single-name panel has one asset by construction, and its `asset` column is
    the same axis the broad panel exposes, not a constant label.
    """
    if distinct_values > 1:
        return True
    return distinct_values == 1 and name.lower() in ENTITY_COLUMN_PRIORITY


def prioritize_columns(columns: list[str], priority: tuple[str, ...]) -> list[str]:
    priority_index = {name: index for index, name in enumerate(priority)}
    return sorted(columns, key=lambda name: (priority_index.get(name, len(priority)), name))


def is_numeric_dtype(dtype: pl.DataType) -> bool:
    # An all-null column has no parquet value type; profile it as an empty numeric feature.
    if dtype == pl.Null:
        return True
    if hasattr(dtype, "is_numeric") and dtype.is_numeric():
        return True
    return any(token in str(dtype) for token in ("Int", "UInt", "Float", "Decimal"))


def is_string_like(dtype: pl.DataType) -> bool:
    return dtype == pl.String or str(dtype) in {"Utf8", "String"}


def safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return result


def format_x(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)
