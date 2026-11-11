"""Signals API router."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import polars as pl
from fastapi import APIRouter, HTTPException, Query, Response
from signals.research_surface import load_research_surface, load_surface_table
from signals.research_versions import FAMILIES_ROOT, discover_signal_research_versions
from strategies.records import family_versions

from ..config import settings
from ..parquet import count_parquet_rows, read_parquet_frame
from ..responses import polars_json_response, ttl_cache

router = APIRouter()

# A sealed research attempt is addressed only by these segments; anything that could
# leave the discovery layout (separators, `..`, dotfiles) is refused before any join.
_RESEARCH_SEGMENT_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_RESEARCH_VERSION_PATTERN = re.compile(r"^v[0-9]{3}$")

UNVERSIONED_PRODUCTION = "production"
_PREFERRED_DATE_COLUMNS = ("timestamp", "date", "datetime", "time")
_LATEST_DATE_COLUMNS = ("predicted_at", "timestamp", "date", "datetime", "time")
# Bookkeeping a runner carries alongside its predictions. Numeric dtype alone does not make
# a column a prediction: `horizon_days` and `observed_through_epoch_us` are both numeric.
_META_COLUMNS = {
    "run_id",
    "predicted_at",
    "timestamp",
    "date",
    "datetime",
    "time",
    "asset",
    "observed_through",
    "observed_through_epoch_us",
    "horizon_days",
    "signal_name",
    "model_id",
}


@ttl_cache(seconds=300)
def _active_signal_catalog() -> dict[str, int | None] | None:
    """Return active signal types and their registered production engine versions.

    Returns ``None`` when the registry cannot be resolved so discovery falls back
    to surfacing every persisted output rather than hiding the whole list.
    """
    try:
        from signals.api import list_catalog

        return {
            str(row["signal_type"]): (row["engine_version"] if isinstance(row.get("engine_version"), int) else None)
            for row in list_catalog()
            if row.get("status") == "active" and row.get("signal_type")
        }
    except Exception:  # pragma: no cover - registry import is a soft dependency
        return None


@ttl_cache(seconds=300)
def _active_signal_types_by_id() -> dict[str, str]:
    """Map each active family's persisted signal ids (preset ``name``) to its current family name.

    Signal ids survive family renames, so this is authoritative over the family recorded in
    older ``runs.json`` entries; empty when the registry cannot be resolved.
    """
    try:
        from signals.api import list_catalog

        return {
            str(signal_id): str(row["signal_type"])
            for row in list_catalog()
            if row.get("status") == "active" and row.get("signal_type")
            for signal_id in row.get("signal_ids") or ()
        }
    except Exception:  # pragma: no cover - registry import is a soft dependency
        return {}


@ttl_cache(seconds=30)
def _cached_discover_signals() -> list[dict[str, Any]]:
    return discover_signals(settings.db_root, _active_signal_catalog(), _active_signal_types_by_id())


@ttl_cache(seconds=30)
def _cached_discover_signal_research_versions() -> list[dict[str, Any]]:
    return discover_signal_research_versions(settings.db_root)


def _signal_dir(signal_id: str) -> Path:
    return settings.db_root / "signals" / signal_id


def _predictions_path(signal_id: str) -> Path:
    return _signal_dir(signal_id) / "predictions.parquet"


def _load_signal_frame(signal_id: str) -> pl.DataFrame:
    predictions_path = _predictions_path(signal_id)
    if not predictions_path.exists():
        raise HTTPException(status_code=404, detail=f"Signal '{signal_id}' not found")
    return read_parquet_frame(predictions_path)


def _load_runs_metadata(signal_id: str) -> dict[str, dict[str, Any]]:
    runs_path = _signal_dir(signal_id) / "runs.json"
    if not runs_path.exists():
        return {}
    payload = json.loads(runs_path.read_text(encoding="utf-8"))
    runs = payload.get("runs", {})
    return runs if isinstance(runs, dict) else {}


def _signal_type_from_runs(runs_metadata: dict[str, dict[str, Any]]) -> str | None:
    # Newest run first: a renamed family keeps its signal ids, so older runs carry the old name.
    for run in reversed(runs_metadata.values()):
        config = run.get("config")
        if isinstance(config, dict):
            signal_type = config.get("signal_type")
            if signal_type:
                return str(signal_type)
    return None


def _pick_date_column(columns: list[str], *, latest: bool = False) -> str | None:
    preferred = _LATEST_DATE_COLUMNS if latest else _PREFERRED_DATE_COLUMNS
    for column in preferred:
        if column in columns:
            return column
    return None


def _prediction_columns(df: pl.DataFrame) -> list[str]:
    columns: list[str] = []
    for column in df.columns:
        if column in _META_COLUMNS:
            continue
        dtype = df.schema[column]
        if hasattr(dtype, "is_numeric") and dtype.is_numeric():
            columns.append(column)
    return columns


def _iso_or_none(value: Any) -> str | None:
    """Render a date-like scalar as an ISO string, or ``None`` when absent."""
    if value is None:
        return None
    isoformat = getattr(value, "isoformat", None)
    return isoformat() if callable(isoformat) else str(value)


def _prediction_bounds(df: pl.DataFrame) -> tuple[str | None, str | None]:
    """Return the first and last prediction dates of a frame as ISO strings.

    This is the prediction clock, not the run clock: a signal whose runner fired
    last night over three-month-old inputs is stale, and only these two answer that.
    """
    column = _pick_date_column(df.columns)
    if column is None or df.is_empty():
        return None, None
    bounds = df.select(pl.col(column).min().alias("first"), pl.col(column).max().alias("last")).row(0)
    return _iso_or_none(bounds[0]), _iso_or_none(bounds[1])


def _serialize_scalar(value: Any) -> Any:
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return value
    return value


def _run_summaries(signal_id: str, df: pl.DataFrame) -> list[dict[str, Any]]:
    if "run_id" in df.columns:
        run_ids = sorted(value for value in df["run_id"].drop_nulls().unique().to_list() if value is not None)
    else:
        run_ids = ["latest"]
        df = df.with_columns(pl.lit("latest").alias("run_id"))

    latest_column = _pick_date_column(df.columns, latest=True)
    summaries: list[dict[str, Any]] = []
    runs_metadata = _load_runs_metadata(signal_id)

    for run_id in run_ids:
        run_df = df.filter(pl.col("run_id") == run_id)
        metadata = runs_metadata.get(str(run_id), {})
        row: dict[str, Any] = {
            "signal_id": signal_id,
            "run_id": run_id,
            "row_count": len(run_df),
        }
        if latest_column is not None:
            row["latest_timestamp"] = run_df.select(pl.col(latest_column).max()).item()
        row["first_prediction"], row["latest_prediction"] = _prediction_bounds(run_df)
        metrics = metadata.get("metrics")
        if isinstance(metrics, dict):
            row["metrics"] = metrics
            accuracy = metrics.get("accuracy")
            if accuracy is not None:
                row["accuracy"] = accuracy
        for field in ("config", "created_at", "data_range", "metadata"):
            if field in metadata:
                row[field] = metadata[field]
        summaries.append(row)

    if latest_column is not None:
        summaries.sort(
            key=lambda row: (
                row.get("latest_timestamp") is not None,
                row.get("latest_timestamp"),
                row["run_id"],
            ),
            reverse=True,
        )
    else:
        summaries.sort(key=lambda row: row["run_id"], reverse=True)
    return summaries


def discover_signals(
    db_root: Path,
    active_catalog: dict[str, int | None] | None = None,
    signal_types_by_id: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    signals_dir = db_root / "signals"
    if not signals_dir.exists():
        return []

    rows: list[dict[str, Any]] = []
    for signal_dir in sorted(path for path in signals_dir.iterdir() if path.is_dir()):
        predictions_path = signal_dir / "predictions.parquet"
        if not predictions_path.exists():
            continue
        signal_type = (signal_types_by_id or {}).get(signal_dir.name) or _signal_type_from_runs(
            _load_runs_metadata(signal_dir.name)
        )
        if active_catalog is not None and signal_type not in active_catalog:
            continue
        df = read_parquet_frame(predictions_path)
        summaries = _run_summaries(signal_dir.name, df)
        best_accuracy = max(
            (summary.get("accuracy") for summary in summaries if isinstance(summary.get("accuracy"), int | float)),
            default=None,
        )
        best_auc = max(
            (
                summary["metrics"].get("auc")
                for summary in summaries
                if isinstance(summary.get("metrics"), dict) and isinstance(summary["metrics"].get("auc"), int | float)
            ),
            default=None,
        )
        latest_summary = summaries[0] if summaries else {}
        latest_config = latest_summary.get("config")
        first_prediction, latest_prediction = _prediction_bounds(df)
        engine_version = active_catalog.get(signal_type) if active_catalog is not None else None
        rows.append(
            {
                "signal_id": signal_dir.name,
                "signal_type": signal_type,
                "production_version": f"v{engine_version:03d}" if engine_version is not None else None,
                "description": (str(latest_config.get("description", "")) if isinstance(latest_config, dict) else ""),
                "row_count": len(df),
                "run_count": len(summaries),
                "best_accuracy": best_accuracy,
                "best_auc": best_auc,
                "latest_run": latest_summary.get("latest_timestamp"),
                "latest_run_id": latest_summary.get("run_id"),
                "first_prediction": first_prediction,
                "latest_prediction": latest_prediction,
            }
        )
    return rows


def _discover_signal_versions_with_research() -> list[dict[str, Any]]:
    """Merge persisted production engine versions with research lifecycle versions."""
    merged = {(row["signal_family"], row["memory_version"]): row for row in _cached_discover_signal_research_versions()}
    canonical: dict[tuple[str, str], dict[str, Any]] = {}
    for signal in _cached_discover_signals():
        signal_family = signal.get("signal_type")
        # Families with no registered engine version still list their persisted signals.
        memory_version = signal.get("production_version") or UNVERSIONED_PRODUCTION
        if not isinstance(signal_family, str):
            continue
        key = (signal_family, memory_version)
        row = canonical.setdefault(
            key,
            {
                "signal_family": signal_family,
                "memory_version": memory_version,
                "total_runs": 0,
                "run_count": 0,
                "latest_run": None,
                "state": "promoted",
                "display_state": "baseline",
                "source": "canonical",
                "selected_run_id": None,
                "experiment": None,
                "has_surface": False,
                "surface_state": None,
                "lifecycle_phase": "registered",
                "lifecycle_status": None,
                "invalidation_reason": None,
                # Every persisted signal id (one per preset) this engine version aggregates,
                # and the id that owns ``selected_run_id`` so the version page can load it.
                "signal_ids": [],
                "selected_signal_id": None,
            },
        )
        signal_id = signal.get("signal_id")
        if isinstance(signal_id, str) and signal_id not in row["signal_ids"]:
            row["signal_ids"].append(signal_id)
        run_count = int(signal.get("run_count") or 0)
        row["total_runs"] += run_count
        row["run_count"] += run_count
        latest_run = _iso_or_none(signal.get("latest_run"))
        if latest_run is not None and (row["latest_run"] is None or latest_run > row["latest_run"]):
            row["latest_run"] = latest_run
            row["selected_run_id"] = signal.get("latest_run_id")
            row["selected_signal_id"] = signal_id if isinstance(signal_id, str) else None

    for row in merged.values():
        row.setdefault("signal_ids", [])
        row.setdefault("selected_signal_id", None)
    # A persisted registered engine is authoritative when a research record happens
    # to use the same version number.
    merged.update(canonical)
    return sorted(merged.values(), key=lambda row: (row["signal_family"], row["memory_version"]))


# --------------------------------------------------------------------------- #
# Sealed research artifacts
# --------------------------------------------------------------------------- #


def _research_segment(value: str, label: str) -> str:
    """Return one addressing segment, or refuse anything that could escape the layout."""
    if _RESEARCH_SEGMENT_PATTERN.fullmatch(value) is None:
        raise HTTPException(status_code=400, detail=f"Invalid {label}")
    return value


def _research_run_root(signal_family: str, memory_version: str, run_id: str) -> Path:
    """Resolve a sealed attempt directory only through the discovery layout."""
    family = _research_segment(signal_family, "signal family")
    version = _research_segment(memory_version, "memory version")
    run = _research_segment(run_id, "run id")
    if _RESEARCH_VERSION_PATTERN.fullmatch(version) is None:
        raise HTTPException(status_code=400, detail="Invalid memory version")

    version_root = Path(settings.db_root) / "research" / "signals" / family / version
    if version_root.is_dir():
        resolved_version_root = version_root.resolve()
        for experiment_root in sorted(path for path in version_root.iterdir() if path.is_dir()):
            if experiment_root.name.startswith("_"):
                continue
            run_root = experiment_root / run
            if not (run_root / "manifest.json").is_file():
                continue
            # A symlinked experiment or run directory must not reach outside the version.
            if run_root.resolve().is_relative_to(resolved_version_root):
                return run_root
    raise HTTPException(
        status_code=404,
        detail=f"Run '{run_id}' not found for {signal_family} {memory_version}",
    )


def _research_manifest(run_root: Path) -> dict[str, Any]:
    try:
        manifest = json.loads((run_root / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=404, detail="Run manifest is unreadable") from error
    if not isinstance(manifest, dict):
        raise HTTPException(status_code=404, detail="Run manifest is unreadable")
    return manifest


def _research_artifact_path(run_root: Path, manifest: dict[str, Any], name: str) -> Path:
    """Return a manifest-listed artifact that exists inside its run directory."""
    files = manifest.get("files")
    if not isinstance(files, dict) or name not in files:
        raise HTTPException(status_code=404, detail=f"Artifact '{name}' is not in the run manifest")

    # `name` is trusted only as far as the manifest: each part of a manifest key
    # (`summary.json`, `arms/<arm>/predictions.parquet`) is still one path segment.
    artifact_path = run_root.joinpath(*(_research_segment(part, "artifact name") for part in name.split("/")))
    if not artifact_path.is_file() or not artifact_path.resolve().is_relative_to(run_root.resolve()):
        raise HTTPException(status_code=404, detail=f"Artifact '{name}' is missing from the run")
    return artifact_path


def _resolve_run(signal_id: str, run_id: str) -> pl.DataFrame:
    df = _load_signal_frame(signal_id)
    if "run_id" not in df.columns:
        if run_id != "latest":
            raise HTTPException(
                status_code=404,
                detail=f"Run '{run_id}' not found for signal '{signal_id}'",
            )
        return df.with_columns(pl.lit("latest").alias("run_id"))

    run_df = df.filter(pl.col("run_id") == run_id)
    if run_df.is_empty():
        raise HTTPException(
            status_code=404,
            detail=f"Run '{run_id}' not found for signal '{signal_id}'",
        )
    return run_df


def _distinct_assets(df: pl.DataFrame) -> list[str] | None:
    """Return the run's sorted distinct assets, or ``None`` when it is not multi-asset.

    One asset is not a cross-section: a single-asset frame keeps the historical payload
    shape so existing consumers see no change.
    """
    if "asset" not in df.columns:
        return None
    assets = sorted(str(value) for value in df["asset"].drop_nulls().unique().to_list())
    return assets if len(assets) > 1 else None


def _asset_view(
    signal_id: str,
    run_id: str,
    df: pl.DataFrame,
    asset: str | None,
) -> tuple[pl.DataFrame, str | None, bool]:
    """Resolve the rows one request should see: ``(frame, applied asset, cross_section)``.

    With ``asset`` given, that asset's whole history. Without it, a multi-asset run collapses
    to the latest timestamp's cross-section, because returning every asset's full history is
    a payload no caller asked for. Anything else is returned unchanged.
    """
    if asset is not None:
        if "asset" not in df.columns:
            raise HTTPException(
                status_code=404,
                detail=f"Run '{run_id}' of signal '{signal_id}' has no 'asset' column",
            )
        filtered = df.filter(pl.col("asset") == asset)
        if filtered.is_empty():
            raise HTTPException(
                status_code=404,
                detail=f"Asset '{asset}' not found in run '{run_id}' of signal '{signal_id}'",
            )
        return filtered, asset, False

    date_column = _pick_date_column(df.columns)
    if _distinct_assets(df) is None or date_column is None or df.is_empty():
        return df, None, False
    latest = df.select(pl.col(date_column).max()).item()
    return df.filter(pl.col(date_column) == latest), None, True


def _signal_payload(
    signal_id: str,
    run_id: str,
    df: pl.DataFrame,
    *,
    assets: list[str] | None = None,
    asset: str | None = None,
    cross_section: bool = False,
) -> dict[str, Any]:
    date_column = _pick_date_column(df.columns)
    if date_column is not None:
        df = df.sort(date_column)
    runs_metadata = _load_runs_metadata(signal_id)
    run_metadata = runs_metadata.get(str(run_id), {})
    metrics = run_metadata.get("metrics")
    config = run_metadata.get("config")
    metadata = run_metadata.get("metadata")
    data_range = run_metadata.get("data_range")
    return {
        "signal_id": signal_id,
        "run_id": run_id,
        "columns": df.columns,
        "date_column": date_column,
        "prediction_columns": _prediction_columns(df),
        "assets": assets,
        "asset": asset,
        "cross_section": cross_section,
        "metrics": metrics if isinstance(metrics, dict) else {},
        "config": config if isinstance(config, dict) else {},
        "metadata": metadata if isinstance(metadata, dict) else None,
        "created_at": run_metadata.get("created_at"),
        "data_range": data_range if isinstance(data_range, dict) else None,
        "data": df,
    }


@router.get("")
def list_signals() -> list[dict[str, Any]]:
    """List signals discovered under db/signals."""
    return _cached_discover_signals()


@router.get("/research/families")
def list_signal_research_families() -> list[dict[str, Any]]:
    """List signal families with registered or persisted research versions."""
    families: dict[str, dict[str, Any]] = {}
    for row in _discover_signal_versions_with_research():
        family = row["signal_family"]
        summary = families.setdefault(
            family,
            {
                "signal_family": family,
                "description": f"Signal family: {family}",
                "total_runs": 0,
                "version_count": 0,
                "versions": [],
                "latest_run": None,
            },
        )
        summary["total_runs"] += int(row.get("total_runs") or 0)
        summary["version_count"] += 1
        summary["versions"].append(row["memory_version"])
        latest_run = row.get("latest_run")
        if latest_run and (summary["latest_run"] is None or latest_run > summary["latest_run"]):
            summary["latest_run"] = latest_run
    return sorted(families.values(), key=lambda row: row["signal_family"])


@router.get("/research/families/{signal_family}/versions")
def list_signal_research_versions(signal_family: str) -> list[dict[str, Any]]:
    """List canonical production and lifecycle versions for one signal family."""
    versions = [row for row in _discover_signal_versions_with_research() if row["signal_family"] == signal_family]
    if not versions:
        raise HTTPException(
            status_code=404,
            detail=f"No research versions found for signal family '{signal_family}'",
        )
    return versions


@router.get("/research/families/{signal_family}/lineage")
def list_signal_family_lineage(signal_family: str) -> list[dict[str, Any]]:
    """One lineage row per version (parent, question, finding, status) for the Evolution view."""
    if not _RESEARCH_SEGMENT_PATTERN.match(signal_family):
        raise HTTPException(status_code=400, detail="invalid signal family")
    try:
        rows = family_versions(signal_family, root=FAMILIES_ROOT)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=f"Unreadable records for '{signal_family}'") from exc
    if not rows:
        raise HTTPException(status_code=404, detail=f"No versions for '{signal_family}'")
    return rows


@router.get("/research/families/{signal_family}/versions/{memory_version}/runs/{run_id}/artifacts/{name:path}")
def get_signal_research_artifact(
    signal_family: str,
    memory_version: str,
    run_id: str,
    name: str,
    limit: int = Query(50_000, ge=1, le=200_000),
    offset: int = Query(0, ge=0),
) -> Response:
    """Serve one manifest-listed file from a sealed signal research attempt.

    JSON artifacts are returned byte-for-byte; parquet artifacts are returned as
    bounded rows. Only files listed in the run manifest are served.
    """
    run_root = _research_run_root(signal_family, memory_version, run_id)
    manifest = _research_manifest(run_root)
    artifact_path = _research_artifact_path(run_root, manifest, name)

    if name.endswith(".json"):
        return Response(content=artifact_path.read_bytes(), media_type="application/json")
    if not name.endswith(".parquet"):
        raise HTTPException(
            status_code=415,
            detail=f"Artifact '{name}' is neither a JSON nor a parquet artifact",
        )

    total_rows = count_parquet_rows(artifact_path)
    frame = read_parquet_frame(artifact_path, limit=limit, offset=offset)
    return polars_json_response(
        {
            "signal_family": signal_family,
            "memory_version": memory_version,
            "experiment": run_root.parent.name,
            "run_id": run_id,
            "name": name,
            "total_rows": total_rows,
            "returned_rows": len(frame),
            "offset": offset,
            "columns": frame.columns,
            "rows": frame,
        },
        df_key="rows",
    )


@router.get("/research/families/{signal_family}/versions/{memory_version}/surface")
def get_signal_research_surface(signal_family: str, memory_version: str) -> dict[str, Any]:
    """Return the selected research surface manifest, with each arm's metric values inline."""
    family = _research_segment(signal_family, "signal family")
    if _RESEARCH_VERSION_PATTERN.fullmatch(memory_version) is None:
        raise HTTPException(status_code=400, detail="Invalid memory version")
    try:
        manifest = load_research_surface(settings.db_root, family, memory_version)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise HTTPException(status_code=422, detail=f"Research surface is invalid: {error}") from error
    if manifest is None:
        raise HTTPException(status_code=404, detail=f"No research surface for {signal_family} {memory_version}")
    return manifest


@router.get("/research/families/{signal_family}/versions/{memory_version}/surface/arms/{arm_id}/{table}")
def get_signal_research_surface_table(
    signal_family: str,
    memory_version: str,
    arm_id: str,
    table: str,
    target_id: str | None = Query(None),
) -> Response:
    """Serve one arm's IC series (with cumulative IC per target) or quantile returns; 404 if the run has none."""
    family = _research_segment(signal_family, "signal family")
    if _RESEARCH_VERSION_PATTERN.fullmatch(memory_version) is None:
        raise HTTPException(status_code=400, detail="Invalid memory version")
    if table not in {"ic", "quantiles"}:
        raise HTTPException(status_code=404, detail="Surface table must be 'ic' or 'quantiles'")
    try:
        frame = load_surface_table(settings.db_root, family, memory_version, arm_id, table)  # type: ignore[arg-type]
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except (OSError, ValueError, pl.exceptions.PolarsError) as error:
        raise HTTPException(status_code=422, detail=f"Research surface is invalid: {error}") from error
    if frame is None:
        raise HTTPException(status_code=404, detail=f"Arm {arm_id!r} has no {table} table in this run")
    if target_id is not None:
        frame = frame.filter(pl.col("target_id") == target_id)
    if table == "ic":
        # Days without an IC add nothing to the running sum; the chart reads the path.
        frame = frame.with_columns(
            pl.col("ic").fill_null(0.0).cum_sum().over("target_id").alias("cumulative_ic"),
            pl.col("decision_time").dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
    return polars_json_response(
        {
            "signal_family": signal_family,
            "memory_version": memory_version,
            "arm_id": arm_id,
            "table": table,
            "columns": frame.columns,
            "rows": frame,
        },
        df_key="rows",
    )


@router.get("/{signal_id}")
def list_signal_runs(signal_id: str) -> list[dict[str, Any]]:
    """List runs for one signal."""
    df = _load_signal_frame(signal_id)
    return _run_summaries(signal_id, df)


@router.get("/{signal_id}/latest")
def get_signal_latest(signal_id: str, asset: str | None = Query(None)):
    """Return the latest run payload for one signal, optionally narrowed to one asset."""
    df = _load_signal_frame(signal_id)
    latest_column = _pick_date_column(df.columns, latest=True)
    if latest_column is None:
        raise HTTPException(
            status_code=400,
            detail="Latest signal lookup requires 'predicted_at' or 'timestamp'",
        )
    summaries = _run_summaries(signal_id, df)
    latest_run_id = summaries[0]["run_id"] if summaries else "latest"
    run_df = _resolve_run(signal_id, latest_run_id)
    assets = _distinct_assets(run_df)
    view, applied_asset, cross_section = _asset_view(signal_id, latest_run_id, run_df, asset)
    return polars_json_response(
        _signal_payload(
            signal_id,
            latest_run_id,
            view,
            assets=assets,
            asset=applied_asset,
            cross_section=cross_section,
        )
    )


def _run_view_response(signal_id: str, run_id: str, asset: str | None) -> Response:
    """Shared body of the run and predictions endpoints: resolve, select, serialize."""
    run_df = _resolve_run(signal_id, run_id)
    assets = _distinct_assets(run_df)
    view, applied_asset, cross_section = _asset_view(signal_id, run_id, run_df, asset)
    return polars_json_response(
        _signal_payload(
            signal_id,
            run_id,
            view,
            assets=assets,
            asset=applied_asset,
            cross_section=cross_section,
        )
    )


@router.get("/{signal_id}/{run_id}")
def get_signal_run(signal_id: str, run_id: str, asset: str | None = Query(None)):
    """Return one run payload for a signal, optionally narrowed to one asset."""
    return _run_view_response(signal_id, run_id, asset)


@router.get("/{signal_id}/{run_id}/predictions")
def get_signal_predictions(signal_id: str, run_id: str, asset: str | None = Query(None)):
    """Return prediction rows for one signal run, optionally narrowed to one asset."""
    return _run_view_response(signal_id, run_id, asset)


@router.get("/{signal_id}/{run_id}/stats")
def get_signal_stats(signal_id: str, run_id: str) -> dict[str, Any]:
    """Return numeric summary statistics for one signal run."""
    run_df = _resolve_run(signal_id, run_id)
    stats: list[dict[str, Any]] = []
    for column in _prediction_columns(run_df):
        series = run_df[column]
        stats.append(
            {
                "column": column,
                "count": int(series.len()),
                "null_count": int(series.null_count()),
                "mean": _serialize_scalar(series.mean()),
                "std": _serialize_scalar(series.std()),
                "min": _serialize_scalar(series.min()),
                "max": _serialize_scalar(series.max()),
            }
        )
    return {
        "signal_id": signal_id,
        "run_id": run_id,
        "prediction_stats": stats,
    }
