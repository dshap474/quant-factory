"""Unit tests for the routine refresh plan.

USAGE: uv run pytest packages/data/tests/unit/test_refresh.py -q
"""

from __future__ import annotations

import time
from pathlib import Path

from data.platform.storage.operator_surface_registry import OperatorScript
from data.platform.storage.refresh import (
    TIMEOUT_RETURNCODE,
    _run_step,
    refresh_command,
    refresh_plan,
)

# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


def _entry(path: str, refresh: str | None = "", cadence: str = "daily", root: str = "pipelines") -> OperatorScript:
    return OperatorScript(
        path=path,
        role="demo",
        example="demo",
        cadence=cadence,
        primary_write_surface="db/data/demo",
        notes="demo",
        root=root,
        refresh=refresh,
    )


SCRIPTS = (
    _entry("derived/1d/b/b_sync_derived.py"),
    _entry("raw/1d/a/a_sync_raw.py", refresh="--days 7"),
    _entry("corrected/1d/a/a_correct.py"),
    _entry("derived/1d/c/c_sync_derived.py", cadence="weekly"),
    _entry("raw/1d/skip/skip_sync_raw.py", refresh=None),
    _entry("raw/1h/a/a_sync_raw.py"),
    _entry("raw/1d/x/x_sync_raw.py", root="scripts"),
)

# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


def test_plan_runs_raw_then_corrected_then_derived_in_registry_order() -> None:
    plan = refresh_plan(resolution="1d", scripts=SCRIPTS)
    assert [entry.path for entry in plan] == [
        "raw/1d/a/a_sync_raw.py",
        "corrected/1d/a/a_correct.py",
        "derived/1d/b/b_sync_derived.py",
        "derived/1d/c/c_sync_derived.py",
    ]


def test_plan_filters_cadence_and_match() -> None:
    assert [entry.path for entry in refresh_plan(resolution="1d", cadence="weekly", scripts=SCRIPTS)] == [
        "derived/1d/c/c_sync_derived.py"
    ]
    assert [entry.path for entry in refresh_plan(resolution="1d", match="/b/", scripts=SCRIPTS)] == [
        "derived/1d/b/b_sync_derived.py"
    ]


def test_command_runs_through_run_local(tmp_path: Path, monkeypatch) -> None:
    run_local = tmp_path / "run-local"
    run_local.touch()
    monkeypatch.setattr("data.platform.storage.refresh.RUN_LOCAL", run_local)
    command = refresh_command(SCRIPTS[1])
    assert command[:2] == [str(run_local), "--"]
    assert command[3].endswith("pipelines/raw/1d/a/a_sync_raw.py")
    assert command[4:] == ["--days", "7"]


def test_plan_without_resolution_covers_every_resolution() -> None:
    assert [entry.path for entry in refresh_plan(scripts=SCRIPTS)] == [
        "raw/1d/a/a_sync_raw.py",
        "raw/1h/a/a_sync_raw.py",
        "corrected/1d/a/a_correct.py",
        "derived/1d/b/b_sync_derived.py",
        "derived/1d/c/c_sync_derived.py",
    ]


def test_step_timeout_kills_the_whole_process_group(tmp_path: Path) -> None:
    marker = tmp_path / "survived"
    # the grandchild outlives its parent unless the whole group is killed
    command = ["bash", "-c", f"(sleep 2; touch {marker}) & sleep 30"]

    started = time.monotonic()
    assert _run_step(command, timeout=0.5) == TIMEOUT_RETURNCODE
    assert time.monotonic() - started < 10
    time.sleep(2.5)
    assert not marker.exists()


def test_step_returns_child_exit_code() -> None:
    assert _run_step(["bash", "-c", "exit 3"], timeout=10) == 3
