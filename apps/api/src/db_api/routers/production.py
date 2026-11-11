"""Read-only production capital telemetry routes.

USAGE::

    GET /api/production/overview
    GET /api/production/series?range=30d&metric=pnl_usd
    GET /api/production/strategies/{family}
    GET /api/production/strategies/{family}/series?range=30d&metric=pnl_usd

This router reads bounded JSON documents published under ``db/production`` by
``qf-production publish-projection``.  It never calls a venue, never loads a
production credential, and never reads the production state root: the projection
is the only thing it can see, and that projection is already redacted.

Series responses only slice and rebase levels the publisher already computed, so
a range change is arithmetic rather than a second aggregation with its own
rounding and cash-flow conventions.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports and constants
# --------------------------------------------------------------------------- #
import json
import os
import re
import stat
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..config import settings

router = APIRouter()

_MAX_JSON_BYTES = 4 * 1024 * 1024
_MAX_SERIES_POINTS = 4000
_FILE_OPEN_FLAGS = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
_DIRECTORY_OPEN_FLAGS = _FILE_OPEN_FLAGS | os.O_DIRECTORY
_FAMILY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

_PROJECTION_DIR = "production"
_STRATEGIES_DIR = "strategies"
_OVERVIEW_FILE = "overview.json"
_SNAPSHOT_FILE = "snapshot.json"

Range = Literal["1d", "7d", "30d", "ytd", "all"]
Metric = Literal["pnl_usd", "return_pct", "equity"]

_RANGE_DAYS: dict[str, int] = {"1d": 1, "7d": 7, "30d": 30}


# --------------------------------------------------------------------------- #
# Response models
# --------------------------------------------------------------------------- #


class ProductionMetrics(BaseModel):
    """Performance metrics; ``null`` means unsupportable, never zero."""

    model_config = ConfigDict(extra="forbid")

    total_pnl_usd: float | None
    total_return: float | None
    max_drawdown: float | None
    annualized_volatility: float | None
    sharpe: float | None
    positive_day_rate: float | None
    observation_count: int = Field(ge=0)


class ProductionMember(BaseModel):
    """One declared portfolio member as the overview presents it."""

    model_config = ConfigDict(extra="forbid")

    family: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    included: bool
    state: str | None
    health: Literal["healthy", "attention", "unknown", "paused"]
    stale: bool
    capital_weight: float | None
    equity_usd: float | None
    inception_pnl_usd: float | None
    period_pnl_usd: float | None
    last_observation_at: datetime | None


class ProductionOverview(BaseModel):
    """Aggregate portfolio truth with explicit completeness."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    portfolio_id: str
    generated_at: datetime
    completeness: Literal["complete", "incomplete", "stale", "empty"]
    equity_usd: float | None
    today_pnl_usd: float | None
    inception_pnl_usd: float | None
    missing_families: list[str]
    stale_families: list[str]
    included_families: list[str]
    metrics: ProductionMetrics
    members: list[ProductionMember]


class ProductionSeriesPoint(BaseModel):
    """One rebased series value at a UTC reporting boundary."""

    model_config = ConfigDict(extra="forbid")

    day: date
    value: float | None
    complete: bool


class ProductionSeriesLine(BaseModel):
    """One named line in a series response."""

    model_config = ConfigDict(extra="forbid")

    family: str | None
    points: list[ProductionSeriesPoint]


class ProductionSeries(BaseModel):
    """Aggregate line plus optional per-strategy overlays for one range."""

    model_config = ConfigDict(extra="forbid")

    range: Range
    metric: Metric
    portfolio_id: str
    generated_at: datetime
    complete: bool
    aggregate: ProductionSeriesLine
    strategies: list[ProductionSeriesLine]


class ProductionPosition(BaseModel):
    """One venue-reported position at the snapshot timestamp."""

    model_config = ConfigDict(extra="forbid")

    instrument: str
    side: Literal["LONG", "SHORT"]
    quantity: float
    contracts: int | None
    current_price: float
    entry_price: float
    market_value_usd: float
    unrealized_pnl_usd: float
    daily_realized_pnl_usd: float | None


class ProductionCapital(BaseModel):
    """Account capital and exposure as of one observation."""

    model_config = ConfigDict(extra="forbid")

    as_of: datetime
    equity_usd: float
    cash_usd: float | None
    gross_exposure_usd: float | None
    net_exposure_usd: float | None
    realized_pnl_usd: float | None
    unrealized_pnl_usd: float | None
    fees_usd: float | None
    funding_pnl_usd: float | None
    capital_weight: float | None
    positions: list[ProductionPosition]


class ProductionDeployment(BaseModel):
    """Non-secret deployment, host, and schedule identity."""

    model_config = ConfigDict(extra="forbid")

    family: str
    memory_version: str
    preset: str
    venue: str
    instrument: str
    account_alias: str
    host_alias: str
    host_region: str
    schedule: str
    timezone: str
    host_git_sha: str
    deployment_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class ProductionAuthority(BaseModel):
    """Independent authority facts; each stays a separate fact."""

    model_config = ConfigDict(extra="forbid")

    activation_state: Literal["missing", "disabled", "expired", "wrong-schema", "enabled"]
    activation_expires_at: datetime | None
    armed: bool
    venue_gate: Literal["open", "closed", "n/a"]
    capital_gate: Literal["open", "closed", "n/a"]
    deactivated: bool
    can_trade: bool
    scheduled: bool
    autonomous_live: bool


class ProductionHealthCheck(BaseModel):
    """One independent operational check."""

    model_config = ConfigDict(extra="forbid")

    name: Literal[
        "deployment_identity",
        "scheduler",
        "pipeline",
        "input_freshness",
        "execution",
        "account_snapshot",
        "reconciliation",
    ]
    state: Literal["passing", "failing", "unknown"]
    detail: str


class ProductionLastRun(BaseModel):
    """Latest production-cycle and runtime-journal facts."""

    model_config = ConfigDict(extra="forbid")

    result: Literal["never", "success", "failure"]
    at: datetime | None
    mode: Literal["dry-run", "live"] | None
    journal_at: datetime | None


class ProductionStrategy(BaseModel):
    """One deployed strategy's published snapshot."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    portfolio_id: str
    generated_at: datetime
    family: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    included: bool
    state: str
    health: Literal["healthy", "attention", "unknown", "paused"]
    stale: bool
    max_age_seconds: int = Field(ge=1)
    last_observation_at: datetime | None
    today_pnl_usd: float | None
    inception_pnl_usd: float | None
    deployment: ProductionDeployment
    authority_facts: ProductionAuthority
    health_checks: list[ProductionHealthCheck]
    last_run: ProductionLastRun
    capital: ProductionCapital | None
    metrics: ProductionMetrics


# --------------------------------------------------------------------------- #
# Fail-closed readers
# --------------------------------------------------------------------------- #


def _open_directory(path: str | os.PathLike[str], *, dir_fd: int | None = None) -> int:
    """Open one directory without following its final path component."""

    descriptor = os.open(path, _DIRECTORY_OPEN_FLAGS, dir_fd=dir_fd)
    try:
        is_directory = stat.S_ISDIR(os.fstat(descriptor).st_mode)
    except BaseException:
        os.close(descriptor)
        raise
    if not is_directory:
        os.close(descriptor)
        raise ValueError("projection path is not a directory")
    return descriptor


def _open_root() -> int | None:
    """Open the projection root safely, or return None when it is absent."""

    try:
        return _open_directory(settings.db_root / _PROJECTION_DIR)
    except FileNotFoundError:
        return None


def _read_json_object(filename: str, *, dir_fd: int) -> dict[str, Any]:
    """Read one direct-child regular JSON object without following symlinks."""

    descriptor = os.open(filename, _FILE_OPEN_FLAGS, dir_fd=dir_fd)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("projection path is not a regular file")
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            payload = handle.read(_MAX_JSON_BYTES + 1)
    finally:
        os.close(descriptor)
    if len(payload) > _MAX_JSON_BYTES:
        raise ValueError("projection exceeds the JSON size limit")
    value = json.loads(payload)
    if not isinstance(value, dict):
        raise ValueError("projection must be a JSON object")
    return value


def _require_family(family: str) -> str:
    """Reject anything that is not a plain family token before any path use."""

    if not _FAMILY_PATTERN.fullmatch(family):
        raise HTTPException(status_code=404, detail="Strategy not found")
    return family


def _load_overview() -> dict[str, Any]:
    """Read the published portfolio overview document."""

    try:
        root_fd = _open_root()
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=500, detail="Production projection is invalid") from exc
    if root_fd is None:
        raise HTTPException(status_code=404, detail="Production projection not found")
    try:
        return _read_json_object(_OVERVIEW_FILE, dir_fd=root_fd)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Production projection not found") from exc
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail="Production projection is invalid") from exc
    finally:
        os.close(root_fd)


def _load_snapshot(family: str) -> dict[str, Any]:
    """Read one strategy's published snapshot document."""

    try:
        root_fd = _open_root()
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=500, detail="Production projection is invalid") from exc
    if root_fd is None:
        raise HTTPException(status_code=404, detail="Strategy not found")
    try:
        strategies_fd = _open_directory(_STRATEGIES_DIR, dir_fd=root_fd)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Strategy not found") from exc
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=500, detail="Production projection is invalid") from exc
    finally:
        os.close(root_fd)
    try:
        family_fd = _open_directory(family, dir_fd=strategies_fd)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Strategy not found") from exc
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=500, detail="Production projection is invalid") from exc
    finally:
        os.close(strategies_fd)
    try:
        return _read_json_object(_SNAPSHOT_FILE, dir_fd=family_fd)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Strategy not found") from exc
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail="Production projection is invalid") from exc
    finally:
        os.close(family_fd)


# --------------------------------------------------------------------------- #
# Range slicing and rebasing
# --------------------------------------------------------------------------- #


def _window_start(selected: str, points: list[dict[str, Any]], *, now: datetime) -> date | None:
    """Return the first day inside the selected range, or None for all history."""

    if selected == "all" or not points:
        return None
    today = now.astimezone(UTC).date()
    if selected == "ytd":
        return date(today.year, 1, 1)
    return today - timedelta(days=_RANGE_DAYS[selected] - 1)


def _rebase(
    raw: list[dict[str, Any]],
    *,
    metric: str,
    start: date | None,
) -> list[ProductionSeriesPoint]:
    """Slice to the window and rebase levels onto the window's opening mark.

    The baseline is the last mark *before* the window when one exists, so a
    30-day P&L line starts at the change since the day before the window rather
    than discarding the first day's move.
    """

    parsed: list[tuple[date, dict[str, Any]]] = []
    for point in raw[-_MAX_SERIES_POINTS:]:
        day_raw = point.get("day")
        if not isinstance(day_raw, str):
            raise ValueError("series point is missing a day")
        parsed.append((date.fromisoformat(day_raw), point))

    if start is None:
        window = parsed
        baseline = parsed[0][1] if parsed else None
    else:
        window = [item for item in parsed if item[0] >= start]
        before = [item for item in parsed if item[0] < start]
        baseline = before[-1][1] if before else (window[0][1] if window else None)

    result: list[ProductionSeriesPoint] = []
    for day, point in window:
        complete = bool(point.get("complete", True))
        result.append(
            ProductionSeriesPoint(day=day, value=_value(point, baseline, metric), complete=complete)
        )
    return result


def _value(point: dict[str, Any], baseline: dict[str, Any] | None, metric: str) -> float | None:
    """Rebase one point's level against the window baseline."""

    if metric == "equity":
        value = point.get("equity_usd")
        return float(value) if isinstance(value, (int, float)) else None
    if metric == "pnl_usd":
        current = point.get("cum_pnl_usd")
        base = None if baseline is None else baseline.get("cum_pnl_usd")
        if not isinstance(current, (int, float)):
            return None
        return float(current) - (float(base) if isinstance(base, (int, float)) else 0.0)
    current = point.get("cum_return")
    base = None if baseline is None else baseline.get("cum_return")
    if not isinstance(current, (int, float)):
        return None
    divisor = 1.0 + (float(base) if isinstance(base, (int, float)) else 0.0)
    if divisor <= 0:
        return None
    return (1.0 + float(current)) / divisor - 1.0


def _series_list(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    """Return one bounded list of series points from a projection document."""

    raw = payload.get(key)
    if raw is None:
        return []
    if not isinstance(raw, list) or any(not isinstance(item, dict) for item in raw):
        raise ValueError(f"projection {key} is not a series")
    return raw


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #


@router.get("/overview", response_model=ProductionOverview)
def get_production_overview() -> ProductionOverview:
    """Return aggregate portfolio truth with explicit completeness."""

    payload = _load_overview()
    payload.pop("series", None)
    payload.pop("strategy_series", None)
    try:
        return ProductionOverview.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(status_code=500, detail="Production projection is invalid") from exc


@router.get("/series", response_model=ProductionSeries)
def get_production_series(
    range: Range = Query(default="30d"),
    metric: Metric = Query(default="pnl_usd"),
) -> ProductionSeries:
    """Return the aggregate line and per-strategy overlays for one range."""

    payload = _load_overview()
    now = datetime.now(tz=UTC)
    try:
        aggregate_raw = _series_list(payload, "series")
        start = _window_start(range, aggregate_raw, now=now)
        aggregate = ProductionSeriesLine(
            family=None, points=_rebase(aggregate_raw, metric=metric, start=start)
        )
        strategy_raw = payload.get("strategy_series") or {}
        if not isinstance(strategy_raw, dict):
            raise ValueError("projection strategy_series is not an object")
        strategies = [
            ProductionSeriesLine(
                family=family,
                points=_rebase(_series_list(strategy_raw, family), metric=metric, start=start),
            )
            for family in sorted(strategy_raw)
            if _FAMILY_PATTERN.fullmatch(family)
        ]
        return ProductionSeries(
            range=range,
            metric=metric,
            portfolio_id=str(payload["portfolio_id"]),
            generated_at=payload["generated_at"],
            complete=payload.get("completeness") == "complete",
            aggregate=aggregate,
            strategies=strategies,
        )
    except (KeyError, TypeError, ValueError, ValidationError) as exc:
        raise HTTPException(status_code=500, detail="Production projection is invalid") from exc


@router.get("/strategies/{family}", response_model=ProductionStrategy)
def get_production_strategy(family: str) -> ProductionStrategy:
    """Return one deployed strategy's snapshot without its level series."""

    payload = _load_snapshot(_require_family(family))
    payload.pop("series", None)
    try:
        snapshot = ProductionStrategy.model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(status_code=500, detail="Production projection is invalid") from exc
    if snapshot.family != family:
        raise HTTPException(status_code=500, detail="Production projection is invalid")
    return snapshot


@router.get("/strategies/{family}/series", response_model=ProductionSeries)
def get_production_strategy_series(
    family: str,
    range: Range = Query(default="30d"),
    metric: Metric = Query(default="pnl_usd"),
) -> ProductionSeries:
    """Return one strategy's line for the selected range and metric."""

    payload = _load_snapshot(_require_family(family))
    now = datetime.now(tz=UTC)
    try:
        raw = _series_list(payload, "series")
        start = _window_start(range, raw, now=now)
        line = ProductionSeriesLine(family=family, points=_rebase(raw, metric=metric, start=start))
        return ProductionSeries(
            range=range,
            metric=metric,
            portfolio_id=str(payload["portfolio_id"]),
            generated_at=payload["generated_at"],
            complete=not bool(payload.get("stale", True)) and bool(raw),
            aggregate=line,
            strategies=[],
        )
    except (KeyError, TypeError, ValueError, ValidationError) as exc:
        raise HTTPException(status_code=500, detail="Production projection is invalid") from exc


__all__ = ["router"]
