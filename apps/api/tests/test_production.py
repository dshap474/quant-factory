"""Tests for the read-only production capital telemetry routes.

USAGE: uv run pytest apps/api/tests/test_production.py -q
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

FINGERPRINT = "396570d65f37e5e8d680cceed20378aca4789f88eb9de76c268ef31031ab06fa"
GENERATED_AT = "2026-08-20T01:00:00+00:00"


# --------------------------------------------------------------------------- #
# Projection fixtures
# --------------------------------------------------------------------------- #


def _metrics(**overrides: Any) -> dict[str, Any]:
    payload = {
        "total_pnl_usd": None,
        "total_return": None,
        "max_drawdown": None,
        "annualized_volatility": None,
        "sharpe": None,
        "positive_day_rate": None,
        "observation_count": 0,
    }
    payload.update(overrides)
    return payload


def _days(count: int) -> list[str]:
    """Return ``count`` consecutive UTC days ending today."""
    today = datetime.now(tz=UTC).date()
    return [(today - timedelta(days=count - 1 - index)).isoformat() for index in range(count)]


def _series(days: list[str], equities: list[float]) -> list[dict[str, Any]]:
    points = []
    cum = 0.0
    growth = 1.0
    for index, (day, equity) in enumerate(zip(days, equities, strict=True)):
        if index == 0:
            period = None
        else:
            period = equity - equities[index - 1]
            cum += period
            growth *= 1.0 + period / equities[index - 1]
        points.append(
            {
                "day": day,
                "observed_at": f"{day}T00:30:00+00:00",
                "equity_usd": equity,
                "cum_pnl_usd": cum,
                "cum_return": growth - 1.0,
                "period_pnl_usd": period,
                "complete": True,
            }
        )
    return points


def _member(**overrides: Any) -> dict[str, Any]:
    payload = {
        "family": "family-a",
        "included": True,
        "state": "registered",
        "health": "unknown",
        "stale": True,
        "capital_weight": None,
        "equity_usd": None,
        "inception_pnl_usd": None,
        "period_pnl_usd": None,
        "last_observation_at": None,
    }
    payload.update(overrides)
    return payload


def _overview(**overrides: Any) -> dict[str, Any]:
    payload = {
        "schema_version": 1,
        "portfolio_id": "qf-production",
        "generated_at": GENERATED_AT,
        "completeness": "empty",
        "equity_usd": None,
        "today_pnl_usd": None,
        "inception_pnl_usd": None,
        "missing_families": ["family-a"],
        "stale_families": [],
        "included_families": ["family-a"],
        "metrics": _metrics(),
        "members": [_member()],
        "series": [],
        "strategy_series": {},
    }
    payload.update(overrides)
    return payload


def _snapshot(**overrides: Any) -> dict[str, Any]:
    payload = {
        "schema_version": 1,
        "portfolio_id": "qf-production",
        "generated_at": GENERATED_AT,
        "family": "family-a",
        "included": True,
        "state": "registered",
        "health": "unknown",
        "stale": True,
        "max_age_seconds": 172800,
        "last_observation_at": None,
        "today_pnl_usd": None,
        "inception_pnl_usd": None,
        "deployment": {
            "family": "family-a",
            "memory_version": "v001",
            "preset": "v001",
            "venue": "example-venue",
            "instrument": "BTC-PERP",
            "account_alias": "family-a-account",
            "host_alias": "prod-a",
            "host_region": "region-a",
            "schedule": "*-*-* 00:00:00",
            "timezone": "UTC",
            "host_git_sha": "0" * 40,
            "deployment_fingerprint": FINGERPRINT,
        },
        "authority_facts": {
            "activation_state": "missing",
            "activation_expires_at": None,
            "armed": False,
            "venue_gate": "closed",
            "capital_gate": "closed",
            "deactivated": False,
            "can_trade": False,
            "scheduled": False,
            "autonomous_live": False,
        },
        "health_checks": [
            {"name": "deployment_identity", "state": "passing", "detail": "matches"},
            {"name": "scheduler", "state": "unknown", "detail": "units not installed"},
            {"name": "pipeline", "state": "unknown", "detail": "never run"},
            {"name": "input_freshness", "state": "unknown", "detail": "no decision"},
            {"name": "execution", "state": "unknown", "detail": "no execution"},
            {"name": "account_snapshot", "state": "unknown", "detail": "no snapshot"},
            {"name": "reconciliation", "state": "unknown", "detail": "nothing to reconcile"},
        ],
        "last_run": {"result": "never", "at": None, "mode": None, "journal_at": None},
        "capital": None,
        "metrics": _metrics(),
        "series": [],
    }
    payload.update(overrides)
    return payload


def write_projection(
    root: Path,
    *,
    overview: dict[str, Any] | None = None,
    snapshots: dict[str, dict[str, Any]] | None = None,
) -> Path:
    """Write a projection tree and return the DB root that contains it."""
    production = root / "production"
    production.mkdir(parents=True, exist_ok=True)
    (production / "overview.json").write_text(
        json.dumps(overview if overview is not None else _overview()), encoding="utf-8"
    )
    for family, snapshot in (snapshots or {"family-a": _snapshot()}).items():
        directory = production / "strategies" / family
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "snapshot.json").write_text(json.dumps(snapshot), encoding="utf-8")
    return root


# --------------------------------------------------------------------------- #
# Overview
# --------------------------------------------------------------------------- #


def test_missing_projection_is_not_found(client, set_db_root, tmp_path):
    set_db_root(tmp_path)
    assert client.get("/api/production/overview").status_code == 404


def test_registered_but_unobserved_portfolio_reads_empty(client, set_db_root, tmp_path):
    set_db_root(write_projection(tmp_path))
    payload = client.get("/api/production/overview").json()
    assert payload["completeness"] == "empty"
    assert payload["equity_usd"] is None
    assert payload["members"][0]["state"] == "registered"
    assert payload["members"][0]["health"] == "unknown"
    assert payload["metrics"]["sharpe"] is None
    # The series belongs to the series endpoint, not the overview payload.
    assert "series" not in payload


def test_incomplete_portfolio_publishes_no_total(client, set_db_root, tmp_path):
    days = _days(3)
    overview = _overview(
        completeness="incomplete",
        equity_usd=None,
        missing_families=["family-b"],
        included_families=["family-a", "family-b"],
        members=[
            _member(stale=False, equity_usd=10100.0, last_observation_at=f"{days[-1]}T00:30:00+00:00"),
            _member(family="family-b", state=None, health="unknown"),
        ],
        series=_series(days, [10000.0, 10050.0, 10100.0]),
    )
    set_db_root(write_projection(tmp_path, overview=overview))
    payload = client.get("/api/production/overview").json()
    assert payload["completeness"] == "incomplete"
    assert payload["equity_usd"] is None
    assert payload["missing_families"] == ["family-b"]


def test_malformed_overview_fails_closed(client, set_db_root, tmp_path):
    root = write_projection(tmp_path)
    (root / "production" / "overview.json").write_text("{not json", encoding="utf-8")
    set_db_root(root)
    assert client.get("/api/production/overview").status_code == 500


def test_unknown_overview_field_fails_closed(client, set_db_root, tmp_path):
    overview = _overview()
    overview["credential_name_sha256"] = "abc"
    set_db_root(write_projection(tmp_path, overview=overview))
    assert client.get("/api/production/overview").status_code == 500


def test_oversized_overview_fails_closed(client, set_db_root, tmp_path):
    root = write_projection(tmp_path)
    (root / "production" / "overview.json").write_text("[" + "0," * 3_000_000 + "0]", encoding="utf-8")
    set_db_root(root)
    assert client.get("/api/production/overview").status_code == 500


def test_symlinked_overview_fails_closed(client, set_db_root, tmp_path):
    root = write_projection(tmp_path)
    elsewhere = tmp_path / "elsewhere.json"
    elsewhere.write_text(json.dumps(_overview()), encoding="utf-8")
    target = root / "production" / "overview.json"
    target.unlink()
    target.symlink_to(elsewhere)
    set_db_root(root)
    assert client.get("/api/production/overview").status_code == 500


def test_symlinked_projection_root_fails_closed(client, set_db_root, tmp_path):
    real = tmp_path / "real"
    write_projection(real)
    fake_root = tmp_path / "fake"
    fake_root.mkdir()
    (fake_root / "production").symlink_to(real / "production")
    set_db_root(fake_root)
    assert client.get("/api/production/overview").status_code == 500


# --------------------------------------------------------------------------- #
# Strategy detail
# --------------------------------------------------------------------------- #


def test_strategy_snapshot_keeps_authority_facts_separate(client, set_db_root, tmp_path):
    set_db_root(write_projection(tmp_path))
    payload = client.get("/api/production/strategies/family-a").json()
    authority = payload["authority_facts"]
    assert payload["state"] == "registered"
    assert authority["can_trade"] is False
    assert authority["scheduled"] is False
    assert authority["autonomous_live"] is False
    assert authority["venue_gate"] == "closed"
    assert authority["capital_gate"] == "closed"
    assert {check["name"] for check in payload["health_checks"]} == {
        "deployment_identity",
        "scheduler",
        "pipeline",
        "input_freshness",
        "execution",
        "account_snapshot",
        "reconciliation",
    }
    assert payload["capital"] is None


def test_unknown_strategy_is_not_found(client, set_db_root, tmp_path):
    set_db_root(write_projection(tmp_path))
    assert client.get("/api/production/strategies/family-b").status_code == 404


@pytest.mark.parametrize(
    "family",
    ["..", "../../etc", "FAMILY-A", "family a", ".hidden", "a" * 65],
)
def test_traversing_or_invalid_family_is_rejected(client, set_db_root, tmp_path, family):
    set_db_root(write_projection(tmp_path))
    response = client.get(f"/api/production/strategies/{family}")
    assert response.status_code == 404


def test_symlinked_strategy_directory_fails_closed(client, set_db_root, tmp_path):
    root = write_projection(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "snapshot.json").write_text(json.dumps(_snapshot(family="family-b")), encoding="utf-8")
    (root / "production" / "strategies" / "family-b").symlink_to(elsewhere)
    set_db_root(root)
    assert client.get("/api/production/strategies/family-b").status_code == 500


def test_snapshot_family_must_match_its_path(client, set_db_root, tmp_path):
    set_db_root(
        write_projection(tmp_path, snapshots={"family-a": _snapshot(family="family-b")})
    )
    assert client.get("/api/production/strategies/family-a").status_code == 500


def test_snapshot_with_capital_reports_positions(client, set_db_root, tmp_path):
    days = _days(2)
    snapshot = _snapshot(
        stale=False,
        health="healthy",
        last_observation_at=f"{days[-1]}T00:30:00+00:00",
        today_pnl_usd=100.0,
        inception_pnl_usd=100.0,
        capital={
            "as_of": f"{days[-1]}T00:30:00+00:00",
            "equity_usd": 10100.0,
            "cash_usd": 10050.0,
            "gross_exposure_usd": 1000.0,
            "net_exposure_usd": 1000.0,
            "realized_pnl_usd": 0.0,
            "unrealized_pnl_usd": 50.0,
            "fees_usd": None,
            "funding_pnl_usd": None,
            "capital_weight": 1.0,
            "positions": [
                {
                    "instrument": "BTC-PERP",
                    "side": "LONG",
                    "quantity": 0.01,
                    "contracts": 1,
                    "current_price": 100000.0,
                    "entry_price": 95000.0,
                    "market_value_usd": 1000.0,
                    "unrealized_pnl_usd": 50.0,
                    "daily_realized_pnl_usd": 0.0,
                }
            ],
        },
        series=_series(days, [10000.0, 10100.0]),
    )
    set_db_root(write_projection(tmp_path, snapshots={"family-a": snapshot}))
    payload = client.get("/api/production/strategies/family-a").json()
    assert payload["capital"]["capital_weight"] == 1.0
    assert payload["capital"]["positions"][0]["contracts"] == 1
    assert payload["capital"]["fees_usd"] is None


# --------------------------------------------------------------------------- #
# Series slicing
# --------------------------------------------------------------------------- #


def test_series_defaults_to_thirty_day_pnl(client, set_db_root, tmp_path):
    days = _days(3)
    overview = _overview(
        completeness="complete",
        equity_usd=10100.0,
        missing_families=[],
        series=_series(days, [10000.0, 10050.0, 10100.0]),
        strategy_series={"family-a": _series(days, [10000.0, 10050.0, 10100.0])},
    )
    set_db_root(write_projection(tmp_path, overview=overview))
    payload = client.get("/api/production/series").json()
    assert payload["range"] == "30d"
    assert payload["metric"] == "pnl_usd"
    assert payload["complete"] is True
    assert [point["value"] for point in payload["aggregate"]["points"]] == [0.0, 50.0, 100.0]
    assert payload["strategies"][0]["family"] == "family-a"


def test_short_range_rebases_onto_the_prior_mark(client, set_db_root, tmp_path):
    days = _days(5)
    overview = _overview(
        completeness="complete",
        series=_series(days, [10000.0, 10100.0, 10200.0, 10300.0, 10400.0]),
    )
    set_db_root(write_projection(tmp_path, overview=overview))
    points = client.get("/api/production/series", params={"range": "1d"}).json()["aggregate"][
        "points"
    ]
    # A one-day window shows the single day's move, baselined on the day before.
    assert len(points) == 1
    assert points[0]["value"] == 100.0


def test_equity_metric_is_not_rebased(client, set_db_root, tmp_path):
    days = _days(3)
    overview = _overview(series=_series(days, [10000.0, 10050.0, 10100.0]))
    set_db_root(write_projection(tmp_path, overview=overview))
    points = client.get(
        "/api/production/series", params={"range": "7d", "metric": "equity"}
    ).json()["aggregate"]["points"]
    assert [point["value"] for point in points] == [10000.0, 10050.0, 10100.0]


def test_return_metric_is_chain_relative(client, set_db_root, tmp_path):
    days = _days(3)
    overview = _overview(series=_series(days, [10000.0, 11000.0, 12100.0]))
    set_db_root(write_projection(tmp_path, overview=overview))
    points = client.get(
        "/api/production/series", params={"range": "all", "metric": "return_pct"}
    ).json()["aggregate"]["points"]
    assert points[0]["value"] == pytest.approx(0.0)
    assert points[-1]["value"] == pytest.approx(0.21)


def test_incomplete_points_are_null_not_zero(client, set_db_root, tmp_path):
    days = _days(3)
    series = _series(days, [10000.0, 10050.0, 10100.0])
    series[1] = {
        "day": days[1],
        "observed_at": None,
        "equity_usd": None,
        "cum_pnl_usd": None,
        "cum_return": None,
        "period_pnl_usd": None,
        "complete": False,
    }
    overview = _overview(completeness="incomplete", series=series)
    set_db_root(write_projection(tmp_path, overview=overview))
    points = client.get("/api/production/series", params={"range": "all"}).json()["aggregate"][
        "points"
    ]
    assert points[1]["value"] is None
    assert points[1]["complete"] is False


def test_empty_series_is_an_empty_line(client, set_db_root, tmp_path):
    set_db_root(write_projection(tmp_path))
    payload = client.get("/api/production/series").json()
    assert payload["aggregate"]["points"] == []
    assert payload["complete"] is False


def test_strategy_series_returns_one_line(client, set_db_root, tmp_path):
    days = _days(3)
    snapshot = _snapshot(stale=False, series=_series(days, [10000.0, 10050.0, 10100.0]))
    set_db_root(write_projection(tmp_path, snapshots={"family-a": snapshot}))
    payload = client.get(
        "/api/production/strategies/family-a/series", params={"range": "30d"}
    ).json()
    assert payload["aggregate"]["family"] == "family-a"
    assert payload["strategies"] == []
    assert [point["value"] for point in payload["aggregate"]["points"]] == [0.0, 50.0, 100.0]


@pytest.mark.parametrize("selected", ["1d", "7d", "30d", "ytd", "all"])
def test_every_documented_range_is_accepted(client, set_db_root, tmp_path, selected):
    days = _days(3)
    overview = _overview(series=_series(days, [10000.0, 10050.0, 10100.0]))
    set_db_root(write_projection(tmp_path, overview=overview))
    assert client.get("/api/production/series", params={"range": selected}).status_code == 200


def test_unknown_range_is_rejected(client, set_db_root, tmp_path):
    set_db_root(write_projection(tmp_path))
    assert client.get("/api/production/series", params={"range": "7y"}).status_code == 422


def test_unknown_metric_is_rejected(client, set_db_root, tmp_path):
    set_db_root(write_projection(tmp_path))
    assert client.get("/api/production/series", params={"metric": "alpha"}).status_code == 422


# --------------------------------------------------------------------------- #
# Read-only surface
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "path",
    [
        "/api/production/overview",
        "/api/production/series",
        "/api/production/strategies/family-a",
        "/api/production/strategies/family-a/series",
    ],
)
def test_routes_reject_mutation(client, set_db_root, tmp_path, path):
    set_db_root(write_projection(tmp_path))
    for method in (client.post, client.put, client.patch, client.delete):
        assert method(path).status_code == 405
