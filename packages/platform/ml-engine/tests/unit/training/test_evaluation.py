"""Unit tests for generic, OOS-only training evaluation.

Usage::

    uv run pytest tests/unit/training/test_evaluation.py -q
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports and fixtures
# --------------------------------------------------------------------------- #
from dataclasses import dataclass

import numpy as np
import pandas as pd
import pytest

from ml_engine.training.evaluation import (
    evaluate_candidates,
    evaluate_oos,
)


@dataclass(frozen=True)
class _MetricConfig:
    name: str
    direction: str | None = None
    min_observations: int = 1
    scope: str | None = None
    base_metric: str | None = None
    statistic: str = "mean"
    kwargs: dict[str, object] | None = None


# --------------------------------------------------------------------------- #
# Regression and classification metrics
# --------------------------------------------------------------------------- #


def test_regression_metrics_use_only_oos_rows() -> None:
    rows = pd.DataFrame(
        {
            "row_id": [4, 5, 6],
            "prediction": [1.0, 3.0, 2.0],
            "target": [2.0, 2.0, 3.0],
            "fold": [0, 0, 1],
        }
    )

    result = evaluate_oos(rows, ("mae", "mse", "rmse"))

    assert result.metrics["mae"] == pytest.approx(1.0)
    assert result.metrics["mse"] == pytest.approx(1.0)
    assert result.metrics["rmse"] == pytest.approx(1.0)
    assert result.n_observations == 3
    assert result.n_folds == 2


def test_classification_metrics_and_auc_undefined_for_one_class() -> None:
    rows = pd.DataFrame(
        {
            "prediction": [0.1, 0.8, 0.9, 0.2],
            "target": [0, 1, 1, 0],
        }
    )
    result = evaluate_oos(rows, ("log_loss", "accuracy", "balanced_accuracy", "roc_auc"))

    assert result.metrics["log_loss"] is not None
    assert result.metrics["accuracy"] == pytest.approx(1.0)
    assert result.metrics["balanced_accuracy"] == pytest.approx(1.0)
    assert result.metrics["roc_auc"] == pytest.approx(1.0)

    undefined = evaluate_oos(
        pd.DataFrame({"prediction": [0.2, 0.3], "target": [1, 1]}),
        ("roc_auc",),
    )
    assert undefined.metrics["roc_auc"] is None
    assert not undefined.metric_results["roc_auc"].defined
    assert "two classes" in (undefined.metric_results["roc_auc"].reason or "")


def test_log_loss_sorts_binary_labels_independent_of_row_order() -> None:
    """One-dimensional probabilities always refer to the sorted positive class."""

    rows = pd.DataFrame(
        {
            "prediction": [0.9, 0.1, 0.8, 0.2],
            "target": [1, 0, 1, 0],
        }
    )

    result = evaluate_oos(rows, ("log_loss",))

    assert result.metrics["log_loss"] == pytest.approx(0.164252033486018)


# --------------------------------------------------------------------------- #
# Correlation and grouped stability summaries
# --------------------------------------------------------------------------- #


def test_correlations_remain_undefined_for_constant_inputs() -> None:
    rows = pd.DataFrame({"prediction": [1.0, 1.0, 1.0], "target": [1.0, 2.0, 3.0]})

    result = evaluate_oos(rows, ("pearson", "spearman"))

    assert result.metrics == {"pearson": None, "spearman": None}
    assert all(not detail.defined for detail in result.metric_results.values())


def test_period_and_fold_summaries_are_available_and_configurable() -> None:
    rows = pd.DataFrame(
        {
            "prediction": [1.0, 2.0, 4.0, 5.0],
            "target": [1.0, 3.0, 3.0, 5.0],
            "period": ["a", "a", "b", "b"],
            "fold": [0, 0, 1, 1],
        }
    )
    metrics = (
        _MetricConfig("pearson_per_period_mean", scope="period", base_metric="pearson"),
        _MetricConfig(
            "pearson_per_period_dispersion",
            scope="period",
            base_metric="pearson",
            statistic="dispersion",
        ),
        _MetricConfig(
            "per_period_hit_rate",
            scope="period",
            base_metric="pearson",
            statistic="hit_rate",
        ),
        _MetricConfig(
            "fold_observation_count",
            scope="fold",
            base_metric="pearson",
            statistic="observation_count",
        ),
    )

    result = evaluate_oos(rows, metrics)

    assert list(result.per_period["period"]) == ["a", "b"]
    assert list(result.per_fold["fold"]) == [0, 1]
    assert result.metrics["pearson_per_period_mean"] is not None
    assert result.metrics["pearson_per_period_dispersion"] == pytest.approx(0.0)
    assert result.metrics["per_period_hit_rate"] == pytest.approx(1.0)
    assert result.metrics["fold_observation_count"] == pytest.approx(4.0)


# --------------------------------------------------------------------------- #
# Config honoring and candidate grouping
# --------------------------------------------------------------------------- #


def test_metric_config_honors_direction_and_minimum_observations() -> None:
    rows = pd.DataFrame({"prediction": [1.0], "target": [2.0]})
    result = evaluate_oos(
        rows,
        (_MetricConfig("mae", direction="maximize", min_observations=2),),
    )

    detail = result.metric_results["mae"]
    assert result.metrics["mae"] is None
    assert detail.direction == "maximize"
    assert detail.n_observations == 1
    assert detail.min_observations == 2


def test_candidate_grouping_keeps_candidates_separate_and_rejects_finance_metrics() -> None:
    rows = pd.DataFrame(
        {
            "candidate": ["a", "a", "b", "b"],
            "prediction": [1.0, 2.0, 0.0, 1.0],
            "target": [1.0, 2.0, 1.0, 1.0],
        }
    )
    summaries = evaluate_candidates(rows, ("mae",))

    assert list(summaries) == ["a", "b"]
    assert summaries["a"].metrics["mae"] == pytest.approx(0.0)
    assert summaries["b"].metrics["mae"] == pytest.approx(0.5)
    with pytest.raises(ValueError, match="outside ml-engine"):
        evaluate_oos(rows.drop(columns="candidate"), ("sharpe",))


def test_nonfinite_rows_are_not_scored_as_zero() -> None:
    rows = pd.DataFrame({"prediction": [np.nan, np.nan], "target": [1.0, 2.0]})

    result = evaluate_oos(rows, ("mae",))

    assert result.metrics["mae"] is None
    assert result.coverage == pytest.approx(0.0)
