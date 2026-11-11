"""Freshness and quality reporting for registered operator write surfaces.

Freshness comes from the data: the newest value of each file's date column (``conventions.timestamp_column``
in ``db/SCHEMA.yaml``, else the first of ``DATE_COLUMN_FALLBACKS``), read from parquet footer statistics.
A ``1d`` pipeline's midnight-stamped bar counts until the end of its day. Surfaces with no date column, or
registered ``freshness="write"``, fall back to the newest write or last successful refresh; ``"weekdays"``
leaves weekends out of the age. Files dated in the future (schedules) never count toward freshness, and
``_archive``/hidden paths are ignored. Daily and weekly surfaces also get three cheap checks: duplicate
``keys`` (when the registry declares them), dates in the future or before ``START_FLOOR``, and price
columns at or below zero; ``quality_exempt`` globs waive files whose values are legitimately so.
A Delta table counts once: bytes and file count from its add actions, latest write from its last commit,
and the same facts computed through a lazy scan of the table.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

import polars as pl
import pyarrow.compute as pc
import pyarrow.parquet as pq
import yaml

from . import delta_read
from .operator_surface_registry import OPERATOR_SCRIPTS, OperatorScript
from .refresh import read_refresh_log

_BRACE_RE = re.compile(r"\{([^{}]*)\}")

# Days after which a pipeline's newest data counts as stale for its
# cadence. ``on_demand`` pipelines are never stale.
CADENCE_STALE_DAYS: dict[str, float] = {"daily": 2.0, "weekly": 9.0}

DATE_COLUMN_FALLBACKS = ("date", "time", "trade_date", "report_date", "settlement_date")
PRICE_COLUMNS = frozenset({"open", "high", "low", "close", "adj_close", "price", "midprice"})
START_FLOOR = datetime(1900, 1, 1, tzinfo=timezone.utc)
FUTURE_TOLERANCE = timedelta(days=1)


def expand_surface_patterns(surface: str) -> list[str]:
    """Expand a registry ``primary_write_surface`` into db-root-relative glob patterns.

    Compound surfaces split on ``" and "``; trailing parenthetical notes are
    dropped; ``{a,b}`` alternations expand; single ``{placeholder}`` tokens
    become ``*``. Non-``db/`` targets (S3, TimescaleDB, audit-only) yield no
    patterns.
    """
    patterns: list[str] = []
    for part in surface.split(" and "):
        token = part.split(" (")[0].strip()
        if not token.startswith("db/"):
            continue
        stack = [token.removeprefix("db/")]
        while stack:
            candidate = stack.pop()
            match = _BRACE_RE.search(candidate)
            if match is None:
                patterns.append(candidate)
                continue
            body = match.group(1)
            choices = [choice.strip() for choice in body.split(",")] if "," in body else ["*"]
            for choice in choices:
                stack.append(candidate[: match.start()] + choice + candidate[match.end() :])
    return patterns


@dataclass(frozen=True, slots=True)
class SurfaceStatus:
    """Parquet footprint, data freshness, and quality issues for one registered pipeline."""

    script: str
    contract: str
    cadence: str
    surface: str
    parquet_files: int
    total_bytes: int
    latest_write: datetime | None
    last_refresh: datetime | None = None
    newest_data: datetime | None = None
    """Newest date inside the data across the surface's files; ``None`` when no file has a date column."""
    issues: tuple[str, ...] = ()
    freshness: str = "data"

    @property
    def latest_update(self) -> datetime | None:
        """Newest data date; without one, the newest write or successful ``qf-data refresh`` run."""
        if self.newest_data is not None:
            return self.newest_data
        stamps = [stamp for stamp in (self.latest_write, self.last_refresh) if stamp is not None]
        return max(stamps) if stamps else None

    @property
    def basis(self) -> str:
        """``data`` when age comes from dates in the files, ``write`` when it falls back to stamps."""
        return "data" if self.newest_data is not None else "write"

    def age_days(self, now: datetime | None = None) -> float | None:
        if self.latest_update is None:
            return None
        reference = now if now is not None else datetime.now(timezone.utc)
        age = (reference - self.latest_update).total_seconds() / 86400.0
        if self.freshness == "weekdays" and self.newest_data is not None:
            age -= _weekend_days(self.newest_data, reference)
        return age

    def is_stale(self, now: datetime | None = None) -> bool:
        """True when a daily/weekly surface is missing or older than its cadence allows."""
        threshold = CADENCE_STALE_DAYS.get(self.cadence)
        if threshold is None:
            return False
        age = self.age_days(now)
        return age is None or age > threshold


def _weekend_days(start: datetime, end: datetime) -> float:
    """Days of Saturday and Sunday (UTC) inside ``[start, end]``."""
    total = 0.0
    day = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
    while day < end:
        if day.weekday() >= 5:
            overlap = min(end, day + timedelta(days=1)) - max(start, day)
            total += max(overlap.total_seconds(), 0.0) / 86400.0
        day += timedelta(days=1)
    return total


# --------------------------------------------------------------------------- #
# Per-file facts
# --------------------------------------------------------------------------- #


def schema_timestamp_column(db_root: Path) -> str:
    """``conventions.timestamp_column`` from ``db/SCHEMA.yaml``; ``timestamp`` when absent."""
    path = db_root / "SCHEMA.yaml"
    if path.is_file():
        loaded = yaml.safe_load(path.read_text()) or {}
        column = (loaded.get("conventions") or {}).get("timestamp_column")
        if isinstance(column, str) and column:
            return column
    return "timestamp"


def _as_utc(value: Any) -> datetime | None:
    """Coerce a parquet statistic (datetime, date, epoch int, ISO string) to an aware UTC datetime."""
    if value is None:
        return None
    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    if isinstance(value, int) and not isinstance(value, bool):
        for magnitude, scale in ((1e17, 1e9), (1e14, 1e6), (1e11, 1e3), (1e8, 1.0)):  # epoch ns, us, ms, s
            if abs(value) >= magnitude:
                return datetime.fromtimestamp(value / scale, tz=timezone.utc)
        return None
    if isinstance(value, str):
        for candidate in (value, value[:10]):
            try:
                return _as_utc(datetime.fromisoformat(candidate))
            except ValueError:
                continue
    return None


def _column_min_max(parquet: pq.ParquetFile, column: str) -> tuple[Any, Any]:
    """Min and max of one column from row-group statistics, reading the column only when stats are missing."""
    index = parquet.schema_arrow.get_field_index(column)
    metadata = parquet.metadata
    lows: list[Any] = []
    highs: list[Any] = []
    for group in range(metadata.num_row_groups):
        stats = metadata.row_group(group).column(index).statistics
        if stats is None or not stats.has_min_max:
            if metadata.row_group(group).num_rows == 0:
                continue
            result = pc.min_max(parquet.read(columns=[column]).column(column))
            return result["min"].as_py(), result["max"].as_py()
        lows.append(stats.min)
        highs.append(stats.max)
    return (min(lows) if lows else None), (max(highs) if highs else None)


def _date_column(names: list[str], timestamp_column: str) -> str | None:
    for column in (timestamp_column, *DATE_COLUMN_FALLBACKS):
        if column in names:
            return column
    return None


def _is_price_column(name: str) -> bool:
    lowered = name.lower()
    return lowered in PRICE_COLUMNS or (lowered.endswith("_price") and not lowered.startswith(("has_", "is_")))


@dataclass(frozen=True, slots=True)
class _FileFacts:
    oldest: datetime | None
    newest: datetime | None
    issues: tuple[str, ...]


def _file_facts(path: Path, *, label: str, timestamp_column: str, keys: tuple[str, ...], now: datetime) -> _FileFacts:
    try:
        parquet = pq.ParquetFile(path)
    except Exception as exc:  # noqa: BLE001 - a corrupt file is itself the finding
        return _FileFacts(None, None, (f"unreadable parquet {label}: {type(exc).__name__}",))
    names = parquet.schema_arrow.names
    issues: list[str] = []
    oldest = newest = None
    column = _date_column(names, timestamp_column)
    if column is not None:
        low, high = _column_min_max(parquet, column)
        oldest, newest = _as_utc(low), _as_utc(high)
        if newest is not None and newest > now + FUTURE_TOLERANCE:
            issues.append(f"future {column} {newest:%Y-%m-%d} in {label}")
        if oldest is not None and oldest < START_FLOOR:
            issues.append(f"{column} {oldest:%Y-%m-%d} before floor {START_FLOOR:%Y-%m-%d} in {label}")
    for name in names:
        if not _is_price_column(name):
            continue
        low, _ = _column_min_max(parquet, name)
        if isinstance(low, (int, float)) and low <= 0:
            issues.append(f"{name} <= 0 (min {low:g}) in {label}")
    if keys and set(keys) <= set(names):
        duplicated = pl.scan_parquet(path).select(keys).collect().is_duplicated().sum()
        if duplicated:
            issues.append(f"{duplicated} rows share a ({', '.join(keys)}) key in {label}")
    return _FileFacts(oldest, newest, tuple(issues))


def _table_facts(path: Path, *, label: str, timestamp_column: str, keys: tuple[str, ...], now: datetime) -> _FileFacts:
    """``_file_facts`` for a Delta table, through one lazy scan (plus one for duplicate keys)."""
    try:
        lazy = delta_read.lake_scan(path)
        names = lazy.collect_schema().names()
    except Exception as exc:  # noqa: BLE001 - an unreadable table is itself the finding
        return _FileFacts(None, None, (f"unreadable Delta table {label}: {type(exc).__name__}",))
    column = _date_column(names, timestamp_column)
    prices = [name for name in names if _is_price_column(name)]
    exprs = [pl.col(column).min().alias("__low"), pl.col(column).max().alias("__high")] if column else []
    exprs += [pl.col(name).min().alias(name) for name in prices]
    row = lazy.select(exprs).collect().row(0, named=True) if exprs else {}
    issues: list[str] = []
    oldest = newest = None
    if column is not None:
        oldest, newest = _as_utc(row["__low"]), _as_utc(row["__high"])
        if newest is not None and newest > now + FUTURE_TOLERANCE:
            issues.append(f"future {column} {newest:%Y-%m-%d} in {label}")
        if oldest is not None and oldest < START_FLOOR:
            issues.append(f"{column} {oldest:%Y-%m-%d} before floor {START_FLOOR:%Y-%m-%d} in {label}")
    for name in prices:
        low = row[name]
        if isinstance(low, (int, float)) and low <= 0:
            issues.append(f"{name} <= 0 (min {low:g}) in {label}")
    if keys and set(keys) <= set(names):
        duplicated = lazy.select(keys).collect().is_duplicated().sum()
        if duplicated:
            issues.append(f"{duplicated} rows share a ({', '.join(keys)}) key in {label}")
    return _FileFacts(oldest, newest, tuple(issues))


# --------------------------------------------------------------------------- #
# Collection
# --------------------------------------------------------------------------- #


def collect_surface_status(
    db_root: Path,
    registry: tuple[OperatorScript, ...] = OPERATOR_SCRIPTS,
    *,
    now: datetime | None = None,
) -> list[SurfaceStatus]:
    """Report freshness and quality for every registry entry that writes under ``db/``.

    Entries whose write surface is external (S3, TimescaleDB, audit-only) are
    omitted. Quality checks run on daily and weekly surfaces only. Results
    order missing artifacts first, then stalest to freshest.
    """
    reference = now if now is not None else datetime.now(timezone.utc)
    refreshed = read_refresh_log(db_root)
    timestamp_column = schema_timestamp_column(db_root)
    results: list[SurfaceStatus] = []
    for entry in registry:
        patterns = expand_surface_patterns(entry.primary_write_surface)
        if not patterns:
            continue
        files: set[Path] = set()
        tables: set[Path] = set()
        for pattern in patterns:
            for match in db_root.glob(pattern):
                if delta_read.is_table_internal(match.relative_to(db_root)):
                    continue
                table = delta_read.enclosing_delta(match, db_root)
                if table is not None:
                    tables.add(table)
                elif match.is_dir():
                    found, nested = delta_read.walk_lake(match)
                    files.update(found)
                    tables.update(nested)
                elif match.suffix == ".parquet":
                    files.add(match)
            tables.update(delta_read.mapped_tables(db_root, pattern))  # surfaces that still name legacy keys
        total_bytes = 0
        file_count = len(files)
        latest_mtime: float | None = None
        for file in files:
            stat = file.stat()
            total_bytes += stat.st_size
            if latest_mtime is None or stat.st_mtime > latest_mtime:
                latest_mtime = stat.st_mtime
        if tables:
            from . import delta_tables as dtab

            for table in tables:
                ref = delta_read.path_ref(table)
                stats = dtab.table_stats(ref)
                total_bytes += stats.bytes
                file_count += stats.files
                committed = dtab.table_commit_time(ref)
                if committed is not None and (latest_mtime is None or committed.timestamp() > latest_mtime):
                    latest_mtime = committed.timestamp()
        newest_data: datetime | None = None
        issues: list[str] = []
        daily_bars = entry.path.split("/")[1:2] == ["1d"]
        for file in sorted(files | tables):
            label = str(file.relative_to(db_root))
            if any(part.startswith(("_archive", ".")) for part in Path(label).parts):
                continue
            facts = (_table_facts if file in tables else _file_facts)(
                file, label=label, timestamp_column=timestamp_column, keys=entry.keys, now=reference
            )
            newest = facts.newest
            if newest is not None and daily_bars and newest.time() == datetime.min.time():
                newest += timedelta(days=1)  # a daily bar covers its whole day
            if newest is not None and newest <= reference + FUTURE_TOLERANCE:
                newest_data = newest if newest_data is None else max(newest_data, newest)
            if entry.cadence in CADENCE_STALE_DAYS and not any(fnmatch(label, glob) for glob in entry.quality_exempt):
                issues.extend(facts.issues)
        results.append(
            SurfaceStatus(
                script=f"{entry.root}/{entry.path}",
                contract=entry.contract,
                cadence=entry.cadence,
                surface=entry.primary_write_surface,
                parquet_files=file_count,
                total_bytes=total_bytes,
                latest_write=(
                    datetime.fromtimestamp(latest_mtime, tz=timezone.utc) if latest_mtime is not None else None
                ),
                last_refresh=refreshed.get(entry.path) if entry.root == "pipelines" else None,
                newest_data=None if entry.freshness == "write" else newest_data,
                issues=tuple(issues),
                freshness=entry.freshness,
            )
        )
    results.sort(key=lambda status: (status.latest_update is not None, status.latest_update or datetime.min))
    return results


__all__ = [
    "CADENCE_STALE_DAYS",
    "SurfaceStatus",
    "collect_surface_status",
    "expand_surface_patterns",
    "schema_timestamp_column",
]
