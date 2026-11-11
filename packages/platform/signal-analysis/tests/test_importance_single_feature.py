"""Verify SFI uses aligned declared one-feature OOS fits and weighted scores.

Usage: ``uv run pytest packages/platform/signal-analysis/tests/test_importance_single_feature.py``.
"""

# --------------------------------------------------------------------------- #
# Imports and declared independent prediction fixtures
# --------------------------------------------------------------------------- #
from datetime import datetime, timezone

import numpy as np
import polars as pl
import pytest

from signal_analysis.importance.single_feature import single_feature_importance


def fixture():
    time = datetime(2024, 1, 1, tzinfo=timezone.utc)
    rows, models = [], []
    # x has weighted accuracies .25 and .75; y scores .75 and 1.
    for partition, feature, prediction in [
        ("a", "x", [0.0, 0.0]),
        ("b", "x", [1.0, 1.0]),
        ("a", "y", [1.0, 1.0]),
        ("b", "y", [0.0, 1.0]),
    ]:
        model = feature + partition
        models.append((partition, model, [feature]))
        for obs, target, pred, weight in zip(["1", "2"], [0.0, 1.0], prediction, [1.0, 3.0], strict=True):
            rows.append((feature, partition, model, obs, time, target, pred, weight))
    return pl.DataFrame(
        rows,
        schema={
            "feature": pl.String,
            "partition_id": pl.String,
            "model_id": pl.String,
            "observation_id": pl.String,
            "decision_time": pl.Datetime("us", "UTC"),
            "target": pl.Float64,
            "prediction": pl.Float64,
            "sample_weight": pl.Float64,
        },
        orient="row",
    ), pl.DataFrame(
        models,
        schema={"partition_id": pl.String, "model_id": pl.String, "feature_columns": pl.List(pl.String)},
        orient="row",
    )


def accuracy(y, p, w):
    return float(np.average(y == p, weights=w))


def run(predictions=None, models=None, **kwargs):
    records, declarations = fixture()
    arguments = dict(
        scorer=accuracy,
        score_name="weighted_accuracy",
        greater_is_better=True,
        heldout=True,
        evaluation_provenance="synthetic/oos",
    )
    arguments.update(kwargs)
    return single_feature_importance(
        records if predictions is None else predictions,
        model_features=declarations if models is None else models,
        **arguments,
    )


# --------------------------------------------------------------------------- #
# Public score, alignment and undefined-result verification
# --------------------------------------------------------------------------- #


def test_hand_calculated_weighted_fold_scores_and_population_dispersion():
    result = run()
    assert result.raw["importance"].to_list() == [0.25, 0.75, 0.75, 1.0]
    x = result.summary.filter(pl.col("feature") == "x").row(0, named=True)
    assert x["importance"] == 0.5
    assert x["fold_population_std"] == 0.25
    assert x["scaled_fold_dispersion"] == pytest.approx(0.25 / np.sqrt(2), abs=1e-12)
    assert result.predictions.equals(fixture()[0])


def test_order_and_weight_scale_invariants_and_loss_direction():
    records, models = fixture()
    first = run()
    assert run(records.reverse(), models.reverse()).raw.equals(first.raw)
    scaled = run(records.with_columns(pl.col("sample_weight") * 11))
    assert scaled.raw["importance"].equals(first.raw["importance"])
    loss = run(scorer=lambda y, p, w: 1 - accuracy(y, p, w), greater_is_better=False)
    assert loss.raw["importance"].to_list() == [0.75, 0.25, 0.25, 0.0]
    assert loss.summary["greater_is_better"].to_list() == [False, False]


@pytest.mark.parametrize("column,value", [("target", 5.0), ("sample_weight", 9.0), ("observation_id", "other")])
def test_misaligned_feature_evaluation_rejected(column, value):
    records, _ = fixture()
    records = records.with_columns(
        pl.when((pl.col("feature") == "y") & (pl.col("partition_id") == "a") & (pl.col("observation_id") == "1"))
        .then(pl.lit(value))
        .otherwise(pl.col(column))
        .alias(column)
    )
    with pytest.raises(ValueError, match="exact evaluation"):
        run(records)


def test_multifeature_and_missing_model_declarations_rejected():
    records, models = fixture()
    with pytest.raises(ValueError, match="exactly one"):
        run(records, models.with_columns(pl.lit(["x", "y"]).alias("feature_columns")))
    with pytest.raises(ValueError, match="declared single"):
        run(records, models.head(3))
    with pytest.raises(ValueError, match="one model"):
        run(
            records.with_columns(
                pl.when(pl.col("observation_id") == "1")
                .then(pl.lit("other"))
                .otherwise(pl.col("model_id"))
                .alias("model_id")
            )
        )


def test_duplicate_records_missing_partitions_and_invalid_provenance_rejected():
    records, _ = fixture()
    with pytest.raises(ValueError, match="unique"):
        run(pl.concat([records, records.head(1)]))
    with pytest.raises(ValueError, match="every partition"):
        run(records.filter(~((pl.col("partition_id") == "b") & (pl.col("feature") == "x"))))
    with pytest.raises(ValueError):
        run(heldout=False)


def test_invalid_prediction_retains_whole_fold_and_reports_partial_summary():
    records, _ = fixture()
    records = records.with_columns(
        pl.when((pl.col("feature") == "x") & (pl.col("partition_id") == "a"))
        .then(pl.lit(float("nan")))
        .otherwise(pl.col("prediction"))
        .alias("prediction")
    )
    result = run(records)
    assert result.raw["importance"].to_list() == [None, 0.75, 0.75, 1.0]
    x = result.summary.filter(pl.col("feature") == "x").row(0, named=True)
    assert x["n_valid"] == 1 and x["n_partitions"] == 2 and x["status"] == "partial"
    assert result.predictions.height == records.height


def test_extreme_finite_fold_scores_have_finite_moments():
    result = run(scorer=lambda y, p, w: 1e308 if p[0] == 1 else 0.0)
    assert result.summary["importance"].to_list() == [5e307, 5e307]
    assert result.summary["fold_population_std"].to_list() == [5e307, 5e307]


@pytest.mark.parametrize(
    "scores,expected_mean,expected_std",
    [
        ([1e16, 1e16 + 2], 1e16, 1.0),
        ([1e308, 1.0, -1e308], 1 / 3, np.sqrt(2 / 3) * 1e308),
        ([1e308, 1e308, -1e308, -1e308, 1e-300], 2e-301, np.sqrt(0.8) * 1e308),
    ],
)
def test_cancellation_and_offset_score_moments_against_exact_structure(scores, expected_mean, expected_std):
    # Scores are returned directly from externally supplied scalar predictions.
    # Pair midpoint/spread, exact cancellation and equal signed masses give
    # these references without reusing production reduction operations.
    records, _ = fixture()
    rows = []
    models = []
    for index, score in enumerate(scores):
        rows.append(
            records.head(1).with_columns(
                pl.lit(str(index)).alias("partition_id"),
                pl.lit(str(index)).alias("model_id"),
                pl.lit(score).alias("prediction"),
            )
        )
        models.append((str(index), str(index), ["x"]))
    declarations = pl.DataFrame(
        models,
        schema={"partition_id": pl.String, "model_id": pl.String, "feature_columns": pl.List(pl.String)},
        orient="row",
    )
    result = run(pl.concat(rows), declarations, scorer=lambda y, p, w: float(p[0]))
    row = result.summary.row(0, named=True)
    assert row["importance"] == pytest.approx(expected_mean, rel=1e-14, abs=0)
    assert row["fold_population_std"] == pytest.approx(expected_std, rel=1e-14, abs=0)
