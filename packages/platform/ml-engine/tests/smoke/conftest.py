"""Provide deterministic dummy data and configs for full pipeline smoke tests.

Usage::

    uv run pytest packages/platform/ml-engine/tests/smoke -q
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports
# --------------------------------------------------------------------------- #

import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LinearRegression, LogisticRegression, Ridge

from ml_engine.training import (
    CandidateConfig,
    EnsembleConfig,
    MetricConfig,
    PreprocessingConfig,
    SelectionConfig,
    SplitConfig,
    TrainingConfig,
)


# --------------------------------------------------------------------------- #
# Daily dummy datasets
# --------------------------------------------------------------------------- #


@pytest.fixture
def daily_regression_frame() -> pd.DataFrame:
    """Return 200 daily rows with a seven-day label-information horizon."""

    rows = 200
    timestamps = pd.date_range("2020-01-01", periods=rows, freq="D", tz="UTC")
    trend = np.linspace(-2.0, 2.0, rows)
    cycle = np.sin(np.arange(rows) / 9.0)
    target = 4.0 * trend - 1.5 * cycle + np.cos(np.arange(rows) / 17.0)
    frame = pd.DataFrame(
        {
            "row_id": np.arange(10_000, 10_000 + rows, dtype=np.int64),
            "timestamp": timestamps,
            "target_end": timestamps + pd.Timedelta(days=7),
            "feature_trend": trend,
            "feature_cycle": cycle,
            "target": target,
        }
    )
    frame.loc[[11, 73, 149], "feature_cycle"] = np.nan
    return frame


@pytest.fixture
def daily_classification_frame() -> pd.DataFrame:
    """Return 180 daily binary rows for conservative fixed-gap splitting."""

    rows = 180
    timestamps = pd.date_range("2021-01-01", periods=rows, freq="D", tz="UTC")
    trend = np.linspace(-1.0, 1.0, rows)
    cycle = np.sin(np.arange(rows) / 5.0)
    target = (cycle + 0.35 * trend > 0.0).astype(np.int64)
    frame = pd.DataFrame(
        {
            "row_id": np.arange(20_000, 20_000 + rows, dtype=np.int64),
            "timestamp": timestamps,
            "feature_trend": trend,
            "feature_cycle": cycle,
            "target": target,
        }
    )
    frame.loc[[8, 91], "feature_trend"] = np.nan
    return frame


# --------------------------------------------------------------------------- #
# Public training configurations
# --------------------------------------------------------------------------- #


@pytest.fixture
def purged_regression_config() -> TrainingConfig:
    """Return an exact-purge walk-forward config with a simple ensemble."""

    return TrainingConfig(
        feature_cols=("feature_trend", "feature_cycle"),
        target_col="target",
        timestamp_col="timestamp",
        row_id_col="row_id",
        target_end_col="target_end",
        split=SplitConfig(
            kind="purged",
            min_train_periods=60,
            eval_periods=28,
            step_periods=28,
        ),
        preprocessing=PreprocessingConfig(impute_strategy="median", scale="standard"),
        candidates=(
            CandidateConfig(name="linear", estimator=LinearRegression()),
            CandidateConfig(name="ridge", estimator=Ridge(alpha=1.0)),
        ),
        metrics=(MetricConfig(name="rmse"),),
        selection=SelectionConfig(
            primary_metric="rmse",
            direction="minimize",
            min_coverage=1.0,
            min_folds=4,
        ),
        ensemble=EnsembleConfig(
            kind="equal_weight",
            base_models=("linear", "ridge"),
        ),
        random_seed=41,
    )


@pytest.fixture
def fixed_gap_classification_config() -> TrainingConfig:
    """Return an expanding config using a seven-day fallback gap."""

    return TrainingConfig(
        feature_cols=("feature_trend", "feature_cycle"),
        target_col="target",
        timestamp_col="timestamp",
        row_id_col="row_id",
        split=SplitConfig(
            kind="expanding",
            min_train_periods=50,
            eval_periods=20,
            step_periods=20,
            embargo_periods=7,
        ),
        preprocessing=PreprocessingConfig(impute_strategy="median", scale="standard"),
        candidates=(CandidateConfig(name="logistic", estimator=LogisticRegression(max_iter=500)),),
        metrics=(MetricConfig(name="log_loss"),),
        selection=SelectionConfig(
            primary_metric="log_loss",
            direction="minimize",
            min_coverage=1.0,
            min_folds=6,
        ),
        random_seed=43,
        task="binary_classification",
    )
