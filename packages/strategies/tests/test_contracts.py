from __future__ import annotations

from datetime import datetime

import polars as pl
import pytest
from strategies.contracts import execution_timing_from_mode, validate_strategy_weights_contract
from strategies.weights import ExecutionMode, ExecutionTiming, StrategyWeights


def test_validate_strategy_weights_contract_accepts_directional() -> None:
    weights = StrategyWeights(
        weights=pl.DataFrame(
            {
                "timestamp": [
                    datetime(2024, 1, 1),
                    datetime(2024, 1, 2),
                ],
                "BTC": [0.5, 0.25],
                "CASH": [0.5, 0.75],
            }
        ),
        assets=["BTC"],
    )

    validate_strategy_weights_contract(weights, output_type="directional")


def test_validate_strategy_weights_contract_rejects_non_neutral_market_neutral() -> None:
    weights = StrategyWeights(
        weights=pl.DataFrame(
            {
                "timestamp": [
                    datetime(2024, 1, 1),
                    datetime(2024, 1, 2),
                ],
                "BTC": [0.6, 0.6],
                "ETH": [-0.2, -0.1],
                "CASH": [0.6, 0.5],
            }
        ),
        assets=["BTC", "ETH"],
    )

    with pytest.raises(ValueError, match="Market-neutral strategies"):
        validate_strategy_weights_contract(weights, output_type="market_neutral")


def test_validate_strategy_weights_contract_accepts_lagged_execution() -> None:
    weights = StrategyWeights(
        weights=pl.DataFrame(
            {
                "timestamp": [datetime(2024, 1, 1)],
                "BTC": [0.25],
                "CASH": [0.75],
            }
        ),
        assets=["BTC"],
        execution=ExecutionTiming.lagged(2),
    )

    validate_strategy_weights_contract(weights, output_type="directional")


def test_execution_timing_from_mode_maps_shared_modes() -> None:
    assert execution_timing_from_mode("same_bar").mode == ExecutionMode.SAME_BAR
    assert execution_timing_from_mode("next_bar").mode == ExecutionMode.NEXT_BAR

    with pytest.raises(ValueError, match="execution_mode must be one of"):
        execution_timing_from_mode("lag_bars")
