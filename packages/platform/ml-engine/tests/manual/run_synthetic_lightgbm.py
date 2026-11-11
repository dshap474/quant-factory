"""Run the synthetic regression fixture through tracked LightGBM training.

Usage::

    uv run python packages/platform/ml-engine/tests/manual/run_synthetic_lightgbm.py

The command writes one real run sidecar and inference artifact beneath the
system temp directory and verifies a trusted load-and-predict round trip.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor

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
# Paths and configuration
# --------------------------------------------------------------------------- #


REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
DATASET_PATH = (
    REPOSITORY_ROOT / "packages/platform/ml-engine/tests/fixtures/synthetic_regression.csv"
)
OUTPUT_ROOT = Path(tempfile.gettempdir()) / "ml-engine-synthetic-lightgbm"


def training_config() -> TrainingConfig:
    """Return one deterministic LightGBM regression configuration."""

    return TrainingConfig(
        feature_cols=("feature_trend", "feature_cycle", "feature_binary"),
        target_col="target",
        timestamp_col="timestamp",
        row_id_col="row_id",
        split=SplitConfig(
            kind="expanding",
            min_train_periods=48,
            eval_periods=8,
            step_periods=8,
            max_folds=4,
        ),
        candidates=(
            CandidateConfig(
                name="lightgbm",
                estimator=LGBMRegressor(
                    learning_rate=0.04,
                    max_depth=4,
                    min_child_samples=4,
                    n_estimators=400,
                    n_jobs=1,
                    verbosity=-1,
                ),
            ),
        ),
        metrics=(MetricConfig(name="rmse"),),
        selection=SelectionConfig(primary_metric="rmse", direction="minimize"),
        random_seed=17,
        final_refit=True,
    )


# --------------------------------------------------------------------------- #
# End-to-end run
# --------------------------------------------------------------------------- #


def main() -> int:
    """Train, save, reload, predict, and print a compact validation receipt."""

    frame = pd.read_csv(DATASET_PATH, parse_dates=["timestamp"])
    with TrainingRun(output_root=OUTPUT_ROOT, producer="tests/synthetic-lightgbm") as run:
        print(json.dumps({"run_id": run.run_id, "status": "running"}), flush=True)
        result = TrainingPipeline(training_config()).run(frame, progress=run.update)
        artifact_path = run.save(result)

    inference = InferencePipeline.load(artifact_path, trusted=True)
    prediction_frame = frame.tail(8).copy()
    prediction = inference.predict(prediction_frame)
    values = np.asarray(prediction.predictions, dtype=float)
    if len(values) != len(prediction_frame) or not np.isfinite(values).all():
        raise RuntimeError("trusted inference round trip returned invalid predictions")
    if prediction.row_ids.tolist() != prediction_frame["row_id"].tolist():
        raise RuntimeError("trusted inference round trip did not preserve row IDs")

    status = json.loads(run.sidecar_path.read_text(encoding="utf-8"))
    if status["status"] != "completed" or status["inference_ready"] is not True:
        raise RuntimeError("tracked run did not finish inference-ready")
    print(
        json.dumps(
            {
                "run_id": run.run_id,
                "status": status["status"],
                "completed_fits": status["completed_fits"],
                "total_fits": status["total_fits"],
                "artifact_path": str(artifact_path.relative_to(REPOSITORY_ROOT)),
                "prediction_rows": len(values),
                "prediction_min": float(values.min()),
                "prediction_max": float(values.max()),
            },
            sort_keys=True,
        )
    )
    return 0


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


if __name__ == "__main__":
    raise SystemExit(main())
