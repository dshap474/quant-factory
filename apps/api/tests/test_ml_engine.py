"""Safety and response-contract tests for the read-only ML Engine API.

USAGE::

    uv run pytest apps/api/tests/test_ml_engine.py -q
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports and fixtures
# --------------------------------------------------------------------------- #
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import joblib
import pytest
from db_api.routers import ml_engine


def _count_sidecar_reads(monkeypatch: pytest.MonkeyPatch) -> "Callable[[], int]":
    """Instrument the router's JSON reader and return the call counter."""

    calls = 0
    original = ml_engine._read_json_object

    def counted(filename: str, *, dir_fd: int) -> dict[str, object]:
        nonlocal calls
        calls += 1
        return original(filename, dir_fd=dir_fd)

    monkeypatch.setattr(ml_engine, "_read_json_object", counted)
    return lambda: calls


def _status(
    run_id: str,
    *,
    started_at: datetime,
    status: str = "running",
    final_refit: bool = False,
    inference_ready: bool = False,
    producer: str = "tests/v1",
) -> dict[str, object]:
    """Return one valid v1 sidecar payload."""

    completed = status != "running"
    timestamp = started_at.isoformat().replace("+00:00", "Z")
    return {
        "schema_version": 1,
        "run_id": run_id,
        "producer": producer,
        "status": status,
        "operation": "training",
        "stage": "selection" if completed else "cross_validation",
        "task": "regression",
        "target": "target",
        "feature_count": 3,
        "final_refit": final_refit,
        "candidate": "linear",
        "candidate_index": 1,
        "candidate_count": 1,
        "fold_index": 1,
        "fold_count": 2,
        "completed_fits": 2 if completed else 1,
        "total_fits": 2,
        "started_at": timestamp,
        "updated_at": timestamp,
        "completed_at": timestamp if completed else None,
        "host": "test-host",
        "inference_ready": inference_ready,
        "error": {"type": "RuntimeError", "message": "fit failed"} if status == "failed" else None,
    }


def _write_status(root: Path, payload: dict[str, object]) -> Path:
    """Write one test-owned sidecar under the operational root."""

    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{payload['run_id']}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _timestamped_run_id(started_at: datetime) -> str:
    """Return a run ID in the engine's timestamp-prefixed filename order."""

    return f"{started_at.strftime('%Y%m%dT%H%M%S%fZ')}-abcdef01"


def _write_series(root: Path, count: int, *, start: datetime, **kwargs: object) -> list[str]:
    """Write ``count`` timestamp-named sidecars, newest last, and return their IDs."""

    run_ids = []
    for index in range(count):
        started_at = start + timedelta(seconds=index)
        run_id = _timestamped_run_id(started_at)
        _write_status(root, _status(run_id, started_at=started_at, **kwargs))  # type: ignore[arg-type]
        run_ids.append(run_id)
    return run_ids


def _write_artifact(root: Path, run_id: str) -> Path:
    """Write allowlisted JSON plus executable-looking files that must remain unopened."""

    artifact = root / run_id
    artifact.mkdir(parents=True)
    for name, payload in {
        "manifest.json": {"selected_candidates": ["linear"]},
        "config.json": {"final_refit": True},
        "schema.json": {"feature_cols": ["a", "b", "c"]},
        "metrics.json": {"linear": {"rmse": 0.25}},
        "selection.json": {"selected_candidates": ["linear"]},
    }.items():
        (artifact / name).write_text(json.dumps(payload), encoding="utf-8")
    (artifact / "preprocessing.joblib").write_bytes(b"must-not-load")
    (artifact / "oos_predictions.parquet").write_bytes(b"must-not-read")
    model_root = artifact / "models"
    model_root.mkdir()
    (model_root / "linear.joblib").write_bytes(b"must-not-load")
    return artifact


# --------------------------------------------------------------------------- #
# List route
# --------------------------------------------------------------------------- #


def test_list_runs_returns_empty_for_missing_root(client, set_db_root, tmp_path: Path) -> None:
    """An unused operational root is a valid empty system."""

    set_db_root(tmp_path / "db")

    response = client.get("/api/ml-engine/runs")

    assert response.status_code == 200
    assert response.json() == {"runs": [], "count": 0, "invalid_count": 0}


def test_list_runs_orders_newest_and_supports_all_statuses(
    client,
    set_db_root,
    tmp_path: Path,
) -> None:
    """Return running, completed, failed, and OOS-only records newest first."""

    db_root = tmp_path / "db"
    root = db_root / "ml-engine"
    start = datetime(2026, 8, 24, tzinfo=UTC)
    _write_status(root, _status("running", started_at=start + timedelta(minutes=3)))
    _write_status(
        root,
        _status(
            "inference",
            started_at=start + timedelta(minutes=2),
            status="completed",
            final_refit=True,
            inference_ready=True,
        ),
    )
    _write_status(
        root,
        _status("oos-only", started_at=start + timedelta(minutes=1), status="completed"),
    )
    _write_status(root, _status("failed", started_at=start, status="failed"))
    set_db_root(db_root)

    response = client.get("/api/ml-engine/runs?limit=3")

    assert response.status_code == 200
    payload = response.json()
    assert [run["run_id"] for run in payload["runs"]] == ["running", "inference", "oos-only"]
    assert payload["count"] == 3
    assert payload["invalid_count"] == 0
    assert payload["runs"][1]["inference_ready"] is True
    assert payload["runs"][2]["final_refit"] is False


def test_list_runs_filters_by_producer_family_and_status(
    client,
    set_db_root,
    tmp_path: Path,
) -> None:
    """Filter runs by exact producer, producer family prefix, and status."""

    db_root = tmp_path / "db"
    root = db_root / "ml-engine"
    start = datetime(2026, 8, 24, tzinfo=UTC)
    _write_status(
        root,
        _status(
            "v004",
            started_at=start + timedelta(minutes=3),
            status="completed",
            producer="example-alpha/v004",
        ),
    )
    _write_status(
        root,
        _status(
            "v005",
            started_at=start + timedelta(minutes=2),
            producer="example-alpha/v005",
        ),
    )
    _write_status(
        root,
        _status(
            "lookalike",
            started_at=start + timedelta(minutes=1),
            status="completed",
            producer="example-beta/v001",
        ),
    )
    _write_status(root, _status("other", started_at=start, status="failed"))
    set_db_root(db_root)

    family = client.get("/api/ml-engine/runs?producer=example-alpha").json()
    assert [run["run_id"] for run in family["runs"]] == ["v004", "v005"]

    exact = client.get("/api/ml-engine/runs?producer=example-alpha/v004").json()
    assert [run["run_id"] for run in exact["runs"]] == ["v004"]

    completed = client.get("/api/ml-engine/runs?status=completed").json()
    assert [run["run_id"] for run in completed["runs"]] == ["v004", "lookalike"]

    both = client.get("/api/ml-engine/runs?producer=example-alpha&status=completed").json()
    assert [run["run_id"] for run in both["runs"]] == ["v004"]

    bad_status = client.get("/api/ml-engine/runs?status=bogus")
    assert bad_status.status_code == 422


@pytest.mark.parametrize("limit", [0, 201])
def test_list_run_limit_is_bounded(client, limit: int) -> None:
    """Reject inventory requests outside the documented bound."""

    response = client.get(f"/api/ml-engine/runs?limit={limit}")

    assert response.status_code == 422


def test_list_counts_invalid_sidecars_and_ignores_temporaries(
    client,
    set_db_root,
    tmp_path: Path,
) -> None:
    """One damaged run cannot hide healthy records or expose atomic temporaries."""

    db_root = tmp_path / "db"
    root = db_root / "ml-engine"
    now = datetime(2026, 8, 24, tzinfo=UTC)
    _write_status(root, _status("healthy", started_at=now))
    (root / "invalid-json.json").write_text("{", encoding="utf-8")
    unsupported = _status("unsupported", started_at=now)
    unsupported["schema_version"] = 2
    _write_status(root, unsupported)
    mismatch = _status("declared", started_at=now)
    (root / "different.json").write_text(json.dumps(mismatch), encoding="utf-8")
    (root / ".healthy.pending.tmp").write_text("{", encoding="utf-8")
    set_db_root(db_root)

    payload = client.get("/api/ml-engine/runs").json()

    assert [run["run_id"] for run in payload["runs"]] == ["healthy"]
    assert payload["invalid_count"] == 3


def test_list_counts_naive_timestamp_as_invalid(
    client,
    set_db_root,
    tmp_path: Path,
) -> None:
    """A timezone-naive sidecar cannot break sorting of healthy UTC runs."""

    db_root = tmp_path / "db"
    root = db_root / "ml-engine"
    now = datetime(2026, 8, 24, tzinfo=UTC)
    _write_status(root, _status("healthy", started_at=now))
    naive = _status("naive", started_at=now)
    naive["started_at"] = "2026-08-24T00:00:00"
    _write_status(root, naive)
    set_db_root(db_root)

    response = client.get("/api/ml-engine/runs")

    assert response.status_code == 200
    assert [run["run_id"] for run in response.json()["runs"]] == ["healthy"]
    assert response.json()["invalid_count"] == 1


def test_list_runs_reads_a_bounded_window_of_the_store(
    client,
    set_db_root,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A newest-first page costs the page size, not the size of the store."""

    db_root = tmp_path / "db"
    root = db_root / "ml-engine"
    run_ids = _write_series(root, 200, start=datetime(2026, 8, 24, tzinfo=UTC))
    set_db_root(db_root)
    reads = _count_sidecar_reads(monkeypatch)

    payload = client.get("/api/ml-engine/runs?limit=5").json()

    assert [run["run_id"] for run in payload["runs"]] == run_ids[-1:-6:-1]
    assert payload["count"] == 5
    assert reads() <= 5 + ml_engine._SCAN_MARGIN


def test_list_runs_filter_reaches_past_the_unfiltered_window(
    client,
    set_db_root,
    tmp_path: Path,
) -> None:
    """A producer filter selects runs that an unfiltered page never reaches."""

    db_root = tmp_path / "db"
    root = db_root / "ml-engine"
    start = datetime(2026, 8, 24, tzinfo=UTC)
    buried = _timestamped_run_id(start)
    _write_status(root, _status(buried, started_at=start, producer="real-family/v004"))
    _write_series(root, 200, start=start + timedelta(seconds=1), producer="unattributed/local")
    set_db_root(db_root)

    unfiltered = client.get("/api/ml-engine/runs?limit=5").json()
    assert buried not in [run["run_id"] for run in unfiltered["runs"]]

    filtered = client.get("/api/ml-engine/runs?limit=5&producer=real-family").json()
    assert [run["run_id"] for run in filtered["runs"]] == [buried]


def test_list_run_invalid_count_covers_only_the_examined_window(
    client,
    set_db_root,
    tmp_path: Path,
) -> None:
    """Damaged sidecars older than the returned page are not counted."""

    db_root = tmp_path / "db"
    root = db_root / "ml-engine"
    start = datetime(2026, 8, 24, tzinfo=UTC)
    root.mkdir(parents=True)
    (root / f"{_timestamped_run_id(start)}.json").write_text("{", encoding="utf-8")
    _write_series(root, 200, start=start + timedelta(seconds=1))
    set_db_root(db_root)

    assert client.get("/api/ml-engine/runs?limit=5").json()["invalid_count"] == 0
    assert client.get("/api/ml-engine/runs?limit=200").json()["invalid_count"] == 1


# --------------------------------------------------------------------------- #
# Producer route
# --------------------------------------------------------------------------- #


def test_producers_returns_families_outside_the_newest_run_page(
    client,
    set_db_root,
    tmp_path: Path,
) -> None:
    """Filter options survive a flood that pushes a family out of the run page."""

    db_root = tmp_path / "db"
    root = db_root / "ml-engine"
    start = datetime(2026, 8, 24, tzinfo=UTC)
    _write_status(
        root,
        _status(_timestamped_run_id(start), started_at=start, producer="real-family/v004"),
    )
    _write_series(root, 200, start=start + timedelta(seconds=1), producer="unattributed/local")
    (root / "broken.json").write_text("{", encoding="utf-8")
    set_db_root(db_root)

    response = client.get("/api/ml-engine/producers")

    assert response.status_code == 200
    assert response.json() == {
        "producers": ["real-family", "unattributed"],
        "invalid_count": 1,
    }


def test_producers_returns_empty_for_missing_root(client, set_db_root, tmp_path: Path) -> None:
    """An unused operational root exposes no producer options."""

    set_db_root(tmp_path / "db")

    response = client.get("/api/ml-engine/producers")

    assert response.status_code == 200
    assert response.json() == {"producers": [], "invalid_count": 0}


def test_producers_rejects_a_symlinked_operational_root(
    client,
    set_db_root,
    tmp_path: Path,
) -> None:
    """Producer aggregation never follows a substituted operational root."""

    db_root = tmp_path / "db"
    db_root.mkdir()
    outside = tmp_path / "outside-root"
    _write_status(outside, _status("outside", started_at=datetime(2026, 8, 24, tzinfo=UTC)))
    (db_root / "ml-engine").symlink_to(outside, target_is_directory=True)
    set_db_root(db_root)

    assert client.get("/api/ml-engine/producers").status_code == 500


# --------------------------------------------------------------------------- #
# Detail route and read-only safety
# --------------------------------------------------------------------------- #


def test_detail_returns_allowlisted_metadata_without_loading_joblib(
    client,
    set_db_root,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Project JSON metadata only, even when executable artifacts are present."""

    db_root = tmp_path / "db"
    root = db_root / "ml-engine"
    _write_status(
        root,
        _status(
            "ready-run",
            started_at=datetime(2026, 8, 24, tzinfo=UTC),
            status="completed",
            final_refit=True,
            inference_ready=True,
        ),
    )
    _write_artifact(root, "ready-run")
    set_db_root(db_root)

    def forbid_joblib(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("DB API must not deserialize Joblib")

    monkeypatch.setattr(joblib, "load", forbid_joblib)
    before = sorted(path.relative_to(root).as_posix() for path in root.rglob("*"))

    response = client.get("/api/ml-engine/runs/ready-run")

    assert response.status_code == 200
    artifact = response.json()["artifact"]
    assert artifact == {
        "path": "db/ml-engine/ready-run",
        "manifest": {"selected_candidates": ["linear"]},
        "config": {"final_refit": True},
        "schema": {"feature_cols": ["a", "b", "c"]},
        "metrics": {"linear": {"rmse": 0.25}},
        "selection": {"selected_candidates": ["linear"]},
    }
    after = sorted(path.relative_to(root).as_posix() for path in root.rglob("*"))
    assert after == before


def test_oos_only_detail_has_no_artifact(client, set_db_root, tmp_path: Path) -> None:
    """A completed research run is valid without an inference directory."""

    db_root = tmp_path / "db"
    _write_status(
        db_root / "ml-engine",
        _status(
            "oos-only",
            started_at=datetime(2026, 8, 24, tzinfo=UTC),
            status="completed",
        ),
    )
    set_db_root(db_root)

    response = client.get("/api/ml-engine/runs/oos-only")

    assert response.status_code == 200
    assert response.json()["artifact"] is None


@pytest.mark.parametrize("run_id", ["unknown", "bad$id", "..%2Fsecret", "nested%2Frun"])
def test_detail_rejects_unknown_and_traversal_ids(client, run_id: str) -> None:
    """Resolve only a validated direct-child sidecar identity."""

    response = client.get(f"/api/ml-engine/runs/{run_id}")

    assert response.status_code == 404


def test_selected_malformed_sidecar_returns_stable_error(
    client,
    set_db_root,
    tmp_path: Path,
) -> None:
    """Distinguish a damaged selected run from an unknown run."""

    db_root = tmp_path / "db"
    root = db_root / "ml-engine"
    root.mkdir(parents=True)
    (root / "broken.json").write_text("{", encoding="utf-8")
    set_db_root(db_root)

    response = client.get("/api/ml-engine/runs/broken")

    assert response.status_code == 500
    assert response.json() == {"detail": "ML Engine run metadata is invalid"}


def test_symlinked_sidecar_and_artifact_root_are_rejected(
    client,
    set_db_root,
    tmp_path: Path,
) -> None:
    """Never follow status or artifact symlinks outside the operational root."""

    db_root = tmp_path / "db"
    root = db_root / "ml-engine"
    outside = tmp_path / "outside"
    outside.mkdir()
    target = outside / "linked.json"
    target.write_text(
        json.dumps(_status("linked", started_at=datetime(2026, 8, 24, tzinfo=UTC))),
        encoding="utf-8",
    )
    root.mkdir(parents=True)
    (root / "linked.json").symlink_to(target)
    _write_status(
        root,
        _status(
            "artifact-link",
            started_at=datetime(2026, 8, 24, tzinfo=UTC),
            status="completed",
            final_refit=True,
            inference_ready=True,
        ),
    )
    (root / "artifact-link").symlink_to(outside, target_is_directory=True)
    set_db_root(db_root)

    listing = client.get("/api/ml-engine/runs").json()
    assert listing["invalid_count"] == 1
    assert client.get("/api/ml-engine/runs/linked").status_code == 500
    assert client.get("/api/ml-engine/runs/artifact-link").status_code == 500


def test_symlinked_operational_root_is_rejected(
    client,
    set_db_root,
    tmp_path: Path,
) -> None:
    """List and detail never follow a substituted operational root."""

    db_root = tmp_path / "db"
    db_root.mkdir()
    outside = tmp_path / "outside-root"
    _write_status(
        outside,
        _status("outside", started_at=datetime(2026, 8, 24, tzinfo=UTC)),
    )
    (db_root / "ml-engine").symlink_to(outside, target_is_directory=True)
    set_db_root(db_root)

    assert client.get("/api/ml-engine/runs").status_code == 500
    assert client.get("/api/ml-engine/runs/outside").status_code == 500


def test_symlinked_artifact_json_is_rejected(
    client,
    set_db_root,
    tmp_path: Path,
) -> None:
    """Allowlisted artifact names still cannot point outside their artifact directory."""

    db_root = tmp_path / "db"
    root = db_root / "ml-engine"
    _write_status(
        root,
        _status(
            "linked-metadata",
            started_at=datetime(2026, 8, 24, tzinfo=UTC),
            status="completed",
            final_refit=True,
            inference_ready=True,
        ),
    )
    artifact = root / "linked-metadata"
    artifact.mkdir()
    outside = tmp_path / "outside-metrics.json"
    outside.write_text(json.dumps({"secret": "must-not-return"}), encoding="utf-8")
    (artifact / "metrics.json").symlink_to(outside)
    set_db_root(db_root)

    response = client.get("/api/ml-engine/runs/linked-metadata")

    assert response.status_code == 500
    assert response.json() == {"detail": "ML Engine run metadata is invalid"}


def test_artifact_json_reads_are_size_bounded(client, set_db_root, tmp_path: Path) -> None:
    """Reject oversized allowlisted JSON without reading model or parquet files."""

    db_root = tmp_path / "db"
    root = db_root / "ml-engine"
    _write_status(
        root,
        _status(
            "oversized",
            started_at=datetime(2026, 8, 24, tzinfo=UTC),
            status="completed",
            final_refit=True,
            inference_ready=True,
        ),
    )
    artifact = root / "oversized"
    artifact.mkdir()
    (artifact / "manifest.json").write_text(
        json.dumps({"payload": "x" * (2 * 1024 * 1024)}),
        encoding="utf-8",
    )
    set_db_root(db_root)

    response = client.get("/api/ml-engine/runs/oversized")

    assert response.status_code == 500
    assert response.json() == {"detail": "ML Engine run metadata is invalid"}
