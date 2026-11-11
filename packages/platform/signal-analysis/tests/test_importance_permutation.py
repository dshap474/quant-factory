"""Verify held-out perturbation scores by exact outcomes and metamorphic checks.

Usage: ``uv run pytest packages/platform/signal-analysis/tests/test_importance_permutation.py``.
"""

# --------------------------------------------------------------------------- #
# Imports and explicit held-out fixtures
# --------------------------------------------------------------------------- #
from datetime import datetime, timezone

import numpy as np
import polars as pl
import pytest

from signal_analysis.importance.permutation import permutation_importance


def observations():
    time = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return pl.DataFrame(
        {
            "observation_id": ["a", "b"],
            "decision_time": [time] * 2,
            "features_available_at": [time] * 2,
            "target": [0.0, 1.0],
            "sample_weight": [1.0, 3.0],
            "x": [0.0, 1.0],
            "noise": [4.0, 4.0],
        }
    )


def accuracy(y, p, w):
    return float(np.average(y == p, weights=w))


def run(frame=None, **kwargs):
    arguments = dict(
        feature_columns=["x", "noise"],
        predict=lambda x: x[:, 0],
        scorer=accuracy,
        score_name="weighted_accuracy",
        greater_is_better=True,
        model_id="fitted",
        partition_id="test",
        heldout=True,
        evaluation_provenance="synthetic/fold",
        repetitions=8,
        seed=7,
        normalization="raw",
    )
    arguments.update(kwargs)
    return permutation_importance(observations() if frame is None else frame, **arguments)


# --------------------------------------------------------------------------- #
# Exact and metamorphic verification
# --------------------------------------------------------------------------- #


def test_exact_permutation_outcomes_weights_and_irrelevant_feature():
    result = run(predict=lambda x: np.zeros(len(x)))
    assert result.raw["baseline_score"].to_list() == [0.25] * 16
    assert result.raw["importance"].to_list() == [0.0] * 16
    result = run()
    for row in result.raw.iter_rows(named=True):
        if row["feature"] == "noise" or row["permutation_indices"] == [0, 1]:
            assert row["importance"] == 0
        else:
            assert row["permutation_indices"] == [1, 0]
            assert row["importance"] == 1
    assert result.raw.filter(pl.col("feature") == "x")["importance"].sum() > 0


def test_loss_direction_and_afml_accuracy_normalization():
    positive = run()
    negative = run(scorer=lambda y, p, w: -accuracy(y, p, w), greater_is_better=False)
    assert positive.raw["importance"].equals(negative.raw["importance"])
    book = run(normalization="afml_relative", score_optimum=1.0)
    for row in book.raw.iter_rows(named=True):
        if row["permuted_score"] == 1:
            assert row["importance"] is None
            assert row["status"] == "zero_normalization_denominator"
        else:
            assert row["importance"] == 1
    assert book.raw["raw_decrease"].equals(positive.raw["raw_decrease"])


def test_negative_log_loss_and_positive_loss_are_equivalent():
    def loss(y, p, w):
        prob = 0.1 + 0.8 * p
        return float(np.average(-(y * np.log(prob) + (1 - y) * np.log1p(-prob)), weights=w))

    first = run(scorer=loss, greater_is_better=False, normalization="afml_relative", score_optimum=0.0)
    second = run(scorer=lambda y, p, w: -loss(y, p, w), normalization="afml_relative", score_optimum=0.0)
    np.testing.assert_allclose(first.raw["importance"], second.raw["importance"], atol=1e-12, rtol=0)
    # Perfect probabilities .9 vs wrong .1: relative gain 1-log(.9)/log(.1).
    expected = 1 - np.log(0.9) / np.log(0.1)
    assert max(first.raw["importance"].to_list()) == pytest.approx(expected, abs=1e-12)


def test_detrimental_features_have_negative_importance():
    result = run(predict=lambda x: 1 - x[:, 0])
    assert min(result.raw["importance"].to_list()) == -1


def test_reproducibility_row_order_weight_scale_and_input_immutability():
    frame = observations()
    copy = frame.clone()
    first = run(frame)
    assert run(frame.reverse()).raw.equals(first.raw)
    assert run(frame).raw.equals(first.raw)
    scaled = run(frame.with_columns(pl.col("sample_weight") * 17))
    assert scaled.raw["importance"].equals(first.raw["importance"])
    assert frame.equals(copy)


def test_joint_groups_preserve_internal_relationship_and_callback_copies():
    frame = observations().with_columns(pl.col("x").alias("noise"))

    def predict(x):
        answer = x[:, 0] - x[:, 1]
        x[:] = -10
        return answer

    def scorer(y, p, w):
        answer = float(np.average(p * p, weights=w))
        y[:] = 999
        w[:] = 0
        return answer

    result = run(frame, predict=predict, scorer=scorer, feature_groups={"joint": ["x", "noise"]})
    assert result.raw["importance"].to_list() == [0.0] * 8
    assert result.raw["weight_sum"].to_list() == [4.0] * 8
    assert frame["target"].to_list() == [0, 1]


@pytest.mark.parametrize(
    "prediction,status", [(float("nan"), "baseline_invalid_prediction"), (float("inf"), "baseline_invalid_prediction")]
)
def test_invalid_predictions_retained(prediction, status):
    result = run(predict=lambda x: np.full(len(x), prediction))
    assert set(result.raw["status"]) == {status}
    assert result.raw["importance"].null_count() == 16


def test_zero_weights_undefined_scores_and_declared_optimum_violation():
    assert set(run(observations().with_columns(pl.lit(0.0).alias("sample_weight"))).raw["status"]) == {
        "baseline_zero_weight"
    }
    assert set(run(scorer=lambda *args: float("nan")).raw["status"]) == {"baseline_undefined_score"}
    assert "score_exceeds_optimum" in run(normalization="afml_relative", score_optimum=0.5).raw["status"]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"heldout": False},
        {"evaluation_provenance": ""},
        {"repetitions": 0},
        {"seed": True},
        {"seed": 2**64},
        {"normalization": "afml_relative"},
        {"feature_groups": {"bad": ["absent"]}},
        {"predict": lambda x: np.zeros(3)},
    ],
)
def test_invalid_operation_contracts_rejected(kwargs):
    with pytest.raises((ValueError, TypeError)):
        run(**kwargs)


def test_nonfinite_features_target_and_invalid_weights_rejected():
    for name, value in [("x", float("nan")), ("target", float("inf")), ("sample_weight", -1.0)]:
        with pytest.raises(ValueError):
            run(observations().with_columns(pl.lit(value).alias(name)))


def test_representable_extreme_score_moments_do_not_overflow():
    result = run(repetitions=10, scorer=lambda y, p, w: 1e308 if p[0] == 0 else 0.0)
    rows = result.raw.filter(pl.col("feature") == "x")
    # The population consists of zeros and 1e308. Use integer counts and the
    # Bernoulli closed form, independent of the production reduction algorithm.
    count = rows.filter(pl.col("importance") == 1e308).height
    fraction = count / 10
    expected_mean = fraction * 1e308
    expected_std = np.sqrt(fraction * (1 - fraction) * 10 / 9) * 1e308
    summary = result.summary.filter(pl.col("feature") == "x").row(0, named=True)
    assert summary["importance"] == pytest.approx(expected_mean, rel=1e-14)
    assert summary["repetition_sample_std"] == pytest.approx(expected_std, rel=1e-14)
    assert np.isfinite(summary["importance"])
    assert np.isfinite(summary["repetition_sample_std"])


@pytest.mark.parametrize("column", ["target", "sample_weight"])
def test_evaluation_metadata_cannot_accidentally_enter_predictor(column):
    with pytest.raises(ValueError, match="evaluation metadata"):
        run(feature_columns=[column])


def test_large_offset_repetition_dispersion_preserves_small_spread():
    result = run(repetitions=10, scorer=lambda y, p, w: 1e16 + 2 if p[0] == 0 else 1e16)
    # Raw decreases are exactly zero or two despite huge score offset.
    for value in result.raw["importance"]:
        assert value in {0.0, 2.0}
    assert max(result.raw["importance"]) == 2.0
