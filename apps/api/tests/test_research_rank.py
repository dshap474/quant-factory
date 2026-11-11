"""Family rank comparison: known-answer ranks and a multi-version fixture.

Usage: uv run pytest apps/api/tests/test_research_rank.py -q
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports and fixtures
# --------------------------------------------------------------------------- #
import json
import math
from datetime import datetime, timedelta
from pathlib import Path

import polars as pl
import pytest
from db_api.config import settings
from db_api.research_rank import dated_path, rank_cell, window_metrics, window_returns
from strategies.research_surface import publish_research_surface

FAMILY = "rank_fixture"
URL = f"/api/backtests/strategy-types/{FAMILY}/versions/v004/surface/rank"


def _days(start: int, count: int) -> list[datetime]:
    return [datetime(2024, 1, 1) + timedelta(days=start + offset) for offset in range(count)]


def _performance(dates: list[datetime], returns: list[float]) -> pl.DataFrame:
    def compounded(values: list[float]) -> list[float]:
        wealth, result = 100.0, []
        for value in values:
            wealth *= 1.0 + value
            result.append(wealth)
        return result

    benchmark = [0.0] + [0.001] * (len(dates) - 1)
    return pl.DataFrame({
        "date": dates,
        "strategy_daily_return": returns,
        "strategy_portfolio_value": compounded(returns),
        "benchmark_daily_return": benchmark,
        "benchmark_portfolio_value": compounded(benchmark),
    })


def _publish(root: Path, version: str, dates: list[datetime], returns: list[float], *,
             state: str = "candidate", grid: dict[str, list[float]] | None = None,
             selected: str = "", control: str = "") -> None:
    kwargs: dict = {}
    if grid is not None:
        series_path = root / "research/strategies" / FAMILY / version / "grid/series.parquet"
        series_path.parent.mkdir(parents=True, exist_ok=True)
        pl.DataFrame({
            "config_id": [config for config in grid for _ in dates],
            "date": dates * len(grid),
            "daily_return": [value for values in grid.values() for value in values],
        }).write_parquet(series_path)
        ids = list(grid)
        kwargs = {
            "grid_summary": pl.DataFrame({
                "rank": list(range(1, len(ids) + 1)),
                "config_id": ids,
                "is_selected": [item == selected for item in ids],
                "is_control": [item == control for item in ids],
                "variant": ids,
                "gross": [2.0] * len(ids),
                "ir": [1.0] * len(ids),
            }),
            "grid": {
                "grid_schema_version": 1,
                "dimensions": [
                    {"key": "variant", "label": "Variant", "format": "text", "values": sorted(ids)},
                    {"key": "gross", "label": "Gross", "format": "number", "values": [2.0]},
                ],
                "metrics": [{"key": "ir", "label": "IR", "format": "number", "higher_is_better": True}],
                "selected_config_id": selected,
                "control_config_id": control,
                "series": {"path": "grid/series.parquet", "config_id_column": "config_id",
                           "date_column": "date", "return_column": "daily_return"},
            },
        }
    publish_research_surface(
        root, strategy_type=FAMILY, memory_version=version, state=state, experiment="fixture",
        run_id=f"20240201T000000Z-{version}", title=version, summary="Rank fixture.",
        performance=_performance(dates, returns), performance_unit="index",
        benchmark={"id": "BTC", "label": "BTC"}, **kwargs,
    )


# Window: v004 marks Jan 2 (zero anchor) through Jan 6 -> four returns.
WINDOW = _days(1, 5)
OWN = {"a": [0.0, 0.02, -0.01, 0.03, 0.01], "ctl": [0.0, 0.01, -0.02, 0.01, 0.0]}
V001 = [0.0, 0.01, 0.01, 0.02, 0.005, 0.01]  # Jan 1-6, no downside: Sortino/Calmar undefined.
V002_DATES = _days(0, 8)  # Jan 1-8, wider than the window on both sides.
V002 = {
    "sel": [0.0, 0.5, 0.03, -0.04, 0.02, 0.01, -0.5, 0.2],
    "ctl": [0.0, 0.5, 0.01, -0.02, 0.01, 0.0, 0.9, 0.9],  # Repeated control: never a peer.
}


@pytest.fixture
def family(tmp_path, monkeypatch):
    _publish(tmp_path, "v001", _days(0, 6), V001)
    _publish(tmp_path, "v002", V002_DATES, V002["sel"], grid=V002, selected="sel", control="ctl")
    _publish(tmp_path, "v003", WINDOW, [0.0, 0.1, 0.1, 0.1, 0.1], state="rejected")
    _publish(tmp_path, "v004", WINDOW, OWN["a"], grid=OWN, selected="a", control="ctl")
    _publish(tmp_path, "v005", _days(0, 4), [0.0, 0.01, 0.02, -0.01])  # Ends Jan 4.
    gap = [day for day in _days(0, 6) if day != datetime(2024, 1, 4)]
    _publish(tmp_path, "v007", gap, [0.0, 0.01, -0.01, 0.01, 0.02])
    not_tested = tmp_path / "research/strategies" / FAMILY / "v006/attempt/run"
    not_tested.mkdir(parents=True)
    (not_tested / "NOT_TESTED.json").write_text(json.dumps({
        "classification": "NOT TESTED", "detected_at_utc": "2024-02-01T00:00:00Z", "reason": "leak",
    }))
    monkeypatch.setattr(settings, "db_root", tmp_path)
    return tmp_path


def _window_values(returns: list[float]) -> dict:
    marks = [day.date() for day in WINDOW]
    return window_metrics(returns, marks)


# --------------------------------------------------------------------------- #
# Known-answer ranks
# --------------------------------------------------------------------------- #


def test_competition_ranks_follow_direction_and_ties():
    assert rank_cell(2.0, [3.0, 2.0, 1.0], "higher") == {
        "rank": 2, "count": 4, "ties": 1, "position": pytest.approx(0.5), "value": 2.0,
    }
    assert rank_cell(1.0, [3.0, 2.0, 2.0], "higher")["rank"] == 4
    assert rank_cell(2.0, [3.0, 2.0, 1.0], "lower")["rank"] == 2
    assert rank_cell(1.0, [3.0, 2.0], "lower") | {"value": 0} == {
        "rank": 1, "count": 3, "ties": 0, "position": 0.0, "value": 0,
    }


def test_signed_drawdown_closer_to_zero_ranks_first():
    assert rank_cell(-0.05, [-0.30, -0.10], "higher")["rank"] == 1
    assert rank_cell(-0.30, [-0.05, -0.10], "higher")["position"] == 1.0


def test_missing_values_shrink_the_denominator_and_never_rank():
    assert rank_cell(None, [1.0, 2.0], "higher") is None
    assert rank_cell(math.nan, [1.0], "higher") is None
    cell = rank_cell(1.0, [None, math.inf, 2.0, math.nan], "higher")
    assert (cell["rank"], cell["count"]) == (2, 2)


def test_singleton_and_all_equal_cohorts_are_neutral():
    assert rank_cell(1.0, [], "higher") == {"rank": 1, "count": 1, "ties": 0, "position": None, "value": 1.0}
    assert rank_cell(1.0, [1.0, 1.0], "lower")["position"] is None
    assert rank_cell(1.0, [1.0, 1.0], "lower")["rank"] == 1


def test_unrounded_values_do_not_tie_and_unranked_metrics_never_rank():
    assert rank_cell(1.0000000001, [1.0], "higher")["ties"] == 0
    assert rank_cell(1.0, [2.0], "unranked") is None


def test_dated_path_keeps_the_anchor_and_restores_an_implied_mark():
    marks = [day.date() for day in _days(0, 3)]
    anchored = dated_path(marks, [0.0, 0.1, 0.2])
    assert anchored.marks == tuple(marks) and anchored.returns == (0.1, 0.2)
    earned = dated_path(marks, [0.05, 0.1, 0.2])
    assert earned.marks[0] == marks[0] - timedelta(days=1) and earned.returns == (0.05, 0.1, 0.2)
    assert window_returns(anchored, marks[1:]) == ((0.2,), None)
    with pytest.raises(ValueError):
        dated_path(marks, [0.0, math.nan, 0.1])


# --------------------------------------------------------------------------- #
# Family fixture through the API
# --------------------------------------------------------------------------- #


def test_family_rank_uses_one_primary_per_other_version(client, family):
    before = {path: path.read_bytes() for path in family.rglob("*") if path.is_file()}

    response = client.get(URL)

    assert response.status_code == 200
    payload = response.json()
    assert payload["label"] == "Against published versions"
    assert payload["window"] == {
        "start_mark": "2024-01-02", "first_return": "2024-01-03", "end": "2024-01-06", "observations": 4,
    }
    assert [(peer["memory_version"], peer["source"], peer["config_id"]) for peer in payload["peers"]] == [
        ("v001", "strategy", None),
        ("v002", "selected_configuration", "sel"),
    ]
    assert {item["memory_version"]: item["reason"] for item in payload["excluded"]} == {
        "v003": "rejected", "v005": "outside_window", "v006": "not_tested", "v007": "date_mismatch",
    }
    # Peers are measured on the common window only; v002's wider history is cut away.
    peers = {peer["memory_version"]: peer["values"] for peer in payload["peers"]}
    assert peers["v002"] == pytest.approx(_window_values(V002["sel"][2:6]), nan_ok=True)
    assert peers["v002"]["total_return"] == pytest.approx(1.03 * 0.96 * 1.02 * 1.01 - 1)
    assert peers["v001"] == pytest.approx(_window_values(V001[2:6]), nan_ok=True)
    assert peers["v001"]["sortino"] is None

    columns = {column["config_id"]: column for column in payload["columns"]}
    assert set(columns) == {"a", "ctl"}  # The requested version stands in once per column.
    assert columns["a"]["values"] == pytest.approx(_window_values(OWN["a"][1:]), nan_ok=True)
    total = columns["a"]["ranks"]["total_return"]
    assert (total["count"], total["value"]) == (3, columns["a"]["values"]["total_return"])
    assert columns["a"]["ranks"]["sortino"]["count"] == 2  # v001 has no defined Sortino.
    ordering = sorted(
        [columns["a"]["values"]["total_return"], *(peer["total_return"] for peer in peers.values())],
        reverse=True,
    )
    assert total["rank"] == ordering.index(total["value"]) + 1
    assert {item["direction"] for item in payload["metrics"] if item["key"] == "annualized_volatility"} == {"lower"}
    after = {path: path.read_bytes() for path in family.rglob("*") if path.is_file()}
    assert after == before  # Read-only: artifacts and published selections are untouched.


def test_family_rank_reports_an_unavailable_short_window(client, family):
    _publish(family, "v008", _days(0, 2), [0.0, 0.01])

    response = client.get(f"/api/backtests/strategy-types/{FAMILY}/versions/v008/surface/rank")

    assert response.status_code == 200
    assert response.json()["window"] is None
    assert "fewer than two" in response.json()["unavailable_reason"]


def test_family_rank_is_404_without_a_surface(client, family):
    assert client.get(f"/api/backtests/strategy-types/{FAMILY}/versions/v099/surface/rank").status_code == 404
