"""Rank one version's displayed configurations against published family versions.

Each other version contributes exactly one primary path: its explicitly published
grid selection, otherwise its strategy performance stream. Every path is cut to one
common daily window and re-measured with one set of conventions before ranking.

USAGE:
    payload = family_rank_comparison(db_root, discovered_versions, "family", "v003")
    rank_cell(1.2, [0.4, 1.2, 2.0], "higher")  # {"rank": 2, "count": 4, "ties": 1, ...}
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import polars as pl
from backtest import summarize_path_risk
from data.query import ParquetQuery, QueryError, query_parquet
from strategies.research_surface import (
    RANKED_METRICS,
    MetricDirection,
    load_research_surface,
    metric_definitions,
    research_display_state,
    summarize_returns,
)

# --------------------------------------------------------------------------- #
# Conventions
# --------------------------------------------------------------------------- #

COMPARISON_LABEL = "Against published versions"
CONVENTIONS = (
    "Every path is cut to the common daily window and restarted at a $100 NAV on the "
    "window's starting mark (the date before its first return). Returns are recorded net "
    "returns; dates are matched exactly, never filled or interpolated. Annualization uses "
    "365 days. Sharpe and volatility use the population standard deviation of daily "
    "returns; Sortino uses a 0% target and the root mean square shortfall over all "
    "returns; drawdowns, Calmar and Martin include the starting mark. Undefined ratios "
    "stay null and are not ranked."
)
_LOAD_ERRORS = (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError, pl.exceptions.PolarsError)


class RankUnavailable(Exception):
    """The requested version has no usable displayed path."""


# --------------------------------------------------------------------------- #
# Dated paths and the common window
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class DatedPath:
    """NAV mark dates (starting mark first) and the return earned on each later mark."""

    marks: tuple[date, ...]
    returns: tuple[float, ...]


def dated_path(dates: Sequence[date], returns: Sequence[float]) -> DatedPath:
    """Build a path; a zero first return is its $100 anchor, else the prior day is.

    This is the existing research surface convention (see research_risk).
    """
    if not dates or len(dates) != len(returns):
        raise ValueError("path needs aligned, nonempty dates and returns")
    if any(right <= left for left, right in zip(dates, dates[1:], strict=False)):
        raise ValueError("path dates must be unique and increasing")
    if any(value is None or not math.isfinite(value) or value < -1.0 for value in returns):
        raise ValueError("path returns must be finite and at least -100%")
    if returns[0] == 0.0:
        return DatedPath(tuple(dates), tuple(returns[1:]))
    return DatedPath((dates[0] - timedelta(days=1), *dates), tuple(returns))


def window_returns(path: DatedPath, window: Sequence[date]) -> tuple[tuple[float, ...] | None, str | None]:
    """Return the path's returns on the window's marks, or an exclusion code."""
    try:
        start = path.marks.index(window[0])
    except ValueError:
        start = -1
    if start >= 0 and path.marks[start:start + len(window)] == tuple(window):
        return path.returns[start:start + len(window) - 1], None
    if path.marks[0] > window[0] or path.marks[-1] < window[-1]:
        return None, "outside_window"
    return None, "date_mismatch"


def common_window(paths: Sequence[DatedPath]) -> tuple[date, ...]:
    """The displayed paths' shared marks; raises when their daily axes disagree."""
    start = max(path.marks[0] for path in paths)
    end = min(path.marks[-1] for path in paths)
    axes = {tuple(mark for mark in path.marks if start <= mark <= end) for path in paths}
    if len(axes) != 1:
        raise RankUnavailable("Displayed configurations do not share one daily date axis.")
    window = axes.pop()
    if len(window) < 3:
        raise RankUnavailable("The common window has fewer than two daily returns.")
    return window


# --------------------------------------------------------------------------- #
# Metrics and ranks
# --------------------------------------------------------------------------- #


def window_metrics(returns: Sequence[float], window: Sequence[date]) -> dict[str, float | None]:
    """Measure one window path with the shared research and backtest helpers."""
    nav = [100.0]
    for value in returns:
        nav.append(nav[-1] * (1.0 + value))
    measured = {**summarize_returns(list(returns)), **summarize_path_risk(nav, list(window), periods_per_year=365.0)}
    return {
        key: float(value) if isinstance(value, (int, float)) and math.isfinite(value) else None
        for key, value in ((key, measured.get(key)) for key in RANKED_METRICS)
    }


def rank_cell(value: float | None, others: Sequence[float | None], direction: MetricDirection) -> dict[str, Any] | None:
    """Competition rank (1, 2, 2, 4) of value among itself and others; 1 is best.

    Count includes only finite observations. Position is 0 (best) to 1 (worst) at the
    tie midpoint, and None for a singleton or an all-equal cohort.
    """
    if direction == "unranked" or value is None or not math.isfinite(value):
        return None
    valid = [item for item in others if item is not None and math.isfinite(item)]
    count = len(valid) + 1
    better = sum(item > value if direction == "higher" else item < value for item in valid)
    ties = sum(item == value for item in valid)
    position = None if count < 2 or ties == count - 1 else (better + ties / 2) / (count - 1)
    return {"rank": better + 1, "count": count, "ties": ties, "position": position, "value": value}


# --------------------------------------------------------------------------- #
# Primary paths from published surfaces
# --------------------------------------------------------------------------- #


def _grid_streams(db_root: Path, strategy_type: str, memory_version: str, grid: Mapping[str, Any],
                  config_ids: tuple[str, ...] | None) -> dict[str, DatedPath]:
    """Read projected grid series once; config_ids=None reads every configuration."""
    series = grid["series"]
    config_column, date_column, return_column = (
        str(series["config_id_column"]), str(series["date_column"]), str(series["return_column"]),
    )
    frame = query_parquet(
        ParquetQuery(
            scope="research",
            path=f"strategies/{strategy_type}/{memory_version}/{series['path']}",
            columns=(config_column, date_column, return_column),
            entity_column=config_column if config_ids else None,
            entity_values=config_ids or (),
            limit=None,
        ),
        db_root=db_root,
    ).frame.select(
        pl.col(config_column).cast(pl.String).alias("config_id"),
        pl.col(date_column).cast(pl.Date).alias("date"),
        pl.col(return_column).cast(pl.Float64).alias("daily_return"),
    )
    return {
        str(config_id): dated_path(stream["date"].to_list(), stream["daily_return"].to_list())
        for (config_id,), stream in frame.sort("date").partition_by("config_id", as_dict=True).items()
    }


def _strategy_stream(frame: pl.DataFrame) -> DatedPath:
    if "strategy_daily_return" not in frame.columns:
        raise LookupError("no_return_path")
    return dated_path(frame["date"].cast(pl.Date).to_list(), frame["strategy_daily_return"].to_list())


def _primary(db_root: Path, strategy_type: str, memory_version: str) -> tuple[DatedPath, str | None, str]:
    """One version's published primary path; raises LookupError(code) when unusable."""
    try:
        loaded = load_research_surface(db_root, strategy_type, memory_version)
    except _LOAD_ERRORS as exc:
        raise LookupError("invalid_surface") from exc
    if loaded is None:
        raise LookupError("no_surface")
    frame, manifest = loaded
    if research_display_state(manifest) == "rejected":
        raise LookupError("rejected")
    grid = manifest.get("grid")
    try:
        if isinstance(grid, dict):
            selected = str(grid["selected_config_id"])
            streams = _grid_streams(db_root, strategy_type, memory_version, grid, (selected,))
            if selected not in streams:
                raise LookupError("incomplete_path")
            return streams[selected], selected, research_display_state(manifest)
        return _strategy_stream(frame), None, research_display_state(manifest)
    except LookupError:
        raise
    except (QueryError, *_LOAD_ERRORS) as exc:
        raise LookupError("incomplete_path") from exc


_REASONS = {
    "rejected": "Rejected surface: not correctness-valid.",
    "not_tested": "Not tested: the latest attempt was invalidated.",
    "no_surface": "No published research surface.",
    "invalid_surface": "Published surface failed validation.",
    "no_return_path": "Surface has no daily return path.",
    "incomplete_path": "Primary path is missing, duplicated or non-finite.",
    "outside_window": "History does not cover the common window.",
    "date_mismatch": "Daily dates inside the common window differ (gap or extra dates).",
}


# --------------------------------------------------------------------------- #
# Family comparison
# --------------------------------------------------------------------------- #


def family_rank_comparison(
    db_root: Path,
    versions: Sequence[Mapping[str, Any]],
    strategy_type: str,
    memory_version: str,
) -> dict[str, Any]:
    """Rank the requested version's displayed configurations against other versions.

    versions is the validated family discovery (strategies.research_surface). The
    requested version's displayed configurations stand in for that version, so it is
    never counted twice. Raises RankUnavailable when the version itself is unusable.
    """
    try:
        loaded = load_research_surface(db_root, strategy_type, memory_version)
    except _LOAD_ERRORS as exc:
        raise RankUnavailable("The requested surface failed validation.") from exc
    if loaded is None:
        raise RankUnavailable("The requested version has no research surface.")
    frame, manifest = loaded
    grid = manifest.get("grid")
    try:
        displayed = (
            _grid_streams(db_root, strategy_type, memory_version, grid, None)
            if isinstance(grid, dict)
            else {"strategy": _strategy_stream(frame)}
        )
    except (LookupError, QueryError, *_LOAD_ERRORS) as exc:
        raise RankUnavailable("The requested version has no complete daily return path.") from exc

    payload: dict[str, Any] = {
        "strategy_type": strategy_type,
        "memory_version": memory_version,
        "label": COMPARISON_LABEL,
        "conventions": CONVENTIONS,
        "metrics": metric_definitions(),
        "window": None,
        "unavailable_reason": None,
        "peers": [],
        "excluded": [],
        "columns": [],
    }
    try:
        window = common_window(list(displayed.values()))
    except RankUnavailable as exc:
        return {**payload, "unavailable_reason": str(exc)}

    peers: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for row in sorted(versions, key=lambda item: str(item["memory_version"])):
        version = str(row["memory_version"])
        if row.get("strategy_type") != strategy_type or version == memory_version:
            continue
        code: str | None = None
        returns: tuple[float, ...] | None = None
        config_id: str | None = None
        display_state = str(row.get("display_state"))
        if row.get("display_state") == "invalidated" or row.get("state") == "invalidated":
            code = "not_tested"
        elif row.get("display_state") == "rejected":
            code = "rejected"
        elif not row.get("has_surface"):
            code = "no_surface"
        if code is None:
            try:
                path, config_id, display_state = _primary(db_root, strategy_type, version)
                returns, code = window_returns(path, window)
            except LookupError as exc:
                code = str(exc.args[0]) if exc.args and str(exc.args[0]) in _REASONS else "no_return_path"
        if code is not None or returns is None:
            code = code or "incomplete_path"
            excluded.append({"memory_version": version, "reason": code, "detail": _REASONS[code]})
            continue
        peers.append({
            "memory_version": version,
            "display_state": display_state,
            "source": "selected_configuration" if config_id is not None else "strategy",
            "config_id": config_id,
            "values": window_metrics(returns, window),
        })

    columns = []
    for config_id, path in displayed.items():
        returns, _ = window_returns(path, window)
        assert returns is not None  # The window is drawn from the displayed axes.
        values = window_metrics(returns, window)
        columns.append({
            "config_id": config_id,
            "values": values,
            "ranks": {
                key: rank_cell(values[key], [peer["values"][key] for peer in peers], direction)
                for key, (direction, _) in RANKED_METRICS.items()
            },
        })
    return {
        **payload,
        "window": {
            "start_mark": window[0].isoformat(),
            "first_return": window[1].isoformat(),
            "end": window[-1].isoformat(),
            "observations": len(window) - 1,
        },
        "peers": peers,
        "excluded": excluded,
        "columns": columns,
    }
