"""Backtest Engine: live and recent strategy runs, their telemetry, and a replay of one saved run.

USAGE::

    GET /api/backtest-engine/runs?limit=100&state=running&state=failed&family=crypto_example-strategy
    GET /api/backtest-engine/runs/{family}/{version}/{preset}/{run_id}
    GET /api/backtest-engine/runs/{family}/{version}/{preset}/{run_id}/assets/BTC
    GET /api/backtest-engine/runs/{family}/{version}/{preset}/{run_id}/execution/2024-01-02
    GET /api/backtest-engine/runs/{family}/{version}/{preset}/{run_id}/execution/2024-01-02/assets/BTC

Runs are ``StrategyRunner`` folders under ``research/strategies/<family>/<version>/<preset>/run-*``,
plus whatever registered run sources list (``register_run_source``: an API extension that reads its
family's own run layout and hands the replay to ``build_replay``). A family whose extension
registers an asset source (``register_asset_source``) gets the asset route: one held asset's price,
weight, position P&L and rebalances over the run (``build_asset``). One that registers an execution
source (``register_execution_source``) gets the Rebalance day route: one
day's parent orders simulated over 1-minute bars under each policy (``db_api.execution_day``),
with each asset's minute data served on its own.
A folder's ``status.json`` (written by the runner) is its record; folders saved before that
file existed get a ``succeeded`` record from ``meta.json``. A ``running`` record whose process
is gone on this host reports ``failed``. ``/runs`` reads every folder's small JSON record; a very
large store would need a bounded newest-first walk.
Read-only: nothing here writes under the lake.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports and constants
# --------------------------------------------------------------------------- #
import json
import math
import re
import socket
from collections.abc import Callable, Iterable
from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, Protocol

import polars as pl
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ValidationError
from strategies.backtest_updates import _alive, job_status
from strategies.contracts import validate_identifier, validate_memory_version

from ..config import settings
from ..execution_day import ExecutionAsset, ExecutionDay, ExecutionInputs, build_execution_day
from ..parquet import read_parquet_frame, read_parquet_schema
from ..responses import sample_display_rows

router = APIRouter()

RunState = Literal["running", "succeeded", "failed"]
_RUN_ID = re.compile(r"^run-[0-9A-Za-z_-]{1,64}$")
_MAX_POINTS = 5_000
_MAX_TRADES = 5_000
_MAX_POSITION_ASSETS = 20
TRADE_EPSILON = 1e-9
_EQUITY_COLUMNS = ("equity", "benchmark_equity")
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_ISO = "%Y-%m-%dT%H:%M:%SZ"


# --------------------------------------------------------------------------- #
# Response models
# --------------------------------------------------------------------------- #


class BacktestRun(BaseModel):
    """One run's telemetry; the path supplies its identity."""

    family: str
    version: str
    preset: str
    run_id: str
    state: RunState
    started_at: str | None = None
    finished_at: str | None = None
    duration_s: float | None = None
    phases: dict[str, float] = {}
    engine: str | None = None
    rows: int | None = None
    assets: int | None = None
    host: str | None = None
    pid: int | None = None
    error: str | None = None
    lag_bars: int | None = None
    metrics: dict[str, float] = {}
    data_range: dict[str, str] | None = None


class BacktestUpdateJob(BaseModel):
    """The last Update-backtest job of one version (``updated/job.json``)."""

    family: str
    version: str
    state: str
    started_at: str | None = None
    finished_at: str | None = None
    error: str | None = None


class BacktestRunSummary(BaseModel):
    running: int
    failed_24h: int
    runs_7d: int
    last_finished_at: str | None


class BacktestRunList(BaseModel):
    runs: list[BacktestRun]
    updates: list[BacktestUpdateJob]
    summary: BacktestRunSummary
    families: list[str]


class ReplayEquity(BaseModel):
    """Display-sampled columns aligned by index."""

    timestamp: list[str]
    equity: list[float | None]
    benchmark_equity: list[float | None]
    drawdown: list[float | None]
    return_to_date: list[float | None]
    gross_exposure: list[float | None]
    net_exposure: list[float | None]


class ReplayPositions(BaseModel):
    """Target weights the backtest holds at each equity timestamp; the smallest assets fold into OTHER."""

    assets: list[str]
    weights: dict[str, list[float | None]]


class ReplayTrade(BaseModel):
    timestamp: str
    asset: str
    from_weight: float
    to_weight: float
    delta: float


class BacktestReplay(BaseModel):
    rows: int
    # False when the run sets quantity (null-weight) targets: positions, exposure and trades are empty.
    weights_known: bool
    equity: ReplayEquity
    positions: ReplayPositions
    trades: list[ReplayTrade]
    total_trades: int
    # Every asset the run held, largest mean holding first (the asset route's roster).
    held_assets: list[str] = []


class BacktestRunDetail(BaseModel):
    status: BacktestRun
    meta: dict[str, Any] | None
    replay: BacktestReplay | None
    execution: bool = False  # the Rebalance day route serves this run's rebalances
    assets: bool = False  # the asset route serves this run's held assets


class AssetTrade(BaseModel):
    """One rebalance of the asset: when, the weight change, and the price at that row."""

    timestamp: str
    delta: float
    price: float | None


class BacktestAsset(BaseModel):
    """One held asset over a run, aligned by index: price, weight held and the position's cumulative P&L in dollars."""

    asset: str
    timestamp: list[str]
    price: list[float | None]
    weight: list[float | None]
    pnl: list[float | None]
    trades: list[AssetTrade]


# --------------------------------------------------------------------------- #
# Run sources (extensions)
# --------------------------------------------------------------------------- #


class RunSource(Protocol):
    """Runs saved in a layout other than ``StrategyRunner``'s, read by an API extension."""

    def records(self) -> Iterable[BacktestRun]: ...

    def detail(self, family: str, version: str, preset: str, run_id: str) -> BacktestRunDetail | None:
        """The run's detail, or None when this source does not hold it."""
        ...


_SOURCES: list[RunSource] = []


def register_run_source(source: RunSource) -> None:
    """Add an extension's runs to the listing and the detail route."""
    _SOURCES.append(source)


ExecutionSource = Callable[[str, str, str, date], ExecutionInputs | None]
"""``(version, preset, run_id, day)`` -> that day's execution inputs, or None when it has no rebalance."""

AssetSource = Callable[[str, str, str, str], BacktestAsset | None]
"""``(version, preset, run_id, asset)`` -> that asset over the run (``build_asset``), or None."""

_ASSET_SOURCES: dict[str, AssetSource] = {}


def register_asset_source(family: str, source: AssetSource) -> None:
    """Serve the asset route for ``family``'s runs from an extension."""
    _ASSET_SOURCES[family] = source


_EXECUTION_SOURCES: dict[str, ExecutionSource] = {}


def register_execution_source(family: str, source: ExecutionSource) -> None:
    """Serve the Rebalance day route for ``family``'s runs from an extension's inputs."""
    _EXECUTION_SOURCES[family] = source


# --------------------------------------------------------------------------- #
# Run records
# --------------------------------------------------------------------------- #


def _root() -> Path:
    return settings.db_root / "research" / "strategies"


def _valid(family: str, version: str, preset: str, run_id: str) -> bool:
    try:
        validate_identifier(family, "family")
        validate_memory_version(version)
        validate_identifier(preset, "preset")
    except ValueError:
        return False
    return _RUN_ID.fullmatch(run_id) is not None


def _families(root: Path) -> list[str]:
    if not root.is_dir():
        return []
    names = []
    for path in root.iterdir():
        try:
            validate_identifier(path.name, "family")
        except ValueError:
            continue  # _archive and stray files
        if path.is_dir():
            names.append(path.name)
    return sorted(names)


def _run_dirs(root: Path, families: list[str]) -> list[Path]:
    """Candidate run folders (``list_runs`` orders the records)."""
    return [
        path
        for family in families
        for path in (root / family).glob("v[0-9][0-9][0-9]/*/run-*")
        if _valid(family, path.parent.parent.name, path.parent.name, path.name)
    ]


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _finite_metrics(metrics: Any) -> dict[str, float]:
    if not isinstance(metrics, dict):
        return {}
    return {
        key: float(value)
        for key, value in metrics.items()
        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    }


def run_metrics(metrics: Any) -> dict[str, float]:
    """A run's finite final metrics; ``max_drawdown`` is non-positive whatever sign the engine wrote."""
    found = _finite_metrics(metrics)
    if "max_drawdown" in found:
        found["max_drawdown"] = -abs(found["max_drawdown"])
    return found


def _record(run_dir: Path) -> BacktestRun | None:
    """The run's status (or legacy meta) as one record; None for folders the runner did not write."""
    status = read_json(run_dir / "status.json")
    meta = read_json(run_dir / "meta.json")
    if status is None and meta is None:
        return None
    record = dict(status or {})
    if status is None:
        record = dict(state="succeeded", finished_at=(meta or {}).get("created_at"))
    elif record.get("state") == "running" and record.get("host") == socket.gethostname():
        if not _alive(record.get("pid")):
            record |= dict(state="failed", error="the run stopped without reporting")
    if record.get("state") not in ("running", "succeeded", "failed"):
        return None
    data_range = (meta or {}).get("data_range")
    try:
        return _validated_record(run_dir, record, meta or {}, data_range)
    except ValidationError:
        return None  # a damaged status file; the folder stays out of the listing


def _validated_record(run_dir: Path, record: dict[str, Any], meta: dict[str, Any], data_range: Any) -> BacktestRun:
    return BacktestRun(
        family=run_dir.parent.parent.parent.name,
        version=run_dir.parent.parent.name,
        preset=run_dir.parent.name,
        run_id=run_dir.name,
        state=record["state"],
        started_at=record.get("started_at"),
        finished_at=record.get("finished_at"),
        duration_s=record.get("duration_s"),
        phases=_finite_metrics(record.get("phases")),
        engine=record.get("engine"),
        rows=record.get("rows"),
        assets=record.get("assets"),
        host=record.get("host"),
        pid=record.get("pid"),
        error=record.get("error"),
        lag_bars=record.get("lag_bars"),
        metrics=run_metrics(meta.get("metrics")),
        data_range={key: str(value) for key, value in data_range.items()} if isinstance(data_range, dict) else None,
    )


def _updates(root: Path, families: list[str]) -> list[BacktestUpdateJob]:
    jobs = []
    for family in families:
        for path in sorted((root / family).glob("v[0-9][0-9][0-9]/updated/job.json")):
            version = path.parent.parent.name
            try:
                job = job_status(settings.db_root, family, version)
            except (OSError, ValueError, KeyError):
                continue
            if job:
                jobs.append(
                    BacktestUpdateJob(
                        family=family,
                        version=version,
                        state=str(job.get("state")),
                        started_at=job.get("started_at"),
                        finished_at=job.get("finished_at"),
                        error=job.get("error"),
                    )
                )
    return sorted(jobs, key=lambda job: job.started_at or "", reverse=True)


def _when(value: str | None) -> datetime | None:
    """Aware time; naive values (legacy ``created_at``) are local time."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo is None else parsed


def _summary(runs: list[BacktestRun]) -> BacktestRunSummary:
    now = datetime.now(UTC)
    # A run that died without reporting has no finish time; its start dates it.
    finished = [(run, _when(run.finished_at or run.started_at)) for run in runs if run.state != "running"]
    finished = [(run, at) for run, at in finished if at is not None]
    return BacktestRunSummary(
        running=sum(run.state == "running" for run in runs),
        failed_24h=sum(run.state == "failed" and at >= now - timedelta(days=1) for run, at in finished),
        runs_7d=sum(
            (at := _when(run.started_at or run.finished_at)) is not None and at >= now - timedelta(days=7)
            for run in runs
        ),
        last_finished_at=max(at for _, at in finished).isoformat() if finished else None,
    )


# --------------------------------------------------------------------------- #
# Replay
# --------------------------------------------------------------------------- #


def _utc_timestamps(frame: pl.DataFrame) -> pl.DataFrame:
    dtype = frame.schema["timestamp"]
    column = pl.col("timestamp").cast(pl.Datetime("us", getattr(dtype, "time_zone", None)))
    column = column.dt.replace_time_zone("UTC") if getattr(dtype, "time_zone", None) is None else column
    return frame.with_columns(column.dt.convert_time_zone("UTC")).sort("timestamp")


def _iso(column: pl.Series) -> list[str]:
    return column.dt.strftime(_ISO).to_list()


def _floats(frame: pl.DataFrame, name: str) -> list[float | None]:
    if name not in frame.columns:
        return [None] * frame.height
    return frame[name].cast(pl.Float64).fill_nan(None).to_list()


def build_replay(
    equity: pl.DataFrame,
    positions: pl.DataFrame | None,
    trades: pl.DataFrame | None,
) -> BacktestReplay:
    """The replay of one run.

    ``equity``: UTC ``timestamp``, ``equity`` and optional ``benchmark_equity``, sorted. ``positions``:
    the weights held from each UTC ``timestamp`` on, one column per asset (``CASH`` kept apart), or
    None when the held weights are unknown. ``trades``: ``timestamp``, ``asset``, ``from_weight``,
    ``to_weight``, ``delta``, newest first, or None with unknown positions.
    """
    assets = [name for name in positions.columns if name not in ("timestamp", "CASH")] if positions is not None else []
    # Drawdown and return to date on full history, then the positions in force at each sampled row.
    first = equity["equity"].drop_nulls().first() if equity["equity"].null_count() < equity.height else None
    sampled = sample_display_rows(
        equity.with_columns(
            drawdown=pl.col("equity") / pl.col("equity").cum_max() - 1.0,
            return_to_date=(pl.col("equity") / first - 1.0) if first else pl.lit(None, pl.Float64),
        ),
        max_points=_MAX_POINTS,
    )
    if positions is not None:
        sampled = sampled.join_asof(positions, on="timestamp", strategy="backward")
    sampled = sampled.with_columns(
        gross_exposure=pl.sum_horizontal([pl.col(a).abs() for a in assets]) if assets else pl.lit(None, pl.Float64),
        net_exposure=pl.sum_horizontal([pl.col(a) for a in assets]) if assets else pl.lit(None, pl.Float64),
    )

    weights: dict[str, list[float | None]] = {}
    ranked: list[str] = []
    if positions is not None:
        ranked = sorted(assets, key=lambda a: positions[a].abs().mean() or 0.0, reverse=True)
        shown, folded = ranked[:_MAX_POSITION_ASSETS], ranked[_MAX_POSITION_ASSETS:]
        weights = {asset: _floats(sampled, asset) for asset in shown}
        if folded:
            weights["OTHER"] = sampled.select(pl.sum_horizontal(folded)).to_series().to_list()
        if "CASH" in positions.columns:
            weights["CASH"] = _floats(sampled, "CASH")

    kept = (
        []
        if trades is None
        else trades.head(_MAX_TRADES).with_columns(pl.col("timestamp").dt.strftime(_ISO)).to_dicts()
    )
    return BacktestReplay(
        rows=equity.height,
        weights_known=positions is not None,
        equity=ReplayEquity(
            timestamp=_iso(sampled["timestamp"]),
            **{
                name: _floats(sampled, name)
                for name in (*_EQUITY_COLUMNS, "drawdown", "return_to_date", "gross_exposure", "net_exposure")
            },
        ),
        positions=ReplayPositions(assets=list(weights), weights=weights),
        trades=[ReplayTrade(**row) for row in kept],
        total_trades=0 if trades is None else trades.height,
        held_assets=ranked,
    )


def build_asset(asset: str, rows: pl.DataFrame, trades: pl.DataFrame | None) -> BacktestAsset:
    """One asset over a run.

    ``rows``: UTC ``timestamp``, ``price``, ``weight`` and ``pnl`` (the position's dollar P&L over each
    row), sorted. ``trades``: UTC ``timestamp`` and ``delta`` (weight change), or None.
    """
    rows = rows.with_columns(pnl=pl.col("pnl").fill_null(0.0).cum_sum())
    marks = []
    if trades is not None and not trades.is_empty():
        priced = trades.sort("timestamp").join_asof(rows.select("timestamp", "price"), on="timestamp")
        marks = [
            AssetTrade(timestamp=row["timestamp"].strftime(_ISO), delta=row["delta"], price=row["price"])
            for row in priced.iter_rows(named=True)
        ]
    sampled = sample_display_rows(rows, max_points=_MAX_POINTS)
    return BacktestAsset(
        asset=asset,
        timestamp=_iso(sampled["timestamp"]),
        price=_floats(sampled, "price"),
        weight=_floats(sampled, "weight"),
        pnl=_floats(sampled, "pnl"),
        trades=marks,
    )


def _replay(run_dir: Path, lag_bars: int) -> BacktestReplay | None:
    backtest_path, decisions_path = run_dir / "backtest.parquet", run_dir / "decisions.parquet"
    if not (backtest_path.is_file() and decisions_path.is_file()):
        return None
    equity_schema = read_parquet_schema(backtest_path)
    if "timestamp" not in equity_schema or "equity" not in equity_schema:
        return None
    equity = _utc_timestamps(
        read_parquet_frame(backtest_path, columns=["timestamp", *[c for c in _EQUITY_COLUMNS if c in equity_schema]])
    )

    # Decision targets (without __metadata__ columns), moved to the equity row where the backtest
    # holds them: ``lag_bars`` rows after the decision, as ``materialize_effective_weights`` does.
    decision_schema = read_parquet_schema(decisions_path)
    weight_columns = [
        name
        for name, dtype in decision_schema.items()
        if name != "timestamp" and not name.startswith("__") and dtype.is_numeric()
    ]
    decisions = _utc_timestamps(read_parquet_frame(decisions_path, columns=["timestamp", *weight_columns]))
    rows = equity.select("timestamp").with_row_index("row")
    decisions = (
        decisions.sort("timestamp")
        .join_asof(rows, on="timestamp", strategy="forward")
        .with_columns(pl.col("row") + lag_bars)
        .filter(pl.col("row") < rows.height)
        .drop("timestamp")
        .join(rows, on="row")
        .drop("row")
        .unique("timestamp", keep="last", maintain_order=True)
        .sort("timestamp")
        .select("timestamp", *weight_columns)
    )
    # A null target holds a quantity (or sets one in metadata), so the held weight is not in these
    # files: report positions, exposure and rebalances as unknown rather than guess them.
    if decisions.select(pl.col(weight_columns).null_count().sum()).sum_horizontal().item():
        return build_replay(equity, None, None)

    # Rebalances: per-asset target changes, newest first.
    assets = [name for name in weight_columns if name != "CASH"]
    trades = None
    if assets:
        trades = (
            decisions.unpivot(index="timestamp", on=assets, variable_name="asset", value_name="to_weight")
            .with_columns(pl.col("to_weight").fill_null(0.0))
            .sort("asset", "timestamp")
            .with_columns(from_weight=pl.col("to_weight").shift(1).over("asset").fill_null(0.0))
            .with_columns(delta=pl.col("to_weight") - pl.col("from_weight"))
            .filter(pl.col("delta").abs() > TRADE_EPSILON)
            .sort(["timestamp", "asset"], descending=[True, False])
            .select("timestamp", "asset", "from_weight", "to_weight", "delta")
        )
    return build_replay(equity, decisions, trades)


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #


@router.get("/runs", response_model=BacktestRunList)
def list_runs(
    limit: int = Query(default=100, ge=1, le=500),
    state: list[RunState] | None = Query(default=None),
    family: list[str] | None = Query(default=None, max_length=50),
) -> BacktestRunList:
    """Newest runs across families, filtered, plus update jobs and a store-wide summary.

    ``summary`` and ``families`` cover every run, so the stat cards and filter options never
    depend on the filters or the page.
    """
    root = _root()
    all_families = _families(root)
    every = [record for run_dir in _run_dirs(root, all_families) if (record := _record(run_dir)) is not None]
    every += [record for source in _SOURCES for record in source.records()]
    every.sort(key=lambda run: _when(run.started_at or run.finished_at) or _EPOCH, reverse=True)
    all_families = sorted({*all_families, *(run.family for run in every)})
    families = [name for name in all_families if not family or name in family]
    runs = [run for run in every if run.family in families and (not state or run.state in state)]
    return BacktestRunList(
        runs=runs[:limit], updates=_updates(root, families), summary=_summary(every), families=all_families
    )


@router.get("/runs/{family}/{version}/{preset}/{run_id}", response_model=BacktestRunDetail)
def get_run(family: str, version: str, preset: str, run_id: str) -> BacktestRunDetail:
    """One run's status, meta and replay (equity, positions and rebalances)."""
    for source in _SOURCES:
        try:
            detail = source.detail(family, version, preset, run_id)
        except (OSError, ValueError, pl.exceptions.PolarsError) as exc:
            raise HTTPException(status_code=500, detail="Backtest run artifacts are unreadable") from exc
        if detail is not None:
            return detail.model_copy(
                update={"execution": family in _EXECUTION_SOURCES, "assets": family in _ASSET_SOURCES}
            )
    if not _valid(family, version, preset, run_id):
        raise HTTPException(status_code=404, detail="Backtest run not found")
    run_dir = _root() / family / version / preset / run_id
    record = _record(run_dir) if run_dir.is_dir() else None
    if record is None:
        raise HTTPException(status_code=404, detail="Backtest run not found")
    meta = read_json(run_dir / "meta.json")
    try:
        replay = _replay(run_dir, 1 if record.lag_bars is None else record.lag_bars)
    except (OSError, ValueError, pl.exceptions.PolarsError) as exc:
        raise HTTPException(status_code=500, detail="Backtest run artifacts are unreadable") from exc
    return BacktestRunDetail(status=record, meta=meta, replay=replay)


@router.get("/runs/{family}/{version}/{preset}/{run_id}/assets/{asset}", response_model=BacktestAsset)
def get_asset(family: str, version: str, preset: str, run_id: str, asset: str) -> BacktestAsset:
    """One held asset over the run: price, weight, cumulative position P&L and rebalances."""
    if family not in _ASSET_SOURCES:
        raise HTTPException(status_code=404, detail="This family serves no per-asset view")
    try:
        found = _ASSET_SOURCES[family](version, preset, run_id, asset)
    except (OSError, ValueError, pl.exceptions.PolarsError) as exc:
        raise HTTPException(status_code=500, detail="Backtest run artifacts are unreadable") from exc
    if found is None:
        raise HTTPException(status_code=404, detail="Asset not found in this run")
    return found


# A busy day's per-asset minute data is tens of MB in memory; keep the last few days.
@lru_cache(maxsize=4)
def _execution_day(
    family: str, version: str, preset: str, run_id: str, day: date
) -> tuple[ExecutionDay, dict[str, ExecutionAsset]] | None:
    inputs = _EXECUTION_SOURCES[family](version, preset, run_id, day)
    return None if inputs is None else build_execution_day(inputs)


def _built_day(
    family: str, version: str, preset: str, run_id: str, day: date
) -> tuple[ExecutionDay, dict[str, ExecutionAsset]]:
    if family not in _EXECUTION_SOURCES:
        raise HTTPException(status_code=404, detail="This family has no intraday execution view")
    try:
        result = _execution_day(family, version, preset, run_id, day)
    except (OSError, ValueError, pl.exceptions.PolarsError) as exc:
        raise HTTPException(status_code=500, detail=f"Rebalance day unavailable: {exc}") from exc
    if result is None:
        raise HTTPException(status_code=404, detail="No rebalance on this day")
    return result


@router.get("/runs/{family}/{version}/{preset}/{run_id}/execution/{day}", response_model=ExecutionDay)
def get_execution_day(family: str, version: str, preset: str, run_id: str, day: date) -> ExecutionDay:
    """One rebalance day's parent orders worked over that day's 1-minute bars under each policy."""
    return _built_day(family, version, preset, run_id, day)[0]


@router.get("/runs/{family}/{version}/{preset}/{run_id}/execution/{day}/assets/{asset}", response_model=ExecutionAsset)
def get_execution_asset(family: str, version: str, preset: str, run_id: str, day: date, asset: str) -> ExecutionAsset:
    """One traded asset's day: 1-minute close and volume from arrival, and each policy's fills."""
    found = _built_day(family, version, preset, run_id, day)[1].get(asset)
    if found is None:
        raise HTTPException(status_code=404, detail="This asset did not trade on this day")
    return found
