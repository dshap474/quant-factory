"""Small explicit tables for testing the public signal-analysis contracts.

Usage: pytest injects panel, targets, windows, and prices into package tests.
"""

from datetime import datetime, timedelta, timezone

import polars as pl
import pytest

# --------------------------------------------------------------------------- #
# Independent input fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture
def panel() -> pl.DataFrame:
    t = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return pl.DataFrame(
        {
            "decision_time": [t] * 4,
            "asset": ["A", "B", "C", "D"],
            "signal_available_at": [t] * 4,
            "signal": [1.0, 2.0, 3.0, 4.0],
            "eligible": [True] * 4,
        }
    )


@pytest.fixture
def targets(panel: pl.DataFrame) -> pl.DataFrame:
    t = panel["decision_time"][0]
    return pl.DataFrame(
        {
            "decision_time": [t] * 4,
            "asset": ["A", "B", "C", "D"],
            "target_id": ["next"] * 4,
            "target_start": [t + timedelta(days=1)] * 4,
            "target_end": [t + timedelta(days=2)] * 4,
            "target": [0.1, 0.2, 0.3, 0.4],
            "target_status": ["ok"] * 4,
            "target_kind": ["price_return"] * 4,
            "return_type": ["simple"] * 4,
        }
    )


@pytest.fixture
def windows(targets: pl.DataFrame) -> pl.DataFrame:
    return targets.select("decision_time", "asset", "target_id", "target_start", "target_end")


@pytest.fixture
def prices(targets: pl.DataFrame) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "asset": ["A", "B", "C", "D"] * 2,
            "timestamp": [targets["target_start"][0]] * 4 + [targets["target_end"][0]] * 4,
            "price": [100.0] * 4 + [110.0, 120.0, 130.0, 140.0],
        }
    )
