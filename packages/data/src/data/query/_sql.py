"""Shared SQL construction helpers for bounded DuckDB parquet reads."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import polars as pl

from .errors import QueryValidationError
from .models import DatasetScope, ParquetCollectionQuery, ParquetQuery

SUPPORTED_SCOPES: tuple[DatasetScope, ...] = (
    "data",
    "features",
    "research",
    "signals",
    "strategies",
)
NUMERIC_DTYPES = {
    pl.Float64,
    pl.Float32,
    pl.Int64,
    pl.Int32,
    pl.Int16,
    pl.Int8,
    pl.UInt64,
    pl.UInt32,
    pl.UInt16,
    pl.UInt8,
}


def validate_scope(scope: DatasetScope) -> None:
    """Reject unknown lake scopes before path resolution."""
    if scope not in SUPPORTED_SCOPES:
        raise QueryValidationError(f"Unsupported dataset scope: {scope}")


def duckdb_where(
    query: ParquetQuery | ParquetCollectionQuery,
    typed_schema: dict[str, pl.DataType],
) -> tuple[str, list[Any]]:
    """Build a safe WHERE clause for shared temporal and entity filters."""
    clauses: list[str] = []
    params: list[Any] = []
    if query.start is not None:
        clauses.append(f"{quote_ident(query.time_column)} >= ?")
        params.append(temporal_bound(query.start, query.time_column, typed_schema, is_end=False))
    if query.end is not None:
        clauses.append(f"{quote_ident(query.time_column)} <= ?")
        params.append(temporal_bound(query.end, query.time_column, typed_schema, is_end=True))
    if query.entity_values:
        placeholders = ", ".join("?" for _ in query.entity_values)
        clauses.append(f"CAST({quote_ident(query.entity_column)} AS VARCHAR) IN ({placeholders})")
        params.extend(query.entity_values)
    if not clauses:
        return "", params
    return " WHERE " + " AND ".join(clauses), params


def limit_offset_sql(*, limit: int | None, offset: int) -> str:
    """Build LIMIT/OFFSET SQL after validation."""
    sql = ""
    if limit is not None:
        sql += f" LIMIT {int(limit)}"
    if offset:
        sql += f" OFFSET {int(offset)}"
    return sql


def quote_ident(name: str | None) -> str:
    """Quote a DuckDB identifier."""
    if name is None:
        raise QueryValidationError("Missing SQL identifier")
    return '"' + name.replace('"', '""') + '"'


def quote_literal(value: str) -> str:
    """Quote a DuckDB string literal."""
    return "'" + value.replace("'", "''") + "'"


def temporal_bound(
    value: str | date | datetime,
    column: str,
    typed_schema: dict[str, pl.DataType],
    *,
    is_end: bool,
) -> str | date | datetime:
    """A start/end bound normalized to the column's type and time zone (both engines use it)."""
    dtype = typed_schema[column]
    if isinstance(dtype, pl.Datetime):
        return _datetime_bound(value, dtype, is_end=is_end)
    if isinstance(dtype, pl.Date):
        return _date_bound(value)
    if isinstance(dtype, pl.String):
        return _string_temporal_bound(value, is_end=is_end)
    raise QueryValidationError(f"Column {column} has unsupported dtype for temporal filtering: {dtype}")


def _datetime_bound(value: str | date | datetime, dtype: pl.Datetime, *, is_end: bool) -> datetime:
    parsed = _parse_iso_temporal(value)
    if isinstance(parsed, datetime):
        bound = parsed
    elif is_end:
        bound = datetime.combine(parsed, time.max)
    else:
        bound = datetime.combine(parsed, time.min)

    if dtype.time_zone is None and bound.tzinfo is not None:
        return bound.astimezone(timezone.utc).replace(tzinfo=None)
    if dtype.time_zone is not None and bound.tzinfo is None:
        try:
            return bound.replace(tzinfo=ZoneInfo(dtype.time_zone))
        except ZoneInfoNotFoundError:
            return bound
    return bound


def _date_bound(value: str | date | datetime) -> date:
    parsed = _parse_iso_temporal(value)
    if isinstance(parsed, datetime):
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc)
        return parsed.date()
    return parsed


def _string_temporal_bound(value: str | date | datetime, *, is_end: bool) -> str:
    parsed = _parse_iso_temporal(value)
    if isinstance(parsed, datetime):
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        if parsed.time() == time.min:
            if is_end:
                return datetime.combine(parsed.date(), time.max).isoformat()
            return parsed.date().isoformat()
        return parsed.isoformat()
    if is_end:
        return datetime.combine(parsed, time.max).isoformat()
    return parsed.isoformat()


def _parse_iso_temporal(value: str | date | datetime) -> date | datetime:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value

    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    if len(normalized) == 10 and normalized[4] == "-" and normalized[7] == "-":
        try:
            return date.fromisoformat(normalized)
        except ValueError as exc:
            raise QueryValidationError(f"Invalid temporal bound: {value}") from exc
    try:
        return datetime.fromisoformat(normalized)
    except ValueError as exc:
        try:
            return date.fromisoformat(normalized)
        except ValueError:
            raise QueryValidationError(f"Invalid temporal bound: {value}") from exc
