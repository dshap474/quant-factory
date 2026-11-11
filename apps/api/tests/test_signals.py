"""Tests for signals API endpoints."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime
from pathlib import Path

import polars as pl
import pytest


@pytest.fixture
def signals_db_root(monkeypatch):
    """Create a temporary db root with signal prediction data.

    Discovery filters by active registry signal types, so the active set is
    pinned to the family used by the in-fixture active signal.
    """
    from db_api.routers import signals as signals_router

    monkeypatch.setattr(signals_router, "_active_signal_catalog", lambda: {"example-direction": 0})

    with tempfile.TemporaryDirectory() as tmp_dir:
        db_root = Path(tmp_dir)

        signal_dir = db_root / "signals" / "example_direction"
        signal_dir.mkdir(parents=True)

        predictions = pl.DataFrame(
            {
                "run_id": ["run-1", "run-1", "run-2", "run-2"],
                "predicted_at": [
                    datetime(2024, 1, 1, 0, 0),
                    datetime(2024, 1, 1, 0, 0),
                    datetime(2024, 1, 2, 0, 0),
                    datetime(2024, 1, 2, 0, 0),
                ],
                "timestamp": [
                    datetime(2024, 1, 1),
                    datetime(2024, 1, 2),
                    datetime(2024, 1, 1),
                    datetime(2024, 1, 2),
                ],
                "pred_direction": [0.1, 0.2, 0.4, 0.5],
                "probability": [0.55, 0.58, 0.62, 0.66],
                # Bookkeeping a runner carries next to its predictions. Two of these are
                # numeric and must still never be offered as a prediction column.
                "asset": ["BTC", "BTC", "BTC", "BTC"],
                "observed_through": [
                    datetime(2023, 12, 31),
                    datetime(2023, 12, 31),
                    datetime(2024, 1, 1),
                    datetime(2024, 1, 1),
                ],
                "observed_through_epoch_us": [1704067200000000] * 4,
                "horizon_days": [30, 30, 30, 30],
                "signal_name": ["example_direction"] * 4,
                "model_id": ["xgboost-v1"] * 4,
            }
        )
        predictions.write_parquet(signal_dir / "predictions.parquet")

        runs_payload = {
            "runs": {
                "run-1": {
                    "metrics": {"accuracy": 0.61, "auc": 0.64},
                    "config": {
                        "window": 30,
                        "signal_type": "example-direction",
                        "description": "Example direction signal",
                    },
                    "created_at": "2024-01-01T00:00:00",
                    "data_range": {"start": "2023-10-01", "end": "2023-12-31"},
                    "metadata": {"model_type": "xgboost"},
                },
                "run-2": {
                    "metrics": {"accuracy": 0.65, "auc": 0.68},
                    "config": {
                        "window": 30,
                        "signal_type": "example-direction",
                        "description": "Example direction signal",
                    },
                    "created_at": "2024-01-02T00:00:00",
                    "data_range": {"start": "2023-10-02", "end": "2024-01-01"},
                    "metadata": {"model_type": "xgboost"},
                },
            }
        }
        (signal_dir / "runs.json").write_text(json.dumps(runs_payload))

        # Stale output from an archived family: must be hidden from discovery.
        legacy_dir = db_root / "signals" / "legacy_returns"
        legacy_dir.mkdir(parents=True)
        pl.DataFrame(
            {
                "run_id": ["run-x"],
                "timestamp": [datetime(2024, 1, 1)],
                "prediction": [0.3],
            }
        ).write_parquet(legacy_dir / "predictions.parquet")
        (legacy_dir / "runs.json").write_text(
            json.dumps({"runs": {"run-x": {"config": {"signal_type": "example-returns-pred"}}}})
        )

        no_time_dir = db_root / "signals" / "no_time_signal"
        no_time_dir.mkdir(parents=True)
        pl.DataFrame(
            {
                "run_id": ["run-a", "run-b"],
                "pred_value": [0.11, 0.22],
            }
        ).write_parquet(no_time_dir / "predictions.parquet")

        yield db_root


def test_list_signals(client, set_db_root, signals_db_root):
    set_db_root(signals_db_root)

    response = client.get("/api/signals")
    assert response.status_code == 200

    payload = response.json()
    row = next(item for item in payload if item["signal_id"] == "example_direction")
    assert row["signal_type"] == "example-direction"
    assert row["production_version"] == "v000"
    assert row["description"] == "Example direction signal"
    assert row["run_count"] == 2
    assert row["best_accuracy"] == 0.65
    assert row["best_auc"] == 0.68
    assert row["latest_run"] == "2024-01-02T00:00:00"
    assert row["latest_run_id"] == "run-2"
    # The prediction clock spans the whole history, independent of when a run fired.
    assert row["first_prediction"] == "2024-01-01T00:00:00"
    assert row["latest_prediction"] == "2024-01-02T00:00:00"


def test_list_signals_hides_inactive_families(client, set_db_root, signals_db_root):
    set_db_root(signals_db_root)

    response = client.get("/api/signals")
    assert response.status_code == 200

    signal_ids = {item["signal_id"] for item in response.json()}
    assert signal_ids == {"example_direction"}
    # Stale archived-family output and untyped output are excluded.
    assert "legacy_returns" not in signal_ids
    assert "no_time_signal" not in signal_ids


def test_signal_research_catalog_uses_version_lifecycle_as_canonical(
    client,
    set_db_root,
    tmp_path,
    monkeypatch,
):
    from db_api.routers import signals as signals_router

    from signals import research_versions

    db_root = tmp_path / "db"
    signal_root = db_root / "signals/example-signal-default"
    signal_root.mkdir(parents=True)
    pl.DataFrame(
        {
            "run_id": ["run-production"],
            "predicted_at": [datetime(2026, 1, 1, 12, 0, 0)],
            "timestamp": [datetime(2026, 8, 31)],
            "prediction": [0.4],
        }
    ).write_parquet(signal_root / "predictions.parquet")
    (signal_root / "runs.json").write_text(
        json.dumps(
            {
                "runs": {
                    "run-production": {
                        "config": {"signal_type": "example-signal"},
                    }
                }
            }
        )
    )
    run_root = db_root / "research/signals/example-signal/v001/example-score/20260101T000000Z-r01"
    run_root.mkdir(parents=True)
    (run_root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "version": "v001",
                "experiment": "example-score",
                "run_id": "20260101T000000Z-r01",
            }
        )
    )
    (run_root / "NOT_TESTED.json").write_text(
        json.dumps(
            {
                "status": "NOT TESTED",
                "recorded_at": "2026-01-02T00:00:10Z",
                "run_id": "20260101T000000Z-r01",
                "error": "Input fingerprint changed",
            }
        )
    )

    package_root = tmp_path / "packages/signals"
    version_root = package_root / "extensions/lib/example-signal/optimization/v001"
    version_root.mkdir(parents=True)
    (version_root / "VERSION.toml").write_text('version = 1\nphase = "recorded"\nstatus = "not_tested"\n')
    example_root = package_root / "extensions/lib/example/optimization/v002"
    example_root.mkdir(parents=True)
    (example_root / "VERSION.toml").write_text('version = 2\nphase = "preregistered"\nstatus = "active"\n')

    monkeypatch.setattr(research_versions, "FAMILIES_ROOT", package_root / "extensions/lib")
    monkeypatch.setattr(
        signals_router,
        "_active_signal_catalog",
        lambda: {"example-signal": 0},
    )
    set_db_root(db_root)

    families_response = client.get("/api/signals/research/families")
    assert families_response.status_code == 200
    assert families_response.json() == [
        {
            "signal_family": "example-signal",
            "description": "Signal family: example-signal",
            "total_runs": 2,
            "version_count": 2,
            "versions": ["v000", "v001"],
            "latest_run": "2026-01-02T00:00:10Z",
        }
    ]

    versions_response = client.get("/api/signals/research/families/example-signal/versions")
    assert versions_response.status_code == 200
    assert versions_response.json() == [
        {
            "signal_family": "example-signal",
            "memory_version": "v000",
            "total_runs": 1,
            "run_count": 1,
            "latest_run": "2026-01-01T12:00:00",
            "state": "promoted",
            "display_state": "baseline",
            "source": "canonical",
            "selected_run_id": "run-production",
            "experiment": None,
            "has_surface": False,
            "surface_state": None,
            "lifecycle_phase": "registered",
            "lifecycle_status": None,
            "invalidation_reason": None,
            "signal_ids": ["example-signal-default"],
            "selected_signal_id": "example-signal-default",
        },
        {
            "signal_family": "example-signal",
            "memory_version": "v001",
            "total_runs": 1,
            "run_count": 1,
            "latest_run": "2026-01-02T00:00:10Z",
            "state": "invalidated",
            "display_state": "invalidated",
            "source": "research",
            "selected_run_id": "20260101T000000Z-r01",
            "experiment": "example-score",
            "has_surface": False,
            "surface_state": None,
            "lifecycle_phase": "recorded",
            "lifecycle_status": "not_tested",
            "invalidation_reason": "Input fingerprint changed",
            "signal_ids": [],
            "selected_signal_id": None,
        },
    ]


def test_signal_research_versions_return_404_for_unknown_family(client, set_db_root, tmp_path):
    set_db_root(tmp_path)

    response = client.get("/api/signals/research/families/does-not-exist/versions")

    assert response.status_code == 404


def test_signal_research_surface_serves_optional_tables_and_not_tested(client, set_db_root, tmp_path):
    from signals.research_surface import SurfaceArm, publish_research_surface

    db_root = tmp_path / "db"
    for version, run_id in (("v001", "20260101T000000Z-r01"), ("v002", "20260103T000000Z-r01")):
        (db_root / f"research/signals/example-signal/{version}/screen/{run_id}").mkdir(parents=True)
    common = {"signal_family": "example-signal", "experiment": "screen", "title": "t", "summary": "s"}
    publish_research_surface(
        db_root,
        memory_version="v001",
        run_id="20260101T000000Z-r01",
        state="rejected",
        arms=[SurfaceArm("control", "control", "control", None, None, {"h7_auc": 0.55})],
        **common,
    )
    publish_research_surface(
        db_root,
        memory_version="v002",
        run_id="20260103T000000Z-r01",
        state="not_tested",
        arms=[],
        blocker="input X missing",
        **common,
    )
    set_db_root(db_root)
    base = "/api/signals/research/families/example-signal/versions"

    summary_only = client.get(f"{base}/v001/surface").json()
    assert summary_only["arms"][0]["ic"] is None
    assert summary_only["arms"][0]["metrics"]["values"] == {"h7_auc": 0.55}
    assert client.get(f"{base}/v001/surface/arms/control/ic").status_code == 404
    not_tested = client.get(f"{base}/v002/surface").json()
    assert (not_tested["state"], not_tested["blocker"], not_tested["arms"]) == ("not_tested", "input X missing", [])


@pytest.fixture
def research_artifact_db_root(tmp_path):
    """Build one sealed attempt: a manifest over a JSON summary, a parquet, and a note."""
    run_root = tmp_path / "db/research/signals/example-signal/v001/example-screen/20260101T000000Z-r01"
    run_root.mkdir(parents=True)

    (run_root / "summary.json").write_text(json.dumps({"decision": {"verdict": "FALSIFIED"}}))
    pl.DataFrame(
        {
            "timestamp": [datetime(2024, 1, 1), datetime(2024, 1, 2)],
            "close": [42000.5, 43000.25],
            "window": ["screen", "holdout"],
        }
    ).write_parquet(run_root / "state_path.parquet")
    (run_root / "notes.txt").write_text("not a served artifact form")
    (run_root / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "version": "v001",
                "experiment": "example-screen",
                "run_id": "20260101T000000Z-r01",
                "files": {
                    "summary.json": {"bytes": 0},
                    "state_path.parquet": {"bytes": 0},
                    "notes.txt": {"bytes": 0},
                    # A hostile manifest: listing a key does not make it addressable.
                    "..": {"bytes": 0},
                    "../../../../etc/passwd": {"bytes": 0},
                },
            }
        )
    )
    return tmp_path / "db"


def _artifact_url(name: str, *, family: str = "example-signal", run: str = "20260101T000000Z-r01") -> str:
    return (
        f"/api/signals/research/families/{family}/versions/v001"
        f"/runs/{run}/artifacts/{name}"
    )


def test_signal_research_artifact_serves_manifest_listed_files(
    client,
    set_db_root,
    research_artifact_db_root,
):
    set_db_root(research_artifact_db_root)

    summary = client.get(_artifact_url("summary.json"))
    assert summary.status_code == 200
    assert summary.headers["content-type"].startswith("application/json")
    assert summary.json() == {"decision": {"verdict": "FALSIFIED"}}

    table = client.get(_artifact_url("state_path.parquet"))
    assert table.status_code == 200
    payload = table.json()
    assert payload["signal_family"] == "example-signal"
    assert payload["memory_version"] == "v001"
    assert payload["experiment"] == "example-screen"
    assert payload["run_id"] == "20260101T000000Z-r01"
    assert payload["columns"] == ["timestamp", "close", "window"]
    assert payload["total_rows"] == 2
    assert payload["returned_rows"] == 2
    assert [row["window"] for row in payload["rows"]] == ["screen", "holdout"]


def test_signal_research_artifact_bounds_parquet_rows(client, set_db_root, research_artifact_db_root):
    set_db_root(research_artifact_db_root)

    response = client.get(_artifact_url("state_path.parquet"), params={"limit": 1, "offset": 1})

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_rows"] == 2
    assert payload["returned_rows"] == 1
    assert payload["offset"] == 1
    assert [row["window"] for row in payload["rows"]] == ["holdout"]


def test_signal_research_artifact_refuses_paths_outside_the_run(
    client,
    set_db_root,
    research_artifact_db_root,
):
    """The manifest is the allowlist; addressing segments never leave the layout."""
    set_db_root(research_artifact_db_root)

    # A manifest key is still a path segment: `..` is listed above and still refused.
    assert client.get(_artifact_url("%2E%2E")).status_code == 400
    # Nested keys are addressable, but every part is still a checked segment: a listed
    # traversal key is refused before it reaches the file layer.
    assert client.get(_artifact_url("..%2F..%2F..%2F..%2Fetc%2Fpasswd")).status_code == 400
    assert client.get(_artifact_url("..%2Fmanifest.json")).status_code == 404
    # An unlisted neighbour of a sealed artifact stays invisible.
    assert client.get(_artifact_url("manifest.json")).status_code == 404
    assert client.get(_artifact_url("summary.json", family=".ssh")).status_code == 400
    assert client.get(_artifact_url("summary.json", run=".ssh")).status_code == 400
    assert client.get(_artifact_url("summary.json", run="20260101T000000Z-r99")).status_code == 404


def test_signal_research_artifact_refuses_unsupported_artifact_forms(
    client,
    set_db_root,
    research_artifact_db_root,
):
    set_db_root(research_artifact_db_root)

    response = client.get(_artifact_url("notes.txt"))

    assert response.status_code == 415


def test_list_signal_runs(client, set_db_root, signals_db_root):
    set_db_root(signals_db_root)

    response = client.get("/api/signals/example_direction")
    assert response.status_code == 200
    payload = response.json()

    assert len(payload) == 2
    run_ids = {row["run_id"] for row in payload}
    assert run_ids == {"run-1", "run-2"}
    for row in payload:
        assert row["first_prediction"] == "2024-01-01T00:00:00"
        assert row["latest_prediction"] == "2024-01-02T00:00:00"


def test_get_signal_data_for_run(client, set_db_root, signals_db_root):
    set_db_root(signals_db_root)

    response = client.get("/api/signals/example_direction/run-1")
    assert response.status_code == 200

    payload = response.json()
    assert payload["signal_id"] == "example_direction"
    assert payload["run_id"] == "run-1"
    assert payload["date_column"] == "timestamp"
    assert payload["columns"] == [
        "run_id",
        "predicted_at",
        "timestamp",
        "pred_direction",
        "probability",
        "asset",
        "observed_through",
        "observed_through_epoch_us",
        "horizon_days",
        "signal_name",
        "model_id",
    ]
    assert payload["prediction_columns"] == ["pred_direction", "probability"]
    assert payload["metrics"] == {"accuracy": 0.61, "auc": 0.64}
    assert payload["config"] == {
        "window": 30,
        "signal_type": "example-direction",
        "description": "Example direction signal",
    }
    assert payload["metadata"] == {"model_type": "xgboost"}
    assert payload["created_at"] == "2024-01-01T00:00:00"
    assert payload["data_range"] == {"start": "2023-10-01", "end": "2023-12-31"}
    assert len(payload["data"]) == 2


def test_get_signal_data_latest(client, set_db_root, signals_db_root):
    set_db_root(signals_db_root)

    response = client.get("/api/signals/example_direction/latest")
    assert response.status_code == 200

    payload = response.json()
    assert payload["run_id"] == "run-2"
    assert len(payload["data"]) == 2


def test_get_signal_predictions(client, set_db_root, signals_db_root):
    set_db_root(signals_db_root)

    response = client.get("/api/signals/example_direction/run-2/predictions")
    assert response.status_code == 200

    payload = response.json()
    assert payload["run_id"] == "run-2"
    assert payload["prediction_columns"]
    assert len(payload["data"]) == 2


def test_get_signal_stats(client, set_db_root, signals_db_root):
    set_db_root(signals_db_root)

    response = client.get("/api/signals/example_direction/run-2/stats")
    assert response.status_code == 200

    payload = response.json()
    assert payload["run_id"] == "run-2"
    assert [stat["column"] for stat in payload["prediction_stats"]] == ["pred_direction", "probability"]


def test_latest_requires_time_column(client, set_db_root, signals_db_root):
    set_db_root(signals_db_root)

    response = client.get("/api/signals/no_time_signal/latest")
    assert response.status_code == 400
    assert "requires 'predicted_at' or 'timestamp'" in response.json()["detail"]


def test_prediction_bounds_are_null_without_a_date_column(client, set_db_root, signals_db_root):
    set_db_root(signals_db_root)

    response = client.get("/api/signals/no_time_signal")
    assert response.status_code == 200

    for row in response.json():
        assert row["first_prediction"] is None
        assert row["latest_prediction"] is None


def test_signal_not_found(client, set_db_root, signals_db_root):
    set_db_root(signals_db_root)

    response = client.get("/api/signals/does_not_exist")
    assert response.status_code == 404


# --------------------------------------------------------------------------- #
# Multi-asset runs: the latest cross-section by default, one asset on request
# --------------------------------------------------------------------------- #


@pytest.fixture
def multi_asset_db_root(tmp_path):
    """A store shaped like a per-asset signal: 3 assets x 3 days in one run."""
    db_root = tmp_path / "db"
    signal_dir = db_root / "signals" / "example-asset-signal-default"
    signal_dir.mkdir(parents=True)

    assets = ["ETH", "SOL", "DOGE"]
    days = [datetime(2024, 1, 1), datetime(2024, 1, 2), datetime(2024, 1, 3)]
    pl.DataFrame(
        {
            "run_id": ["run-1"] * 9,
            "timestamp": [day for day in days for _ in assets],
            "asset": assets * 3,
            "prediction": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9],
            "score_delta": [0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09],
            "label": ["state-a"] * 9,
            "model_id": ["example-asset-signal-default"] * 9,
        }
    ).write_parquet(signal_dir / "predictions.parquet")
    (signal_dir / "runs.json").write_text(
        json.dumps(
            {
                "runs": {
                    "run-1": {"config": {"signal_type": "example_asset-signal"}},
                }
            }
        )
    )
    return db_root


def test_multi_asset_run_returns_the_latest_cross_section(client, set_db_root, multi_asset_db_root):
    set_db_root(multi_asset_db_root)

    response = client.get("/api/signals/example-asset-signal-default/run-1")
    assert response.status_code == 200

    payload = response.json()
    assert payload["cross_section"] is True
    assert payload["asset"] is None
    assert payload["assets"] == ["DOGE", "ETH", "SOL"]
    assert len(payload["data"]) == 3
    assert {row["timestamp"] for row in payload["data"]} == {"2024-01-03 00:00:00"}
    assert {row["asset"] for row in payload["data"]} == {"DOGE", "ETH", "SOL"}


def test_multi_asset_run_filters_to_one_asset_history(client, set_db_root, multi_asset_db_root):
    set_db_root(multi_asset_db_root)

    response = client.get("/api/signals/example-asset-signal-default/run-1?asset=ETH")
    assert response.status_code == 200

    payload = response.json()
    assert payload["cross_section"] is False
    assert payload["asset"] == "ETH"
    # The selector still lists every asset in the run, not just the selected one.
    assert payload["assets"] == ["DOGE", "ETH", "SOL"]
    assert [row["asset"] for row in payload["data"]] == ["ETH", "ETH", "ETH"]
    assert [row["timestamp"] for row in payload["data"]] == [
        "2024-01-01 00:00:00",
        "2024-01-02 00:00:00",
        "2024-01-03 00:00:00",
    ]


def test_multi_asset_predictions_endpoint_behaves_the_same(client, set_db_root, multi_asset_db_root):
    set_db_root(multi_asset_db_root)

    cross_section = client.get("/api/signals/example-asset-signal-default/run-1/predictions")
    assert cross_section.status_code == 200
    assert cross_section.json()["cross_section"] is True
    assert len(cross_section.json()["data"]) == 3

    filtered = client.get("/api/signals/example-asset-signal-default/run-1/predictions?asset=SOL")
    assert filtered.status_code == 200
    assert filtered.json()["asset"] == "SOL"
    assert len(filtered.json()["data"]) == 3


def test_unknown_asset_is_not_found(client, set_db_root, multi_asset_db_root):
    set_db_root(multi_asset_db_root)

    response = client.get("/api/signals/example-asset-signal-default/run-1?asset=NOPE")
    assert response.status_code == 404
    assert "NOPE" in response.json()["detail"]


def test_stats_still_cover_the_whole_multi_asset_run(client, set_db_root, multi_asset_db_root):
    set_db_root(multi_asset_db_root)

    response = client.get("/api/signals/example-asset-signal-default/run-1/stats")
    assert response.status_code == 200

    stats = {row["column"]: row for row in response.json()["prediction_stats"]}
    assert stats["prediction"]["count"] == 9


def test_single_asset_run_is_unchanged(client, set_db_root, signals_db_root):
    """A one-asset store keeps its whole history and reports no cross-section."""
    set_db_root(signals_db_root)

    response = client.get("/api/signals/example_direction/run-1")
    assert response.status_code == 200

    payload = response.json()
    assert payload["assets"] is None
    assert payload["asset"] is None
    assert payload["cross_section"] is False
    assert len(payload["data"]) == 2


def test_single_asset_run_still_accepts_its_own_asset(client, set_db_root, signals_db_root):
    set_db_root(signals_db_root)

    filtered = client.get("/api/signals/example_direction/run-1?asset=BTC")
    assert filtered.status_code == 200
    assert filtered.json()["asset"] == "BTC"
    assert len(filtered.json()["data"]) == 2

    missing = client.get("/api/signals/example_direction/run-1?asset=ETH")
    assert missing.status_code == 404


def test_latest_endpoint_is_an_asset_view_too(client, set_db_root, multi_asset_db_root):
    """`/latest` follows the run endpoints: cross-section by default, one history with `asset`."""
    set_db_root(multi_asset_db_root)

    response = client.get("/api/signals/example-asset-signal-default/latest")
    assert response.status_code == 200
    payload = response.json()
    assert payload["cross_section"] is True
    assert payload["asset"] is None
    assert payload["assets"] == ["DOGE", "ETH", "SOL"]
    assert sorted(row["asset"] for row in payload["data"]) == ["DOGE", "ETH", "SOL"]
    assert {row["timestamp"][:10] for row in payload["data"]} == {"2024-01-03"}

    response = client.get("/api/signals/example-asset-signal-default/latest?asset=SOL")
    assert response.status_code == 200
    payload = response.json()
    assert payload["cross_section"] is False
    assert payload["asset"] == "SOL"
    assert [row["timestamp"][:10] for row in payload["data"]] == [
        "2024-01-01",
        "2024-01-02",
        "2024-01-03",
    ]

    response = client.get("/api/signals/example-asset-signal-default/latest?asset=XYZ")
    assert response.status_code == 404
