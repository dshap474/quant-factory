"""Tests for chronology-safe ensemble mechanics.

Usage::

    python -m pytest tests/unit/training/test_ensemble.py
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports and fixtures
# --------------------------------------------------------------------------- #
import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import Ridge

from ml_engine.training import EnsembleConfig
from ml_engine.training.ensemble import EnsembleError, fit_ensemble


def _predictions(n: int = 12) -> pd.DataFrame:
    x = np.arange(float(n))
    return pd.DataFrame(
        {
            "row_id": np.tile(np.arange(n), 2),
            "candidate": np.repeat(["left", "right"], n),
            "prediction": np.concatenate([x, n - x]),
            "target": np.tile(x, 2),
            "timestamp": np.tile(pd.date_range("2024-01-01", periods=n, freq="D"), 2),
        }
    )


def _config(kind: str, **kwargs: object) -> EnsembleConfig:
    return EnsembleConfig(kind=kind, **kwargs)


# --------------------------------------------------------------------------- #
# Weighted policies
# --------------------------------------------------------------------------- #


def test_none_does_not_construct_a_combiner() -> None:
    result = fit_ensemble(_config("none"), _predictions())

    assert result.combiner is None
    assert result.oos_predictions is None


def test_equal_and_fixed_weights_are_row_aligned() -> None:
    predictions = _predictions(3)
    equal = fit_ensemble(_config("equal_weight"), predictions)
    fixed = fit_ensemble(_config("fixed_weight", weights={"left": 3, "right": 1}), predictions)

    np.testing.assert_allclose(equal.oos_predictions, [1.5, 1.5, 1.5])
    np.testing.assert_allclose(fixed.oos_predictions, [0.75, 1.25, 1.75])
    np.testing.assert_allclose(fixed.weights, [0.75, 0.25])


def test_long_oos_table_is_pivoted_without_cross_candidate_misalignment() -> None:
    frame = pd.DataFrame(
        {
            "row_id": [1, 1, 2, 2],
            "timestamp": pd.to_datetime(["2024-01-01", "2024-01-01", "2024-01-02", "2024-01-02"]),
            "candidate": ["a", "b", "a", "b"],
            "prediction": [1.0, 3.0, 2.0, 4.0],
            "target": [2.0, 2.0, 3.0, 3.0],
        }
    )
    result = fit_ensemble(_config("equal_weight"), frame)

    np.testing.assert_allclose(result.oos_predictions, [2.0, 3.0])
    np.testing.assert_array_equal(result.row_ids, [1, 2])


def test_allow_missing_weighted_rows_renormalize_observed_models() -> None:
    result = fit_ensemble(
        _config("equal_weight", allow_missing=True),
        pd.DataFrame(
            {
                "row_id": [0, 1, 0, 1],
                "candidate": ["left", "left", "right", "right"],
                "prediction": [1.0, np.nan, 3.0, 5.0],
            }
        ),
    )

    np.testing.assert_allclose(result.oos_predictions, [2.0, 5.0])


# --------------------------------------------------------------------------- #
# Learned policies and leakage guards
# --------------------------------------------------------------------------- #


def test_optimized_weights_report_only_meta_oos_rows() -> None:
    n = 12
    timestamps = pd.date_range("2024-01-01", periods=n, freq="D")
    result = fit_ensemble(
        _config("optimized_weight", meta_splits=3),
        _predictions(n),
    )

    assert result.meta_folds
    assert result.meta_oos_predictions is not None
    assert result.oos_predictions is not None
    assert np.isnan(result.oos_predictions).sum() > 0
    for fold in result.meta_folds:
        assert set(fold.train_indices).isdisjoint(fold.evaluation_indices)
        assert max(timestamps[list(fold.train_indices)]) < min(
            timestamps[list(fold.evaluation_indices)]
        )


def test_stacking_fits_final_model_after_meta_cross_fit() -> None:
    n = 12
    result = fit_ensemble(
        _config("stacking", meta_splits=3, combiner=Ridge(alpha=1.0)),
        _predictions(n),
    )

    assert result.combiner is not None
    assert result.meta_oos_predictions is not None
    assert len(result.meta_oos_predictions) < n
    assert result.meta_evaluation_indices == tuple(
        np.flatnonzero(np.isfinite(result.oos_predictions))
    )


def test_learned_ensemble_fails_closed_without_history_or_uses_explicit_none_fallback() -> None:
    with pytest.raises(EnsembleError):
        fit_ensemble(
            _config("optimized_weight", meta_splits=3),
            _predictions(3),
        )

    fallback = fit_ensemble(
        _config("stacking", meta_splits=3, fallback="none"),
        _predictions(3),
    )
    assert fallback.kind == "none"
    assert fallback.fallback_used is True


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
