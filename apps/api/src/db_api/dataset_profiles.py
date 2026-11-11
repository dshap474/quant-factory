"""Generic parquet feature profiling for catalog and feature browser views."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Literal

import polars as pl
from fastapi import HTTPException

from .dataset_browser import Scope, _resolve_scoped_path, get_scope_root
from .dataset_charts import _normalize_temporal_frame, chart_metadata
from .dataset_profile_common import (
    ENTITY_COLUMN_PRIORITY,
    ColumnBlocks,
    column_blocks,
    format_x,
    is_entity_column,
    is_numeric_dtype,
    is_string_like,
    prioritize_columns,
    safe_float,
)
from .dataset_profile_sql import (
    histogram as sql_histogram,
)
from .dataset_profile_sql import (
    latest_entity_extremes,
    metadata_null_counts,
    sampled_detail_sparkline,
    sampled_sparklines,
    summary_stats,
)
from .entity_labels import entity_labels
from .parquet import is_parquet_directory, read_parquet_frame, read_parquet_schema

PROFILE_SORTS = {"schema", "family", "coverage_desc", "missing_desc", "std_desc", "name"}
_PROFILE_QUANTILE_METHOD = "nearest"
_HISTOGRAM_BINS = 20
# Sorts that order columns without their statistics, so only the page is aggregated.
_ORDER_ONLY_SORTS = {"schema", "family", "name"}
_NULL_COUNT_SORTS = {"coverage_desc", "missing_desc"}


def profile_parquet_features(
    db_root: Path,
    scope: Scope,
    path: str,
    *,
    query: str = "",
    family: str = "all",
    sort: Literal["schema", "family", "coverage_desc", "missing_desc", "std_desc", "name"] = "schema",
    page: int = 1,
    page_size: int = 100,
    entity_column: str | None = None,
    entity_value: str | None = None,
    max_spark_points: int = 36,
    columns: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Return column-first feature summaries for a parquet dataset."""
    target = _resolve_parquet_path(db_root, scope, path)
    schema = read_parquet_schema(target, db_root=db_root)
    chart_meta = chart_metadata(db_root, scope, path, target)
    x_column = chart_meta["x_column"]
    entity_columns = chart_meta["entity_columns"] or _infer_entity_columns(target, schema, db_root)
    selected_entity_column, selected_entity_value = _resolve_entity_selection(
        entity_columns=entity_columns,
        entity_column=entity_column,
        entity_value=entity_value,
    )

    feature_columns = _numeric_feature_columns(schema, x_column=x_column)
    if columns is not None:
        unknown = set(columns) - set(feature_columns)
        if unknown:
            raise HTTPException(400, "Unknown numeric profile columns")
        feature_columns = [column for column in feature_columns if column in columns]
    queried_columns = _apply_column_query(feature_columns, query)
    blocks = column_blocks(scope, path)
    family_counts = blocks.counts(queried_columns)
    family_filtered_columns = [
        column for column in queried_columns if family in {"", "all", blocks.of(column)}
    ]

    equals = _entity_equals(selected_entity_column, selected_entity_value)
    if _sql_profile_supported(schema, x_column):
        if sort in _ORDER_ONLY_SORTS:
            ordered_columns = _sort_profile_columns(family_filtered_columns, {}, sort, blocks)
            paged_columns = ordered_columns[(page - 1) * page_size : page * page_size]
            total_rows, stats_by_column = summary_stats(target, paged_columns, x_column=x_column, equals=equals)
        else:
            null_counts = metadata_null_counts(target, family_filtered_columns) if equals is None else None
            if sort in _NULL_COUNT_SORTS and null_counts is not None:
                # Footer null counts order coverage and missing sorts without a scan.
                row_count, nulls = null_counts
                sort_keys = {
                    column: {
                        "null_count": nulls[column],
                        "coverage": 1 - nulls[column] / row_count if row_count else 0.0,
                    }
                    for column in family_filtered_columns
                }
                ordered_columns = _sort_profile_columns(family_filtered_columns, sort_keys, sort, blocks)
                paged_columns = ordered_columns[(page - 1) * page_size : page * page_size]
                total_rows, stats_by_column = summary_stats(target, paged_columns, x_column=x_column, equals=equals)
            else:
                total_rows, stats_by_column = summary_stats(
                    target, family_filtered_columns, x_column=x_column, equals=equals
                )
                ordered_columns = _sort_profile_columns(family_filtered_columns, stats_by_column, sort, blocks)
                paged_columns = ordered_columns[(page - 1) * page_size : page * page_size]
        sparks = sampled_sparklines(
            target, paged_columns, x_column=x_column, equals=equals, max_points=max_spark_points
        )
    else:
        frame = read_parquet_frame(
            target,
            columns=_projection_columns(schema, x_column, selected_entity_column, *family_filtered_columns),
            equals=equals,
            db_root=db_root,
        )
        if x_column:
            frame = _normalize_temporal_frame(frame, column=x_column, dtype=schema[x_column])
        filtered_lf = frame.lazy()
        total_rows = int(filtered_lf.select(pl.len()).collect().item() or 0)
        stats_by_column = _collect_summary_stats(
            filtered_lf, family_filtered_columns, total_rows=total_rows, x_column=x_column
        )
        ordered_columns = _sort_profile_columns(family_filtered_columns, stats_by_column, sort, blocks)
        paged_columns = ordered_columns[(page - 1) * page_size : page * page_size]
        sparks = _collect_sparklines(
            filtered_lf,
            x_column=x_column,
            columns=paged_columns,
            max_points=max_spark_points,
        )

    return {
        "path": path,
        "total_rows": total_rows,
        "total_columns": len(schema),
        "feature_columns": len(feature_columns),
        "x_column": x_column,
        "entity_columns": entity_columns,
        "selected_entity_column": selected_entity_column,
        "selected_entity_value": selected_entity_value,
        "families": [{"id": "all", "label": "All", "count": len(queried_columns)}, *family_counts],
        "page": page,
        "page_size": page_size,
        "total_features": len(ordered_columns),
        "features": [
            _profile_payload(
                name=column,
                blocks=blocks,
                dtype=schema[column],
                stats=stats_by_column[column],
                sparkline=sparks.get(column, []),
            )
            for column in paged_columns
        ],
    }


def profile_parquet_feature_detail(
    db_root: Path,
    scope: Scope,
    path: str,
    *,
    column: str,
    entity_column: str | None = None,
    entity_value: str | None = None,
    max_spark_points: int = 120,
) -> dict[str, Any]:
    """Return detail diagnostics for one numeric parquet feature column."""
    target = _resolve_parquet_path(db_root, scope, path)
    blocks = column_blocks(scope, path)
    schema = read_parquet_schema(target, db_root=db_root)
    if column not in schema:
        raise HTTPException(status_code=404, detail=f"Column '{column}' not found")
    if not is_numeric_dtype(schema[column]):
        raise HTTPException(status_code=400, detail=f"Column '{column}' is not numeric")

    chart_meta = chart_metadata(db_root, scope, path, target)
    x_column = chart_meta["x_column"]
    entity_columns = chart_meta["entity_columns"] or _infer_entity_columns(target, schema, db_root)
    selected_entity_column, selected_entity_value = _resolve_entity_selection(
        entity_columns=entity_columns,
        entity_column=entity_column,
        entity_value=entity_value,
    )
    latest_entity_column = selected_entity_column or (entity_columns[0] if entity_columns else None)
    equals = _entity_equals(selected_entity_column, selected_entity_value)
    if _sql_profile_supported(schema, x_column):
        _, stats_by_column = summary_stats(target, [column], x_column=x_column, equals=equals, quantiles=True)
        stats = stats_by_column[column]
        sparkline = sampled_detail_sparkline(
            target, column, x_column=x_column, equals=equals, max_points=max_spark_points
        )
        latest_timestamp, latest_top, latest_bottom = latest_entity_extremes(
            target, column, x_column=x_column, entity_column=latest_entity_column, equals=equals
        )
        histogram = sql_histogram(target, column, equals=equals, bins=_HISTOGRAM_BINS)
    else:
        frame = read_parquet_frame(
            target,
            columns=_projection_columns(schema, x_column, selected_entity_column, latest_entity_column, column),
            equals=equals,
            db_root=db_root,
        )
        if x_column:
            frame = _normalize_temporal_frame(frame, column=x_column, dtype=schema[x_column])
        filtered_lf = frame.lazy()
        total_rows = int(filtered_lf.select(pl.len()).collect().item() or 0)
        stats = _collect_summary_stats(filtered_lf, [column], total_rows=total_rows, x_column=x_column)[column]
        sparkline = _collect_detail_sparkline(
            filtered_lf,
            x_column=x_column,
            column=column,
            max_points=max_spark_points,
        )
        latest_timestamp, latest_top, latest_bottom = _latest_entity_extremes(
            filtered_lf,
            x_column=x_column,
            entity_column=latest_entity_column,
            column=column,
        )
        histogram = _histogram(filtered_lf, column)

    labels = entity_labels(
        db_root,
        scope,
        path,
        latest_entity_column,
        [str(row["entity"]) for row in (*latest_top, *latest_bottom)],
    )
    if labels:
        latest_top = [{**row, "label": labels.get(str(row["entity"]))} for row in latest_top]
        latest_bottom = [{**row, "label": labels.get(str(row["entity"]))} for row in latest_bottom]

    return {
        "path": path,
        "column": column,
        "dtype": str(schema[column]),
        "family": blocks.of(column),
        "family_label": blocks.label(column),
        "stats": _profile_payload(
            name=column,
            blocks=blocks,
            dtype=schema[column],
            stats=stats,
            sparkline=[],
        ),
        "sparkline": sparkline,
        "histogram": histogram,
        "latest_timestamp": latest_timestamp,
        "latest_top": latest_top,
        "latest_bottom": latest_bottom,
    }


def _resolve_parquet_path(db_root: Path, scope: Scope, path: str) -> Path:
    scope_root = get_scope_root(db_root, scope)
    if not scope_root.exists():
        raise HTTPException(status_code=404, detail=f"{scope.title()} root not found")
    target = _resolve_scoped_path(scope_root, path)
    if target.suffix != ".parquet" and not is_parquet_directory(target, db_root=db_root):
        raise HTTPException(status_code=400, detail="Only parquet files can be profiled")
    return target


def _sql_profile_supported(schema: pl.Schema, x_column: str | None) -> bool:
    """DuckDB aggregates in the scan when x needs no epoch or string parsing first."""
    return x_column is None or schema[x_column].is_temporal()


def _numeric_feature_columns(schema: pl.Schema, *, x_column: str | None) -> list[str]:
    return [
        name
        for name, dtype in schema.items()
        if name != x_column and is_numeric_dtype(dtype)
    ]


def _infer_entity_columns(target: Path, schema: pl.Schema, db_root: Path) -> list[str]:
    string_columns = [name for name, dtype in schema.items() if is_string_like(dtype)]
    if not string_columns:
        return []
    stats = read_parquet_frame(target, columns=string_columns, db_root=db_root).lazy().select(
        *(pl.col(column).drop_nulls().n_unique().alias(column) for column in string_columns)
    ).collect().row(0, named=True)
    candidates = [
        column for column in string_columns if is_entity_column(column, int(stats.get(column) or 0))
    ]
    return prioritize_columns(candidates, ENTITY_COLUMN_PRIORITY)


def _projection_columns(schema: pl.Schema, *columns: str | None) -> list[str]:
    seen: set[str] = set()
    projected: list[str] = []
    for column in columns:
        if column is None or column in seen or column not in schema:
            continue
        seen.add(column)
        projected.append(column)
    if projected:
        return projected
    first_column = next(iter(schema), None)
    return [first_column] if first_column is not None else []


def _resolve_entity_selection(
    *,
    entity_columns: list[str],
    entity_column: str | None,
    entity_value: str | None,
) -> tuple[str | None, str | None]:
    if not entity_column:
        return None, None
    if entity_column not in entity_columns:
        raise HTTPException(status_code=400, detail=f"Column '{entity_column}' is not a valid entity selector")
    return entity_column, entity_value or None


def _entity_equals(entity_column: str | None, entity_value: str | None) -> tuple[str, str] | None:
    """Scan-level filter for one selected entity, so a single asset never loads the panel."""
    return (entity_column, entity_value) if entity_column and entity_value else None


def _apply_column_query(columns: list[str], query: str) -> list[str]:
    value = query.strip().lower()
    if not value:
        return columns
    return [column for column in columns if value in column.lower()]


def _collect_summary_stats(
    lf: pl.LazyFrame,
    columns: list[str],
    *,
    total_rows: int,
    x_column: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Per-column summary statistics, plus first/last observed date when there is one.

    Coverage alone cannot distinguish a column that stopped updating from one that
    started late, so the same single pass carries the x-value bounds of the column's
    non-null rows.
    """
    if not columns:
        return {}
    exprs: list[pl.Expr] = []
    for column in columns:
        if x_column is not None and x_column != column:
            exprs.extend(
                [
                    pl.col(x_column)
                    .filter(pl.col(column).is_not_null())
                    .min()
                    .alias(f"{column}__first"),
                    pl.col(x_column)
                    .filter(pl.col(column).is_not_null())
                    .max()
                    .alias(f"{column}__last"),
                ]
            )
        exprs.extend(
            [
                pl.col(column).drop_nulls().len().alias(f"{column}__non_null"),
                pl.col(column).null_count().alias(f"{column}__null"),
                pl.col(column).mean().alias(f"{column}__mean"),
                pl.col(column).std().alias(f"{column}__std"),
                pl.col(column).min().alias(f"{column}__min"),
                pl.col(column).quantile(0.25, interpolation=_PROFILE_QUANTILE_METHOD).alias(f"{column}__p25"),
                pl.col(column).median().alias(f"{column}__p50"),
                pl.col(column).quantile(0.75, interpolation=_PROFILE_QUANTILE_METHOD).alias(f"{column}__p75"),
                pl.col(column).max().alias(f"{column}__max"),
            ]
        )
    row = lf.select(exprs).collect().row(0, named=True)
    result: dict[str, dict[str, Any]] = {}
    for column in columns:
        non_null = int(row.get(f"{column}__non_null") or 0)
        null_count = int(row.get(f"{column}__null") or 0)
        denominator = max(total_rows, non_null + null_count)
        first_value = row.get(f"{column}__first")
        last_value = row.get(f"{column}__last")
        result[column] = {
            "non_null_count": non_null,
            "null_count": null_count,
            "coverage": (non_null / denominator) if denominator else 0.0,
            "first_non_null": format_x(first_value) if first_value is not None else None,
            "last_non_null": format_x(last_value) if last_value is not None else None,
            "mean": safe_float(row.get(f"{column}__mean")),
            "std": safe_float(row.get(f"{column}__std")),
            "min": safe_float(row.get(f"{column}__min")),
            "p25": safe_float(row.get(f"{column}__p25")),
            "p50": safe_float(row.get(f"{column}__p50")),
            "p75": safe_float(row.get(f"{column}__p75")),
            "max": safe_float(row.get(f"{column}__max")),
        }
    return result


def _sort_profile_columns(
    columns: list[str],
    stats_by_column: dict[str, dict[str, Any]],
    sort: str,
    blocks: ColumnBlocks,
) -> list[str]:
    if sort not in PROFILE_SORTS:
        raise HTTPException(status_code=400, detail=f"Invalid profile sort: {sort}")
    if sort == "name":
        return sorted(columns)
    if sort == "family":
        order = {block: index for index, block in enumerate(blocks.labels)}
        return sorted(columns, key=lambda column: (order.get(blocks.of(column), len(order)), column))
    if sort == "coverage_desc":
        return sorted(columns, key=lambda column: (stats_by_column[column]["coverage"], column), reverse=True)
    if sort == "missing_desc":
        return sorted(columns, key=lambda column: (stats_by_column[column]["null_count"], column), reverse=True)
    if sort == "std_desc":
        return sorted(columns, key=lambda column: (stats_by_column[column]["std"] or float("-inf"), column), reverse=True)
    return columns


def _collect_sparklines(
    lf: pl.LazyFrame,
    *,
    x_column: str | None,
    columns: list[str],
    max_points: int,
) -> dict[str, list[dict[str, Any]]]:
    if not x_column or not columns:
        return {column: [] for column in columns}
    grouped = (
        lf.select([x_column, *columns])
        .filter(pl.col(x_column).is_not_null())
        .group_by(x_column)
        .agg(*(pl.col(column).median().alias(column) for column in columns))
        .sort(x_column)
    )
    sampled = _sample_lazy_frame(grouped, max_points=max_points)
    rows = sampled.collect()
    return {
        column: [
            {"x": format_x(row[x_column]), "y": safe_float(row[column])}
            for row in rows.iter_rows(named=True)
        ]
        for column in columns
    }


def _collect_detail_sparkline(
    lf: pl.LazyFrame,
    *,
    x_column: str | None,
    column: str,
    max_points: int,
) -> list[dict[str, Any]]:
    if not x_column:
        return []
    grouped = (
        lf.select([x_column, column])
        .filter(pl.col(x_column).is_not_null())
        .group_by(x_column)
        .agg(
            pl.col(column).median().alias("y"),
            pl.col(column).quantile(0.10, interpolation=_PROFILE_QUANTILE_METHOD).alias("p10"),
            pl.col(column).quantile(0.90, interpolation=_PROFILE_QUANTILE_METHOD).alias("p90"),
        )
        .sort(x_column)
    )
    rows = _sample_lazy_frame(grouped, max_points=max_points).collect()
    return [
        {
            "x": format_x(row[x_column]),
            "y": safe_float(row["y"]),
            "p10": safe_float(row["p10"]),
            "p90": safe_float(row["p90"]),
        }
        for row in rows.iter_rows(named=True)
    ]


def _sample_lazy_frame(lf: pl.LazyFrame, *, max_points: int) -> pl.LazyFrame:
    max_points = max(1, int(max_points))
    total = int(lf.select(pl.len()).collect().item() or 0)
    if total <= max_points:
        return lf
    stride = max(1, math.ceil(total / max_points))
    return (
        lf.with_row_index("__row")
        .filter(
            (pl.col("__row") == 0)
            | (pl.col("__row") == total - 1)
            | (pl.col("__row") % stride == 0)
        )
        .drop("__row")
    )


def _latest_entity_extremes(
    lf: pl.LazyFrame,
    *,
    x_column: str | None,
    entity_column: str | None,
    column: str,
) -> tuple[str | None, list[dict[str, Any]], list[dict[str, Any]]]:
    if not x_column or not entity_column:
        return None, [], []
    latest = lf.select(pl.col(x_column).max().alias("__latest")).collect().item()
    if latest is None:
        return None, [], []
    base = (
        lf.select(
            pl.col(x_column),
            pl.col(entity_column).cast(pl.String).alias("entity"),
            pl.col(column).alias("value"),
        )
        .filter(
            (pl.col(x_column) == latest)
            & pl.col("entity").is_not_null()
            & pl.col("value").is_not_null()
        )
    )
    top = base.sort("value", descending=True).head(10).collect()
    bottom = base.sort("value").head(10).collect()
    return (
        format_x(latest),
        [{"entity": row["entity"], "value": safe_float(row["value"])} for row in top.iter_rows(named=True)],
        [{"entity": row["entity"], "value": safe_float(row["value"])} for row in bottom.iter_rows(named=True)],
    )


def _histogram(lf: pl.LazyFrame, column: str) -> list[dict[str, Any]]:
    values = (
        lf.select(pl.col(column).alias("value"))
        .filter(pl.col("value").is_not_null())
        .collect()["value"]
        .to_list()
    )
    finite_values = [float(value) for value in values if safe_float(value) is not None]
    if not finite_values:
        return []
    min_value = min(finite_values)
    max_value = max(finite_values)
    if min_value == max_value:
        return [{"bin_start": min_value, "bin_end": max_value, "count": len(finite_values)}]
    width = (max_value - min_value) / _HISTOGRAM_BINS
    bins = [0 for _ in range(_HISTOGRAM_BINS)]
    for value in finite_values:
        index = min(_HISTOGRAM_BINS - 1, int((value - min_value) / width))
        bins[index] += 1
    return [
        {
            "bin_start": min_value + index * width,
            "bin_end": min_value + (index + 1) * width,
            "count": count,
        }
        for index, count in enumerate(bins)
    ]


def _profile_payload(
    *,
    name: str,
    blocks: ColumnBlocks,
    dtype: pl.DataType,
    stats: dict[str, Any],
    sparkline: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "name": name,
        "dtype": str(dtype),
        "role": "feature",
        "family": blocks.of(name),
        "family_label": blocks.label(name),
        **stats,
        "sparkline": sparkline,
    }
