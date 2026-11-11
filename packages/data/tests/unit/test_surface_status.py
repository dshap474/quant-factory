"""Unit tests for the operator surface freshness report."""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import polars as pl
from data.platform.storage.operator_surface_registry import OperatorScript
from data.platform.storage.surface_status import (
    SurfaceStatus,
    collect_surface_status,
    expand_surface_patterns,
)


def _entry(
    surface: str, path: str = "raw/1d/demo/demo_sync_raw.py", cadence: str = "daily", **fields
) -> OperatorScript:
    return OperatorScript(
        path=path,
        role="demo",
        example=f"uv run python packages/data/extensions/pipelines/{path}",
        cadence=cadence,
        primary_write_surface=surface,
        notes="demo",
        **fields,
    )


def test_expand_alternation() -> None:
    assert sorted(expand_surface_patterns("db/data/raw/1d/{sec,macro}")) == [
        "data/raw/1d/macro",
        "data/raw/1d/sec",
    ]


def test_expand_placeholders_become_wildcards() -> None:
    assert expand_surface_patterns("db/data/raw/{resolution}/example/{product}/{venue}") == [
        "data/raw/*/example/*/*"
    ]


def test_expand_compound_surface_and_parenthetical_note() -> None:
    assert sorted(expand_surface_patterns("db/data/raw/1d/{sec,macro} and db/data/derived/1d/{sec,macro}")) == [
        "data/derived/1d/macro",
        "data/derived/1d/sec",
        "data/raw/1d/macro",
        "data/raw/1d/sec",
    ]
    assert expand_surface_patterns("db/research/audits/data/provider-parity (diagnostic report only)") == [
        "research/audits/data/provider-parity"
    ]


def test_expand_non_db_targets_yield_nothing() -> None:
    assert expand_surface_patterns("s3://.../external/processed") == []
    assert expand_surface_patterns("Audit only") == []
    assert expand_surface_patterns("raw.example_table in an external database") == []


def test_collect_reports_files_size_and_latest_write(tmp_path: Path) -> None:
    target = tmp_path / "data" / "raw" / "1d" / "demo"
    nested = target / "nested"
    nested.mkdir(parents=True)
    old_file = target / "old.parquet"
    new_file = nested / "new.parquet"
    old_file.write_bytes(b"12345")
    new_file.write_bytes(b"1234567890")
    old_time = datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp()
    os.utime(old_file, (old_time, old_time))

    statuses = collect_surface_status(tmp_path, registry=(_entry("db/data/raw/1d/demo"),))

    assert len(statuses) == 1
    status = statuses[0]
    assert status.script == "pipelines/raw/1d/demo/demo_sync_raw.py"
    assert status.cadence == "daily"
    assert status.parquet_files == 2
    assert status.total_bytes == 15
    assert status.latest_write is not None
    assert abs(status.latest_write.timestamp() - new_file.stat().st_mtime) < 1e-5
    assert status.age_days(now=status.latest_write + timedelta(days=2)) == 2.0


def test_collect_orders_missing_first_then_stalest(tmp_path: Path) -> None:
    fresh_dir = tmp_path / "data" / "raw" / "1d" / "fresh"
    stale_dir = tmp_path / "data" / "raw" / "1d" / "stale"
    fresh_dir.mkdir(parents=True)
    stale_dir.mkdir(parents=True)
    (fresh_dir / "data.parquet").write_bytes(b"x")
    stale_file = stale_dir / "data.parquet"
    stale_file.write_bytes(b"x")
    stale_time = datetime(2025, 6, 1, tzinfo=timezone.utc).timestamp()
    os.utime(stale_file, (stale_time, stale_time))

    registry = (
        _entry("db/data/raw/1d/fresh", path="raw/1d/fresh/a.py"),
        _entry("db/data/raw/1d/missing", path="raw/1d/missing/b.py"),
        _entry("db/data/raw/1d/stale", path="raw/1d/stale/c.py"),
        _entry("Audit only", path="raw/1d/external/d.py"),
    )
    statuses = collect_surface_status(tmp_path, registry=registry)

    assert [status.script for status in statuses] == [
        "pipelines/raw/1d/missing/b.py",
        "pipelines/raw/1d/stale/c.py",
        "pipelines/raw/1d/fresh/a.py",
    ]
    missing = statuses[0]
    assert missing.parquet_files == 0
    assert missing.latest_write is None
    assert missing.age_days() is None


def _status(cadence: str, latest_write: datetime | None) -> SurfaceStatus:
    return SurfaceStatus(
        script="pipelines/raw/1d/demo/demo_sync_raw.py",
        contract="control_plane",
        cadence=cadence,
        surface="db/data/raw/1d/demo",
        parquet_files=1 if latest_write is not None else 0,
        total_bytes=1 if latest_write is not None else 0,
        latest_write=latest_write,
    )


def test_surface_status_age_uses_now_when_not_supplied() -> None:
    status = _status("daily", datetime.now(timezone.utc) - timedelta(days=1))
    age = status.age_days()
    assert age is not None
    assert 0.9 < age < 1.1


def test_is_stale_follows_cadence_thresholds() -> None:
    now = datetime(2026, 7, 4, tzinfo=timezone.utc)
    three_days_old = now - timedelta(days=3)
    assert _status("daily", three_days_old).is_stale(now)
    assert not _status("weekly", three_days_old).is_stale(now)
    assert _status("weekly", now - timedelta(days=10)).is_stale(now)
    assert not _status("on_demand", now - timedelta(days=365)).is_stale(now)


def test_is_stale_missing_artifacts_flag_only_routine_cadences() -> None:
    assert _status("daily", None).is_stale()
    assert _status("weekly", None).is_stale()
    assert not _status("on_demand", None).is_stale()


# --------------------------------------------------------------------------- #
# Data-based freshness
# --------------------------------------------------------------------------- #

NOW = datetime(2026, 10, 16, 2, 0, tzinfo=timezone.utc)  # a Friday


def _write(db_root: Path, relative: str, frame: pl.DataFrame) -> None:
    path = db_root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.write_parquet(path)


def _one(db_root: Path, surface: str = "db/data/raw/1d/demo", **fields) -> SurfaceStatus:
    (status,) = collect_surface_status(db_root, registry=(_entry(surface, **fields),), now=NOW)
    return status


def test_freshness_reads_newest_date_in_data_not_mtime(tmp_path: Path) -> None:
    _write(tmp_path, "data/raw/1d/demo/data.parquet", pl.DataFrame({"timestamp": [datetime(2026, 9, 1)], "close": [1.0]}))

    status = _one(tmp_path)

    # the file was just written, but its data is six weeks old; a 1d bar counts until its day ends
    assert status.basis == "data"
    assert status.newest_data == datetime(2026, 9, 2, tzinfo=timezone.utc)
    assert status.is_stale(NOW)


def test_freshness_uses_schema_timestamp_column_then_fallbacks(tmp_path: Path) -> None:
    (tmp_path / "SCHEMA.yaml").write_text("conventions:\n  timestamp_column: ts\n")
    _write(
        tmp_path,
        "data/raw/1d/demo/a.parquet",
        pl.DataFrame({"ts": [datetime(2026, 10, 15)], "date": [date(2020, 1, 1)]}),
    )
    _write(tmp_path, "data/raw/1d/demo/b.parquet", pl.DataFrame({"time": [int(datetime(2026, 10, 14, tzinfo=timezone.utc).timestamp() * 1000)]}))
    _write(tmp_path, "data/raw/1d/demo/c.parquet", pl.DataFrame({"report_date": ["2026-10-13"]}))

    status = _one(tmp_path)

    assert status.newest_data == datetime(2026, 10, 16, tzinfo=timezone.utc)
    assert not status.is_stale(NOW)


def test_freshness_falls_back_to_write_without_date_column_or_when_registered(tmp_path: Path) -> None:
    _write(tmp_path, "data/raw/1d/demo/data.parquet", pl.DataFrame({"date": [date(2026, 8, 1)], "value": [1.0]}))
    _write(tmp_path, "data/raw/1d/other/data.parquet", pl.DataFrame({"cik": ["1"]}))

    assert _one(tmp_path, freshness="write").basis == "write"
    assert not _one(tmp_path, freshness="write").is_stale(NOW)
    assert _one(tmp_path, surface="db/data/raw/1d/other").basis == "write"


def test_weekdays_freshness_leaves_weekends_out(tmp_path: Path) -> None:
    monday = datetime(2026, 10, 19, 2, 0, tzinfo=timezone.utc)
    _write(tmp_path, "data/raw/1d/demo/data.parquet", pl.DataFrame({"date": [date(2026, 10, 16)]}))  # Friday's bar

    (calendar,) = collect_surface_status(tmp_path, registry=(_entry("db/data/raw/1d/demo"),), now=monday)
    (weekdays,) = collect_surface_status(
        tmp_path, registry=(_entry("db/data/raw/1d/demo", freshness="weekdays"),), now=monday
    )

    assert calendar.is_stale(monday)
    assert not weekdays.is_stale(monday)
    assert abs((weekdays.age_days(monday) or 0) - 2 / 24) < 1e-6


def test_future_dated_and_archived_files_never_count_toward_freshness(tmp_path: Path) -> None:
    _write(tmp_path, "data/raw/1d/demo/data.parquet", pl.DataFrame({"date": [date(2026, 9, 1)]}))
    _write(tmp_path, "data/raw/1d/demo/holidays.parquet", pl.DataFrame({"date": [date(2027, 1, 1)]}))
    _write(tmp_path, "data/raw/1d/demo/_archive/old.parquet", pl.DataFrame({"date": [date(2026, 10, 15)]}))

    status = _one(tmp_path, quality_exempt=("data/raw/1d/demo/holidays.parquet",))

    assert status.newest_data == datetime(2026, 9, 2, tzinfo=timezone.utc)
    assert status.issues == ()


# --------------------------------------------------------------------------- #
# Quality checks
# --------------------------------------------------------------------------- #


def test_quality_flags_duplicate_keys_only_where_declared(tmp_path: Path) -> None:
    frame = pl.DataFrame({"date": [date(2026, 10, 14)] * 2, "symbol": ["A", "A"], "close": [1.0, 2.0]})
    _write(tmp_path, "data/raw/1d/demo/data.parquet", frame)

    assert _one(tmp_path).issues == ()
    (issue,) = _one(tmp_path, keys=("date", "symbol")).issues
    assert "2 rows share a (date, symbol) key" in issue


def test_quality_flags_future_dates_and_dates_before_floor(tmp_path: Path) -> None:
    _write(tmp_path, "data/raw/1d/demo/data.parquet", pl.DataFrame({"timestamp": [datetime(1833, 1, 7), datetime(2026, 12, 1)]}))

    issues = _one(tmp_path).issues

    assert any(issue.startswith("future timestamp 2026-12-01") for issue in issues)
    assert any("1833-01-07 before floor 1900-01-01" in issue for issue in issues)


def test_quality_flags_non_positive_prices_unless_exempt(tmp_path: Path) -> None:
    frame = pl.DataFrame(
        {"date": [date(2026, 10, 14)] * 2, "close_price": [10.0, 0.0], "has_price": [0, 1], "spread": [-1.0, 1.0]}
    )
    _write(tmp_path, "data/raw/1d/demo/data.parquet", frame)

    (issue,) = _one(tmp_path).issues
    assert issue.startswith("close_price <= 0 (min 0)")
    assert _one(tmp_path, quality_exempt=("data/raw/1d/demo/*",)).issues == ()


def test_quality_flags_unreadable_parquet_and_skips_on_demand(tmp_path: Path) -> None:
    target = tmp_path / "data" / "raw" / "1d" / "demo"
    target.mkdir(parents=True)
    (target / "data.parquet").write_bytes(b"torn")

    (issue,) = _one(tmp_path).issues
    assert issue.startswith("unreadable parquet data/raw/1d/demo/data.parquet")
    assert _one(tmp_path, cadence="on_demand").issues == ()
