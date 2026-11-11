"""DuckDB aggregations behind the feature profile endpoints.

The profile pages aggregate inside the parquet scan and return only the numbers
they display, so a page of ten columns never materializes the full panel as a
frame. Sparklines aggregate only the sampled x values they plot.

USAGE:
    total_rows, stats = summary_stats(target, ["close"], x_column="timestamp", equals=None)
    sparks = sampled_sparklines(target, ["close"], x_column="timestamp", equals=None, max_points=36)
"""

from __future__ import annotations

import math
from contextlib import AbstractContextManager
from functools import lru_cache
from pathlib import Path
from typing import Any

import duckdb

from .dataset_profile_common import format_x, safe_float
from .duck import cursor
from .parquet import _quote_ident, _quote_literal, fingerprint, source_sql

# --------------------------------------------------------------------------- #
# Scan helpers
# --------------------------------------------------------------------------- #


def _connect(target: Path) -> AbstractContextManager[duckdb.DuckDBPyConnection]:
    """A cursor on the API's shared DuckDB connection (UTC), with ``delta`` loaded for Delta tables."""
    return cursor(delta=source_sql(target)[1])


def _scan(target: Path, equals: tuple[str, str] | None, condition: str | None = None) -> tuple[str, list[Any]]:
    """FROM/WHERE clause for the parquet scan, with the optional entity filter.

    ``condition`` is ANDed after the entity filter, so its placeholders bind
    after the entity value.
    """
    conditions: list[str] = []
    params: list[Any] = []
    if equals is not None:
        conditions.append(f"CAST({_quote_ident(equals[0])} AS VARCHAR) = ?")
        params.append(equals[1])
    if condition is not None:
        conditions.append(condition)
    where_sql = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    return f"FROM {source_sql(target)[0]}{where_sql}", params


def _fingerprint(target: Path) -> tuple[str, int, int]:
    return str(target), *fingerprint(target)


# --------------------------------------------------------------------------- #
# Summary statistics
# --------------------------------------------------------------------------- #


def summary_stats(
    target: Path,
    columns: list[str],
    *,
    x_column: str | None,
    equals: tuple[str, str] | None,
    quantiles: bool = False,
) -> tuple[int, dict[str, dict[str, Any]]]:
    """Row count and per-column summary statistics in one scan.

    Quantiles need a sort per column, so list pages omit them (null) and only
    the single-column detail view asks for them.
    """
    return _summary_stats_cached(_fingerprint(target), tuple(columns), x_column, equals, quantiles)


@lru_cache(maxsize=64)
def _summary_stats_cached(
    fingerprint: tuple[str, int, int],
    columns: tuple[str, ...],
    x_column: str | None,
    equals: tuple[str, str] | None,
    quantiles: bool,
) -> tuple[int, dict[str, dict[str, Any]]]:
    target = Path(fingerprint[0])
    exprs = ["count(*)"]
    for column in columns:
        col = _quote_ident(column)
        # Non-finite source values must not make the inspector's STDDEV throw.
        # Value statistics use finite observations; coverage still counts non-nulls.
        finite = f"CASE WHEN isfinite(CAST({col} AS DOUBLE)) THEN {col} END"
        exprs.extend([f"count({col})", f"avg({finite})", f"stddev_samp({finite})", f"min({finite})", f"max({finite})"])
        if quantiles:
            # One list quantile sorts the column once for all three cut points.
            exprs.append(f"quantile_disc({finite}, [0.25, 0.5, 0.75])")
        if x_column is not None and x_column != column:
            x = _quote_ident(x_column)
            exprs.extend(
                [
                    f"min(CASE WHEN {col} IS NOT NULL THEN {x} END)",
                    f"max(CASE WHEN {col} IS NOT NULL THEN {x} END)",
                ]
            )
    scan_sql, params = _scan(target, equals)
    with _connect(target) as conn:
        row = conn.execute(f"SELECT {', '.join(exprs)} {scan_sql}", params).fetchone()

    total_rows = int(row[0] or 0)
    values = iter(row[1:])
    result: dict[str, dict[str, Any]] = {}
    for column in columns:
        non_null, mean, std, min_value, max_value = (next(values) for _ in range(5))
        p25, p50, p75 = (next(values) or (None, None, None)) if quantiles else (None, None, None)
        first_value, last_value = (
            (next(values), next(values)) if x_column is not None and x_column != column else (None, None)
        )
        non_null = int(non_null or 0)
        result[column] = {
            "non_null_count": non_null,
            "null_count": total_rows - non_null,
            "coverage": (non_null / total_rows) if total_rows else 0.0,
            "first_non_null": format_x(first_value) if first_value is not None else None,
            "last_non_null": format_x(last_value) if last_value is not None else None,
            "mean": safe_float(mean),
            "std": safe_float(std),
            "min": safe_float(min_value),
            "p25": safe_float(p25),
            "p50": safe_float(p50),
            "p75": safe_float(p75),
            "max": safe_float(max_value),
        }
    return total_rows, result


def metadata_null_counts(target: Path, columns: list[str]) -> tuple[int, dict[str, int]] | None:
    """Row count and per-column null counts from parquet footers, without a scan.

    Returns None when any requested column lacks row-group null statistics, or for a Delta table
    or a folder of files.
    """
    if source_sql(target)[1] or target.is_dir():
        return None
    with _connect(target) as conn:
        rows = conn.execute(
            "SELECT path_in_schema, count(*), count(stats_null_count), sum(stats_null_count) "
            f"FROM parquet_metadata({_quote_literal(str(target))}) GROUP BY 1",
        ).fetchall()
        total_rows = conn.execute(
            f"SELECT sum(num_rows) FROM parquet_file_metadata({_quote_literal(str(target))})"
        ).fetchone()[0]
    by_column = {name: (groups, with_stats, nulls) for name, groups, with_stats, nulls in rows}
    null_counts: dict[str, int] = {}
    for column in columns:
        groups, with_stats, nulls = by_column.get(column, (0, 0, None))
        if not groups or with_stats != groups:
            return None
        null_counts[column] = int(nulls or 0)
    return int(total_rows or 0), null_counts


# --------------------------------------------------------------------------- #
# Sparklines
# --------------------------------------------------------------------------- #


def _sampled_x_values(
    conn: duckdb.DuckDBPyConnection,
    target: Path,
    *,
    x_column: str,
    equals: tuple[str, str] | None,
    max_points: int,
) -> list[Any]:
    """Evenly spaced distinct x values: first, last, and every stride-th one."""
    x = _quote_ident(x_column)
    scan_sql, params = _scan(target, equals, f"{x} IS NOT NULL")
    rows = conn.execute(f"SELECT DISTINCT {x} {scan_sql} ORDER BY 1", params).fetchall()
    values = [row[0] for row in rows]
    max_points = max(1, int(max_points))
    if len(values) <= max_points:
        return values
    stride = max(1, math.ceil(len(values) / max_points))
    last = len(values) - 1
    return [value for index, value in enumerate(values) if index % stride == 0 or index == last]


def _grouped_at(
    conn: duckdb.DuckDBPyConnection,
    target: Path,
    *,
    x_column: str,
    equals: tuple[str, str] | None,
    x_values: list[Any],
    aggregates: list[str],
) -> list[tuple[Any, ...]]:
    x = _quote_ident(x_column)
    placeholders = ", ".join("?" for _ in x_values)
    scan_sql, params = _scan(target, equals, f"{x} IN ({placeholders})")
    sql = f"SELECT {x}, {', '.join(aggregates)} {scan_sql} GROUP BY 1 ORDER BY 1"
    return conn.execute(sql, [*params, *x_values]).fetchall()


def sampled_sparklines(
    target: Path,
    columns: list[str],
    *,
    x_column: str | None,
    equals: tuple[str, str] | None,
    max_points: int,
) -> dict[str, list[dict[str, Any]]]:
    """Per-x median of each column at the sampled x values."""
    if not x_column or not columns:
        return {column: [] for column in columns}
    with _connect(target) as conn:
        x_values = _sampled_x_values(conn, target, x_column=x_column, equals=equals, max_points=max_points)
        if not x_values:
            return {column: [] for column in columns}
        rows = _grouped_at(
            conn,
            target,
            x_column=x_column,
            equals=equals,
            x_values=x_values,
            aggregates=[f"median({_quote_ident(column)})" for column in columns],
        )
    return {
        column: [{"x": format_x(row[0]), "y": safe_float(row[index + 1])} for row in rows]
        for index, column in enumerate(columns)
    }


def sampled_detail_sparkline(
    target: Path,
    column: str,
    *,
    x_column: str | None,
    equals: tuple[str, str] | None,
    max_points: int,
) -> list[dict[str, Any]]:
    """Per-x median with the p10/p90 band at the sampled x values."""
    if not x_column:
        return []
    col = _quote_ident(column)
    with _connect(target) as conn:
        x_values = _sampled_x_values(conn, target, x_column=x_column, equals=equals, max_points=max_points)
        if not x_values:
            return []
        rows = _grouped_at(
            conn,
            target,
            x_column=x_column,
            equals=equals,
            x_values=x_values,
            aggregates=[f"median({col})", f"quantile_disc({col}, [0.1, 0.9])"],
        )
    return [
        {
            "x": format_x(row[0]),
            "y": safe_float(row[1]),
            "p10": safe_float((row[2] or (None, None))[0]),
            "p90": safe_float((row[2] or (None, None))[1]),
        }
        for row in rows
    ]


# --------------------------------------------------------------------------- #
# Detail diagnostics
# --------------------------------------------------------------------------- #


def histogram(
    target: Path,
    column: str,
    *,
    equals: tuple[str, str] | None,
    bins: int,
) -> list[dict[str, Any]]:
    """Equal-width histogram over the column's finite values."""
    col = _quote_ident(column)
    finite_sql, params = _scan(target, equals, f"isfinite(CAST({col} AS DOUBLE))")
    with _connect(target) as conn:
        count, min_value, max_value = conn.execute(
            f"SELECT count(*), min(CAST({col} AS DOUBLE)), max(CAST({col} AS DOUBLE)) {finite_sql}", params
        ).fetchone()
        if not count:
            return []
        if min_value == max_value:
            return [{"bin_start": min_value, "bin_end": max_value, "count": int(count)}]
        width = (max_value - min_value) / bins
        rows = conn.execute(
            f"SELECT least({bins - 1}, CAST(floor((CAST({col} AS DOUBLE) - ?) / ?) AS BIGINT)) AS bin, count(*) "
            f"{finite_sql} GROUP BY 1",
            [min_value, width, *params],
        ).fetchall()
    counts = dict(rows)
    return [
        {
            "bin_start": min_value + index * width,
            "bin_end": min_value + (index + 1) * width,
            "count": int(counts.get(index, 0)),
        }
        for index in range(bins)
    ]


def latest_entity_extremes(
    target: Path,
    column: str,
    *,
    x_column: str | None,
    entity_column: str | None,
    equals: tuple[str, str] | None,
    limit: int = 10,
) -> tuple[str | None, list[dict[str, Any]], list[dict[str, Any]]]:
    """Highest and lowest entities on the latest x value."""
    if not x_column or not entity_column:
        return None, [], []
    x = _quote_ident(x_column)
    col = _quote_ident(column)
    entity = _quote_ident(entity_column)
    scan_sql, params = _scan(target, equals)
    with _connect(target) as conn:
        latest = conn.execute(f"SELECT max({x}) {scan_sql}", params).fetchone()[0]
        if latest is None:
            return None, [], []
        latest_sql, _ = _scan(target, equals, f"{x} = ? AND {entity} IS NOT NULL AND {col} IS NOT NULL")
        base = f"SELECT CAST({entity} AS VARCHAR), {col} {latest_sql}"
        top = conn.execute(f"{base} ORDER BY 2 DESC LIMIT {int(limit)}", [*params, latest]).fetchall()
        bottom = conn.execute(f"{base} ORDER BY 2 ASC LIMIT {int(limit)}", [*params, latest]).fetchall()
    return (
        format_x(latest),
        [{"entity": name, "value": safe_float(value)} for name, value in top],
        [{"entity": name, "value": safe_float(value)} for name, value in bottom],
    )
