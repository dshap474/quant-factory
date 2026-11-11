"""Verify always-on run tracking around every training pipeline execution.

Usage::

    uv run pytest packages/platform/ml-engine/tests/unit/training/test_auto_tracking.py -q
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LinearRegression

from ml_engine.training import (
    CandidateConfig,
    MetricConfig,
    SelectionConfig,
    SplitConfig,
    TrainingConfig,
    TrainingPipeline,
    TrainingRun,
    current_training_run,
)
from ml_engine.training.progress import TrainingProgress

# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture
def frame() -> pd.DataFrame:
    """Return a tiny deterministic regression dataset."""

    rows = 120
    timestamps = pd.date_range("2022-01-01", periods=rows, freq="D", tz="UTC")
    trend = np.linspace(-1.0, 1.0, rows)
    return pd.DataFrame(
        {
            "row_id": np.arange(rows, dtype=np.int64),
            "timestamp": timestamps,
            "feature_trend": trend,
            "target": 2.0 * trend + np.sin(np.arange(rows) / 7.0),
        }
    )


@pytest.fixture
def config() -> TrainingConfig:
    """Return a minimal expanding walk-forward configuration."""

    return TrainingConfig(
        feature_cols=("feature_trend",),
        target_col="target",
        timestamp_col="timestamp",
        row_id_col="row_id",
        split=SplitConfig(kind="expanding", min_train_periods=40, eval_periods=20, step_periods=20),
        candidates=(CandidateConfig(name="linear", estimator=LinearRegression()),),
        metrics=(MetricConfig(name="rmse"),),
        selection=SelectionConfig(primary_metric="rmse", direction="minimize", min_folds=1),
        final_refit=False,
        random_seed=7,
    )


def _sidecars(root: Path) -> list[dict[str, object]]:
    """Return every sidecar document under one run store root."""

    return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(root.glob("*.json"))]


def _enable_auto_tracking(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    """Simulate a non-test process pointed at an isolated run store."""

    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("ML_ENGINE_TRACKING", raising=False)
    monkeypatch.setenv("ML_ENGINE_OUTPUT_ROOT", str(root))


# --------------------------------------------------------------------------- #
# Implicit tracking
# --------------------------------------------------------------------------- #


def test_untracked_run_creates_one_completed_sidecar(
    frame: pd.DataFrame,
    config: TrainingConfig,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A bare pipeline run registers exactly one completed run record."""

    _enable_auto_tracking(monkeypatch, tmp_path)
    monkeypatch.setenv("ML_ENGINE_PRODUCER", "family/v999")
    TrainingPipeline(config).run(frame)
    sidecars = _sidecars(tmp_path)
    assert len(sidecars) == 1
    record = sidecars[0]
    assert record["producer"] == "family/v999"
    assert record["status"] == "completed"
    assert record["completed_fits"] == record["total_fits"]
    assert record["inference_ready"] is False


def test_unattributed_producer_falls_back_to_script_identity(
    frame: pd.DataFrame,
    config: TrainingConfig,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without a declared producer the record stays honest, not absent."""

    _enable_auto_tracking(monkeypatch, tmp_path)
    monkeypatch.delenv("ML_ENGINE_PRODUCER", raising=False)
    TrainingPipeline(config).run(frame)
    (record,) = _sidecars(tmp_path)
    assert str(record["producer"]).startswith("unattributed/")


def test_failed_run_records_failed_status_and_propagates(
    frame: pd.DataFrame,
    config: TrainingConfig,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Training failures terminate the implicit record as failed."""

    _enable_auto_tracking(monkeypatch, tmp_path)
    broken = frame.copy()
    broken["target"] = np.nan
    with pytest.raises(ValueError):
        TrainingPipeline(config).run(broken)
    (record,) = _sidecars(tmp_path)
    assert record["status"] == "failed"
    assert record["error"] is not None


def test_explicit_training_run_owns_the_sidecar(
    frame: pd.DataFrame,
    config: TrainingConfig,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Inside an explicit context no second implicit record is created."""

    _enable_auto_tracking(monkeypatch, tmp_path)
    with TrainingRun(output_root=tmp_path, producer="family/v999") as run:
        assert current_training_run() is run
        TrainingPipeline(config).run(frame)
    assert current_training_run() is None
    (record,) = _sidecars(tmp_path)
    assert record["producer"] == "family/v999"
    assert record["status"] == "completed"
    assert record["completed_fits"] == record["total_fits"]


def test_explicit_context_with_explicit_progress_not_double_forwarded(
    frame: pd.DataFrame,
    config: TrainingConfig,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Passing run.update explicitly must not duplicate sidecar updates."""

    _enable_auto_tracking(monkeypatch, tmp_path)
    updates: list[TrainingProgress] = []
    original_update = TrainingRun.update

    def counting_update(self: TrainingRun, value: TrainingProgress) -> None:
        updates.append(value)
        original_update(self, value)

    monkeypatch.setattr(TrainingRun, "update", counting_update)
    with TrainingRun(output_root=tmp_path, producer="family/v999") as run:
        TrainingPipeline(config).run(frame, progress=run.update)
    total = updates[-1].total_fits
    assert total is not None
    # One update per lifecycle notification, not two per notification.
    stages = [value.stage for value in updates]
    assert stages.count("selection") == 1


# --------------------------------------------------------------------------- #
# Suppression and failure isolation
# --------------------------------------------------------------------------- #


def test_pytest_processes_do_not_write_sidecars(
    frame: pd.DataFrame,
    config: TrainingConfig,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test-suite fits stay out of the canonical run store by default."""

    monkeypatch.setenv("ML_ENGINE_OUTPUT_ROOT", str(tmp_path))
    assert "PYTEST_CURRENT_TEST" in __import__("os").environ
    TrainingPipeline(config).run(frame)
    assert _sidecars(tmp_path) == []


def test_tracking_opt_out_environment(
    frame: pd.DataFrame,
    config: TrainingConfig,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ML_ENGINE_TRACKING=0 suppresses the implicit record."""

    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("ML_ENGINE_TRACKING", "0")
    monkeypatch.setenv("ML_ENGINE_OUTPUT_ROOT", str(tmp_path))
    TrainingPipeline(config).run(frame)
    assert _sidecars(tmp_path) == []


def test_deleted_cwd_warns_and_training_still_succeeds(
    frame: pd.DataFrame,
    config: TrainingConfig,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Root resolution errors (e.g. deleted cwd) never reach the training body."""

    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("ML_ENGINE_TRACKING", raising=False)
    monkeypatch.delenv("ML_ENGINE_OUTPUT_ROOT", raising=False)
    monkeypatch.delenv("QUANT_DB_ROOT", raising=False)

    def deleted_cwd() -> Path:
        raise FileNotFoundError("current working directory was deleted")

    monkeypatch.setattr(Path, "cwd", deleted_cwd)
    with pytest.warns(RuntimeWarning, match="tracking disabled"):
        result = TrainingPipeline(config).run(frame)
    assert result.selected_candidates == ("linear",)
    assert any("tracking disabled" in item for item in result.warnings)


def test_explicit_run_sidecar_write_failure_does_not_fail_training(
    frame: pd.DataFrame,
    config: TrainingConfig,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mid-run store loss inside an explicit context degrades to a warning."""

    _enable_auto_tracking(monkeypatch, tmp_path)
    with TrainingRun(output_root=tmp_path, producer="family/v999") as run:

        def boom() -> None:
            raise OSError("no space left on device")

        run._replace_state = boom  # type: ignore[method-assign]
        with pytest.warns(RuntimeWarning, match="stopped mid-run"):
            result = TrainingPipeline(config).run(frame)
        del run.__dict__["_replace_state"]
    assert result.selected_candidates == ("linear",)
    assert any("stopped mid-run" in item for item in result.warnings)
    (record,) = _sidecars(tmp_path)
    assert record["status"] == "completed"


def test_stale_context_registry_falls_back_to_implicit_tracking(
    frame: pd.DataFrame,
    config: TrainingConfig,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Out-of-order context exits never poison later pipeline runs."""

    _enable_auto_tracking(monkeypatch, tmp_path)
    run_a = TrainingRun(output_root=tmp_path, producer="family/a")
    run_b = TrainingRun(output_root=tmp_path, producer="family/b")
    run_a.__enter__()
    run_b.__enter__()
    run_a.__exit__(None, None, None)
    run_b.__exit__(None, None, None)
    # The registry may now point at a closed run; training must still track.
    result = TrainingPipeline(config).run(frame)
    assert result.selected_candidates == ("linear",)
    assert len(_sidecars(tmp_path)) == 3


def test_unwritable_store_warns_and_training_still_succeeds(
    frame: pd.DataFrame,
    config: TrainingConfig,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Telemetry failures degrade to a warning; the fit result is unaffected."""

    blocked = tmp_path / "store"
    blocked.write_text("not a directory", encoding="utf-8")
    _enable_auto_tracking(monkeypatch, blocked)
    with pytest.warns(RuntimeWarning, match="tracking disabled"):
        result = TrainingPipeline(config).run(frame)
    assert result.selected_candidates == ("linear",)
    assert any("tracking disabled" in item for item in result.warnings)
