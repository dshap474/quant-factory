"""Unit tests for saved research runs, promotion, and promoted-version discovery."""

from __future__ import annotations

import json
from datetime import datetime

import polars as pl
import pytest
from strategies.results import BacktestOutput
from strategies.versioned import (
    discover_strategy_versions,
    get_version_final_dir,
    load_version_final_artifact,
    load_version_runs,
    promote_run,
)

from strategies import StrategyWeights

# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

TYPE, VERSION = "example-ranking-strategy", "v001"


def _save_run(db_root, *, run_id: str, preset: str, total_return: float):
    run_dir = db_root / "research/strategies" / TYPE / VERSION / preset / run_id
    stamps = [datetime(2024, 1, day) for day in (1, 2, 3)]
    StrategyWeights(
        weights=pl.DataFrame({"timestamp": stamps, "BTC": [0.5] * 3, "CASH": [0.5] * 3}), assets=["BTC"]
    ).save(run_dir / "decisions.parquet")
    BacktestOutput(
        strategy_id=preset,
        run_id=run_id,
        equity=pl.DataFrame({"timestamp": stamps, "equity": [1.0, 1.0 + total_return / 2, 1.0 + total_return]}),
        metrics={"total_return": total_return, "sharpe": total_return * 2.0},
        config={"preset": preset},
        created_at=datetime(2024, 1, 3, 12),
        data_range={"start": "2024-01-01", "end": "2024-01-03"},
        strategy_type=TYPE,
        memory_version=VERSION,
        preset=preset,
    ).save(run_dir)
    return run_dir


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


def test_load_version_runs_reads_saved_run_dirs_only(tmp_path):
    _save_run(tmp_path, run_id="run-a", preset="alpha", total_return=0.1)
    _save_run(tmp_path, run_id="run-b", preset="beta", total_return=0.3)
    stray = tmp_path / "research/strategies" / TYPE / VERSION / "grid/run-c"
    stray.mkdir(parents=True)
    (stray / "meta.json").write_text("{}")

    runs = load_version_runs(tmp_path, TYPE, VERSION)

    assert runs["run_id"].to_list() == ["run-a", "run-b"]
    assert runs["preset"].to_list() == ["alpha", "beta"]
    assert runs["total_return"].to_list() == [0.1, 0.3]
    assert runs["data_start"].to_list() == ["2024-01-01"] * 2


def test_promote_run_copies_the_chosen_run_and_never_overwrites(tmp_path):
    _save_run(tmp_path, run_id="run-a", preset="alpha", total_return=0.1)
    _save_run(tmp_path, run_id="run-b", preset="beta", total_return=0.3)

    final_dir = promote_run(tmp_path, TYPE, VERSION, "run-a")

    assert final_dir == get_version_final_dir(tmp_path, TYPE, VERSION)
    assert (final_dir / "decisions.parquet").exists()
    equity, meta = load_version_final_artifact(tmp_path, TYPE, VERSION)
    assert equity.height == 3
    assert meta["selected_run_id"] == "run-a" and meta["preset"] == "alpha"
    with pytest.raises(FileExistsError):
        promote_run(tmp_path, TYPE, VERSION, "run-b")
    with pytest.raises(FileNotFoundError):
        promote_run(tmp_path, TYPE, "v002", "run-a")


def test_discover_strategy_versions_lists_promoted_finals_only(tmp_path):
    _save_run(tmp_path, run_id="run-a", preset="alpha", total_return=0.1)
    (tmp_path / "strategies" / TYPE / "versions" / "v002").mkdir(parents=True)
    assert discover_strategy_versions(tmp_path) == []

    promote_run(tmp_path, TYPE, VERSION, "run-a")

    assert discover_strategy_versions(tmp_path) == [{
        "strategy_type": TYPE,
        "memory_version": VERSION,
        "total_runs": 1,
        "has_final": True,
        "best_sharpe": 0.2,
        "best_return": 0.1,
        "final_run_id": "run-a",
        "latest_run": "2024-01-03T12:00:00",
    }]


def test_saved_meta_records_family_version_and_preset(tmp_path):
    run_dir = _save_run(tmp_path, run_id="run-a", preset="alpha", total_return=0.1)
    meta = json.loads((run_dir / "meta.json").read_text())
    assert (meta["strategy_type"], meta["memory_version"], meta["preset"]) == (TYPE, VERSION, "alpha")
    loaded = BacktestOutput.from_path(run_dir)
    assert (loaded.strategy_type, loaded.memory_version, loaded.preset) == (TYPE, VERSION, "alpha")
