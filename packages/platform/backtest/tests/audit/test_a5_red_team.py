"""A5 adversarial public-boundary regressions.

Purpose: freeze red-team findings before production fixes and prove the public
strategy-weights execution seam cannot trade stale or mismatched targets.

USAGE:
    uv run pytest -q packages/platform/backtest/tests/audit/test_a5_red_team.py
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import polars as pl
from backtest import BacktestConfig, run_backtest_from_strategy_weights
from backtest.errors import BacktestContractError, BacktestEngineExecutionError
from backtest.preparation import strategy_weights_fingerprint

from execution import TimeWeightedTakerPolicy
from strategies import ExecutionTiming, StrategyWeights

from .a3_support import T0, capture_rejection, prepare, run, valid_packet, valid_spec

# --------------------------------------------------------------------------- #
# A5-C01: strategy/prepared provenance mismatch
# --------------------------------------------------------------------------- #


def test_a5_prepared_execution_rejects_different_strategy_weights() -> None:
    prepared = prepare(valid_packet())
    opposite = StrategyWeights(
        weights=pl.DataFrame({"timestamp": [T0], "BTC": [-0.5], "CASH": [1.5]}),
        assets=["BTC"],
        execution=ExecutionTiming.next_bar(),
    )
    capture_rejection(
        "A5-C01",
        "public strategy-weights connector",
        lambda: run_backtest_from_strategy_weights(
            weights=opposite,
            data=None,
            config=BacktestConfig(
                initial_capital=100000,
                trade_cost_bps=0,
                include_funding=True,
                frequency="1m",
                benchmark="BTCUSDT",
                metrics=[],
            ),
            prepared_execution=prepared,
        ),
        BacktestContractError,
        "strategy weights do not match prepared_execution provenance",
    )


def test_a5_weights_fingerprint_ignores_non_ordering_representation() -> None:
    first = StrategyWeights(
        weights=pl.DataFrame(
            {
                "timestamp": [T0],
                "BTC": [0.4],
                "ETH": [-0.2],
                "CASH": [0.8],
            }
        ),
        assets=["BTC", "ETH"],
        execution=ExecutionTiming.next_bar(),
        metadata={"run": "first"},
    )
    second = StrategyWeights(
        weights=pl.DataFrame(
            {
                "timestamp": [T0],
                "ETH": [Decimal("-0.20")],
                "CASH": [Decimal("0.800")],
                "BTC": [Decimal("0.4000")],
            }
        ),
        assets=["ETH", "BTC"],
        execution=ExecutionTiming.next_bar(),
        metadata={"run": "second", "ignored": True},
    )
    assert strategy_weights_fingerprint(first) == strategy_weights_fingerprint(second)


def test_a5_weights_fingerprint_covers_every_ordering_fact() -> None:
    base = StrategyWeights(
        weights=pl.DataFrame({"timestamp": [T0], "BTC": [0.5], "CASH": [0.5]}),
        assets=["BTC"],
        execution=ExecutionTiming.next_bar(),
    )
    variants = (
        StrategyWeights(
            weights=pl.DataFrame({"timestamp": [T0], "BTC": [-0.5], "CASH": [1.5]}),
            assets=["BTC"],
            execution=ExecutionTiming.next_bar(),
        ),
        StrategyWeights(
            weights=pl.DataFrame({"timestamp": [T0 + timedelta(minutes=1)], "BTC": [0.5], "CASH": [0.5]}),
            assets=["BTC"],
            execution=ExecutionTiming.next_bar(),
        ),
        StrategyWeights(
            weights=pl.DataFrame({"timestamp": [T0], "ETH": [0.5], "CASH": [0.5]}),
            assets=["ETH"],
            execution=ExecutionTiming.next_bar(),
        ),
        StrategyWeights(
            weights=pl.DataFrame({"timestamp": [T0], "BTC": [0.5], "RESERVE": [0.5]}),
            assets=["BTC"],
            cash_col="RESERVE",
            execution=ExecutionTiming.next_bar(),
        ),
        StrategyWeights(
            weights=pl.DataFrame({"timestamp": [T0], "BTC": [0.5], "CASH": [0.5]}),
            assets=["BTC"],
            execution=ExecutionTiming.lagged(2),
        ),
    )
    baseline = strategy_weights_fingerprint(base)
    assert all(strategy_weights_fingerprint(variant) != baseline for variant in variants)


# --------------------------------------------------------------------------- #
# A5-C02: instrument symbol/currency identity
# --------------------------------------------------------------------------- #


def test_a5_instrument_rejects_symbol_base_currency_mismatch() -> None:
    capture_rejection(
        "A5-C02",
        "engine-neutral instrument construction",
        lambda: valid_spec(base_currency="ETH"),
        ValueError,
        "symbol must equal base_currency + quote_currency",
    )


# --------------------------------------------------------------------------- #
# A5-H03: per-slice TWAP trade limits
# --------------------------------------------------------------------------- #


def test_a5_twap_rejects_child_below_minimum_notional() -> None:
    packet = valid_packet()
    packet["instrument_specs"] = (
        valid_spec(
            quantity_increment=Decimal("1"),
            min_quantity=Decimal("1"),
            min_notional=Decimal("300"),
        ),
    )
    packet["weights"] = StrategyWeights(
        weights=pl.DataFrame({"timestamp": [T0], "BTC": [0.006], "CASH": [0.994]}),
        assets=["BTC"],
        execution=ExecutionTiming.next_bar(),
    )
    packet["policy"] = TimeWeightedTakerPolicy(3, timedelta(minutes=1))
    capture_rejection(
        "A5-H03",
        "public TWAP runtime",
        lambda: run(packet),
        (BacktestContractError, BacktestEngineExecutionError),
        "below min_notional",
    )
