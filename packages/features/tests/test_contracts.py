"""Feature package contract tests for frame validity."""

from __future__ import annotations

from datetime import datetime

import polars as pl
import pytest
from features.publication.validation import validate_feature_frame


def test_validate_feature_frame_requires_timestamp() -> None:
    df = pl.DataFrame({"x": [1.0, 2.0]})
    with pytest.raises(ValueError, match="timestamp"):
        validate_feature_frame(df, require_asset=False, category="macro")


def test_validate_feature_frame_requires_asset_for_panel() -> None:
    df = pl.DataFrame(
        {
            "timestamp": [datetime(2024, 1, 1), datetime(2024, 1, 2)],
            "feature_a": [1.0, 2.0],
        }
    )
    with pytest.raises(ValueError, match="requires 'asset' column"):
        validate_feature_frame(
            df,
            require_asset=True,
            category="cross_sectional/example/panel",
        )


def test_validate_feature_frame_accepts_valid_dataset() -> None:
    df = pl.DataFrame(
        {
            "timestamp": [datetime(2024, 1, 1), datetime(2024, 1, 2)],
            "feature_a": [1.0, 2.0],
        }
    )
    result = validate_feature_frame(df, require_asset=False, category="macro")
    assert result.columns[0] == "timestamp"


def test_validate_feature_frame_rejects_asset_for_single_asset_dataset() -> None:
    df = pl.DataFrame(
        {
            "timestamp": [datetime(2024, 1, 1), datetime(2024, 1, 2)],
            "asset": ["BTC", "BTC"],
            "feature_a": [1.0, 2.0],
        }
    )
    with pytest.raises(ValueError, match="must not include 'asset'"):
        validate_feature_frame(df, require_asset=False, category="example/category")


def test_validate_feature_frame_rejects_non_numeric_feature_columns() -> None:
    df = pl.DataFrame(
        {
            "timestamp": [datetime(2024, 1, 1), datetime(2024, 1, 2)],
            "feature_a": ["x", "y"],
        }
    )
    with pytest.raises(ValueError, match="must be numeric"):
        validate_feature_frame(df, require_asset=False, category="macro")


def test_validate_feature_frame_admits_only_declared_string_label_columns() -> None:
    df = pl.DataFrame(
        {
            "timestamp": [datetime(2024, 1, 1), datetime(2024, 1, 2)],
            "feature_a": [1.0, 2.0],
            "return_basis": ["price", "price"],
            "other": ["x", "y"],
        }
    )
    with pytest.raises(ValueError, match="'other'.*must be numeric"):
        validate_feature_frame(df, require_asset=False, category="macro", label_columns=("return_basis",))
    result = validate_feature_frame(
        df.drop("other"), require_asset=False, category="macro", label_columns=("return_basis",)
    )
    assert result["return_basis"].to_list() == ["price", "price"]


def test_validate_feature_frame_rejects_missing_or_non_string_label_columns() -> None:
    df = pl.DataFrame({"timestamp": [datetime(2024, 1, 1)], "feature_a": [1.0]})
    with pytest.raises(ValueError, match="missing"):
        validate_feature_frame(df, require_asset=False, category="macro", label_columns=("return_basis",))
    with pytest.raises(ValueError, match="must be String"):
        validate_feature_frame(df, require_asset=False, category="macro", label_columns=("feature_a",))
