"""Hermetic valid-input packet and fault-record helpers for A3.

Purpose: provide one small public prepared-path fixture that A3 tests mutate
one fact at a time, without importing existing unit-test helpers.

USAGE:
    packet = valid_packet()
    prepared = prepare_execution_from_strategy_weights(**packet)
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import polars as pl
from backtest import BacktestConfig, prepare_execution_from_strategy_weights, run_backtest_from_strategy_weights

from execution import ImmediateMarketPolicy, InstrumentKey, InstrumentSpec
from strategies import ExecutionTiming, StrategyWeights

# --------------------------------------------------------------------------- #
# Frozen valid world
# --------------------------------------------------------------------------- #

UTC = timezone.utc
T0 = datetime(2024, 6, 1, 12, 0, tzinfo=UTC)
CAL = tuple(T0 + timedelta(minutes=index) for index in range(8))
KEY = InstrumentKey("BINANCE", "BTCUSDT")
WIRE = "BINANCE:BTCUSDT"


def valid_weights() -> StrategyWeights:
    return StrategyWeights(
        weights=pl.DataFrame({"timestamp": [T0], "BTC": [0.5], "CASH": [0.5]}),
        assets=["BTC"],
        execution=ExecutionTiming.next_bar(),
    )


def valid_bars(*, calendar: tuple[datetime, ...] = CAL) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "instrument": WIRE,
                "source_timestamp": timestamp,
                "ts_event": timestamp,
                "ts_init": timestamp,
                "open": 100.0,
                "high": 100.0,
                "low": 100.0,
                "close": 100.0,
                "volume": 1.0,
            }
            for timestamp in calendar
        ]
    )


def valid_references() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "decision_at": [T0],
            "instrument": [WIRE],
            "observed_at": [T0],
            "price": [100.0],
        }
    )


def valid_spec(**changes: object) -> InstrumentSpec:
    values: dict[str, object] = {
        "key": KEY,
        "product": "perpetual",
        "base_currency": "BTC",
        "quote_currency": "USDT",
        "settlement_currency": "USDT",
        "is_inverse": False,
        "multiplier": Decimal("1"),
        "price_increment": Decimal("0.01"),
        "quantity_increment": Decimal("0.001"),
        "min_quantity": Decimal("0.001"),
        "max_quantity": Decimal("1000000"),
        "min_notional": Decimal("0"),
        "max_notional": Decimal("1000000000"),
        "maker_fee_rate": Decimal("0"),
        "taker_fee_rate": Decimal("0"),
    }
    values.update(changes)
    return InstrumentSpec(**values)  # type: ignore[arg-type]


def valid_packet() -> dict[str, Any]:
    return {
        "weights": valid_weights(),
        "asset_instruments": {"BTC": KEY},
        "reference_prices": valid_references(),
        "bars": valid_bars(),
        "instrument_specs": (valid_spec(),),
        "execution_calendar": CAL,
        "reporting_times": (CAL[0], CAL[1], CAL[2]),
        "policy": ImmediateMarketPolicy(),
        "funding_settlements": None,
    }


def prepare(packet: dict[str, Any]):
    return prepare_execution_from_strategy_weights(**packet)


def run(packet: dict[str, Any], *, include_funding: bool = True):
    prepared = prepare(packet)
    return run_backtest_from_strategy_weights(
        weights=packet["weights"],
        data=None,
        config=BacktestConfig(
            initial_capital=100000,
            trade_cost_bps=0,
            include_funding=include_funding,
            frequency="1m",
            benchmark="BTCUSDT",
            metrics=[],
        ),
        prepared_execution=prepared,
    )


# --------------------------------------------------------------------------- #
# Evidence record
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class RejectionEvidence:
    scenario_id: str
    boundary: str
    exception: str
    message: str
    white_box: bool


def capture_rejection(
    scenario_id: str,
    boundary: str,
    operation: Callable[[], object],
    expected_exception: type[Exception] | tuple[type[Exception], ...],
    *message_fragments: str,
    white_box: bool = False,
) -> RejectionEvidence:
    try:
        operation()
    except expected_exception as exc:
        message = str(exc)
        for fragment in message_fragments:
            if fragment not in message:
                raise AssertionError(f"missing error fragment {fragment!r} in {message!r}") from exc
        return RejectionEvidence(
            scenario_id=scenario_id,
            boundary=boundary,
            exception=type(exc).__name__,
            message=message,
            white_box=white_box,
        )
    except Exception as exc:
        expected_name = (
            expected_exception.__name__
            if isinstance(expected_exception, type)
            else " or ".join(item.__name__ for item in expected_exception)
        )
        raise AssertionError(f"expected {expected_name}, got {type(exc).__name__}: {exc}") from exc
    raise AssertionError(f"{scenario_id} was unsafely accepted at {boundary}")
