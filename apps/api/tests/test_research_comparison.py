"""Selected-run control delivery and pairing regressions.

USAGE: pytest apps/api/tests/test_research_comparison.py -q
"""

from datetime import date, timedelta

import polars as pl
import pytest
from strategies.research_surface import publish_research_surface

# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture
def comparison_run(tmp_path, set_db_root):
    set_db_root(tmp_path)
    dates = [date(2025, 1, 1) + timedelta(days=i) for i in range(101)]
    values = [0.1, -0.1, 0.0] + [0.0] * 98
    frame = pl.DataFrame(
        {"date": dates, "strategy_daily_return": values, "benchmark_daily_return": [0.0] * 101}
    ).with_columns(
        ((1 + pl.col("strategy_daily_return")).cum_prod() * 100).alias("strategy_portfolio_value"),
        pl.lit(100.0).alias("benchmark_portfolio_value"),
    )
    publish_research_surface(
        tmp_path,
        strategy_type="example",
        memory_version="v002",
        state="candidate",
        experiment="economics",
        run_id="run-1",
        title="Candidate",
        summary="A paired experiment.",
        benchmark={"id": "BTC", "label": "BTC buy & hold"},
        performance=frame,
        provenance=[{"label": "control", "value": "v001 continuation"}],
    )
    run = tmp_path / "research/strategies/example/v002/economics/run-1"
    for name, returns in [("candidate", values), ("control", [0.02, 0.03, -0.01] + [0.0] * 98)]:
        pl.DataFrame({"session_date": dates, "net_return": returns}).write_parquet(run / f"{name}_returns.parquet")
    return run


URL = "/api/backtests/strategy-types/example/versions/v002/surface"

# --------------------------------------------------------------------------- #
# API regressions
# --------------------------------------------------------------------------- #


def test_same_run_control_is_distinct_from_market_benchmark(client, comparison_run):
    response = client.get(URL)
    assert response.status_code == 200
    body = response.json()
    control = body["comparison"]
    assert body["benchmark"]["id"] == "BTC"
    assert control["label"] == "v001 continuation"
    assert control["run_id"] == body["run_id"] == "run-1"
    assert control["metrics"]["total_return"] == pytest.approx(0.040094)
    assert control["data"][-1]["portfolio_value"] == pytest.approx(104.0094)
    assert body["metrics"]["strategy"]["total_return"] == pytest.approx(-0.01)
    assert body["comparison_issue"] is None


def test_sampling_keeps_dates_paired_and_full_population_metrics(client, comparison_run):
    body = client.get(URL + "?max_points=50").json()
    control = body["comparison"]
    assert control["points_total"] == body["points_total"] == 101
    assert control["points_returned"] == body["points_returned"] <= 50
    assert [row["date"] for row in control["data"]] == [row["date"] for row in body["data"]]
    assert control["metrics"]["total_return"] == pytest.approx(0.040094)


@pytest.mark.parametrize("damage", ["candidate_mismatch", "dates", "symlink"])
def test_invalid_comparison_never_replaces_valid_candidate(client, comparison_run, damage, tmp_path):
    run = comparison_run
    target = run / "control_returns.parquet"
    if damage == "symlink":
        outside = tmp_path / "outside.parquet"
        target.rename(outside)
        target.symlink_to(outside)
    else:
        path = run / "candidate_returns.parquet" if damage == "candidate_mismatch" else target
        frame = pl.read_parquet(path)
        frame = (
            frame.with_columns(pl.lit(0.0).alias("net_return")) if damage == "candidate_mismatch" else frame.slice(1)
        )
        frame.write_parquet(path)
    response = client.get(URL)
    assert response.status_code == 200
    assert response.json()["comparison"] is None
    assert "unavailable" in response.json()["comparison_issue"]
    assert response.json()["metrics"]["strategy"]["total_return"] == pytest.approx(-0.01)


def test_legacy_surface_without_run_return_contract_still_loads(client, comparison_run):
    (comparison_run / "control_returns.parquet").unlink()
    body = client.get(URL).json()
    assert body["comparison"] is None
    assert body["comparison_issue"] is None
    assert len(body["data"]) == 101
