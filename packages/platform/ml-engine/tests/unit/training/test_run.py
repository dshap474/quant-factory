"""Verify tracked-run identity, lifecycle, and atomic sidecar behavior.

Usage::

    uv run pytest packages/platform/ml-engine/tests/unit/training/test_run.py -q
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

from ml_engine.training import TrainingProgress, TrainingRun


# --------------------------------------------------------------------------- #
# Sidecar helpers
# --------------------------------------------------------------------------- #


def _read(path: Path) -> dict[str, object]:
    """Read one test-owned status sidecar."""

    return json.loads(path.read_text(encoding="utf-8"))


def _progress(*, completed: int = 0) -> TrainingProgress:
    """Return one exact single-fit progress value."""

    return TrainingProgress(
        stage="cross_validation",
        task="regression",
        target="target",
        feature_count=3,
        final_refit=False,
        candidate="linear",
        candidate_index=1,
        candidate_count=1,
        fold_index=1,
        fold_count=1,
        completed_fits=completed,
        total_fits=1,
    )


# --------------------------------------------------------------------------- #
# Run lifecycle
# --------------------------------------------------------------------------- #


def test_generated_and_explicit_run_ids() -> None:
    """Generate the documented identity shape and validate caller IDs before I/O."""

    generated = TrainingRun(output_root="unused", producer="tests")
    explicit = TrainingRun(output_root="unused", producer="tests", run_id="valid.run-1")

    assert re.fullmatch(r"\d{8}T\d{12}Z-[0-9a-f]{8}", generated.run_id)
    assert explicit.run_id == "valid.run-1"
    with pytest.raises(ValueError, match="run_id"):
        TrainingRun(output_root="unused", producer="tests", run_id="../escape")


def test_normal_completion_and_operation_update(tmp_path: Path) -> None:
    """Write one running document and finish it without creating an artifact."""

    with TrainingRun(output_root=tmp_path, producer="tests/v1", run_id="run-1") as run:
        assert _read(run.sidecar_path)["status"] == "running"
        run.set_operation("determinism_replay")
        run.update(_progress(completed=1))
        running = _read(run.sidecar_path)
        assert running["operation"] == "determinism_replay"
        assert running["completed_fits"] == 1

    completed = _read(run.sidecar_path)
    assert completed["status"] == "completed"
    assert completed["completed_at"] is not None
    assert completed["inference_ready"] is False
    assert not run.artifact_path.exists()


def test_exception_marks_failed_and_propagates(tmp_path: Path) -> None:
    """Record bounded error identity without swallowing the training exception."""

    run = TrainingRun(output_root=tmp_path, producer="tests/v1", run_id="failed-run")
    with pytest.raises(ValueError, match="bad training data"):
        with run:
            raise ValueError("bad training data")

    failed = _read(run.sidecar_path)
    assert failed["status"] == "failed"
    assert failed["error"] == {"type": "ValueError", "message": "bad training data"}
    assert "traceback" not in failed


def test_abruptly_abandoned_context_remains_running(tmp_path: Path) -> None:
    """Without a context exit, the last honest durable state remains running."""

    run = TrainingRun(output_root=tmp_path, producer="tests/v1", run_id="abrupt-run")
    run.__enter__()
    run.update(_progress())

    assert _read(run.sidecar_path)["status"] == "running"


def test_collisions_reject_sidecars_and_artifact_directories(tmp_path: Path) -> None:
    """Never overwrite either durable object associated with an existing ID."""

    (tmp_path / "sidecar.json").write_text("{}", encoding="utf-8")
    with pytest.raises(FileExistsError, match="sidecar"):
        with TrainingRun(output_root=tmp_path, producer="tests", run_id="sidecar"):
            pass

    (tmp_path / "artifact").mkdir()
    with pytest.raises(FileExistsError, match="artifact"):
        with TrainingRun(output_root=tmp_path, producer="tests", run_id="artifact"):
            pass


def test_replacements_are_complete_atomic_sibling_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Every update reaches os.replace as valid JSON from a dot-prefixed sibling."""

    observed: list[Path] = []
    original = os.replace

    def inspect_replace(
        source: str | os.PathLike[str], destination: str | os.PathLike[str]
    ) -> None:
        temporary = Path(source)
        target = Path(destination)
        assert temporary.parent == target.parent == tmp_path
        assert temporary.name.startswith(".atomic-run.")
        _read(temporary)
        observed.append(temporary)
        original(source, destination)

    monkeypatch.setattr(os, "replace", inspect_replace)
    with TrainingRun(output_root=tmp_path, producer="tests", run_id="atomic-run") as run:
        run.update(_progress())

    assert len(observed) == 2
    assert not list(tmp_path.glob(".*.tmp"))


def test_update_write_failures_propagate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A required sidecar failure stops the tracked execution path."""

    run = TrainingRun(output_root=tmp_path, producer="tests", run_id="write-failure")
    run.__enter__()

    def fail_replace(_source: object, _destination: object) -> None:
        raise OSError("disk unavailable")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="disk unavailable"):
        run.update(_progress())


def test_exit_write_failure_preserves_training_exception(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep the training failure primary when its terminal sidecar write also fails."""

    run = TrainingRun(output_root=tmp_path, producer="tests", run_id="double-failure")

    def fail_replace(_source: object, _destination: object) -> None:
        raise OSError("disk unavailable")

    with pytest.raises(ValueError, match="bad training data") as caught:
        with run:
            monkeypatch.setattr(os, "replace", fail_replace)
            raise ValueError("bad training data")

    assert isinstance(caught.value.__cause__, OSError)
    assert str(caught.value.__cause__) == "disk unavailable"
