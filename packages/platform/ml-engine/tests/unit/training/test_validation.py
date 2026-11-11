"""Boundary tests for training-frame validation.

Usage::

    pytest tests/unit/training/test_validation.py
"""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from ml_engine.training.config import TrainingConfig
from ml_engine.training.validation import validate_training_data

# --------------------------------------------------------------------------- #
# Fixtures and helpers
# --------------------------------------------------------------------------- #


def _config(**overrides: object) -> TrainingConfig:
    """Create the smallest config-shaped instance needed by validation."""

    values = {
        "feature_cols": ("feature_a", "feature_b"),
        "target_col": "target",
        "timestamp_col": "timestamp",
        "row_id_col": "row_id",
        "entity_col": None,
        "period_col": None,
        "target_end_col": None,
        "training_cutoff": None,
        "preprocessing": SimpleNamespace(),
    }
    values.update(overrides)
    config = object.__new__(TrainingConfig)
    for name, value in values.items():
        object.__setattr__(config, name, value)
    return config


def _frame() -> pd.DataFrame:
    """Return deliberately unsorted input with tied timestamps."""

    return pd.DataFrame(
        {
            "row_id": ["r2", "r1", "r3"],
            "timestamp": ["2024-01-02", "2024-01-01", "2024-01-01"],
            "feature_a": [2.0, 1.0, 3.0],
            "feature_b": [20.0, 10.0, 30.0],
            "target": [0.2, 0.1, None],
        }
    )


# --------------------------------------------------------------------------- #
# Validation behavior
# --------------------------------------------------------------------------- #


def test_normalizes_utc_and_stably_sorts_without_mutating_input() -> None:
    """Timestamps are UTC and ties retain incoming row order."""

    source = _frame()
    prepared = validate_training_data(source, _config())

    assert str(prepared.frame["timestamp"].dtype).endswith(", UTC]")
    assert prepared.frame["row_id"].tolist() == ["r1", "r3", "r2"]
    assert prepared.frame.index.tolist() == [0, 1, 2]
    assert source["timestamp"].tolist() == ["2024-01-02", "2024-01-01", "2024-01-01"]
    assert prepared.frame[prepared.target_col].notna().tolist() == [True, False, True]


def test_assigns_deterministic_internal_row_ids_when_column_is_omitted() -> None:
    """An omitted row ID is assigned before sorting, not from sorted position."""

    source = _frame().drop(columns="row_id")
    prepared = validate_training_data(source, _config(row_id_col=None))

    assert prepared.row_id_col.startswith("__ml_engine_row_id__")
    assert prepared.frame[prepared.row_id_col].tolist() == [1, 2, 0]


@pytest.mark.parametrize(
    ("mutator", "message"),
    (
        (lambda frame: frame.assign(row_id=["r1", "r1", "r3"]), "unique"),
        (lambda frame: frame.assign(feature_a=[None, None, None]), "entirely null"),
        (lambda frame: frame.assign(feature_a=["bad", "dtype", "values"]), "numeric"),
        (lambda frame: frame.assign(target=[None, None, None]), "entirely null"),
    ),
)
def test_rejects_invalid_schema_and_values(mutator, message: str) -> None:
    """Invalid identity, dtypes, and all-null columns fail closed."""

    with pytest.raises((TypeError, ValueError), match=message):
        validate_training_data(mutator(_frame()), _config())


def test_rejects_missing_required_columns() -> None:
    """Required feature and target columns cannot be silently invented."""

    with pytest.raises(ValueError, match="missing required"):
        validate_training_data(_frame().drop(columns="feature_b"), _config())


def test_cutoff_excludes_future_rows_and_keeps_unknown_targets() -> None:
    """Rows after a cutoff are outside the training universe only."""

    prepared = validate_training_data(
        _frame(),
        _config(training_cutoff="2024-01-01T23:59:59Z"),
    )

    assert prepared.frame["row_id"].tolist() == ["r1", "r3"]
    assert prepared.frame[prepared.target_col].isna().tolist() == [False, True]
    assert prepared.training_cutoff == pd.Timestamp("2024-01-01T23:59:59Z")


def test_entity_identity_is_checked_when_configured() -> None:
    """Configured entities participate in duplicate identity validation."""

    source = _frame().assign(entity="asset")
    source.loc[1, "row_id"] = source.loc[0, "row_id"]
    with pytest.raises(ValueError, match="unique"):
        validate_training_data(source, _config(entity_col="entity"))
