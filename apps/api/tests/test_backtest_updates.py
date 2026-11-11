"""Backtest-update routes serve one version's updated curves and refuse unsafe or unknown versions.

USAGE: uv run pytest apps/api/tests/test_backtest_updates.py -q
"""

from __future__ import annotations

from datetime import UTC, datetime

import polars as pl

# --------------------------------------------------------------------------- #
# A curve written the way an update job writes it
# --------------------------------------------------------------------------- #


def write_curve(root):
    folder = root / "research/strategies/fam/v001/updated"
    folder.mkdir(parents=True)
    pl.DataFrame({"timestamp": [datetime(2026, 10, 4, tzinfo=UTC)], "nav": [100_000.0]}).write_parquet(
        folder / "b2x.parquet")
    (folder / "b2x.json").write_text('{"preset": "b2x", "nav": 100000.0}')
    return root


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
def test_serves_one_version(client, set_db_root, tmp_path):
    set_db_root(write_curve(tmp_path))
    view = client.get("/api/backtest-updates/fam/v001").json()
    assert view["presets"][0]["preset"] == "b2x" and view["job"] is None
    assert view["presets"][0]["series"][0]["nav"] == 100_000.0
    assert client.get("/api/backtest-updates/fam").json() == {}  # no such family in the library


def test_unknown_versions_cannot_start_and_unsafe_paths_are_rejected(client, set_db_root, tmp_path):
    set_db_root(write_curve(tmp_path))
    assert client.get("/api/backtest-updates/fam/v009").json()["presets"] == []
    assert client.post("/api/backtest-updates/fam/v001").status_code == 404
    assert client.get("/api/backtest-updates/fam/..%2F..").status_code in (400, 404)
    assert client.get("/api/backtest-updates/..%2F..").status_code in (400, 404)
