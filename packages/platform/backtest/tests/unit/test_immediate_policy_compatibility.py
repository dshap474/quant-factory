"""Immediate-policy compatibility vs legacy weight replay.

Purpose: prove the opt-in prepared ImmediateMarketPolicy path produces the same
economic entry cost and terminal equity as the legacy
``run_backtest_from_strategy_weights(weights=..., data=...)`` path on a planted
flat-price Binance USDT linear perpetual fixture, within a documented
fill-cost tolerance. Also prove both paths keep the frozen seven-column
result schema and that immediate fills/outcomes actually occur.

Timing construction (no same-bar lookahead):
  - Prepared execution decides at a completed close (CAL[0]) and executes next-bar (CAL[1]) via
    ``ExecutionTiming.next_bar()``.
  - Legacy control is the *equivalent effective holdings schedule* with a cash
    lead-in: all-cash at CAL[0], target at CAL[1], hold at CAL[2], passed with
    ``materialize_timing=False`` so entry is not charged on the decision bar.

Tolerance (terminal equity, absolute USD):
  Flat price isolates fee accounting. Legacy turnover on cash→0.5 BTC is
  ``0.5 * (|0.5| + |-0.5|) = 0.5``; at ``trade_cost_bps=4`` the cost return is
  ``0.5 * 4e-4 = 2e-4`` of capital ⇒ ``$20`` on ``$100_000``. The execution taker fee is
  ``qty * price * 0.0004 = 500 * 100 * 0.0004 = $20``. Both paths therefore
  target the exact same ``$99_980`` terminal equity. Allow
  ``TERMINAL_EQUITY_ABS_TOL = 1e-6`` for float reconstruction only — not a
  broad economic band.

USAGE:
    uv run --project packages/platform/backtest pytest \\
      packages/platform/backtest/tests/unit/test_immediate_policy_compatibility.py -v
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import polars as pl
import pytest
from backtest import (
    BacktestConfig,
    prepare_execution_from_strategy_weights,
    run_backtest_from_strategy_weights,
)
from backtest.engines.nautilus.construction import REQUIRED_NAUTILUS_VERSION

from execution import ImmediateMarketPolicy, InstrumentKey, InstrumentSpec, OrderStatus
from strategies import ExecutionTiming, StrategyWeights

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

UTC = timezone.utc
T0 = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
CAL = tuple(T0 + timedelta(minutes=i) for i in range(0, 5))

PRICE = 100.0
INITIAL_CAPITAL = 100_000.0
BTC_WEIGHT = 0.5
# Match InstrumentSpec.taker_fee_rate = 4 bps.
TAKER_FEE_BPS = 4.0
TAKER_FEE_RATE = Decimal("0.0004")

# See module docstring: exact fee match expected; this is float noise only.
TERMINAL_EQUITY_ABS_TOL = 1e-6
EXPECTED_TERMINAL_EQUITY = 99_980.0
EXPECTED_FILL_QTY = Decimal("500.000")
EXPECTED_FILL_FEE = EXPECTED_FILL_QTY * Decimal(str(PRICE)) * TAKER_FEE_RATE

SEVEN_COLUMNS = [
    "equity",
    "benchmark_equity",
    "price_return",
    "funding_return",
    "cost_return",
    "net_return",
    "turnover",
]


# --------------------------------------------------------------------------- #
# Fixtures / builders
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="module")
def _nautilus_ready() -> None:
    pytest.importorskip("nautilus_trader")
    import nautilus_trader

    assert nautilus_trader.__version__ == REQUIRED_NAUTILUS_VERSION


def _instrument_key() -> InstrumentKey:
    return InstrumentKey(venue="BINANCE", symbol="BTCUSDT")


def _wire() -> str:
    return "BINANCE:BTCUSDT"


def _instrument_spec() -> InstrumentSpec:
    return InstrumentSpec(
        key=_instrument_key(),
        product="perpetual",
        base_currency="BTC",
        quote_currency="USDT",
        settlement_currency="USDT",
        is_inverse=False,
        multiplier=Decimal("1"),
        price_increment=Decimal("0.01"),
        quantity_increment=Decimal("0.001"),
        min_quantity=Decimal("0.001"),
        max_quantity=Decimal("1000000"),
        min_notional=Decimal("5"),
        max_notional=Decimal("100000000"),
        maker_fee_rate=Decimal("0.0002"),
        taker_fee_rate=TAKER_FEE_RATE,
    )


def _legacy_config() -> BacktestConfig:
    return BacktestConfig(
        initial_capital=INITIAL_CAPITAL,
        trade_cost_bps=TAKER_FEE_BPS,
        include_funding=False,
        frequency="1m",
        benchmark="BTC",
    )


def _prepared_config() -> BacktestConfig:
    return BacktestConfig(
        initial_capital=INITIAL_CAPITAL,
        trade_cost_bps=TAKER_FEE_BPS,
        include_funding=True,
        frequency="1m",
        benchmark="BTCUSDT",
    )


def _run_legacy_effective_schedule():
    """Legacy path on cash lead-in + two-step effective holdings schedule."""
    # CAL[0] cash lead-in; CAL[1] entry; CAL[2] hold. Already-effective
    # schedule — materialize_timing=False avoids re-applying lag.
    data = pl.DataFrame(
        {
            "timestamp": [CAL[0], CAL[1], CAL[2]],
            "BTC": [PRICE, PRICE, PRICE],
            "CASH": [1.0, 1.0, 1.0],
        }
    )
    weights = StrategyWeights(
        weights=pl.DataFrame(
            {
                "timestamp": [CAL[0], CAL[1], CAL[2]],
                "BTC": [0.0, BTC_WEIGHT, BTC_WEIGHT],
                "CASH": [1.0, 1.0 - BTC_WEIGHT, 1.0 - BTC_WEIGHT],
            }
        ),
        assets=["BTC"],
        execution=ExecutionTiming.same_bar(),
    )
    return run_backtest_from_strategy_weights(
        weights=weights,
        data=data,
        config=_legacy_config(),
        materialize_timing=False,
    )


def _run_prepared_immediate():
    """Prepared ImmediateMarketPolicy path: decide CAL[0], fill CAL[1]."""
    decision = CAL[0]
    earliest = CAL[1]
    weights = StrategyWeights(
        weights=pl.DataFrame(
            {
                "timestamp": [decision],
                "BTC": [BTC_WEIGHT],
                "CASH": [1.0 - BTC_WEIGHT],
            }
        ),
        assets=["BTC"],
        execution=ExecutionTiming.next_bar(),
    )
    bars = pl.DataFrame(
        [
            {
                "instrument": _wire(),
                "source_timestamp": ts,
                "ts_event": ts,
                "ts_init": ts,
                "open": PRICE,
                "high": PRICE,
                "low": PRICE,
                "close": PRICE,
                "volume": 1.0,
            }
            for ts in CAL
        ]
    )
    refs = pl.DataFrame(
        {
            "decision_at": [decision],
            "instrument": [_wire()],
            "observed_at": [decision],
            "price": [PRICE],
        }
    )
    prepared = prepare_execution_from_strategy_weights(
        weights=weights,
        asset_instruments={"BTC": _instrument_key()},
        reference_prices=refs,
        bars=bars,
        instrument_specs=[_instrument_spec()],
        execution_calendar=CAL,
        # Report post-fill and hold bars so terminal equity is after entry.
        reporting_times=(earliest, CAL[2]),
        policy=ImmediateMarketPolicy(),
    )
    return run_backtest_from_strategy_weights(
        weights=weights,
        data=None,
        config=_prepared_config(),
        prepared_execution=prepared,
    )


# --------------------------------------------------------------------------- #
# Compatibility
# --------------------------------------------------------------------------- #


def test_immediate_policy_matches_legacy_effective_schedule_entry_cost(
    _nautilus_ready: None,
) -> None:
    """Immediate prepared path matches legacy cash-lead-in entry economics."""
    legacy = _run_legacy_effective_schedule()
    prepared = _run_prepared_immediate()

    # --- Immediate fill / outcome coverage (actual runtime, not schedule-only)
    assert prepared.execution is not None
    ex = prepared.execution
    assert len(ex.fills) == 1
    fill = ex.fills[0]
    assert fill.quantity == EXPECTED_FILL_QTY
    assert fill.price == Decimal(str(PRICE)).quantize(Decimal("0.01"))
    assert fill.fee == EXPECTED_FILL_FEE
    assert fill.fee_currency == "USDT"
    assert len(ex.outcomes) == 1
    assert ex.outcomes[0].status is OrderStatus.FILLED
    assert ex.outcomes[0].unfilled_quantity == 0
    assert len(ex.intents) == 1
    assert fill.filled_at == CAL[1]
    assert ex.intents[0].scheduled_at == CAL[1]

    # --- Seven-column schema on both public paths
    assert list(legacy.to_dataframe().columns) == SEVEN_COLUMNS
    assert list(prepared.to_dataframe().columns) == SEVEN_COLUMNS
    assert legacy.execution is None
    assert prepared.execution is not None

    # --- Economic compatibility (aligned post-entry / terminal points)
    # Legacy: equity[0]=cash lead-in, equity[1]=post-entry, equity[2]=hold.
    # Prepared: equity[0]=first report post-fill, equity[1]=hold report.
    legacy_post_entry = float(legacy.equity[1])
    legacy_terminal = float(legacy.equity[-1])
    prepared_post_entry = float(prepared.equity[0])
    prepared_terminal = float(prepared.equity[-1])

    assert legacy_post_entry == pytest.approx(EXPECTED_TERMINAL_EQUITY, rel=0, abs=TERMINAL_EQUITY_ABS_TOL)
    assert prepared_post_entry == pytest.approx(EXPECTED_TERMINAL_EQUITY, rel=0, abs=TERMINAL_EQUITY_ABS_TOL)
    assert prepared_terminal == pytest.approx(legacy_terminal, rel=0, abs=TERMINAL_EQUITY_ABS_TOL)
    assert prepared_post_entry == pytest.approx(legacy_post_entry, rel=0, abs=TERMINAL_EQUITY_ABS_TOL)

    # Legacy entry cost identity: 0.5 turnover × 4 bps.
    assert float(legacy.cost_return[0]) == pytest.approx(0.0002, rel=0, abs=1e-12)
    assert float(legacy.turnover[0]) == pytest.approx(0.5, rel=0, abs=1e-12)
