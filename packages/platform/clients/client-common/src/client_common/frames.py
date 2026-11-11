"""Shared frame normalization helpers for platform clients.

USAGE: from client_common import records_to_frame; records_to_frame([{"a": 1}])
"""

from __future__ import annotations

import csv
import io
from typing import Any

import polars as pl


def _normalize_record(record: Any) -> dict[str, Any]:
    if hasattr(record, "model_dump"):
        return dict(record.model_dump(mode="json"))
    if hasattr(record, "dict"):
        return dict(record.dict())
    return dict(record)


def records_to_frame(records: list[Any]) -> pl.DataFrame:
    if not records:
        return pl.DataFrame()
    return pl.DataFrame([_normalize_record(record) for record in records])


def csv_text_to_frame(text: str) -> pl.DataFrame:
    rows = list(csv.DictReader(io.StringIO(text)))
    return pl.DataFrame(rows) if rows else pl.DataFrame()


def key_value_frame(
    mapping: dict[str, Any],
    *,
    key_column: str = "key",
    value_column: str = "value",
    extra: dict[str, Any] | None = None,
) -> pl.DataFrame:
    rows = []
    for key, value in mapping.items():
        row = {key_column: key, value_column: value}
        if extra:
            row.update(extra)
        rows.append(row)
    return pl.DataFrame(rows) if rows else pl.DataFrame()
