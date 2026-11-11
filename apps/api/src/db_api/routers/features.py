"""Features API router."""

import time
from pathlib import Path
from typing import Any, Literal, cast

import polars as pl
import yaml
from data.platform.storage import delta_read
from data.query import ParquetQuery, get_parquet_metadata, query_parquet
from fastapi import APIRouter, HTTPException, Query, Response
from features.api import list_feature_presets

from ..config import settings
from ..dataset_browser import (
    compute_scope_stats,
)
from ..dataset_browser import (
    list_directory as list_scoped_directory,
)
from ..dataset_browser import (
    preview_markdown as preview_scoped_markdown,
)
from ..dataset_browser import (
    preview_structured_file as preview_scoped_structured_file,
)
from ..dataset_charts import (
    ChartBundleRequest,
    get_chart_values,
)
from ..dataset_charts import (
    preview_chart as preview_scoped_chart,
)
from ..dataset_charts import (
    preview_chart_bundle as preview_scoped_chart_bundle,
)
from ..dataset_profiles import profile_parquet_feature_detail, profile_parquet_features
from ..feature_overview import feature_overview
from ..feature_publication import panel_meta, panel_run_report
from ..parquet import read_parquet_frame, read_parquet_schema
from ..responses import polars_json_response, polars_nested_json_response, ttl_cache

router = APIRouter()


@router.get("/overview/{path:path}")
def get_feature_overview(path: str, diagnostics: bool = True) -> dict[str, Any]:
    """Compare registered presets against one read-only published snapshot."""
    return feature_overview(settings.db_root, path, diagnostics=diagnostics)


@router.get("/panel-meta/{path:path}")
def get_feature_panel_meta(path: str) -> dict[str, Any]:
    """Read the published panel's meta.yaml: per-column contract, as-of, freshness."""
    return panel_meta(settings.db_root, path)


@router.get("/run-report/{path:path}")
def get_feature_run_report(path: str) -> dict[str, Any]:
    """Read the refresh run report published beside the panel, when one exists."""
    return panel_run_report(settings.db_root, path)


_NUMERIC_DTYPES = (pl.Float64, pl.Float32, pl.Int64, pl.Int32)
_CORRELATION_COLUMNS = {
    "row_index",
    "column_index",
    "row_feature",
    "column_feature",
    "correlation",
    "abs_correlation",
    "row_cluster_id",
    "column_cluster_id",
    "row_is_representative",
    "column_is_representative",
}
_IC_COLUMNS = {
    "feature",
    "horizon",
    "mean_oriented_ic",
    "mean_validation_ic",
    "positive_fold_rate",
    "valid_folds",
}


@ttl_cache(seconds=30)
def _cached_profile_feature_parquet_features(
    db_root: Path,
    path: str,
    query: str,
    family: str,
    sort: str,
    page: int,
    page_size: int,
    entity_column: str | None,
    entity_value: str | None,
    max_spark_points: int,
    columns: tuple[str, ...] | None = None,
) -> dict[str, object]:
    return profile_parquet_features(
        db_root,
        "features",
        path,
        query=query,
        family=family,
        sort=cast(
            Literal["schema", "family", "coverage_desc", "missing_desc", "std_desc", "name"],
            sort,
        ),
        page=page,
        page_size=page_size,
        entity_column=entity_column,
        entity_value=entity_value,
        max_spark_points=max_spark_points,
        columns=columns,
    )


@ttl_cache(seconds=30)
def _cached_profile_feature_parquet_feature_detail(
    db_root: Path,
    path: str,
    column: str,
    entity_column: str | None,
    entity_value: str | None,
    max_spark_points: int,
) -> dict[str, object]:
    return profile_parquet_feature_detail(
        db_root,
        "features",
        path,
        column=column,
        entity_column=entity_column,
        entity_value=entity_value,
        max_spark_points=max_spark_points,
    )


@ttl_cache(seconds=30)
def _cached_discover_features():
    return discover_features(settings.db_root)


def _load_registry(db_root: Path) -> dict[str, Any]:
    registry_path = db_root / "features" / "REGISTRY.yaml"
    if not registry_path.exists():
        return {}
    with open(registry_path) as f:
        loaded = yaml.safe_load(f) or {}
    if not isinstance(loaded, dict):
        return {}
    return loaded


def _load_meta(data_path: Path) -> dict[str, Any]:
    """A panel's meta.yaml, from ``data.parquet``'s directory or a Delta table's ``_qf/``."""
    meta_file = delta_read.meta_path(data_path)
    if not meta_file.exists():
        return {}
    with open(meta_file) as f:
        return yaml.safe_load(f) or {}


def discover_features(db_root: Path) -> list[dict[str, Any]]:
    """Discover canonical feature files in db/features.

    Preferred source: REGISTRY.yaml.
    Fallback source: filesystem scan excluding _archive categories.
    """
    features_dir = db_root / "features"

    if not features_dir.exists():
        return []

    registry = _load_registry(db_root)
    registry_features = registry.get("features", {})
    registry_categories = registry.get("categories", {})

    results: list[dict[str, Any]] = []
    for feature_key, feature_info in registry_features.items():
        if "/" not in feature_key:
            continue

        resolution, category_path = feature_key.split("/", 1)
        category_meta = registry_categories.get(category_path, {})
        status = category_meta.get("status", feature_info.get("status", "active"))
        if status != "active":
            continue

        category_dir = features_dir / resolution / Path(*category_path.split("/"))
        if not category_dir.exists():
            continue

        data_path = category_dir / "data.parquet"
        if delta_read.is_delta_dir(category_dir):  # a Delta feature table is the category directory
            data_path = category_dir
        elif not data_path.exists():
            continue

        meta = _load_meta(data_path)
        results.append(
            {
                "resolution": resolution,
                "category_path": category_path,
                "version": "latest",
                "path": data_path,
                "meta": meta,
                "category_meta": category_meta,
                "registry_meta": feature_info,
            }
        )

    if results:
        results.sort(key=lambda x: (x["resolution"], x["category_path"], x["version"]))
        return results

    # Fallback: scan filesystem for canonical paths if registry is absent/stale.
    files, tables = delta_read.walk_lake(features_dir)
    for data_file in sorted([*(file for file in files if file.name == "data.parquet"), *tables]):
        table = data_file in tables
        rel_parts = data_file.relative_to(features_dir).parts + (("data.parquet",) if table else ())
        if len(rel_parts) < 3:
            continue

        resolution = rel_parts[0]
        category_parts = rel_parts[1:-1]
        if not category_parts:
            continue
        if any(part in {"", ".", ".."} for part in category_parts):
            continue
        if any(part.startswith("_") for part in category_parts):
            continue

        category_path = "/".join(category_parts)
        meta = _load_meta(data_file)
        results.append(
            {
                "resolution": resolution,
                "category_path": category_path,
                "version": "latest",
                "path": data_file,
                "meta": meta,
                "category_meta": {},
                "registry_meta": {},
            }
        )

    results.sort(key=lambda x: (x["resolution"], x["category_path"], x["version"]))
    return results


def _validate_category_path(category_path: str) -> str:
    value = category_path.strip().strip("/")
    if not value:
        raise HTTPException(status_code=400, detail="category_path is required")

    segments = value.split("/")
    if any(seg in {"", ".", ".."} for seg in segments):
        raise HTTPException(status_code=400, detail="category_path contains invalid segments")
    return "/".join(segments)


def _resolve_feature(
    resolution: str,
    category_path: str,
    version: str,
) -> dict[str, Any]:
    safe_category_path = _validate_category_path(category_path)
    category_parts = safe_category_path.split("/")
    feature_file = settings.db_root / "features" / resolution / Path(*category_parts) / "data.parquet"
    if delta_read.is_delta_dir(feature_file.parent):  # a Delta feature table is the category directory
        feature_file = feature_file.parent

    if not feature_file.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Feature '{resolution}/{safe_category_path}' not found",
        )

    meta = _load_meta(feature_file)

    return {
        "resolution": resolution,
        "category_path": safe_category_path,
        "version": "latest",
        "path": feature_file,
        "meta": meta,
    }


@router.get("/browser")
def browse_feature_root() -> dict[str, object]:
    """List contents of db/features root directory."""
    return list_scoped_directory(settings.db_root, "features")


@router.get("/browser/{path:path}")
def browse_feature_directory(path: str) -> dict[str, object]:
    """Browse a directory in db/features."""
    return list_scoped_directory(settings.db_root, "features", path)


@router.get("/markdown/{path:path}")
def preview_feature_markdown(path: str) -> dict[str, object]:
    """Preview a markdown file in db/features."""
    return preview_scoped_markdown(settings.db_root, "features", path)


@router.get("/structured/{path:path}")
def preview_feature_structured_file(path: str) -> dict[str, object]:
    """Preview a JSON or YAML file in db/features."""
    return preview_scoped_structured_file(settings.db_root, "features", path)


@router.get("/chart/{path:path}")
def preview_feature_chart(
    path: str,
    metric: str | None = Query(None, description="Numeric metric to plot"),
    entity_column: str | None = Query(None, description="Entity column for tall tables"),
    entity_value: str | None = Query(None, description="Entity value to filter before plotting"),
    max_points: int = Query(2000, ge=50, le=5000, description="Max chart points to return"),
):
    """Build a time-series chart preview for a parquet file in db/features."""
    payload, series = preview_scoped_chart(
        settings.db_root,
        "features",
        path,
        metric=metric,
        entity_column=entity_column,
        entity_value=entity_value,
        max_points=max_points,
    )
    payload["series"] = series
    return polars_json_response(payload, df_key="series")


@router.post("/chart-bundle/{path:path}")
def preview_feature_chart_bundle(path: str, request: ChartBundleRequest):
    """Build a multi-chart bundle preview for a parquet file in db/features."""
    payload = preview_scoped_chart_bundle(
        settings.db_root,
        "features",
        path,
        request=request,
    )
    return polars_nested_json_response(payload)


@router.get("/chart-values/{path:path}")
def preview_feature_chart_values(
    path: str,
    entity_column: str = Query(..., description="Entity column to fetch distinct values for"),
    query: str = Query("", description="Case-insensitive substring filter"),
    limit: int = Query(100, ge=1, le=50_000, description="Max values to return"),
    offset: int = Query(0, ge=0, description="Distinct value offset"),
) -> dict[str, object]:
    """Get distinct entity values for a parquet chart selector in db/features."""
    return get_chart_values(
        settings.db_root,
        "features",
        path,
        entity_column=entity_column,
        query=query,
        limit=limit,
        offset=offset,
    )


@router.get("/analysis/correlation/{path:path}")
def get_feature_analysis_correlation(
    path: str,
    response: Response,
    representatives_only: bool = Query(True, description="Return only representative cluster cells"),
) -> dict[str, object]:
    """Return compact clustered correlation arrays for feature analysis charts."""
    started = time.perf_counter()
    payload = _cached_feature_analysis_correlation(settings.db_root, path, representatives_only)
    response.headers["Server-Timing"] = f"analysis;dur={(time.perf_counter() - started) * 1000:.2f}"
    return payload


@ttl_cache(seconds=60)
def _cached_feature_analysis_correlation(
    db_root: Path,
    path: str,
    representatives_only: bool,
) -> dict[str, object]:
    analysis_file = _resolve_analysis_file(path, "analysis_cluster_heatmap.parquet")
    analysis_path = str(analysis_file.relative_to(db_root / "features"))
    metadata = get_parquet_metadata(scope="features", path=analysis_path, db_root=db_root)
    schema = {column.name for column in metadata.columns}
    missing = sorted(_CORRELATION_COLUMNS - schema)
    if missing:
        raise HTTPException(status_code=400, detail=f"Correlation artifact missing columns: {', '.join(missing)}")

    frame = query_parquet(
        ParquetQuery(
            scope="features",
            path=analysis_path,
            columns=tuple(sorted(_CORRELATION_COLUMNS)),
            limit=None,
        ),
        db_root=db_root,
        metadata=metadata,
    ).frame
    total_rows = metadata.total_rows
    dimension = frame.select((pl.max("row_index") + 1).alias("dimension")).item()
    clusters = frame.select(pl.col("row_cluster_id").n_unique()).item()
    representatives = frame.filter(pl.col("row_is_representative")).select(pl.col("row_index").n_unique()).item()

    cells = frame
    if representatives_only:
        cells = cells.filter(pl.col("row_is_representative") & pl.col("column_is_representative"))

    frame = cells.select(["row_index", "column_index", "correlation"]).sort(["row_index", "column_index"])
    non_diagonal = cells.filter(pl.col("row_index") != pl.col("column_index"))
    distribution = _correlation_distribution(non_diagonal)
    top_pairs = (
        non_diagonal.filter(pl.col("row_index") < pl.col("column_index"))
        .select(
            [
                "row_feature",
                "column_feature",
                "correlation",
                "abs_correlation",
                "row_cluster_id",
                "column_cluster_id",
            ]
        )
        .sort("abs_correlation", descending=True)
        .head(24)
        .to_dicts()
    )

    return {
        "path": analysis_path,
        "total_rows": total_rows,
        "returned_cells": frame.height,
        "dimension": dimension or 0,
        "feature_count": dimension or 0,
        "clusters": clusters or 0,
        "representatives": representatives or 0,
        "representatives_only": representatives_only,
        "row_index": frame["row_index"].to_list(),
        "column_index": frame["column_index"].to_list(),
        "correlation": frame["correlation"].to_list(),
        "distribution": distribution,
        "top_pairs": top_pairs,
    }


def _correlation_distribution(frame: pl.DataFrame) -> list[dict[str, object]]:
    buckets = [
        ("strong_negative", "<= -0.70", lambda value: value <= -0.7),
        ("moderate_negative", "-0.70 to -0.35", lambda value: -0.7 < value <= -0.35),
        ("weak", "-0.35 to 0.35", lambda value: -0.35 < value < 0.35),
        ("moderate_positive", "0.35 to 0.70", lambda value: 0.35 <= value < 0.7),
        ("strong_positive", ">= 0.70", lambda value: value >= 0.7),
    ]
    values = [value for value in frame["correlation"].to_list() if isinstance(value, (int, float))]
    total = max(1, len(values))
    return [
        {
            "key": key,
            "label": label,
            "count": count,
            "share": count / total,
        }
        for key, label, predicate in buckets
        for count in [sum(1 for value in values if predicate(value))]
    ]


@router.get("/analysis/ic/{path:path}")
def get_feature_analysis_ic(
    path: str,
    response: Response,
    max_features: int = Query(80, ge=1, le=250, description="Maximum feature rows to return"),
) -> dict[str, object]:
    """Return a compact top-feature IC matrix for feature analysis charts."""
    started = time.perf_counter()
    payload = _cached_feature_analysis_ic(settings.db_root, path, max_features)
    response.headers["Server-Timing"] = f"analysis;dur={(time.perf_counter() - started) * 1000:.2f}"
    return payload


@ttl_cache(seconds=60)
def _cached_feature_analysis_ic(
    db_root: Path,
    path: str,
    max_features: int,
) -> dict[str, object]:
    analysis_file = _resolve_analysis_file(path, "analysis_horizon_ic_matrix.parquet")
    analysis_path = str(analysis_file.relative_to(db_root / "features"))
    metadata = get_parquet_metadata(scope="features", path=analysis_path, db_root=db_root)
    schema = {column.name for column in metadata.columns}
    missing = sorted(_IC_COLUMNS - schema)
    if missing:
        raise HTTPException(status_code=400, detail=f"IC artifact missing columns: {', '.join(missing)}")

    frame = query_parquet(
        ParquetQuery(
            scope="features",
            path=analysis_path,
            columns=tuple(sorted(_IC_COLUMNS)),
            limit=None,
        ),
        db_root=db_root,
        metadata=metadata,
    ).frame
    total_rows = metadata.total_rows
    if total_rows == 0:
        return {
            "path": analysis_path,
            "total_rows": 0,
            "total_features": 0,
            "features": [],
            "horizons": [],
            "feature_index": [],
            "horizon": [],
            "mean_oriented_ic": [],
            "mean_validation_ic": [],
            "positive_fold_rate": [],
            "valid_folds": [],
        }

    top_features_frame = (
        frame.group_by("feature")
        .agg(pl.col("mean_oriented_ic").abs().max().alias("score"))
        .sort("score", descending=True)
        .head(max_features)
    )
    features = top_features_frame["feature"].to_list()
    feature_order = {feature: index for index, feature in enumerate(features)}
    horizons = frame.select("horizon").unique().sort("horizon")["horizon"].to_list()

    selected = frame.filter(pl.col("feature").is_in(features)).select(
        [
            "feature",
            "horizon",
            "mean_oriented_ic",
            "mean_validation_ic",
            "positive_fold_rate",
            "valid_folds",
        ]
    )
    rows = sorted(selected.iter_rows(named=True), key=lambda row: (feature_order[row["feature"]], row["horizon"]))

    return {
        "path": analysis_path,
        "total_rows": total_rows,
        "total_features": frame.select(pl.col("feature").n_unique()).item(),
        "features": features,
        "horizons": horizons,
        "feature_index": [feature_order[row["feature"]] for row in rows],
        "horizon": [row["horizon"] for row in rows],
        "mean_oriented_ic": [row["mean_oriented_ic"] for row in rows],
        "mean_validation_ic": [row["mean_validation_ic"] for row in rows],
        "positive_fold_rate": [row["positive_fold_rate"] for row in rows],
        "valid_folds": [row["valid_folds"] for row in rows],
    }


@router.get("/profile/{path:path}")
def profile_feature_parquet_features(
    path: str,
    query: str = Query("", description="Case-insensitive feature-name filter"),
    family: str = Query("all", description="Inferred feature family id"),
    sort: str = Query("schema", description="Feature sort order"),
    page: int = Query(1, ge=1, description="1-based feature page number"),
    page_size: int = Query(100, ge=1, le=250, description="Feature rows per page"),
    entity_column: str | None = Query(None, description="Optional entity column"),
    entity_value: str | None = Query(None, description="Optional entity value"),
    max_spark_points: int = Query(36, ge=1, le=80, description="Max sparkline points"),
    preset: str | None = Query(None, description="Registered preset column projection"),
) -> dict[str, object]:
    """Profile numeric feature columns for a parquet file in db/features."""
    return _cached_profile_feature_parquet_features(
        settings.db_root,
        path,
        query,
        family,
        sort,
        page,
        page_size,
        entity_column,
        entity_value,
        max_spark_points,
        _preset_columns(path, preset),
    )


def _preset_columns(path: str, preset: str | None) -> tuple[str, ...] | None:
    if preset is None or preset == "full":
        return None
    definitions = list_feature_presets("/".join(Path(path).parts[1:-1]))
    definition = next((item for item in definitions if item["name"] == preset), None)
    if definition is None:
        raise HTTPException(400, "Unknown feature preset")
    if not definition["columns"]:
        raise HTTPException(422, "This preset requires a build; no selected-column contract exists")
    return tuple(definition["columns"])


def _resolve_analysis_file(path: str, filename: str) -> Path:
    value = path.strip().strip("/")
    if not value:
        raise HTTPException(status_code=400, detail="path is required")
    segments = value.split("/")
    if any(segment in {"", ".", ".."} for segment in segments):
        raise HTTPException(status_code=400, detail="path contains invalid segments")
    if segments[-1] != "data.parquet":
        raise HTTPException(status_code=400, detail="Analysis paths must target data.parquet")

    target = settings.db_root / "features" / Path(*segments[:-1]) / filename
    if not target.exists():
        raise HTTPException(status_code=404, detail=f"Analysis artifact '{filename}' not found")
    return target


@router.get("/profile-detail/{path:path}")
def profile_feature_parquet_feature_detail(
    path: str,
    column: str = Query(..., description="Numeric feature column to inspect"),
    entity_column: str | None = Query(None, description="Optional entity column"),
    entity_value: str | None = Query(None, description="Optional entity value"),
    max_spark_points: int = Query(120, ge=20, le=500, description="Max detail sparkline points"),
) -> dict[str, object]:
    """Profile one numeric feature column for a parquet file in db/features."""
    return _cached_profile_feature_parquet_feature_detail(
        settings.db_root,
        path,
        column,
        entity_column,
        entity_value,
        max_spark_points,
    )


@ttl_cache(seconds=300, maxsize=4)
def _cached_feature_browser_stats():
    return compute_scope_stats(settings.db_root, "features")


def clear_feature_browser_cache() -> None:
    """Invalidate feature discovery and statistics after an explicit refresh."""
    _cached_discover_features.cache_clear()
    _cached_feature_browser_stats.cache_clear()


@router.get("/browser-stats")
def get_feature_browser_stats() -> dict[str, object]:
    """Get overall statistics about db/features."""
    return _cached_feature_browser_stats()


@router.get("")
def list_features() -> list[dict[str, Any]]:
    """List all available feature categories."""
    features = _cached_discover_features()

    by_res_cat: dict[str, dict[str, dict[str, Any]]] = {}
    for feature in features:
        resolution = feature["resolution"]
        category_path = feature["category_path"]

        if resolution not in by_res_cat:
            by_res_cat[resolution] = {}
        if category_path not in by_res_cat[resolution]:
            by_res_cat[resolution][category_path] = {
                "versions": [],
                "status": feature.get("category_meta", {}).get("status", "active"),
                "description": feature.get("category_meta", {}).get("description"),
                "asset_column": feature.get("category_meta", {}).get("asset_column"),
            }

    return [
        {
            "resolution": res,
            "categories": [
                {
                    "category_path": cat,
                    "versions": ["latest"],
                    "status": meta.get("status", "active"),
                    "description": meta.get("description"),
                    "asset_column": meta.get("asset_column"),
                }
                for cat, meta in sorted(cats.items())
            ],
        }
        for res, cats in sorted(by_res_cat.items())
    ]


@router.get("/{resolution}")
def list_resolution_features(resolution: str) -> list[dict[str, Any]]:
    """List all feature categories for a resolution."""
    features = _cached_discover_features()

    res_features = [f for f in features if f["resolution"] == resolution]
    if not res_features:
        raise HTTPException(
            status_code=404,
            detail=f"No features found for resolution '{resolution}'",
        )

    by_cat: dict[str, dict[str, Any]] = {}
    for feature in res_features:
        category_path = feature["category_path"]
        if category_path not in by_cat:
            by_cat[category_path] = {
                "versions": [],
                "status": feature.get("category_meta", {}).get("status", "active"),
                "description": feature.get("category_meta", {}).get("description"),
                "asset_column": feature.get("category_meta", {}).get("asset_column"),
            }

    return [
        {
            "category_path": cat,
            "versions": ["latest"],
            "status": meta.get("status", "active"),
            "description": meta.get("description"),
            "asset_column": meta.get("asset_column"),
        }
        for cat, meta in sorted(by_cat.items())
    ]


@router.get("/{resolution}/correlation")
def get_feature_correlation(
    resolution: str,
    category_path: str | None = Query(None, description="Nested feature category path"),
    version: str | None = Query(None, description="Feature version"),
) -> dict[str, Any]:
    """Get correlation matrix for features in a category."""
    feature = _resolve_feature(resolution, category_path or "", version or "")

    schema = read_parquet_schema(feature["path"])
    numeric_cols = [c for c, dt in schema.items() if dt in _NUMERIC_DTYPES]

    if len(numeric_cols) < 2:
        raise HTTPException(status_code=400, detail="Not enough numeric columns for correlation")

    df = read_parquet_frame(feature["path"], columns=numeric_cols)

    correlations = []
    for col1 in numeric_cols:
        row = []
        for col2 in numeric_cols:
            corr = df.select(pl.corr(col1, col2)).item()
            row.append(round(corr, 4) if corr is not None else None)
        correlations.append(row)

    return {
        "resolution": resolution,
        "category_path": feature["category_path"],
        "version": feature["version"],
        "columns": numeric_cols,
        "matrix": correlations,
    }
