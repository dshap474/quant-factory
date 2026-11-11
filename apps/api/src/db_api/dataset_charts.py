"""UI-specific chart helpers for scoped parquet browser routes.

Every row read goes through ``data.query`` (DuckDB). Column projections and the
entity filter are pushed into the parquet scan, so tall multi-entity
panels never materialize rows for other entities.
Chart metadata (temporal axis, entity candidates, repeated-timestamp flag),
default entity selection, and entity selector values are computed as DuckDB
aggregations and memoized per file signature (path, mtime, size), so repeated
bundle requests against an unchanged file skip the full-table scans.

USAGE:
    payload = preview_chart_bundle(db_root, "features", path, request=request)
    payload, series = preview_chart(db_root, "features", path, metric="close")
    values = get_chart_values(db_root, "features", path, entity_column="asset")
    meta = chart_metadata(db_root, "features", path, target)  # sibling helpers
    clear_chart_caches()  # tests / cache reset
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports
# --------------------------------------------------------------------------- #
from dataclasses import dataclass
from functools import lru_cache
from math import ceil
from pathlib import Path
from typing import Any, Literal

import polars as pl
from data.platform.storage import delta_read
from data.query import (
    AggregationSpec,
    ParquetCollectionQuery,
    ParquetQuery,
    aggregate_parquet_collection,
    query_parquet,
)
from fastapi import HTTPException
from pydantic import BaseModel, Field

from .dataset_browser import Scope, _resolve_scoped_path, get_scope_root
from .dataset_profile_common import (
    ENTITY_COLUMN_PRIORITY,
    column_blocks,
    is_entity_column,
)
from .entity_labels import entity_label, entity_labels
from .parquet import fingerprint, is_parquet_directory, read_parquet_schema

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

_DEFAULT_CHART_MAX_POINTS = 2000
_CACHE_SIZE = 128
_TIME_COLUMN_PRIORITY = (
    "timestamp",
    "datetime",
    "date",
    "time",
    "period_end",
    "snapshot_date",
)
_EPOCH_SECOND_MIN = 100_000_000
_EPOCH_MILLISECOND_MIN = 100_000_000_000
_EPOCH_MICROSECOND_MIN = 100_000_000_000_000
_EPOCH_NANOSECOND_MIN = 100_000_000_000_000_000
_METRIC_PRIORITY = (
    "close",
    "value",
    "price",
    "midprice",
    "equity",
    "prediction",
    "signal",
    "open",
    "high",
    "low",
    "volume",
)
_ENTITY_PRIORITY = ENTITY_COLUMN_PRIORITY

# File signature used as the cache key: (absolute path, mtime_ns, size).
_FileSignature = tuple[str, int, int]

# --------------------------------------------------------------------------- #
# Request models
# --------------------------------------------------------------------------- #


class ChartBundleSeriesRequest(BaseModel):
    metric: str
    axis: Literal["left", "right"] = "left"


class ChartBundleCellRequest(BaseModel):
    chart_id: str
    series: list[ChartBundleSeriesRequest] = Field(default_factory=list)


class ChartBundleRequest(BaseModel):
    entity_column: str | None = None
    entity_value: str | None = None
    charts: list[ChartBundleCellRequest] = Field(default_factory=list)
    max_points: int = Field(default=_DEFAULT_CHART_MAX_POINTS, ge=50, le=5000)


@dataclass(frozen=True)
class _ChartInfo:
    """Typed schema plus the JSON-safe chart metadata payload for one file."""

    schema: dict[str, pl.DataType]
    meta: dict[str, Any]


# --------------------------------------------------------------------------- #
# Public helpers
# --------------------------------------------------------------------------- #


def preview_chart(
    db_root: Path,
    scope: Scope,
    path: str,
    *,
    metric: str | None = None,
    entity_column: str | None = None,
    entity_value: str | None = None,
    max_points: int = _DEFAULT_CHART_MAX_POINTS,
) -> tuple[dict[str, Any], pl.DataFrame]:
    target = _resolve_parquet_path(db_root, scope, path, action="charted")
    max_points = max(50, max_points)

    info = _chart_info(db_root, scope, path, target)
    chart_meta = info.meta

    if not chart_meta["chartable"]:
        return (
            {
                "path": path,
                **chart_meta,
                "selected_y_column": None,
                "selected_entity_column": None,
                "selected_entity_value": None,
                "points_total": 0,
                "points_returned": 0,
                "downsampled": False,
                "series_label": None,
            },
            pl.DataFrame(schema={"x": pl.String, "y": pl.Float64}),
        )

    x_column = chart_meta["x_column"]
    selected_metric = metric if metric in chart_meta["y_columns"] else chart_meta["default_y_column"]
    entity_columns = chart_meta["entity_columns"]
    selected_entity_column = (
        entity_column
        if entity_column in entity_columns
        else (entity_columns[0] if chart_meta["has_repeated_timestamps"] and entity_columns else None)
    )
    selected_entity_value = None
    if selected_entity_column and selected_metric:
        selected_entity_value = entity_value or _default_entity_value(
            db_root,
            scope,
            path,
            target,
            entity_column=selected_entity_column,
            metric=selected_metric,
        )

    frame = _read_chart_frame(
        db_root,
        scope,
        path,
        columns=_unique_columns(x_column, selected_metric),
        entity_column=selected_entity_column,
        entity_value=selected_entity_value,
    )
    frame = _normalize_temporal_frame(frame, column=x_column, dtype=info.schema[x_column])
    series_lf = _build_series_frame(
        frame.lazy(),
        x_column=x_column,
        metric=selected_metric,
        has_repeated_timestamps=chart_meta["has_repeated_timestamps"],
    )
    points_total = int(series_lf.select(pl.len()).collect().item() or 0)
    downsampled = points_total > max_points
    series_df = _sample_lazy_frame(series_lf, max_points=max_points, total=points_total).collect()

    return (
        {
            "path": path,
            **chart_meta,
            "selected_y_column": selected_metric,
            "selected_entity_column": selected_entity_column,
            "selected_entity_value": selected_entity_value,
            "points_total": points_total,
            "points_returned": len(series_df),
            "downsampled": downsampled,
            "series_label": _build_series_label(
                metric=selected_metric,
                entity_column=selected_entity_column,
                entity_value=entity_label(db_root, scope, path, selected_entity_column, selected_entity_value)
                or selected_entity_value,
            ),
        },
        series_df,
    )


def preview_chart_bundle(
    db_root: Path,
    scope: Scope,
    path: str,
    *,
    request: ChartBundleRequest,
) -> dict[str, Any]:
    target = _resolve_parquet_path(db_root, scope, path, action="charted")
    info = _chart_info(db_root, scope, path, target)
    chart_meta = info.meta
    requested_metrics = _collect_requested_metrics(request.charts)

    if not chart_meta["chartable"]:
        return {
            "path": path,
            **chart_meta,
            "selected_entity_column": None,
            "selected_entity_value": None,
            "points_total": 0,
            "points_returned": 0,
            "downsampled": False,
            "charts": _empty_bundle_charts(request.charts),
        }

    invalid_metrics = sorted(metric for metric in requested_metrics if metric not in chart_meta["y_columns"])
    if invalid_metrics:
        joined = ", ".join(invalid_metrics)
        raise HTTPException(status_code=400, detail=f"Invalid metric selection: {joined}")

    entity_columns = chart_meta["entity_columns"]
    selected_entity_column = (
        request.entity_column
        if request.entity_column in entity_columns
        else (entity_columns[0] if chart_meta["has_repeated_timestamps"] and entity_columns else None)
    )
    seed_metric = requested_metrics[0] if requested_metrics else chart_meta["default_y_column"]
    selected_entity_value = None
    if selected_entity_column and seed_metric:
        selected_entity_value = request.entity_value or _default_entity_value(
            db_root,
            scope,
            path,
            target,
            entity_column=selected_entity_column,
            metric=seed_metric,
        )

    if not requested_metrics:
        return {
            "path": path,
            **chart_meta,
            "selected_entity_column": selected_entity_column,
            "selected_entity_value": selected_entity_value,
            "points_total": 0,
            "points_returned": 0,
            "downsampled": False,
            "charts": _empty_bundle_charts(request.charts),
        }

    x_column = chart_meta["x_column"]
    frame = _read_chart_frame(
        db_root,
        scope,
        path,
        columns=_unique_columns(x_column, *requested_metrics),
        entity_column=selected_entity_column,
        entity_value=selected_entity_value,
    )
    frame = _normalize_temporal_frame(frame, column=x_column, dtype=info.schema[x_column])
    bundle_lf = _build_bundle_chart_frame(
        frame.lazy(),
        x_column=x_column,
        metrics=requested_metrics,
        has_repeated_timestamps=chart_meta["has_repeated_timestamps"],
    )
    stats = (
        bundle_lf.select(
            pl.len().alias("__row_count"),
            *(
                pl.col(metric).is_not_null().sum().alias(f"__count__{metric}")
                for metric in requested_metrics
            ),
        )
        .collect()
        .row(0, named=True)
    )
    points_total = int(stats["__row_count"] or 0)
    downsampled = points_total > request.max_points
    sampled_df = _sample_lazy_frame(bundle_lf, max_points=request.max_points, total=points_total).collect()
    series_counts = {
        metric: int(stats.get(f"__count__{metric}") or 0)
        for metric in requested_metrics
    }

    entity_display = (
        entity_label(db_root, scope, path, selected_entity_column, selected_entity_value) or selected_entity_value
    )
    charts = []
    for chart in request.charts:
        chart_series = []
        for series in chart.series:
            series_df = sampled_df.select(
                pl.col("x"),
                pl.col(series.metric).alias("y"),
            ).filter(pl.col("y").is_not_null())
            chart_series.append(
                {
                    "metric": series.metric,
                    "axis": series.axis,
                    "label": _build_series_label(
                        metric=series.metric,
                        entity_column=selected_entity_column,
                        entity_value=entity_display,
                    ),
                    "points_total": series_counts[series.metric],
                    "points_returned": len(series_df),
                    "points": series_df,
                }
            )
        charts.append({"chart_id": chart.chart_id, "series": chart_series})

    return {
        "path": path,
        **chart_meta,
        "selected_entity_column": selected_entity_column,
        "selected_entity_value": selected_entity_value,
        "points_total": points_total,
        "points_returned": len(sampled_df),
        "downsampled": downsampled,
        "charts": charts,
    }


def get_chart_values(
    db_root: Path,
    scope: Scope,
    path: str,
    *,
    entity_column: str,
    query: str = "",
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    target = _resolve_parquet_path(db_root, scope, path, action="chart values")
    info = _chart_info(db_root, scope, path, target)

    if entity_column not in info.meta["entity_columns"]:
        raise HTTPException(
            status_code=400,
            detail=f"Column '{entity_column}' is not a valid entity selector",
        )

    query = query.strip()
    values = _distinct_entity_values(db_root, scope, path, target, column=entity_column)
    labels = entity_labels(db_root, scope, path, entity_column, values)
    if labels:
        # Opaque keys sort meaninglessly; a labelled roster reads in label order.
        values = tuple(sorted(values, key=lambda value: (labels.get(value, value).casefold(), value)))
    if query:
        # A label match counts too: "bitcoin" finds the asset whose key is a UUID.
        needle = query.lower()
        values = tuple(
            value for value in values if needle in value.lower() or needle in labels.get(value, "").lower()
        )
    page = list(values[offset : offset + limit])
    return {
        "path": path,
        "entity_column": entity_column,
        "query": query,
        "total_values": len(values),
        "values": page,
        "labels": {value: labels[value] for value in page if value in labels},
        "limit": limit,
        "offset": offset,
    }


def chart_metadata(db_root: Path, scope: Scope, path: str, target: Path) -> dict[str, Any]:
    """Memoized chart metadata (x axis, y columns, entity columns) for a resolved parquet file."""
    return _chart_info(db_root, scope, path, target).meta


def clear_chart_caches() -> None:
    """Drop memoized chart metadata, default entities, and selector values."""
    _cached_chart_info.cache_clear()
    _cached_default_entity_value.cache_clear()
    _cached_distinct_entity_values.cache_clear()


# --------------------------------------------------------------------------- #
# Chart metadata (memoized per file signature)
# --------------------------------------------------------------------------- #


def _chart_info(db_root: Path, scope: Scope, path: str, target: Path) -> _ChartInfo:
    return _cached_chart_info(_file_signature(target), db_root, scope, path)


@lru_cache(maxsize=_CACHE_SIZE)
def _cached_chart_info(
    signature: _FileSignature,
    db_root: Path,
    scope: Scope,
    path: str,
) -> _ChartInfo:
    target = Path(signature[0])
    schema = read_parquet_schema(target, db_root=db_root)
    return _ChartInfo(schema=schema, meta=_infer_chart_metadata(db_root, scope, path, schema))


def _metric_families(scope: Scope, path: str, y_columns: list[str]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """Group plottable metrics into the blocks the profile atlas uses."""
    blocks = column_blocks(scope, path)
    return blocks.counts(y_columns), {column: blocks.of(column) for column in y_columns}


def _infer_chart_metadata(
    db_root: Path,
    scope: Scope,
    path: str,
    schema: dict[str, pl.DataType],
) -> dict[str, Any]:
    x_column = _infer_temporal_column(db_root, scope, path, schema)
    y_columns = _prioritize_columns(
        [name for name, dtype in schema.items() if name != x_column and dtype.is_numeric()],
        _METRIC_PRIORITY,
    )
    string_columns = [
        name for name, dtype in schema.items() if name != x_column and _is_string_like(dtype)
    ]
    families, y_column_families = _metric_families(scope, path, y_columns)

    if x_column is None:
        return {
            "chartable": False,
            "reason": "This parquet file has no temporal column to use as the x-axis.",
            "x_column": None,
            "y_columns": y_columns,
            "default_y_column": y_columns[0] if y_columns else None,
            "families": families,
            "y_column_families": y_column_families,
            "entity_columns": [],
            "has_repeated_timestamps": False,
        }
    if not y_columns:
        return {
            "chartable": False,
            "reason": "This parquet file has no numeric column to plot on the y-axis.",
            "x_column": x_column,
            "y_columns": [],
            "default_y_column": None,
            "families": [],
            "y_column_families": {},
            "entity_columns": [],
            "has_repeated_timestamps": False,
        }

    # One DuckDB aggregation pass: row count, distinct x, distinct per string column.
    aggregations = [
        AggregationSpec("count_star", alias="__row_count"),
        AggregationSpec("count_distinct", x_column, alias="__x_unique"),
        *(
            AggregationSpec("count_distinct", column, alias=f"__entity_unique__{column}")
            for column in string_columns
        ),
    ]
    stats = (
        aggregate_parquet_collection(
            ParquetCollectionQuery(
                scope=scope,
                path_glob=path,
                union_by_name=True,  # a folder's files may order columns differently
                aggregations=tuple(aggregations),
                limit=None,
            ),
            db_root=db_root,
        )
        .frame.row(0, named=True)
    )
    entity_candidates = [
        column
        for column in string_columns
        if is_entity_column(column, int(stats.get(f"__entity_unique__{column}") or 0))
    ]

    return {
        "chartable": True,
        "reason": None,
        "x_column": x_column,
        "y_columns": y_columns,
        "default_y_column": y_columns[0],
        "families": families,
        "y_column_families": y_column_families,
        "entity_columns": _prioritize_columns(entity_candidates, _ENTITY_PRIORITY),
        "has_repeated_timestamps": (stats["__row_count"] or 0) > (stats["__x_unique"] or 0),
    }


def _infer_temporal_column(
    db_root: Path,
    scope: Scope,
    path: str,
    schema: dict[str, pl.DataType],
) -> str | None:
    candidates = [
        name
        for name, dtype in schema.items()
        if dtype.is_temporal()
        or (name.lower() in _TIME_COLUMN_PRIORITY and (dtype.is_numeric() or _is_string_like(dtype)))
    ]
    priority_index = {name: index for index, name in enumerate(_TIME_COLUMN_PRIORITY)}
    candidates.sort(key=lambda name: priority_index.get(name.lower(), len(priority_index)))

    for column in candidates:
        if schema[column].is_temporal():
            return column
        # Named epoch / date-string columns: project just that column to test parseability.
        frame = query_parquet(
            ParquetQuery(scope=scope, path=path, columns=(column,), limit=None),
            db_root=db_root,
        ).frame
        normalized = _normalize_temporal_frame(frame, column=column, dtype=schema[column])
        if normalized[column].is_not_null().any():
            return column
    return None


# --------------------------------------------------------------------------- #
# data.query readers
# --------------------------------------------------------------------------- #


def _read_chart_frame(
    db_root: Path,
    scope: Scope,
    path: str,
    *,
    columns: list[str],
    entity_column: str | None,
    entity_value: str | None,
) -> pl.DataFrame:
    """Project the chart columns and push the entity filter into the DuckDB scan."""
    filtered = entity_column is not None and entity_value is not None
    query = ParquetQuery(
        scope=scope,
        path=path,
        columns=tuple(columns),
        entity_column=entity_column if filtered else None,
        entity_values=(entity_value,) if filtered and entity_value is not None else (),
        limit=None,
    )
    return query_parquet(query, db_root=db_root).frame


def _default_entity_value(
    db_root: Path,
    scope: Scope,
    path: str,
    target: Path,
    *,
    entity_column: str,
    metric: str,
) -> str | None:
    return _cached_default_entity_value(
        _file_signature(target), db_root, scope, path, entity_column, metric
    )


@lru_cache(maxsize=_CACHE_SIZE)
def _cached_default_entity_value(
    signature: _FileSignature,
    db_root: Path,
    scope: Scope,
    path: str,
    entity_column: str,
    metric: str,
) -> str | None:
    """Entity with the most non-null metric observations (ties broken by name)."""
    del signature  # cache key only
    counts = (
        aggregate_parquet_collection(
            ParquetCollectionQuery(
                scope=scope,
                path_glob=path,
                union_by_name=True,  # a folder's files may order columns differently
                group_by=(entity_column,),
                aggregations=(AggregationSpec("count", metric, alias="__count"),),
                limit=None,
            ),
            db_root=db_root,
        )
        .frame.select(
            pl.col(entity_column).cast(pl.String).alias("entity"),
            pl.col("__count"),
        )
        .filter(pl.col("entity").is_not_null())
        .sort(["__count", "entity"], descending=[True, False])
        .head(1)
    )
    if counts.is_empty():
        return None
    return counts["entity"][0]


def _distinct_entity_values(
    db_root: Path,
    scope: Scope,
    path: str,
    target: Path,
    *,
    column: str,
) -> tuple[str, ...]:
    return _cached_distinct_entity_values(_file_signature(target), db_root, scope, path, column)


@lru_cache(maxsize=_CACHE_SIZE)
def _cached_distinct_entity_values(
    signature: _FileSignature,
    db_root: Path,
    scope: Scope,
    path: str,
    column: str,
) -> tuple[str, ...]:
    """Sorted distinct non-null selector values, grouped in DuckDB."""
    del signature  # cache key only
    values = (
        aggregate_parquet_collection(
            ParquetCollectionQuery(
                scope=scope,
                path_glob=path,
                union_by_name=True,  # a folder's files may order columns differently
                group_by=(column,),
                aggregations=(AggregationSpec("count_star", alias="__rows"),),
                limit=None,
            ),
            db_root=db_root,
        )
        .frame.select(pl.col(column).cast(pl.String).alias("value"))
        .drop_nulls()
        .sort("value")
    )
    return tuple(values["value"].to_list())


def _file_signature(target: Path) -> _FileSignature:
    return (str(target), *fingerprint(target))


# --------------------------------------------------------------------------- #
# Temporal normalization
# --------------------------------------------------------------------------- #


def _normalize_temporal_frame(
    frame: pl.DataFrame,
    *,
    column: str,
    dtype: pl.DataType,
) -> pl.DataFrame:
    if dtype.is_temporal():
        return frame
    if dtype.is_numeric():
        unit = _infer_epoch_unit(frame[column])
        if unit is None:
            return frame.with_columns(pl.lit(None, dtype=pl.Datetime("us")).alias(column))
        return frame.with_columns(
            pl.from_epoch(pl.col(column).cast(pl.Int64), time_unit=unit).dt.replace_time_zone("UTC").alias(column)
        )
    if _is_string_like(dtype):
        return frame.with_columns(
            pl.col(column).cast(pl.String).str.to_datetime(strict=False, time_zone="UTC").alias(column)
        )
    return frame


def _infer_epoch_unit(series: pl.Series) -> Literal["s", "ms", "us", "ns"] | None:
    raw_max_value = series.drop_nulls().cast(pl.Float64).abs().max()
    if raw_max_value is None:
        return None
    max_value = float(raw_max_value)
    if max_value >= _EPOCH_NANOSECOND_MIN:
        return "ns"
    if max_value >= _EPOCH_MICROSECOND_MIN:
        return "us"
    if max_value >= _EPOCH_MILLISECOND_MIN:
        return "ms"
    if max_value >= _EPOCH_SECOND_MIN:
        return "s"
    return None


# --------------------------------------------------------------------------- #
# Frame shaping
# --------------------------------------------------------------------------- #


def _build_series_frame(
    lf: pl.LazyFrame,
    *,
    x_column: str,
    metric: str,
    has_repeated_timestamps: bool,
) -> pl.LazyFrame:
    series_lf = lf.select(
        pl.col(x_column).alias("x"),
        pl.col(metric).alias("y"),
    )

    if has_repeated_timestamps:
        series_lf = (
            series_lf.sort("x")
            .group_by("x")
            .agg(pl.col("y").drop_nulls().last().alias("y"))
            .sort("x")
        )
    else:
        series_lf = series_lf.sort("x")

    return series_lf.filter(pl.col("x").is_not_null() & pl.col("y").is_not_null())


def _build_bundle_chart_frame(
    lf: pl.LazyFrame,
    *,
    x_column: str,
    metrics: list[str],
    has_repeated_timestamps: bool,
) -> pl.LazyFrame:
    select_exprs: list[pl.Expr] = [pl.col(x_column).alias("x")]
    select_exprs.extend(pl.col(metric).alias(metric) for metric in metrics)

    frame_lf = lf.select(select_exprs).filter(pl.col("x").is_not_null())

    if has_repeated_timestamps:
        frame_lf = (
            frame_lf.sort("x")
            .group_by("x")
            .agg(*(pl.col(metric).drop_nulls().last().alias(metric) for metric in metrics))
            .sort("x")
        )
    else:
        frame_lf = frame_lf.sort("x")

    return frame_lf.filter(
        pl.any_horizontal(*(pl.col(metric).is_not_null() for metric in metrics))
    )


def _sample_lazy_frame(lf: pl.LazyFrame, *, max_points: int, total: int) -> pl.LazyFrame:
    if total <= max_points:
        return lf
    stride = max(1, ceil(total / max_points))
    return (
        lf.with_row_index("__row")
        .filter(
            (pl.col("__row") == 0)
            | (pl.col("__row") == total - 1)
            | (pl.col("__row") % stride == 0)
        )
        .drop("__row")
    )


# --------------------------------------------------------------------------- #
# Utilities
# --------------------------------------------------------------------------- #


def _resolve_parquet_path(db_root: Path, scope: Scope, path: str, *, action: str) -> Path:
    scope_root = get_scope_root(db_root, scope)
    if not scope_root.exists():
        raise HTTPException(status_code=404, detail=f"{scope.title()} root not found")
    requested = scope_root / path.strip("/")
    ref = delta_read.delta_ref(db_root, requested) if _inside(requested, scope_root) else None
    if ref is not None:  # a Delta table; a filtered legacy key keeps its requested path
        return db_root / ref.key if not ref.filters else requested
    target = _resolve_scoped_path(scope_root, path)
    if target.suffix != ".parquet" and not is_parquet_directory(target, db_root=db_root):
        raise HTTPException(status_code=400, detail=f"Only parquet files expose {action}")
    return target


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _build_series_label(
    *,
    metric: str,
    entity_column: str | None,
    entity_value: str | None,
) -> str:
    if entity_column and entity_value:
        return f"{entity_value} · {metric}"
    return metric


def _collect_requested_metrics(charts: list[ChartBundleCellRequest]) -> list[str]:
    seen: set[str] = set()
    metrics: list[str] = []
    for chart in charts:
        for series in chart.series:
            if series.metric in seen:
                continue
            seen.add(series.metric)
            metrics.append(series.metric)
    return metrics


def _empty_bundle_charts(charts: list[ChartBundleCellRequest]) -> list[dict[str, Any]]:
    return [{"chart_id": chart.chart_id, "series": []} for chart in charts]


def _prioritize_columns(columns: list[str], priority: tuple[str, ...]) -> list[str]:
    priority_index = {name: idx for idx, name in enumerate(priority)}
    original_index = {name: idx for idx, name in enumerate(columns)}
    return sorted(
        columns,
        key=lambda name: (
            0 if name in priority_index else 1,
            priority_index.get(name, 10_000),
            original_index[name],
        ),
    )


def _unique_columns(*columns: str | None) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for column in columns:
        if column is None or column in seen:
            continue
        seen.add(column)
        result.append(column)
    return result


def _is_string_like(dtype: pl.DataType) -> bool:
    return dtype == pl.String or str(dtype).startswith("Categorical") or str(dtype).startswith("Enum")
