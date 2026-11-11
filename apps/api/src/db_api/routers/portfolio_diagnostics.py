"""Read explicitly selected portfolio diagnostics; never discover by recency.

USAGE: GET /api/portfolio-diagnostics/{strategy_type}/{memory_version}
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

import polars as pl
from data.query import ParquetQuery, get_parquet_metadata, query_parquet
from fastapi import APIRouter, HTTPException

from ..config import settings
from ..responses import polars_json_response

# --------------------------------------------------------------------------- #
# Selection validation
# --------------------------------------------------------------------------- #

router = APIRouter()
DATASETS = {
    "capital": ("timestamp", "scenario", "basis", "rate", "reserve_needed", "backing_multiple", "cushion"),
    "exposure": (
        "timestamp",
        "point",
        "btc_exposure",
        "drift_since_fill",
        "long_exposure",
        "short_exposure",
        "gross_leverage",
        "net_exposure",
        "predicted_total_vol",
    ),
    "attribution": (
        "timestamp",
        "btc_factor_pnl",
        "residual_price_pnl",
        "unmodeled_price_pnl",
        "funding",
        "fees",
        "net_pnl",
    ),
    "rolling_btc": ("timestamp", "window", "beta", "beta_ci95_low", "beta_ci95_high"),
}


def _inside(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if not relative or Path(relative).is_absolute() or not path.is_relative_to(root.resolve()):
        raise ValueError("Diagnostics reference escapes its owning directory")
    return path


def _json(path: Path) -> dict:
    value = json.loads(path.read_text())
    if not isinstance(value, dict) or value.get("schema_version") != 1:
        raise ValueError("Invalid diagnostics metadata schema")
    return value


def _selected(strategy_type: str, memory_version: str, run_id: str | None, account: str | None) -> dict | None:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", strategy_type) or not re.fullmatch(r"v[0-9]+", memory_version):
        raise HTTPException(400, "Invalid strategy identity")
    try:
        root = _inside(settings.db_root / "research", f"strategies/{strategy_type}/{memory_version}")
        selection_path = _inside(root, "portfolio_diagnostics/selected.json")
    except ValueError as error:
        raise HTTPException(409, "Diagnostics selection escapes its owning directory") from error
    if not (root / 'surface.json').is_file():
        return None
    try:
        pointer = _json(_inside(root, "surface.json"))
        manifest_path = _inside(root, pointer["selected_manifest"])
        manifest = _json(manifest_path)
        selected_run = manifest["run_id"]
        selected_account = (account or manifest.get("grid", {}).get("selected_config_id")
                            or manifest.get("attribution", {}).get("selected_config_id"))
        if (
            not isinstance(selected_run, str)
            or not selected_run
            or not isinstance(selected_account, str)
            or not selected_account
        ):
            return None
        if run_id is not None and run_id != selected_run:
            return None
        if not re.fullmatch(r'[A-Za-z0-9_-]+', selected_account):
            raise ValueError('Invalid diagnostics account')
        if pointer.get("state") not in {"candidate", "rejected"} or manifest.get("state") not in {
            "candidate",
            "rejected",
        }:
            return None
        for value in (pointer, manifest):
            if value.get("strategy_type") != strategy_type or value.get("memory_version") != memory_version:
                raise ValueError("Diagnostics selection identity mismatch")
        run_root = _inside(root, f"{manifest['experiment']}/{selected_run}")
        if manifest_path != run_root / 'surface/manifest.json':
            raise ValueError('Surface is not in its declared run')
        report_root = _inside(run_root, f'cells/{selected_account}/portfolio_diagnostics')
        explicit = _json(selection_path) if selection_path.is_file() else None
        if explicit and (explicit.get('strategy_type') != strategy_type
                         or explicit.get('memory_version') != memory_version):
            raise ValueError('Diagnostics selection identity mismatch')
        selected_explicit = bool(explicit and explicit.get('source_run_id') == selected_run
                                 and explicit.get('source_account') == selected_account)
        if selected_explicit:
            # A reviewed reporting correction can supersede the embedded report
            # without rewriting the original account. Never select by recency.
            selection = explicit
            if not re.fullmatch(r'[A-Za-z0-9_-]+', selection.get('attempt_id', '')):
                raise ValueError('Diagnostics selection identity mismatch')
            attempt_root = _inside(root, f"portfolio_diagnostics/{selection['attempt_id']}")
            attempt = _json(_inside(attempt_root, 'attempt.json'))
            if (attempt.get('attempt_id') != selection['attempt_id'] or attempt.get('status') != 'complete'
                    or attempt.get('diagnostics_status') != 'complete'
                    or attempt.get('source', {}).get('run_id') != selected_run):
                raise ValueError('Selected diagnostics attempt is incomplete or mismatched')
            report_root = _inside(attempt_root, 'portfolio_diagnostics')
        elif report_root.exists():
            selection = dict(schema_version=1, strategy_type=strategy_type, memory_version=memory_version,
                             source_run_id=selected_run, source_account=selected_account, attempt_id=selected_run)
        else:
            return None
        summary = _json(_inside(report_root, 'summary.json'))
        if summary.get("status") != "complete":
            raise ValueError("Selected diagnostics report is incomplete")
        if (
            summary.get("source", {}).get("run_id") != selected_run
            or summary["source"].get("strategy_type", strategy_type if selected_explicit else None) != strategy_type
            or summary["source"].get("memory_version") != memory_version
            or summary["source"].get("preset_name") != selected_account
        ):
            raise ValueError("Diagnostics report source mismatch")
        capital = summary["conventions"]["initial_equity"]
        if not isinstance(capital, (float, int)) or not math.isfinite(capital) or capital <= 0:
            raise ValueError("Invalid starting capital")
        for name in ("capital", "exposure", "attribution", "realized", "risk"):
            if summary[name].get("status") != "complete":
                raise ValueError(f"Incomplete {name} diagnostics")
        datasets = {}
        for name, columns in DATASETS.items():
            path = _inside(report_root, f"{name}.parquet")
            relative = path.relative_to((settings.db_root / "research").resolve()).as_posix()
            metadata = get_parquet_metadata(scope="research", path=relative, db_root=settings.db_root)
            if not set(columns).issubset({column.name for column in metadata.columns}):
                raise ValueError(f"Missing required {name} fields")
            if metadata.total_rows > (1_000_000 if name == "capital" else 20_000):
                raise ValueError("Diagnostics exceeds the supported report size")
            datasets[name] = {"path": relative, "columns": list(columns), "rows": metadata.total_rows}
        return {"selection": selection, "summary": summary, "datasets": datasets}
    except (KeyError, ValueError, OSError, TypeError) as error:
        raise HTTPException(409, "Selected portfolio diagnostics metadata is invalid") from error


# --------------------------------------------------------------------------- #
# Read-only routes
# --------------------------------------------------------------------------- #


@router.get("/{strategy_type}/{memory_version}")
def get_diagnostics(
    strategy_type: str, memory_version: str, run_id: str | None = None, account: str | None = None
) -> dict:
    report = _selected(strategy_type, memory_version, run_id, account)
    return {"available": report is not None, "report": report}


@router.get("/{strategy_type}/{memory_version}/capital")
def get_capital(
    strategy_type: str, memory_version: str, attempt_id: str, run_id: str | None = None, account: str | None = None
):
    report = _selected(strategy_type, memory_version, run_id, account)
    if report is None:
        raise HTTPException(404, "No matching selected diagnostics")
    if report["selection"]["attempt_id"] != attempt_id:
        raise HTTPException(409, "Diagnostics selection changed; reload the report")
    # UTC timestamps stay UTC through Polars bucketing; DuckDB's generic time
    # bucket currently casts to the host-local timezone before truncating.
    result = query_parquet(
        ParquetQuery(
            scope="research",
            path=report["datasets"]["capital"]["path"],
            columns=DATASETS["capital"],
            limit=1_000_000,
        ),
        db_root=settings.db_root,
    )
    if result.returned_rows != report["datasets"]["capital"]["rows"]:
        raise HTTPException(409, "Capital evidence is truncated or changed")
    daily = (
        result.frame.with_columns(pl.col("timestamp").dt.convert_time_zone("UTC").dt.truncate("1d"))
        .group_by("timestamp", "scenario", "basis", "rate")
        .agg(
            pl.col("reserve_needed").max(),
            pl.col("backing_multiple").max(),
            pl.col("cushion").min(),
        )
        .sort("timestamp")
    )
    if daily.height > 20_000:
        raise HTTPException(409, "Diagnostics exceeds the supported daily chart size")
    return polars_json_response({"aggregation": "UTC daily extrema", "rows": daily}, df_key="rows")
