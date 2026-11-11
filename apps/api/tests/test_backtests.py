"""Tests for backtests API endpoints, focusing on ML tracking artifacts."""

import json
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest
from db_api.config import settings
from db_api.main import create_app
from db_api.routers import backtests as backtests_router
from fastapi.testclient import TestClient
from strategies.research_surface import publish_research_surface
from strategies.results import BacktestOutput
from strategies.versioned import promote_run
from strategies.weights import StrategyWeights


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(create_app(load_extensions=False))


@pytest.fixture
def temp_db_root():
    """Create a temporary database root with mock backtest data."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_root = Path(tmp_dir)

        # Create a mock backtest run
        strategy_dir = db_root / "strategies" / "example-strategy" / "test_preset" / "run-20240101-120000"
        strategy_dir.mkdir(parents=True)

        # Create backtest.parquet
        backtest_df = pl.DataFrame(
            {
                "timestamp": [datetime(2024, 1, 1) + timedelta(days=d) for d in range(10)],
                "equity": [1.0 + d * 0.01 for d in range(10)],
                "benchmark_equity": [1.0 + d * 0.005 for d in range(10)],
            }
        )
        backtest_df.write_parquet(strategy_dir / "backtest.parquet")

        # Create meta.json
        meta = {
            "strategy_type": "example-strategy",
            "metrics": {"sharpe": 1.5, "total_return": 0.10, "max_drawdown": -0.05},
            "config": {"preset": "test_preset"},
            "created_at": "2024-01-01T12:00:00",
            "data_range": {"start": "2024-01-01", "end": "2024-01-10"},
        }
        (strategy_dir / "meta.json").write_text(json.dumps(meta))

        yield db_root, strategy_dir


@pytest.fixture
def temp_db_with_ml_tracking(temp_db_root):
    """Create mock ML tracking artifacts."""
    db_root, strategy_dir = temp_db_root

    # Create rankings.parquet
    rankings_rows = []
    for d in range(5):
        ts = datetime(2024, 1, 5) + timedelta(days=d)
        for i, asset in enumerate(["BTC", "ETH", "SOL", "DOGE"]):
            rankings_rows.append(
                {
                    "timestamp": ts,
                    "asset": asset,
                    "score": 1.0 - i * 0.2,
                    "rank": i + 1,
                }
            )
    rankings_df = pl.DataFrame(rankings_rows)
    rankings_df.write_parquet(strategy_dir / "rankings.parquet")

    # Create weights.parquet
    weights_rows = []
    for d in range(5):
        ts = datetime(2024, 1, 5) + timedelta(days=d)
        for asset, weight in [("BTC", 0.25), ("ETH", 0.25), ("SOL", -0.25), ("DOGE", -0.25)]:
            weights_rows.append(
                {
                    "timestamp": ts,
                    "asset": asset,
                    "weight": weight,
                }
            )
    weights_df = pl.DataFrame(weights_rows)
    weights_df.write_parquet(strategy_dir / "weights.parquet")

    # Create ic_series.parquet
    ic_rows = []
    for d in range(5):
        ts = datetime(2024, 1, 5) + timedelta(days=d)
        ic_rows.append(
            {
                "timestamp": ts,
                "ic": 0.05 + d * 0.01 if d % 2 == 0 else -0.02,  # Mix of positive and negative
                "n_assets": 4,
            }
        )
    ic_df = pl.DataFrame(ic_rows)
    ic_df.write_parquet(strategy_dir / "ic_series.parquet")

    return db_root, strategy_dir


@pytest.fixture
def temp_versioned_db():
    """Create a temporary version-first strategy result layout."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        db_root = Path(tmp_dir)
        strategy_type = "example-strategy"
        memory_version = "v001"

        runs = [
            {
                "run_id": "run-20240101-120000",
                "preset": "default",
                "total_return": 0.10,
                "sharpe": 1.10,
                "created_at": datetime(2024, 1, 1, 12, 0, 0),
            },
            {
                "run_id": "run-20240102-120000",
                "preset": "default",
                "total_return": 0.12,
                "sharpe": 1.20,
                "created_at": datetime(2024, 1, 2, 12, 0, 0),
            },
            {
                "run_id": "run-20240103-120000",
                "preset": "preset-a",
                "total_return": 0.18,
                "sharpe": 1.50,
                "created_at": datetime(2024, 1, 3, 12, 0, 0),
            },
        ]

        stamps = [datetime(2024, 1, d) for d in range(1, 6)]
        for run in runs:
            run_dir = (
                db_root / "research" / "strategies" / strategy_type / memory_version / run["preset"] / run["run_id"]
            )
            StrategyWeights(
                weights=pl.DataFrame({"timestamp": stamps, "BTC": [1.0] * 5, "CASH": [0.0] * 5}), assets=["BTC"]
            ).save(run_dir / "decisions.parquet")
            BacktestOutput(
                strategy_id=run["preset"],
                run_id=run["run_id"],
                equity=pl.DataFrame(
                    {
                        "timestamp": stamps,
                        "equity": [1.0, 1.01, 1.04, 1.08, 1.0 + run["total_return"]],
                        "benchmark_equity": [1.0, 1.01, 1.03, 1.04, 1.06],
                    }
                ),
                metrics={
                    "total_return": run["total_return"],
                    "sharpe": run["sharpe"],
                    "max_drawdown": 0.08,
                    "win_rate": 0.55,
                },
                config={"preset": run["preset"]},
                created_at=run["created_at"],
                data_range={"start": "2024-01-01", "end": "2024-01-05"},
                strategy_type=strategy_type,
                memory_version=memory_version,
                preset=run["preset"],
            ).save(run_dir)

        promote_run(db_root, strategy_type, memory_version, runs[1]["run_id"])

        yield db_root


@pytest.fixture(autouse=True)
def clear_backtest_router_caches():
    """Clear cached discovery between tests so temporary db roots are respected."""
    backtests_router._cached_discover_saved_backtests.cache_clear()
    backtests_router._cached_discover_strategy_versions.cache_clear()
    yield
    backtests_router._cached_discover_saved_backtests.cache_clear()
    backtests_router._cached_discover_strategy_versions.cache_clear()


def test_legacy_discovery_skips_archive_root(tmp_path):
    active = BacktestOutput(
        strategy_id="active_preset",
        run_id="run-20240101-120000",
        equity=pl.DataFrame(
            {
                "timestamp": [datetime(2024, 1, 1), datetime(2024, 1, 2)],
                "equity": [1.0, 1.05],
                "benchmark_equity": [1.0, 1.02],
            }
        ),
        metrics={"sharpe": 1.0, "total_return": 0.05, "max_drawdown": 0.01},
        config={"preset": "active_preset"},
        created_at=datetime(2024, 1, 1, 12, 0, 0),
        data_range={"start": "2024-01-01", "end": "2024-01-02"},
    )
    active.save(tmp_path / "strategies" / "active_strategy" / active.strategy_id / active.run_id)

    archived = BacktestOutput(
        strategy_id="stale_preset",
        run_id="run-20240102-120000",
        equity=pl.DataFrame(
            {
                "timestamp": [datetime(2024, 1, 1), datetime(2024, 1, 2)],
                "equity": [1.0, 1.1],
                "benchmark_equity": [1.0, 1.05],
            }
        ),
        metrics={"sharpe": 0.5, "total_return": 0.1, "max_drawdown": 0.02},
        config={"preset": "stale_preset"},
        created_at=datetime(2024, 1, 2, 12, 0, 0),
        data_range={"start": "2024-01-01", "end": "2024-01-02"},
    )
    archived.save(tmp_path / "strategies" / "_archive" / archived.strategy_id / archived.run_id)

    discovered = backtests_router._discover_saved_backtests(tmp_path)

    assert {row["strategy_type"] for row in discovered} == {"active_strategy"}


class TestGetBacktestArtifacts:
    """Tests for /api/backtests/{strategy_id}/{run_id}/artifacts endpoint."""

    def test_artifacts_none_available(self, client, temp_db_root, monkeypatch):
        """Test when no ML tracking artifacts exist."""
        db_root, _ = temp_db_root
        monkeypatch.setattr(settings, "db_root", db_root)

        response = client.get("/api/backtests/test_preset/run-20240101-120000/artifacts")

        assert response.status_code == 200
        data = response.json()
        assert data["has_rankings"] is False
        assert data["has_weights"] is False
        assert data["has_ic_series"] is False

    def test_artifacts_all_available(self, client, temp_db_with_ml_tracking, monkeypatch):
        """Test when all ML tracking artifacts exist."""
        db_root, _ = temp_db_with_ml_tracking
        monkeypatch.setattr(settings, "db_root", db_root)

        response = client.get("/api/backtests/test_preset/run-20240101-120000/artifacts")

        assert response.status_code == 200
        data = response.json()
        assert data["has_rankings"] is True
        assert data["has_weights"] is True
        assert data["has_ic_series"] is True

    def test_artifacts_not_found(self, client, temp_db_root, monkeypatch):
        """Test when backtest doesn't exist."""
        db_root, _ = temp_db_root
        monkeypatch.setattr(settings, "db_root", db_root)

        response = client.get("/api/backtests/nonexistent/run-99999/artifacts")

        assert response.status_code == 404


class TestGetBacktestRankings:
    """Tests for /api/backtests/{strategy_id}/{run_id}/rankings endpoint."""

    def test_rankings_returns_data(self, client, temp_db_with_ml_tracking, monkeypatch):
        """Test getting rankings data."""
        db_root, _ = temp_db_with_ml_tracking
        monkeypatch.setattr(settings, "db_root", db_root)

        response = client.get("/api/backtests/test_preset/run-20240101-120000/rankings")

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "columns" in data
        assert "timestamps" in data
        assert "total_rows" in data
        assert len(data["data"]) == 20  # 5 days * 4 assets
        assert "timestamp" in data["columns"]
        assert "asset" in data["columns"]
        assert "score" in data["columns"]
        assert "rank" in data["columns"]

    def test_rankings_filter_by_timestamp(self, client, temp_db_with_ml_tracking, monkeypatch):
        """Test filtering rankings by timestamp."""
        db_root, _ = temp_db_with_ml_tracking
        monkeypatch.setattr(settings, "db_root", db_root)

        # Filter to specific timestamp
        ts = "2024-01-05T00:00:00"
        response = client.get(f"/api/backtests/test_preset/run-20240101-120000/rankings?timestamp={ts}")

        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 4  # 4 assets for 1 timestamp

    def test_rankings_not_found(self, client, temp_db_root, monkeypatch):
        """Test when rankings file doesn't exist."""
        db_root, _ = temp_db_root
        monkeypatch.setattr(settings, "db_root", db_root)

        response = client.get("/api/backtests/test_preset/run-20240101-120000/rankings")

        assert response.status_code == 404
        assert "No rankings data" in response.json()["detail"]

    def test_rankings_limit_reports_total_rows(self, client, temp_db_with_ml_tracking, monkeypatch):
        """Test total_rows reflects full result set while data is limited."""
        db_root, _ = temp_db_with_ml_tracking
        monkeypatch.setattr(settings, "db_root", db_root)

        response = client.get("/api/backtests/test_preset/run-20240101-120000/rankings?limit=3")

        assert response.status_code == 200
        payload = response.json()
        assert payload["total_rows"] == 20
        assert payload["returned_rows"] == 3
        assert len(payload["data"]) == 3

    def test_rankings_invalid_timestamp_returns_400(self, client, temp_db_with_ml_tracking, monkeypatch):
        """Test invalid timestamp query returns a validation error."""
        db_root, _ = temp_db_with_ml_tracking
        monkeypatch.setattr(settings, "db_root", db_root)

        response = client.get("/api/backtests/test_preset/run-20240101-120000/rankings?timestamp=not-a-date")

        assert response.status_code == 400
        assert "Invalid timestamp format" in response.json()["detail"]


class TestGetBacktestWeights:
    """Tests for /api/backtests/{strategy_id}/{run_id}/weights endpoint."""

    def test_weights_returns_data(self, client, temp_db_with_ml_tracking, monkeypatch):
        """Test getting weights data."""
        db_root, _ = temp_db_with_ml_tracking
        monkeypatch.setattr(settings, "db_root", db_root)

        response = client.get("/api/backtests/test_preset/run-20240101-120000/weights")

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "columns" in data
        assert "timestamps" in data
        assert len(data["data"]) == 20  # 5 days * 4 assets

        # Check that side column was added
        assert "side" in data["columns"]

        # Verify side values
        sides = {row["asset"]: row["side"] for row in data["data"][:4]}
        assert sides["BTC"] == "LONG"
        assert sides["ETH"] == "LONG"
        assert sides["SOL"] == "SHORT"
        assert sides["DOGE"] == "SHORT"

    def test_weights_filter_by_timestamp(self, client, temp_db_with_ml_tracking, monkeypatch):
        """Test filtering weights by timestamp."""
        db_root, _ = temp_db_with_ml_tracking
        monkeypatch.setattr(settings, "db_root", db_root)

        ts = "2024-01-05T00:00:00"
        response = client.get(f"/api/backtests/test_preset/run-20240101-120000/weights?timestamp={ts}")

        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 4  # 4 assets for 1 timestamp

    def test_weights_not_found(self, client, temp_db_root, monkeypatch):
        """Test when weights file doesn't exist."""
        db_root, _ = temp_db_root
        monkeypatch.setattr(settings, "db_root", db_root)

        response = client.get("/api/backtests/test_preset/run-20240101-120000/weights")

        assert response.status_code == 404
        assert "No weights data" in response.json()["detail"]

    def test_weights_limit_reports_total_rows(self, client, temp_db_with_ml_tracking, monkeypatch):
        """Test total_rows reflects full result set while data is limited."""
        db_root, _ = temp_db_with_ml_tracking
        monkeypatch.setattr(settings, "db_root", db_root)

        response = client.get("/api/backtests/test_preset/run-20240101-120000/weights?limit=5")

        assert response.status_code == 200
        payload = response.json()
        assert payload["total_rows"] == 20
        assert payload["returned_rows"] == 5
        assert len(payload["data"]) == 5

    def test_weights_invalid_timestamp_returns_400(self, client, temp_db_with_ml_tracking, monkeypatch):
        """Test invalid timestamp query returns a validation error."""
        db_root, _ = temp_db_with_ml_tracking
        monkeypatch.setattr(settings, "db_root", db_root)

        response = client.get("/api/backtests/test_preset/run-20240101-120000/weights?timestamp=bad-ts")

        assert response.status_code == 400
        assert "Invalid timestamp format" in response.json()["detail"]


class TestGetBacktestIC:
    """Tests for /api/backtests/{strategy_id}/{run_id}/ic endpoint."""

    def test_ic_returns_data(self, client, temp_db_with_ml_tracking, monkeypatch):
        """Test getting IC series data."""
        db_root, _ = temp_db_with_ml_tracking
        monkeypatch.setattr(settings, "db_root", db_root)

        response = client.get("/api/backtests/test_preset/run-20240101-120000/ic")

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "columns" in data
        assert "stats" in data
        assert "total_rows" in data
        assert len(data["data"]) == 5

    def test_ic_computes_stats(self, client, temp_db_with_ml_tracking, monkeypatch):
        """Test that IC stats are computed correctly."""
        db_root, _ = temp_db_with_ml_tracking
        monkeypatch.setattr(settings, "db_root", db_root)

        response = client.get("/api/backtests/test_preset/run-20240101-120000/ic")

        assert response.status_code == 200
        stats = response.json()["stats"]

        # Check all stats are present
        assert "mean_ic" in stats
        assert "std_ic" in stats
        assert "min_ic" in stats
        assert "max_ic" in stats
        assert "positive_pct" in stats
        assert "ic_ir" in stats

        # Verify stats are reasonable
        assert stats["mean_ic"] is not None
        assert stats["min_ic"] <= stats["mean_ic"] <= stats["max_ic"]
        assert 0 <= stats["positive_pct"] <= 1

    def test_ic_not_found(self, client, temp_db_root, monkeypatch):
        """Test when IC series file doesn't exist."""
        db_root, _ = temp_db_root
        monkeypatch.setattr(settings, "db_root", db_root)

        response = client.get("/api/backtests/test_preset/run-20240101-120000/ic")

        assert response.status_code == 404
        assert "No IC series data" in response.json()["detail"]


class TestBacktestNotFound:
    """Tests for 404 handling across all endpoints."""

    def test_backtest_not_found_artifacts(self, client, temp_db_root, monkeypatch):
        """Test artifacts endpoint with nonexistent backtest."""
        db_root, _ = temp_db_root
        monkeypatch.setattr(settings, "db_root", db_root)

        response = client.get("/api/backtests/fake_strategy/fake_run/artifacts")
        assert response.status_code == 404

    def test_backtest_not_found_rankings(self, client, temp_db_root, monkeypatch):
        """Test rankings endpoint with nonexistent backtest."""
        db_root, _ = temp_db_root
        monkeypatch.setattr(settings, "db_root", db_root)

        response = client.get("/api/backtests/fake_strategy/fake_run/rankings")
        assert response.status_code == 404

    def test_backtest_not_found_weights(self, client, temp_db_root, monkeypatch):
        """Test weights endpoint with nonexistent backtest."""
        db_root, _ = temp_db_root
        monkeypatch.setattr(settings, "db_root", db_root)

        response = client.get("/api/backtests/fake_strategy/fake_run/weights")
        assert response.status_code == 404

    def test_backtest_not_found_ic(self, client, temp_db_root, monkeypatch):
        """Test IC endpoint with nonexistent backtest."""
        db_root, _ = temp_db_root
        monkeypatch.setattr(settings, "db_root", db_root)

        response = client.get("/api/backtests/fake_strategy/fake_run/ic")
        assert response.status_code == 404


class TestVersionEndpoints:
    """Tests for saved-run and promoted-final version endpoints."""

    def test_runs_lists_every_saved_run_newest_first(self, client, temp_versioned_db, monkeypatch):
        monkeypatch.setattr(settings, "db_root", temp_versioned_db)

        response = client.get("/api/backtests/strategy-types/example-strategy/versions/v001/runs")

        assert response.status_code == 200
        payload = response.json()
        assert [row["run_id"] for row in payload["data"]] == [
            "run-20240103-120000",
            "run-20240102-120000",
            "run-20240101-120000",
        ]
        assert payload["data"][0]["preset"] == "preset-a"
        assert payload["data"][0]["total_return"] == pytest.approx(0.18)

    def test_final_returns_the_promoted_run(self, client, temp_versioned_db, monkeypatch):
        monkeypatch.setattr(settings, "db_root", temp_versioned_db)

        response = client.get("/api/backtests/strategy-types/example-strategy/versions/v001/final")

        assert response.status_code == 200
        payload = response.json()
        assert payload["selected_run_id"] == "run-20240102-120000"
        assert payload["metrics"]["total_return"] == pytest.approx(0.12)
        assert payload["columns"] == ["timestamp", "equity", "benchmark_equity"]
        assert len(payload["data"]) == 5

    def test_leader_endpoints_are_gone(self, client, temp_versioned_db, monkeypatch):
        monkeypatch.setattr(settings, "db_root", temp_versioned_db)
        base = "/api/backtests/strategy-types/example-strategy/versions/v001"

        assert client.get(f"{base}/leader").status_code == 404
        assert client.get(f"{base}/preset-leaders").status_code == 404

    def test_strategy_versions_report_the_promoted_final(self, client, temp_versioned_db, monkeypatch):
        monkeypatch.setattr(settings, "db_root", temp_versioned_db)

        response = client.get("/api/backtests/strategy-types/example-strategy/versions")

        assert response.status_code == 200
        payload = response.json()
        assert len(payload) == 1
        row = payload[0]
        assert row["memory_version"] == "v001"
        assert row["total_runs"] == 3
        assert row["run_count"] == 3
        assert row["best_return"] == pytest.approx(0.12)
        assert row["final_run_id"] == "run-20240102-120000"
        assert "has_leader" not in row

    def test_research_surface_is_discovered_and_returned(self, client, tmp_path, monkeypatch):
        returns = [0.01, -0.02, 0.03]
        benchmark_returns = [0.0, 0.01, -0.005]

        def compounded(values):
            wealth = 100.0
            result = []
            for value in values:
                wealth *= 1.0 + value
                result.append(wealth)
            return result

        publish_research_surface(
            tmp_path,
            strategy_type="example-strategy",
            memory_version="v002",
            state="rejected",
            experiment="optimizer",
            run_id="20240104T000000Z-run",
            performance=pl.DataFrame(
                {
                    "date": [datetime(2024, 1, day) for day in range(1, 4)],
                    "strategy_daily_return": returns,
                    "strategy_portfolio_value": compounded(returns),
                    "benchmark_daily_return": benchmark_returns,
                    "benchmark_portfolio_value": compounded(benchmark_returns),
                }
            ),
            title="Rejected v002",
            summary="Validated research evidence.",
            benchmark={"id": "BTC", "label": "BTC buy & hold"},
        )
        monkeypatch.setattr(settings, "db_root", tmp_path)

        versions = client.get("/api/backtests/strategy-types/example-strategy/versions")
        surface = client.get("/api/backtests/strategy-types/example-strategy/versions/v002/surface")

        assert versions.status_code == 200
        assert versions.json()[0]["state"] == "rejected"
        assert versions.json()[0]["source"] == "research"
        assert surface.status_code == 200
        assert surface.json()["run_id"] == "20240104T000000Z-run"
        assert len(surface.json()["data"]) == 3

    def test_text_only_research_record_is_discovered_and_returned(self, client, tmp_path, monkeypatch):
        publish_research_surface(
            tmp_path,
            strategy_type="family-a",
            memory_version="v001",
            state="rejected",
            experiment="example-record",
            run_id="20240101T000000Z-record",
            title="Family A v001",
            summary="The example feature claim was falsified.",
            diagnostics=[
                {
                    "key": "events",
                    "label": "Matched evaluation events",
                    "value": 500,
                    "format": "number",
                }
            ],
        )
        monkeypatch.setattr(settings, "db_root", tmp_path)

        versions = client.get("/api/backtests/strategy-types/family-a/versions")
        surface = client.get("/api/backtests/strategy-types/family-a/versions/v001/surface")

        assert versions.status_code == 200
        assert versions.json()[0]["best_return"] is None
        assert versions.json()[0]["has_surface"] is True
        assert surface.status_code == 200
        assert surface.json()["benchmark"] is None
        assert surface.json()["metrics"] is None
        assert surface.json()["columns"] == []
        assert surface.json()["data"] == []

    def test_pnl_research_surface_is_returned(self, client, tmp_path, monkeypatch):
        publish_research_surface(
            tmp_path,
            strategy_type="example-research-strategy",
            memory_version="v001",
            state="rejected",
            experiment="gate-record",
            run_id="pnl-surface-v1",
            title="Family B v001",
            summary="Cumulative PnL on a $100 allocation.",
            pnl=pl.DataFrame(
                {
                    "timestamp": [datetime(2024, 2, 1, hour, tzinfo=UTC) for hour in range(3)],
                    "cumulative_pnl_usd": [0.0, 2.5, -1.25],
                }
            ),
            pnl_metadata={
                "label": "v001 cumulative PnL",
                "allocation_usd": 100.0,
                "interpretation": "backtest",
            },
        )
        monkeypatch.setattr(settings, "db_root", tmp_path)

        surface = client.get("/api/backtests/strategy-types/example-research-strategy/versions/v001/surface")

        assert surface.status_code == 200
        assert surface.json()["columns"] == ["timestamp", "cumulative_pnl_usd"]
        assert surface.json()["data"][0]["cumulative_pnl_usd"] == 0.0
        assert surface.json()["pnl"]["allocation_usd"] == 100.0
        assert surface.json()["pnl"]["interpretation"] == "backtest"

    def test_pnl_research_surface_returns_comparison(self, client, tmp_path, monkeypatch):
        publish_research_surface(
            tmp_path,
            strategy_type="example-research-strategy",
            memory_version="v003",
            state="rejected",
            experiment="signal-record",
            run_id="comparison-surface-v1",
            title="Family B v003",
            summary="Candidate and v001 cumulative PnL.",
            pnl=pl.DataFrame(
                {
                    "timestamp": [datetime(2024, 2, 1, hour, tzinfo=UTC) for hour in range(3)],
                    "cumulative_pnl_usd": [0.0, -0.5, -1.0],
                    "benchmark_cumulative_pnl_usd": [0.0, -2.0, -5.0],
                }
            ),
            pnl_metadata={
                "label": "v003",
                "allocation_usd": 100.0,
                "interpretation": "backtest",
            },
            benchmark={"id": "v001", "label": "v001"},
        )
        monkeypatch.setattr(settings, "db_root", tmp_path)

        surface = client.get("/api/backtests/strategy-types/example-research-strategy/versions/v003/surface")

        assert surface.status_code == 200
        assert surface.json()["benchmark"] == {"id": "v001", "label": "v001"}
        assert surface.json()["columns"] == [
            "timestamp",
            "cumulative_pnl_usd",
            "benchmark_cumulative_pnl_usd",
        ]
        assert surface.json()["data"][-1]["benchmark_cumulative_pnl_usd"] == -5.0

    def test_pnl_research_surface_is_sampled_for_chart_delivery(self, client, tmp_path, monkeypatch):
        timestamps = [datetime(2024, 2, 1, tzinfo=UTC) + timedelta(minutes=i) for i in range(101)]
        publish_research_surface(
            tmp_path,
            strategy_type="example-research-strategy",
            memory_version="v004",
            state="candidate",
            experiment="sampled-pnl",
            run_id="sampled-pnl-v1",
            title="Family B v004",
            summary="Cumulative PnL sampled for display.",
            pnl=pl.DataFrame(
                {
                    "timestamp": timestamps,
                    "cumulative_pnl_usd": [float(i) for i in range(101)],
                }
            ),
            pnl_metadata={
                "label": "v004",
                "allocation_usd": 1000.0,
                "interpretation": "backtest",
            },
        )
        monkeypatch.setattr(settings, "db_root", tmp_path)

        surface = client.get(
            "/api/backtests/strategy-types/example-research-strategy/versions/v004/surface?max_points=50"
        )

        assert surface.status_code == 200
        payload = surface.json()
        assert payload["points_total"] == 101
        assert payload["points_returned"] == len(payload["data"])
        assert payload["points_returned"] <= 50
        assert payload["downsampled"] is True
        assert payload["pnl"]["row_count"] == 101
        assert payload["data"][0]["cumulative_pnl_usd"] == 0.0
        assert payload["data"][-1]["cumulative_pnl_usd"] == 100.0

    def test_research_optimizer_grid_summary_and_configuration(self, client, tmp_path, monkeypatch):
        dates = [datetime(2024, 1, day) for day in range(1, 4)]
        selected_returns = [0.01, -0.02, 0.03]
        control_returns = [0.005, -0.01, 0.02]
        benchmark_returns = [0.0, 0.01, -0.005]

        def compounded(values):
            wealth = 100.0
            result = []
            for value in values:
                wealth *= 1.0 + value
                result.append(wealth)
            return result

        version_root = tmp_path / "research/strategies/example-strategy/v002"
        series_path = version_root / "optimizer/source/grid_daily.parquet"
        series_path.parent.mkdir(parents=True)
        pl.DataFrame(
            {
                "config_id": ["selected"] * 3 + ["control"] * 3,
                "date": dates + dates,
                "daily_return": selected_returns + control_returns,
            }
        ).write_parquet(series_path)
        grid_summary = pl.DataFrame(
            {
                "rank": [1, 2],
                "config_id": ["selected", "control"],
                "is_selected": [True, False],
                "is_control": [False, True],
                "penalty": [0.001, 0.002],
                "gross": [2.0, 2.0],
                "ir": [1.2, 0.9],
            }
        )
        publish_research_surface(
            tmp_path,
            strategy_type="example-strategy",
            memory_version="v002",
            state="rejected",
            experiment="optimizer",
            run_id="20240104T000000Z-grid",
            performance=pl.DataFrame(
                {
                    "date": dates,
                    "strategy_daily_return": selected_returns,
                    "strategy_portfolio_value": compounded(selected_returns),
                    "benchmark_daily_return": benchmark_returns,
                    "benchmark_portfolio_value": compounded(benchmark_returns),
                }
            ),
            title="Optimizer grid",
            summary="Static optimizer response surface.",
            benchmark={"id": "BTC", "label": "BTC buy & hold"},
            grid_summary=grid_summary,
            grid={
                "grid_schema_version": 1,
                "dimensions": [
                    {"key": "penalty", "label": "Penalty", "format": "bps", "values": [0.001, 0.002]},
                    {"key": "gross", "label": "Gross", "format": "number", "values": [2.0]},
                ],
                "metrics": [
                    {"key": "ir", "label": "IR", "format": "number", "higher_is_better": True},
                ],
                "selected_config_id": "selected",
                "control_config_id": "control",
                "series": {
                    "path": "optimizer/source/grid_daily.parquet",
                    "config_id_column": "config_id",
                    "date_column": "date",
                    "return_column": "daily_return",
                },
            },
        )
        monkeypatch.setattr(settings, "db_root", tmp_path)

        grid = client.get("/api/backtests/strategy-types/example-strategy/versions/v002/surface/grid")
        detail = client.get(
            "/api/backtests/strategy-types/example-strategy/versions/v002/surface/grid/configurations/selected"
        )
        missing = client.get(
            "/api/backtests/strategy-types/example-strategy/versions/v002/surface/grid/configurations/missing"
        )

        assert grid.status_code == 200
        assert len(grid.json()["data"]) == 2
        grid_rows = {row["config_id"]: row for row in grid.json()["data"]}
        assert grid_rows["selected"]["rank"] == 1  # Published selection/rank is immutable.
        assert grid_rows["selected"]["sortino"] == pytest.approx((365 / 3) ** 0.5)
        assert grid_rows["control"]["sortino"] > grid_rows["selected"]["sortino"]
        assert {"sortino", "martin"} <= {metric["key"] for metric in grid.json()["metrics"]}
        assert detail.status_code == 200
        payload = detail.json()
        assert payload["config"]["config_id"] == "selected"
        assert grid_rows["selected"]["martin"] == pytest.approx(payload["metrics"]["selected"]["martin"])
        assert payload["control"]["config_id"] == "control"
        assert len(payload["data"]) == 3
        assert payload["data"][-1]["selected_portfolio_value"] == pytest.approx(compounded(selected_returns)[-1])
        assert missing.status_code == 404

    def test_strategy_type_summary_includes_versions(self, client, temp_versioned_db, monkeypatch):
        monkeypatch.setattr(settings, "db_root", temp_versioned_db)

        response = client.get("/api/backtests/strategy-types")

        assert response.status_code == 200
        payload = response.json()
        assert len(payload) == 1
        row = payload[0]
        assert row["strategy_type"] == "example-strategy"
        assert row["version_count"] == 1
        assert row["versions"] == ["v001"]

    def test_strategy_type_summary_ignores_archived_version_root(self, client, temp_versioned_db, monkeypatch):
        (temp_versioned_db / "strategies" / "_archive" / "versions" / "v001").mkdir(parents=True)
        monkeypatch.setattr(settings, "db_root", temp_versioned_db)

        response = client.get("/api/backtests/strategy-types")

        assert response.status_code == 200
        payload = response.json()
        assert len(payload) == 1
        assert payload[0]["strategy_type"] == "example-strategy"

    def test_signals_routes_remain_mounted(self, client):
        paths = {route.path for route in client.app.router.routes}

        assert "/api/signals" in paths


def test_surface_risk_uses_full_history_before_chart_sampling(client, tmp_path, monkeypatch):
    """One gain and one loss among 99 intervals: Sortino = sqrt(365 / 99)."""
    returns = [0.0, 0.2, -0.1] + [0.0] * 97
    wealth = 100.0
    equity = []
    for value in returns:
        wealth *= 1 + value
        equity.append(wealth)
    publish_research_surface(
        tmp_path,
        strategy_type="risk-fixture",
        memory_version="v001",
        state="candidate",
        experiment="risk",
        run_id="known-answer",
        performance=pl.DataFrame(
            {
                "date": [datetime(2024, 1, 1) + timedelta(days=i) for i in range(100)],
                "strategy_daily_return": returns,
                "strategy_portfolio_value": equity,
                "benchmark_daily_return": [0.0] * 100,
                "benchmark_portfolio_value": [100.0] * 100,
            }
        ),
        title="Risk fixture",
        summary="Known-answer risk reporting.",
        benchmark={"id": "flat", "label": "Flat"},
    )
    monkeypatch.setattr(settings, "db_root", tmp_path)
    response = client.get("/api/backtests/strategy-types/risk-fixture/versions/v001/surface?max_points=50")
    assert response.status_code == 200
    payload = response.json()
    assert payload["points_returned"] < payload["points_total"]
    assert payload["metrics"]["strategy"]["sortino"] == pytest.approx((365 / 99) ** 0.5, rel=1e-12)
    # Full path has 98 observations at -10% drawdown and two at the peak.
    expected_martin = (1.08 ** (365 / 99) - 1) / (0.1 * (98 / 100) ** 0.5)
    assert payload["metrics"]["strategy"]["martin"] == pytest.approx(expected_martin, rel=1e-12)
    assert payload["metrics"]["strategy"]["longest_drawdown_days"] == 98
    assert payload["metrics"]["strategy"]["current_drawdown_days"] == 98
    assert payload["metrics"]["benchmark"]["sortino"] is None
    assert payload["metrics"]["benchmark"]["martin"] is None
