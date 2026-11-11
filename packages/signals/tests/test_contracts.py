from __future__ import annotations

from datetime import datetime

import polars as pl
import pytest

from signals.contracts import validate_prediction_frame


def test_validate_prediction_frame_accepts_single_asset() -> None:
    df = pl.DataFrame(
        {
            "timestamp": [
                datetime(2024, 1, 1),
                datetime(2024, 1, 2),
                datetime(2024, 1, 3),
            ],
            "prediction": [0.1, 0.2, 0.3],
        }
    )

    validate_prediction_frame(df)


def test_validate_prediction_frame_rejects_duplicate_timestamp_keys() -> None:
    df = pl.DataFrame(
        {
            "timestamp": [datetime(2024, 1, 1), datetime(2024, 1, 1)],
            "prediction": [0.1, 0.2],
        }
    )

    with pytest.raises(ValueError, match="duplicate"):
        validate_prediction_frame(df)


def test_validate_prediction_frame_accepts_cross_sectional_keys() -> None:
    df = pl.DataFrame(
        {
            "timestamp": [datetime(2024, 1, 1), datetime(2024, 1, 1)],
            "asset": ["BTC", "ETH"],
            "prediction": [0.1, -0.2],
        }
    )

    validate_prediction_frame(df)
