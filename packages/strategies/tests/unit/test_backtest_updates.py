"""Updated backtests rerun a version's backtest through the newest inputs beside the published one.

USAGE: uv run pytest packages/strategies/tests/unit/test_backtest_updates.py -q
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta

import polars as pl
import pytest

from strategies import ExecutionTiming, LedgerInputs, StrategyRunConfig, StrategyRunner, StrategyWeights
from strategies import backtest_updates as updates

DAY, CLOSE = timedelta(days=1), timedelta(days=1, microseconds=-1)
FIRST = datetime(2026, 1, 1, tzinfo=UTC)
DAYS = 10


# --------------------------------------------------------------------------- #
# Three fake families: account-aware, weight-history and event-driven (own NAV)
# --------------------------------------------------------------------------- #
def _config(family: str, version: str) -> StrategyRunConfig:
    return StrategyRunConfig(strategy_id=family, strategy_type=family, save=False, memory_version=version)


class LedgerRunner(StrategyRunner):
    def load_data(self):
        return pl.DataFrame()

    def get_config_dict(self):
        return {}

    def _decide_with_account_state(self, data, state):
        return StrategyWeights(
            weights=pl.DataFrame({"timestamp": [state.timestamp], "BTC": [0.5], "CASH": [0.5]}),
            assets=["BTC"], execution=ExecutionTiming.next_bar())

    def ledger_inputs(self, market=None):
        days = [FIRST + i * DAY for i in range(DAYS)]
        times = [t for day in days for t in (day, day + CLOSE)]
        market = pl.DataFrame({"timestamp": times, "kind": ["open", "close"] * DAYS,
                               "BTC": [100.0 + i for i in range(len(times))]})
        return LedgerInputs(market=market, decision_times=[day + CLOSE for day in days[:-1]])


class WeightsRunner(StrategyRunner):
    def load_data(self):
        stamps = [FIRST + i * DAY for i in range(DAYS)]
        return pl.DataFrame({"timestamp": stamps, "BTC": [100.0 + i for i in range(DAYS)]})

    def get_config_dict(self):
        return {}

    def generate_weights(self, data):
        return StrategyWeights(weights=data.select("timestamp", pl.lit(0.5).alias("BTC"), pl.lit(0.5).alias("CASH")),
                               assets=["BTC"])


class NavRunner(StrategyRunner):
    def load_data(self):
        return pl.DataFrame()

    def get_config_dict(self):
        return {}

    def run_nav(self):
        stamps = [FIRST + i * DAY + timedelta(hours=h) for i in range(DAYS) for h in (1, 13)]
        return pl.DataFrame({"timestamp": stamps, "nav": [100.0 - i for i in range(len(stamps))]})


RERUNS = {  # (family, folder, version): rerun.py source, importing the runners above
    ("paper-ledger", "version", "v001"): ("LedgerRunner", ("a_2x", "a_3x")),
    ("paper-ledger", "", "v002"): ("LedgerRunner", ("a_2x",)),
    ("paper-weights", "version", "v001"): ("WeightsRunner", ("base",)),
    ("paper-events", "", "v001"): ("NavRunner", ("book",)),
}


@pytest.fixture
def families(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "paper_fakes", sys.modules[__name__])
    library = tmp_path / "lib"
    for (family, folder, version), (runner, presets) in RERUNS.items():
        rerun = library / family / "optimization" / folder / version / "rerun.py"
        rerun.parent.mkdir(parents=True)
        rerun.write_text(f"from paper_fakes import {runner}, _config\nPRESETS = {presets!r}\n"
                         f"def build(preset):\n    return {runner}(_config({family!r}, {version!r}))\n")
    # A sealed version's unrelated module of another name, and a .dev scratch copy, are not reruns.
    (library / "paper-ledger" / "optimization" / "version" / "v001" / "book.py").write_text("raise ImportError\n")
    scratch = library / "paper-ledger" / "optimization" / ".dev" / "v009" / "rerun.py"
    scratch.parent.mkdir(parents=True)
    scratch.write_text("raise ImportError\n")
    record = library / "paper-ledger" / "optimization" / "version" / "v001" / "VERSION.toml"
    record.write_text('version = 1\nbacktest_run_at = "2026-01-05T12:00:00Z"\nbacktest_run_at_source = "run_id"\n')
    monkeypatch.setattr(updates, "FAMILIES_ROOT", library)
    yield tmp_path / "db"
    for name in [name for name in sys.modules if name.startswith("strategies_rerun_paper_")]:
        del sys.modules[name]


# --------------------------------------------------------------------------- #
# Targets, refresh and view
# --------------------------------------------------------------------------- #
def test_targets_list_every_rerun_preset_and_narrow(families):
    assert updates.targets() == [("paper-events", "v001", "book"), ("paper-ledger", "v001", "a_2x"),
                               ("paper-ledger", "v001", "a_3x"), ("paper-ledger", "v002", "a_2x"),
                               ("paper-weights", "v001", "base")]
    assert updates.targets("paper-ledger", "v002") == [("paper-ledger", "v002", "a_2x")]


def test_refresh_refuses_an_unknown_preset_or_a_version_without_a_rerun(families):
    with pytest.raises(ValueError, match="no preset 'base'"):
        updates.update_preset(families, "paper-ledger", "v001", "base")
    with pytest.raises(ValueError, match="no rerun.py"):
        updates.update_preset(families, "paper-ledger", "v003", "a_2x")


@pytest.mark.parametrize("family, preset", [("paper-ledger", "a_2x"), ("paper-weights", "base"),
                                            ("paper-events", "book")])
def test_refresh_writes_the_full_daily_nav_and_is_rerunnable(families, family, preset):
    status = updates.update_preset(families, family, "v001", preset)
    nav = pl.read_parquet(updates.updated_dir(families, family, "v001") / f"{preset}.parquet")
    assert nav.columns == ["timestamp", "nav"] and nav.height >= DAYS - 1
    assert nav["timestamp"].is_sorted() and status["nav"] == nav["nav"][-1]
    assert updates.update_preset(families, family, "v001", preset)["nav"] == status["nav"]


def test_update_version_writes_every_preset_and_the_view_reads_them(families):
    updates.update_version(families, "paper-ledger", "v001")
    view = updates.load_view(families, "paper-ledger", "v001")
    assert updates.backtest_run_dates("paper-ledger") == {"v001": "2026-01-05T12:00:00Z"}
    assert view["updatable"] and view["job"] is None
    assert [row["preset"] for row in view["presets"]] == ["a_2x", "a_3x"]
    assert view["presets"][0]["series"][0]["timestamp"].startswith("2026-01-01")


def test_view_of_a_version_never_updated_or_without_a_rerun(families):
    assert updates.load_view(families, "paper-weights", "v001") == dict(
        family="paper-weights", version="v001", updatable=True, job=None, presets=[])
    assert not updates.load_view(families, "paper-weights", "v009")["updatable"]
    with pytest.raises(LookupError, match="no rerun.py"):
        updates.start_update(families, "paper-weights", "v009")


def test_event_driven_refresh_keeps_each_day_closing_nav_and_run_refuses(families):
    updates.update_preset(families, "paper-events", "v001", "book")
    nav = pl.read_parquet(updates.updated_dir(families, "paper-events", "v001") / "book.parquet")
    assert nav.height == DAYS and nav["nav"].to_list() == [99.0 - 2 * i for i in range(DAYS)]
    with pytest.raises(TypeError, match="event-driven"):
        NavRunner(_config("paper-events", "v001")).run()
