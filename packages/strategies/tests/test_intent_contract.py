"""Independent acceptance for canonical hold and signed reduce-only decisions.

USAGE: uv run pytest packages/strategies/tests/test_intent_contract.py -q
Oracle: a target is a percentage; a hold preserves quantity; a reduce-only
limit cannot reopen or enlarge a position. Artifact round-trips preserve
intent rather than substituting realized holdings. No implementation-derived
expected numeric outputs are used here.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Canonical artifact fixtures and lossless persistence
# --------------------------------------------------------------------------- #
from datetime import UTC, datetime, timedelta

import polars as pl
import pytest
from strategies.weights import ExecutionTiming, StrategyWeights

T = datetime(2025, 1, 1, tzinfo=UTC)


def artifact():
    return StrategyWeights(
        weights=pl.DataFrame(
            {
                "timestamp": [T, T + timedelta(days=1)],
                "LONG": [1.2, None],
                "SHORT": [-0.4, 0.0],
                "CASH": [0.2, None],
            }
        ),
        assets=["LONG", "SHORT"],
        execution=ExecutionTiming.lagged(2),
        metadata={
            "strategy_id": "independent_fixture",
            "capital": 1000.0,
            "assumptions": {"cost_bps": 5, "quote_currency": "USD"},
        },
        quantity_limits=pl.DataFrame(
            {
                "timestamp": [T, T + timedelta(days=1)],
                "LONG": [None, 8.0],
                "SHORT": [-3.0, 0.0],
            }
        ),
    )


def test_save_load_preserves_intent_timing_identity_and_limits(tmp_path):
    decision = artifact()
    path = tmp_path / "intent.parquet"
    decision.save(path)
    loaded = StrategyWeights.from_parquet(path)
    assert loaded.weights.equals(decision.weights)
    assert loaded.quantity_limits.equals(decision.quantity_limits)
    assert loaded.assets == ["LONG", "SHORT"]
    assert loaded.execution == ExecutionTiming.lagged(2)
    assert loaded.metadata == decision.metadata
    loaded.validate()


def test_plain_legacy_parquet_remains_readable(tmp_path):
    path = tmp_path / "legacy.parquet"
    frame = pl.DataFrame({"timestamp": [T], "X": [-0.5], "CASH": [1.5]})
    frame.write_parquet(path)
    loaded = StrategyWeights.from_parquet(path)
    assert loaded.assets == ["X"]
    assert loaded.execution == ExecutionTiming.next_bar()
    assert loaded.quantity_limits is None
    assert loaded.weights.equals(frame)


@pytest.mark.parametrize("limit", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_limit_cannot_be_a_missing_instruction(limit):
    with pytest.raises(ValueError):
        decision = StrategyWeights(
            weights=pl.DataFrame({"timestamp": [T], "X": [0.2], "CASH": [0.8]}),
            assets=["X"],
            quantity_limits=pl.DataFrame({"timestamp": [T], "X": [limit]}),
        )
        decision.validate()


def test_quantity_limits_must_match_decision_times():
    with pytest.raises(ValueError):
        decision = StrategyWeights(
            weights=pl.DataFrame({"timestamp": [T], "X": [0.2], "CASH": [0.8]}),
            assets=["X"],
            quantity_limits=pl.DataFrame({"timestamp": [T + timedelta(days=1)], "X": [1.0]}),
        )
        decision.validate()


def test_partial_hold_row_cannot_claim_known_cash_residual():
    with pytest.raises(ValueError):
        decision = StrategyWeights(
            weights=pl.DataFrame({"timestamp": [T], "X": [None], "CASH": [1.0]}, schema_overrides={"X": pl.Float64}),
            assets=["X"],
        )
        decision.validate()


def test_complete_targets_still_require_unit_weight_sum():
    with pytest.raises(ValueError):
        decision = StrategyWeights(
            weights=pl.DataFrame({"timestamp": [T], "X": [1.2], "CASH": [0.2]}),
            assets=["X"],
        )
        decision.validate()
