"""Backtests and version-strategy API router."""

from __future__ import annotations

import json
import math
from datetime import timedelta
from pathlib import Path
from typing import Any

import polars as pl
from data.query import ParquetQuery, QueryError, query_parquet
from fastapi import APIRouter, HTTPException, Query, Request
from strategies.research_surface import (
    discover_strategy_versions_with_research,
    load_research_surface,
    research_display_state,
    summarize_returns,
)
from strategies.results import BacktestOutput
from strategies.versioned import (
    load_version_final_artifact,
    load_version_runs,
)

from ..config import settings
from ..parquet import read_parquet_frame, read_parquet_schema
from ..research_comparison import load_run_comparison
from ..research_rank import RankUnavailable, family_rank_comparison
from ..research_risk import grid_risk_metrics, observed_returns, surface_risk_metrics
from ..research_supplements import load_surface_supplements
from ..responses import polars_json_response, polars_nested_json_response, sample_display_rows, ttl_cache
from ..strategy_single_asset import (
    SingleAssetIntegrityError,
    SingleAssetSelectionError,
    load_single_asset_view,
)

router = APIRouter()

_DEFAULT_SURFACE_MAX_POINTS = 2_000


@ttl_cache(seconds=30)
def _cached_discover_saved_backtests():
    return _discover_saved_backtests(settings.db_root)


@ttl_cache(seconds=30)
def _cached_discover_strategy_versions():
    return discover_strategy_versions_with_research(settings.db_root)


def _discover_saved_backtests(db_root: Path) -> list[dict[str, Any]]:
    """Discover per-run saved artifacts under db/strategies/*/*/*."""
    strategies_dir = Path(db_root) / "strategies"
    if not strategies_dir.exists():
        return []

    discovered: list[dict[str, Any]] = []
    for strategy_type_dir in sorted(strategies_dir.iterdir()):
        if not strategy_type_dir.is_dir() or strategy_type_dir.name.startswith("_"):
            continue
        for strategy_id_dir in sorted(strategy_type_dir.iterdir()):
            if not strategy_id_dir.is_dir() or strategy_id_dir.name == "versions":
                continue
            for run_dir in sorted(strategy_id_dir.iterdir()):
                if not run_dir.is_dir():
                    continue
                try:
                    output = BacktestOutput.from_path(run_dir)
                except (FileNotFoundError, ValueError, OSError, json.JSONDecodeError):
                    continue
                discovered.append(
                    {
                        "strategy_type": strategy_type_dir.name,
                        "strategy_id": output.strategy_id,
                        "run_id": output.run_id,
                        "metrics": output.metrics,
                        "config": output.config,
                        "created_at": output.created_at.isoformat(),
                        "data_range": output.data_range,
                        "run_dir": run_dir,
                    }
                )
    return discovered


@router.get("")
def list_backtests() -> list[dict[str, Any]]:
    """List all available backtests."""
    backtests = _cached_discover_saved_backtests()
    return [
        {
            "strategy_id": bt["strategy_id"],
            "run_id": bt["run_id"],
            "metrics": bt["metrics"],
            "config": bt["config"],
            "created_at": bt["created_at"],
            "data_range": bt["data_range"],
        }
        for bt in backtests
    ]


def _get_strategy_type_description(strategy_type: str) -> str:
    descriptions = {
        "unknown": "Uncategorized strategy runs.",
    }
    return descriptions.get(strategy_type, f"Strategy type: {strategy_type}")


@router.get("/strategy-types")
def list_strategy_types() -> list[dict[str, Any]]:
    """List all strategy types with aggregate statistics."""
    versions = _cached_discover_strategy_versions()
    if versions:
        stats_by_type: dict[str, dict[str, Any]] = {}
        for row in versions:
            st = row["strategy_type"]
            stats = stats_by_type.setdefault(
                st,
                {
                    "strategy_type": st,
                    "description": _get_strategy_type_description(st),
                    "total_runs": 0,
                    "version_count": 0,
                    "versions": [],
                    "finalized_versions": 0,
                    "best_sharpe": None,
                    "latest_run": None,
                },
            )
            stats["total_runs"] += int(row.get("total_runs") or 0)
            stats["version_count"] += 1
            stats["versions"].append(str(row["memory_version"]))
            if row.get("has_final"):
                stats["finalized_versions"] += 1
            sharpe = row.get("best_sharpe")
            if sharpe is not None and (stats["best_sharpe"] is None or sharpe > stats["best_sharpe"]):
                stats["best_sharpe"] = sharpe
            latest = row.get("latest_run")
            if latest and (stats["latest_run"] is None or latest > stats["latest_run"]):
                stats["latest_run"] = latest

        for stats in stats_by_type.values():
            stats["versions"] = sorted(set(stats["versions"]))
        result = sorted(stats_by_type.values(), key=lambda x: x["total_runs"], reverse=True)
        return result

    backtests = _cached_discover_saved_backtests()
    type_stats: dict[str, dict[str, Any]] = {}
    for bt in backtests:
        st = bt["strategy_type"]
        if st not in type_stats:
            type_stats[st] = {
                "strategy_type": st,
                "description": _get_strategy_type_description(st),
                "total_runs": 0,
                "version_count": 0,
                "versions": [],
                "finalized_versions": 0,
                "best_sharpe": None,
                "latest_run": None,
            }
        type_stats[st]["total_runs"] += 1
        sharpe = bt.get("metrics", {}).get("sharpe")
        if sharpe is not None and (type_stats[st]["best_sharpe"] is None or sharpe > type_stats[st]["best_sharpe"]):
            type_stats[st]["best_sharpe"] = sharpe
        created_at = bt.get("created_at")
        if created_at and (type_stats[st]["latest_run"] is None or created_at > type_stats[st]["latest_run"]):
            type_stats[st]["latest_run"] = created_at
    return sorted(type_stats.values(), key=lambda x: x["total_runs"], reverse=True)


@router.get("/strategy-types/{strategy_type}/versions")
def list_versions_for_type(strategy_type: str) -> list[dict[str, Any]]:
    """List memory versions for a strategy type."""
    versions = [row for row in _cached_discover_strategy_versions() if row["strategy_type"] == strategy_type]
    if not versions:
        raise HTTPException(status_code=404, detail=f"No versions found for strategy type '{strategy_type}'")
    return [
        {
            **row,
            "run_count": row.get("total_runs", 0),
        }
        for row in versions
    ]


@router.get("/strategy-types/{strategy_type}/versions/{memory_version}/runs")
def get_version_runs(strategy_type: str, memory_version: str):
    """Get summary run table for one strategy memory version."""
    df = load_version_runs(settings.db_root, strategy_type, memory_version)
    if df.is_empty():
        raise HTTPException(status_code=404, detail=f"No runs found for '{strategy_type}/{memory_version}'")
    return polars_json_response({
        "strategy_type": strategy_type,
        "memory_version": memory_version,
        "columns": df.columns,
        "data": df.sort("created_at", descending=True),
    })


@router.get("/strategy-types/{strategy_type}/versions/{memory_version}/surface")
def get_version_surface(
    request: Request,
    strategy_type: str,
    memory_version: str,
    max_points: int = Query(default=_DEFAULT_SURFACE_MAX_POINTS, ge=50, le=5_000),
):
    """Return the validated selected research surface for one strategy version."""
    try:
        loaded = load_research_surface(settings.db_root, strategy_type, memory_version)
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError, pl.exceptions.PolarsError) as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Invalid research surface for '{strategy_type}/{memory_version}'",
        ) from exc
    if loaded is None:
        raise HTTPException(
            status_code=404,
            detail=f"No research surface found for '{strategy_type}/{memory_version}'",
        )
    frame, manifest = loaded
    display_frame = sample_display_rows(frame, max_points=max_points)
    try:
        supplements = (
            load_surface_supplements(request.app, settings.db_root, manifest, frame, display_frame["date"].to_list())
            if "date" in display_frame.columns
            else {}
        )
    except (KeyError, OSError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="Invalid selected surface supplement") from exc
    # Supplement immutable published metrics from the complete observed NAV path.
    if manifest.get("metrics") is not None:
        manifest = {
            **manifest,
            "metrics": {
                role: {
                    **values,
                    **surface_risk_metrics(
                        frame[f"{role}_portfolio_value"].to_list(), frame["date"].to_list(),
                        first_return=frame[f"{role}_daily_return"][0],
                    ),
                }
                for role, values in manifest["metrics"].items()
            },
        }
    comparison, comparison_issue = load_run_comparison(settings.db_root, manifest, frame)
    if comparison is not None:
        comparison_frame = comparison["data"]
        sampled_comparison = sample_display_rows(comparison_frame, max_points=max_points)
        comparison = {
            **comparison,
            "metrics": {
                **comparison["metrics"],
                **surface_risk_metrics(
                    comparison_frame["portfolio_value"].to_list(), comparison_frame["date"].to_list(),
                    first_return=comparison_frame["daily_return"][0],
                ),
            },
            "points_total": comparison_frame.height,
            "points_returned": sampled_comparison.height,
            "data": sampled_comparison,
        }
    return polars_nested_json_response({
        **manifest,
        "display_state": research_display_state(manifest),
        "columns": display_frame.columns,
        "points_total": frame.height,
        "points_returned": display_frame.height,
        "downsampled": display_frame.height < frame.height,
        "data": display_frame,
        "comparison": comparison,
        "comparison_issue": comparison_issue,
        "supplements": supplements,
    })


@router.get("/strategy-types/{strategy_type}/versions/{memory_version}/single-asset")
def get_version_single_asset(
    strategy_type: str,
    memory_version: str,
    asset: str | None = None,
    config_id: str | None = None,
    max_points: int = Query(default=_DEFAULT_SURFACE_MAX_POINTS, ge=50, le=5_000),
):
    """Return one selected-run asset's marked weight, net contribution and price."""
    version = next(
        (
            row
            for row in _cached_discover_strategy_versions()
            if row["strategy_type"] == strategy_type and row["memory_version"] == memory_version
        ),
        None,
    )
    if version is None:
        raise HTTPException(
            status_code=404,
            detail=f"No version found for '{strategy_type}/{memory_version}'",
        )
    try:
        payload = load_single_asset_view(
            settings.db_root,
            strategy_type,
            memory_version,
            asset=asset,
            config_id=config_id,
            expected_run_id=version.get("selected_run_id"),
            max_points=max_points,
        )
    except SingleAssetSelectionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (
        SingleAssetIntegrityError,
        QueryError,
        pl.exceptions.PolarsError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        raise HTTPException(
            status_code=409,
            detail=f"Selected-run asset attribution is unavailable for '{strategy_type}/{memory_version}'",
        ) from exc
    return polars_json_response(payload)


def _research_grid_path(strategy_type: str, memory_version: str, relative_path: str) -> str:
    return f"strategies/{strategy_type}/{memory_version}/{relative_path}"


def _load_research_grid(strategy_type: str, memory_version: str) -> tuple[pl.DataFrame, dict[str, Any]]:
    try:
        loaded = load_research_surface(settings.db_root, strategy_type, memory_version)
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError, pl.exceptions.PolarsError) as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Invalid research surface for '{strategy_type}/{memory_version}'",
        ) from exc
    if loaded is None or not isinstance(loaded[1].get("grid"), dict):
        raise HTTPException(
            status_code=404,
            detail=f"No optimizer grid found for '{strategy_type}/{memory_version}'",
        )
    return loaded


@router.get("/strategy-types/{strategy_type}/versions/{memory_version}/surface/grid")
def get_version_surface_grid(strategy_type: str, memory_version: str):
    """Return one optimizer-grid summary."""
    _, manifest = _load_research_grid(strategy_type, memory_version)
    grid = manifest["grid"]
    summary = grid["summary"]
    series = grid["series"]
    try:
        result = query_parquet(
            ParquetQuery(
                scope="research",
                path=_research_grid_path(strategy_type, memory_version, summary["path"]),
                limit=int(summary["row_count"]),
                order_by="rank",
            ),
            db_root=settings.db_root,
        )
        streams = query_parquet(
            ParquetQuery(
                scope="research",
                path=_research_grid_path(strategy_type, memory_version, series["path"]),
                columns=(series["config_id_column"], series["date_column"], series["return_column"]),
                limit=int(series["row_count"]),
            ),
            db_root=settings.db_root,
        ).frame.select(
            pl.col(series["config_id_column"]).cast(pl.String).alias("config_id"),
            pl.col(series["date_column"]).cast(pl.Date).alias("date"),
            pl.col(series["return_column"]).cast(pl.Float64).alias("daily_return"),
        )
        supplements = grid_risk_metrics(streams)
        missing = [key for key in ("sortino", "martin", "observed_days") if key not in result.frame.columns]
        frame = result.frame.join(supplements.select("config_id", *missing), on="config_id", how="left", validate="1:1", maintain_order="left")
    except (QueryError, ValueError, pl.exceptions.PolarsError) as exc:
        raise HTTPException(status_code=404, detail="Optimizer grid summary is unavailable") from exc
    metric_keys = {metric["key"] for metric in grid["metrics"]}
    return polars_json_response(
        {
            **grid,
            "metrics": [*grid["metrics"], *[
                {"key": key, "label": f"{key.title()} ratio", "format": "number", "higher_is_better": True, "nullable": True}
                for key in ("sortino", "martin") if key not in metric_keys
            ]],
            "columns": frame.columns,
            "data": frame,
        }
    )


@router.get("/strategy-types/{strategy_type}/versions/{memory_version}/surface/grid/configurations/{config_id}")
def get_version_surface_grid_configuration(
    strategy_type: str,
    memory_version: str,
    config_id: str,
):
    """Return one complete static optimizer stream beside its control and benchmark."""
    benchmark, manifest = _load_research_grid(strategy_type, memory_version)
    grid = manifest["grid"]
    summary_meta = grid["summary"]
    series_meta = grid["series"]
    summary_path = _research_grid_path(strategy_type, memory_version, summary_meta["path"])
    series_path = _research_grid_path(strategy_type, memory_version, series_meta["path"])
    control_id = str(grid["control_config_id"])
    benchmark_meta = manifest["benchmark"]
    benchmark_id = str(benchmark_meta["id"]) if isinstance(benchmark_meta, dict) else ""
    config_column = str(series_meta["config_id_column"])
    date_column = str(series_meta["date_column"])
    return_column = str(series_meta["return_column"])
    try:
        summary = query_parquet(
            ParquetQuery(
                scope="research",
                path=summary_path,
                entity_column="config_id",
                entity_values=tuple(dict.fromkeys((config_id, control_id))),
                limit=2,
            ),
            db_root=settings.db_root,
        ).frame
        streams = query_parquet(
            ParquetQuery(
                scope="research",
                path=series_path,
                columns=(config_column, date_column, return_column),
                entity_column=config_column,
                # A benchmark that is itself a grid configuration (e.g. the hold control) reads its own path.
                entity_values=tuple(dict.fromkeys((config_id, control_id, benchmark_id))),
                limit=None,
                order_by=date_column,
            ),
            db_root=settings.db_root,
        ).frame
    except QueryError as exc:
        raise HTTPException(status_code=404, detail="Optimizer grid stream is unavailable") from exc

    selected_rows = summary.filter(pl.col("config_id") == config_id)
    control_rows = summary.filter(pl.col("config_id") == control_id)
    if selected_rows.height != 1:
        raise HTTPException(status_code=404, detail=f"Unknown optimizer configuration '{config_id}'")
    if control_rows.height != 1:
        raise HTTPException(status_code=404, detail="Optimizer grid control configuration is unavailable")

    def stream_for(identifier: str, prefix: str) -> pl.DataFrame:
        frame = (
            streams.filter(pl.col(config_column) == identifier)
            .select(
                pl.col(date_column).cast(pl.Date).alias("date"),
                pl.col(return_column).cast(pl.Float64).alias(f"{prefix}_daily_return"),
            )
            .sort("date")
        )
        if frame.is_empty() or frame["date"].n_unique() != frame.height:
            raise HTTPException(status_code=404, detail=f"Optimizer grid {prefix} stream is incomplete")
        return frame

    selected_stream = stream_for(config_id, "selected")
    control_stream = stream_for(control_id, "control")
    try:
        # One ordered display calendar: every date either grid account carries, observed or not.
        calendar = selected_stream.join(control_stream, on="date", how="full", coalesce=True, validate="1:1").sort("date")
        if streams.filter(pl.col(config_column) == benchmark_id).height:
            benchmark_stream, starts_earlier = stream_for(benchmark_id, "benchmark"), False
        else:
            # Other benchmarks keep their own published coverage on the display calendar.
            benchmark_stream = benchmark.select("date", "benchmark_daily_return")
            starts_earlier = bool(benchmark_stream.select(pl.col("date").min() < calendar["date"].min()).item())
        comparison = calendar.join(benchmark_stream, on="date", how="left", validate="1:1").sort("date")
        if starts_earlier:
            # The grid window starts after the benchmark's: its first day is the starting mark, as for the grid streams.
            comparison = comparison.with_columns(
                pl.when((pl.int_range(pl.len()) == 0) & pl.col("benchmark_daily_return").is_not_null())
                .then(0.0).otherwise(pl.col("benchmark_daily_return"))
                .alias("benchmark_daily_return"))
        roles = ("selected", "control", "benchmark")
        # Values compound each role's own observed returns; a missing day stays null, never a flat mark.
        comparison = comparison.with_columns(
            ((pl.col(f"{role}_daily_return") + 1.0).cum_prod() * 100.0).alias(f"{role}_portfolio_value")
            for role in roles
        ).select("date", *[f"{role}_{field}" for role in roles for field in ("daily_return", "portfolio_value")])
        observed = {role: observed_returns(comparison, f"{role}_daily_return") for role in roles}
    except (QueryError, ValueError, pl.exceptions.PolarsError) as exc:
        raise HTTPException(status_code=404, detail="Optimizer grid stream is unavailable") from exc
    if observed["selected"].is_empty() or observed["control"].is_empty():
        raise HTTPException(status_code=404, detail="Optimizer grid account has no observed returns")
    metrics: dict[str, Any] = {}
    coverage: dict[str, Any] = {}
    for role, rows in observed.items():
        coverage[role] = {
            "observed_days": rows.height,
            "first_date": rows["date"][0].isoformat() if rows.height else None,
            "last_date": rows["date"][-1].isoformat() if rows.height else None,
        }
        if not rows.height:
            metrics[role] = None
            continue
        returns = rows[f"{role}_daily_return"].to_list()
        expected = summarize_returns(returns)["ending_value"]
        actual = rows[f"{role}_portfolio_value"][-1]
        if expected is None or not math.isclose(expected, actual, rel_tol=1e-10, abs_tol=1e-8):
            raise HTTPException(status_code=404, detail=f"Optimizer grid {role} values do not reconcile")
        metrics[role] = {
            **summarize_returns(returns),
            **surface_risk_metrics(
                rows[f"{role}_portfolio_value"].to_list(), rows["date"].to_list(), first_return=returns[0],
            ),
        }

    return polars_json_response(
        {
            "config": selected_rows.row(0, named=True),
            "control": control_rows.row(0, named=True),
            "benchmark": manifest["benchmark"],
            "metrics": metrics,
            "coverage": {"calendar_days": comparison.height, **coverage},
            "columns": comparison.columns,
            "data": _break_missing_days(comparison),
        }
    )


def _break_missing_days(frame: pl.DataFrame) -> pl.DataFrame:
    """Daily grid paths skip excluded calendar intervals; one all-null row after each skip ends the line there."""
    gap = frame["date"].diff().shift(-1) > timedelta(days=1)
    if not gap.fill_null(False).any():
        return frame
    breaks = frame.filter(gap.fill_null(False)).select(pl.col("date") + timedelta(days=1)).with_columns(
        pl.lit(None, dtype=pl.Float64).alias(name) for name in frame.columns if name != "date")
    return pl.concat([frame, breaks.select(frame.columns)]).sort("date")


@ttl_cache(seconds=60, maxsize=32)
def _cached_version_rank(db_root: Path, strategy_type: str, memory_version: str) -> dict[str, Any]:
    versions = [row for row in _cached_discover_strategy_versions() if row["strategy_type"] == strategy_type]
    return family_rank_comparison(db_root, versions, strategy_type, memory_version)


@router.get("/strategy-types/{strategy_type}/versions/{memory_version}/surface/rank")
def get_version_surface_rank(strategy_type: str, memory_version: str) -> dict[str, Any]:
    """Rank displayed configurations against each other published version's primary path."""
    try:
        return _cached_version_rank(settings.db_root, strategy_type, memory_version)
    except RankUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/strategy-types/{strategy_type}/versions/{memory_version}/final")
def get_version_final(strategy_type: str, memory_version: str):
    """Get the single finalized backtest artifact for one strategy memory version."""
    loaded = load_version_final_artifact(settings.db_root, strategy_type, memory_version)
    if loaded is None:
        raise HTTPException(status_code=404, detail=f"No final artifact found for '{strategy_type}/{memory_version}'")

    df, meta = loaded
    return polars_json_response({
        "strategy_type": strategy_type,
        "memory_version": memory_version,
        "metrics": meta.get("metrics", {}),
        "config": meta.get("config", {}),
        "selected_run_id": meta.get("selected_run_id"),
        "created_at": meta.get("created_at"),
        "data_range": meta.get("data_range"),
        "data": df,
        "columns": df.columns,
    })


@router.get("/by-type/{strategy_type}")
def list_runs_by_type(strategy_type: str) -> list[dict[str, Any]]:
    """List all saved preset/run directories for a type."""
    backtests = _cached_discover_saved_backtests()
    runs = [bt for bt in backtests if bt["strategy_type"] == strategy_type]
    if not runs:
        raise HTTPException(status_code=404, detail=f"No backtests found for strategy type '{strategy_type}'")
    return [
        {
            "preset": bt["strategy_id"],
            "strategy_type": bt["strategy_type"],
            "run_id": bt["run_id"],
            "metrics": bt["metrics"],
            "config": bt["config"],
            "created_at": bt["created_at"],
            "data_range": bt["data_range"],
        }
        for bt in runs
    ]


@router.get("/{strategy_id}")
def list_strategy_runs(strategy_id: str) -> list[dict[str, Any]]:
    """List runs for a preset/strategy_id."""
    backtests = _cached_discover_saved_backtests()
    runs = [bt for bt in backtests if bt["strategy_id"] == strategy_id]
    if not runs:
        raise HTTPException(status_code=404, detail=f"Strategy '{strategy_id}' not found")
    return [
        {
            "run_id": bt["run_id"],
            "metrics": bt["metrics"],
            "config": bt["config"],
            "created_at": bt["created_at"],
            "data_range": bt["data_range"],
        }
        for bt in runs
    ]


def _parse_timestamp_param(timestamp: str) -> Any:
    from datetime import datetime as dt

    try:
        return dt.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="Invalid timestamp format. Use ISO-8601 (e.g., 2024-01-05T00:00:00Z).",
        ) from exc


def _find_backtest_dir(strategy_id: str, run_id: str, strategy_type: str | None = None) -> Path | None:
    """Find a saved backtest directory under the strategy result tree."""
    if strategy_type:
        new_path = settings.db_root / "strategies" / strategy_type / strategy_id / run_id
        if (new_path / "backtest.parquet").exists():
            return new_path

    strategies_dir = settings.db_root / "strategies"
    if strategies_dir.exists():
        for type_dir in strategies_dir.iterdir():
            if not type_dir.is_dir():
                continue
            candidate = type_dir / strategy_id / run_id
            if (candidate / "backtest.parquet").exists():
                return candidate

    return None


@router.get("/{strategy_id}/{run_id}")
def get_backtest(strategy_id: str, run_id: str):
    """Return detailed backtest data including equity curve."""
    backtest_dir = _find_backtest_dir(strategy_id, run_id)
    if backtest_dir is None:
        raise HTTPException(status_code=404, detail=f"Backtest '{strategy_id}/{run_id}' not found")

    df = read_parquet_frame(backtest_dir / "backtest.parquet")
    meta = {}
    meta_file = backtest_dir / "meta.json"
    if meta_file.exists():
        meta = json.loads(meta_file.read_text())

    return polars_json_response({
        "strategy_id": strategy_id,
        "strategy_type": meta.get("strategy_type", "unknown"),
        "run_id": run_id,
        "metrics": meta.get("metrics", {}),
        "config": meta.get("config", {}),
        "created_at": meta.get("created_at"),
        "data_range": meta.get("data_range"),
        "data": df,
        "columns": df.columns,
    })


@router.get("/{strategy_id}/{run_id}/equity")
def get_equity_curve(strategy_id: str, run_id: str):
    """Return just equity curve data."""
    backtest_dir = _find_backtest_dir(strategy_id, run_id)
    if backtest_dir is None:
        raise HTTPException(status_code=404, detail=f"Backtest '{strategy_id}/{run_id}' not found")

    backtest_file = backtest_dir / "backtest.parquet"
    schema = read_parquet_schema(backtest_file)
    col_names = list(schema.keys())

    equity_col = next((col for col in ["equity", "cumulative_return", "cum_return", "portfolio_value"] if col in col_names), None)
    date_col = next((col for col in ["date", "datetime", "timestamp", "time"] if col in col_names), None)

    if equity_col is None:
        df = read_parquet_frame(backtest_file)
        numeric_cols = [col for col in df.columns if df[col].dtype in [pl.Float64, pl.Float32, pl.Int64]]
        return polars_json_response({"columns": df.columns, "numeric_columns": numeric_cols, "data": df})

    cols = [c for c in [date_col, equity_col] if c]
    df = read_parquet_frame(backtest_file, columns=cols)
    if not date_col:
        df = df.with_row_index("index")

    return polars_json_response({"date_column": date_col, "equity_column": equity_col, "data": df})


@router.get("/{strategy_id}/{run_id}/artifacts")
def get_backtest_artifacts(strategy_id: str, run_id: str) -> dict[str, bool]:
    """Check which optional ML tracking artifacts are available."""
    backtest_dir = _find_backtest_dir(strategy_id, run_id)
    if backtest_dir is None:
        raise HTTPException(status_code=404, detail=f"Backtest '{strategy_id}/{run_id}' not found")
    return {
        "has_rankings": (backtest_dir / "rankings.parquet").exists(),
        "has_weights": (backtest_dir / "weights.parquet").exists(),
        "has_ic_series": (backtest_dir / "ic_series.parquet").exists(),
    }


@router.get("/{strategy_id}/{run_id}/rankings")
def get_backtest_rankings(strategy_id: str, run_id: str, timestamp: str | None = None, limit: int = 1000):
    backtest_dir = _find_backtest_dir(strategy_id, run_id)
    if backtest_dir is None:
        raise HTTPException(status_code=404, detail=f"Backtest '{strategy_id}/{run_id}' not found")
    rankings_file = backtest_dir / "rankings.parquet"
    if not rankings_file.exists():
        raise HTTPException(status_code=404, detail=f"No rankings data for '{strategy_id}/{run_id}'")

    df = read_parquet_frame(rankings_file)
    if timestamp:
        df = df.filter(pl.col("timestamp") == _parse_timestamp_param(timestamp))
    total_rows = len(df)
    unique_timestamps = df["timestamp"].unique().sort().to_list()
    df = df.head(limit)
    return polars_json_response({
        "columns": df.columns,
        "timestamps": [str(t) for t in unique_timestamps],
        "total_rows": total_rows,
        "returned_rows": len(df),
        "data": df,
    })


@router.get("/{strategy_id}/{run_id}/weights")
def get_backtest_weights(strategy_id: str, run_id: str, timestamp: str | None = None, limit: int = 1000):
    backtest_dir = _find_backtest_dir(strategy_id, run_id)
    if backtest_dir is None:
        raise HTTPException(status_code=404, detail=f"Backtest '{strategy_id}/{run_id}' not found")
    weights_file = backtest_dir / "weights.parquet"
    if not weights_file.exists():
        raise HTTPException(status_code=404, detail=f"No weights data for '{strategy_id}/{run_id}'")

    df = read_parquet_frame(weights_file)
    if timestamp:
        df = df.filter(pl.col("timestamp") == _parse_timestamp_param(timestamp))
    total_rows = len(df)
    unique_timestamps = df["timestamp"].unique().sort().to_list()
    df = df.with_columns(
        pl.when(pl.col("weight") > 0).then(pl.lit("LONG"))
        .when(pl.col("weight") < 0).then(pl.lit("SHORT"))
        .otherwise(pl.lit("NEUTRAL"))
        .alias("side")
    ).head(limit)
    return polars_json_response({
        "columns": df.columns,
        "timestamps": [str(t) for t in unique_timestamps],
        "total_rows": total_rows,
        "returned_rows": len(df),
        "data": df,
    })


@router.get("/{strategy_id}/{run_id}/ic")
def get_backtest_ic(strategy_id: str, run_id: str):
    backtest_dir = _find_backtest_dir(strategy_id, run_id)
    if backtest_dir is None:
        raise HTTPException(status_code=404, detail=f"Backtest '{strategy_id}/{run_id}' not found")
    ic_file = backtest_dir / "ic_series.parquet"
    if not ic_file.exists():
        raise HTTPException(status_code=404, detail=f"No IC series data for '{strategy_id}/{run_id}'")

    df = read_parquet_frame(ic_file)
    ic_values = df["ic"].drop_nulls()
    stats = {
        "mean_ic": float(ic_values.mean()) if len(ic_values) > 0 else None,
        "std_ic": float(ic_values.std()) if len(ic_values) > 1 else None,
        "min_ic": float(ic_values.min()) if len(ic_values) > 0 else None,
        "max_ic": float(ic_values.max()) if len(ic_values) > 0 else None,
        "positive_pct": float((ic_values > 0).mean()) if len(ic_values) > 0 else None,
        "ic_ir": float(ic_values.mean() / ic_values.std()) if len(ic_values) > 1 and ic_values.std() not in (0, None) else None,
    }
    return polars_json_response({
        "columns": df.columns,
        "stats": stats,
        "total_rows": len(df),
        "data": df,
    })
