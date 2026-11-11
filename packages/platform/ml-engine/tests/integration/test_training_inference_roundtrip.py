"""Exercise the public training, artifact, and inference contract end to end.

Usage::

    pytest tests/integration/test_training_inference_roundtrip.py

The fixture is deliberately tiny and deterministic.  The subprocess check
proves that a saved artifact carries enough state for a fresh interpreter to
load it and preserve caller row order and persisted feature order.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports and public fixtures
# --------------------------------------------------------------------------- #
import dataclasses
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

from ml_engine.inference import InferencePipeline
from ml_engine.training import (
    CandidateConfig,
    MetricConfig,
    SelectionConfig,
    SplitConfig,
    TrainingConfig,
    TrainingPipeline,
    TrainingRun,
)

# --------------------------------------------------------------------------- #
# Deterministic tabular fixture
# --------------------------------------------------------------------------- #


def _dataset(rows: int = 24) -> pd.DataFrame:
    """Return an ordered regression fixture with stable caller row IDs."""
    x = np.arange(float(rows))
    return pd.DataFrame(
        {
            "row_id": np.arange(10_000, 10_000 + rows, dtype=np.int64),
            "timestamp": pd.date_range("2024-01-01", periods=rows, freq="D"),
            "feature_a": x,
            "feature_b": np.sin(x / 3.0),
            "target": 2.5 * x - np.sin(x / 3.0),
        }
    )


def _config() -> TrainingConfig:
    """Construct the smallest explicit chronological training configuration."""
    return TrainingConfig(
        feature_cols=["feature_a", "feature_b"],
        target_col="target",
        timestamp_col="timestamp",
        row_id_col="row_id",
        split=SplitConfig(kind="chronological_holdout", min_train_periods=12, eval_periods=6),
        candidates=[CandidateConfig(name="linear", estimator=LinearRegression())],
        metrics=[MetricConfig(name="rmse")],
        selection=SelectionConfig(primary_metric="rmse", direction="minimize"),
        random_seed=17,
    )


def _prediction_values(value: object) -> np.ndarray:
    """Read the stable prediction vector from a public PredictionResult."""
    return np.asarray(value.predictions, dtype=float)  # type: ignore[attr-defined]


# --------------------------------------------------------------------------- #
# Artifact and fresh-process round trip
# --------------------------------------------------------------------------- #


def test_train_save_load_predict_matches_in_memory_and_fresh_process(
    tmp_path: Path,
) -> None:
    """A complete artifact reproduces predictions outside the training process."""
    frame = _dataset()
    result = TrainingPipeline(_config()).run(frame)
    assert result.inference_pipeline is not None

    # Deliberately shuffle feature columns and rows.  Inference must select the
    # persisted feature order but preserve this caller order in its result.
    new_data = pd.DataFrame(
        {
            "row_id": [20_001, 20_000, 20_002],
            "timestamp": pd.to_datetime(["2024-02-01", "2024-02-02", "2024-02-03"]),
            "feature_b": [0.25, -0.5, 0.75],
            "unused_extra": ["ignored", "ignored", "ignored"],
            "feature_a": [2.5, 1.5, 3.5],
        }
    )
    in_memory_result = result.inference_pipeline.predict(new_data)
    expected = _prediction_values(in_memory_result)
    np.testing.assert_array_equal(in_memory_result.row_ids, new_data["row_id"].to_numpy())
    np.testing.assert_array_equal(
        in_memory_result.timestamps,
        new_data["timestamp"].to_numpy(),
    )

    destination = tmp_path / "model-v1"
    assert result.save(destination) == destination
    loaded = InferencePipeline.load(destination, trusted=True)
    loaded_result = loaded.predict(new_data)
    np.testing.assert_allclose(_prediction_values(loaded_result), expected)
    np.testing.assert_array_equal(loaded_result.row_ids, new_data["row_id"].to_numpy())

    input_path = tmp_path / "new-data.json"
    input_path.write_text(new_data.to_json(orient="split", date_format="iso"), encoding="utf-8")
    script = """
import json
import sys
import pandas as pd
from ml_engine.inference import InferencePipeline

frame = pd.read_json(sys.argv[2], orient="split")
result = InferencePipeline.load(sys.argv[1], trusted=True).predict(frame)
print(json.dumps({"predictions": result.predictions.tolist(), "row_ids": result.row_ids.tolist()}))
"""
    environment = os.environ.copy()
    source_root = str(Path(__file__).parents[2] / "src")
    environment["PYTHONPATH"] = os.pathsep.join(
        path for path in (source_root, environment.get("PYTHONPATH", "")) if path
    )
    completed = subprocess.run(
        [sys.executable, "-c", script, str(destination), str(input_path)],
        check=True,
        capture_output=True,
        text=True,
        cwd=Path(__file__).parents[2],
        env=environment,
    )
    from_process = json.loads(completed.stdout)
    np.testing.assert_allclose(from_process["predictions"], expected)
    assert from_process["row_ids"] == new_data["row_id"].tolist()


def test_tracked_run_saves_directly_loadable_inference_artifact(tmp_path: Path) -> None:
    """The run-ID directory preserves the existing trusted inference contract."""

    frame = _dataset()
    root = tmp_path / "ml-engine"
    with TrainingRun(output_root=root, producer="tests/v1", run_id="tracked-run") as run:
        result = TrainingPipeline(_config()).run(frame, progress=run.update)
        assert run.save(result) == root / "tracked-run"

    status = json.loads(run.sidecar_path.read_text(encoding="utf-8"))
    assert status["status"] == "completed"
    assert status["inference_ready"] is True
    assert status["candidate"] == "linear"
    assert status["candidate_index"] == status["candidate_count"] == 1
    assert status["fold_index"] == status["fold_count"] == 1
    assert status["completed_fits"] == status["total_fits"] == 1
    loaded = InferencePipeline.load(root / "tracked-run", trusted=True)
    expected = _prediction_values(result.inference_pipeline.predict(frame))
    np.testing.assert_allclose(_prediction_values(loaded.predict(frame)), expected)


def test_tracked_oos_only_run_completes_without_artifact(tmp_path: Path) -> None:
    """A final_refit=False run remains a successful non-inference-ready run."""

    config = dataclasses.replace(_config(), final_refit=False)
    root = tmp_path / "ml-engine"
    with TrainingRun(output_root=root, producer="tests/v1", run_id="oos-only") as run:
        result = TrainingPipeline(config).run(_dataset(), progress=run.update)

    assert not result.oos_predictions.empty
    status = json.loads(run.sidecar_path.read_text(encoding="utf-8"))
    assert status["status"] == "completed"
    assert status["final_refit"] is False
    assert status["inference_ready"] is False
    assert not run.artifact_path.exists()


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

if __name__ == "__main__":  # pragma: no cover
    raise SystemExit("run this module through pytest")
