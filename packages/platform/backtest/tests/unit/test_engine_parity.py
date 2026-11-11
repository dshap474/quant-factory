"""Ledger-vs-Nautilus parity on one shared fixture WITH costs and funding.

Purpose: the two ordinary engines document different turnover conventions
(Nautilus: half-turnover including CASH on target deltas; ledger: gross non-CASH
traded notional under current-equity drift), but their funding legs share one
convention and every leg must reconcile to a hand-derived closed form on the
same fixture. The cvxportfolio oracle is price-only, so this module is the
numerical comparison of the engines' cost and funding legs.

Expected values are hand-derived from the fixture; production accounting
helpers are not imported into expectations.

USAGE:
    uv run --project packages/platform/backtest pytest \\
      packages/platform/backtest/tests/unit/test_engine_parity.py -q
"""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import polars as pl
import pytest
from backtest import BacktestConfig, run_backtest

# --------------------------------------------------------------------------- #
# Fixture: 2 risky assets + CASH, 8 rows, costs AND funding active
# --------------------------------------------------------------------------- #

EXACT = 1e-12
# Nautilus replays through quantized engine positions sized from marked current
# equity; its price leg tracks the closed form only to engine precision
# (observed max deviation ~5.2e-8 on this fixture; 1e-6 leaves ~20x headroom).
NAUTILUS_PRICE_TOLERANCE = 1e-6

TRADE_COST_BPS = 20.0
COST_RATE = TRADE_COST_BPS / 10_000.0

TIMESTAMPS = [datetime(2024, 1, 1) + timedelta(days=i) for i in range(8)]

PRICES = {
    "BTC": [100.0, 104.0, 101.0, 103.0, 106.0, 102.0, 105.0, 107.0],
    "ETH": [50.0, 49.0, 51.0, 52.0, 50.0, 53.0, 54.0, 52.0],
}

WEIGHTS = {
    "BTC": [0.4, 0.3, -0.2, 0.5, 0.1, -0.3, 0.2, 0.2],
    "ETH": [-0.2, 0.3, 0.4, -0.1, 0.3, 0.2, -0.2, -0.2],
}

FUNDING = {
    "BTC": [0.0004, -0.0002, 0.0003, 0.0001, -0.0004, 0.0002, 0.0005, 0.0],
    "ETH": [-0.0001, 0.0003, -0.0002, 0.0004, 0.0001, -0.0003, 0.0002, 0.0],
}


def _frames() -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    cash_weights = [1.0 - b - e for b, e in zip(WEIGHTS["BTC"], WEIGHTS["ETH"], strict=True)]
    prices = pl.DataFrame({"timestamp": TIMESTAMPS, **PRICES, "CASH": [1.0] * 8})
    weights = pl.DataFrame({"timestamp": TIMESTAMPS, **WEIGHTS, "CASH": cash_weights})
    funding = pl.DataFrame({"timestamp": TIMESTAMPS, **FUNDING, "CASH": [0.0] * 8})
    return prices, weights, funding


def _run(engine: str):
    prices, weights, funding = _frames()
    return run_backtest(
        prices=prices,
        weights=weights,
        funding_rates=funding,
        config=BacktestConfig(engine=engine, include_funding=True, trade_cost_bps=TRADE_COST_BPS),
    )


@pytest.fixture(scope="module")
def ledger_result():
    return _run("ledger")


@pytest.fixture(scope="module")
def nautilus_result():
    pytest.importorskip("nautilus_trader")
    return _run("nautilus")


def _closed_form_funding() -> np.ndarray:
    return np.array(
        [
            -(WEIGHTS["BTC"][i] * FUNDING["BTC"][i] + WEIGHTS["ETH"][i] * FUNDING["ETH"][i])
            for i in range(7)
        ]
    )


def _closed_form_price() -> np.ndarray:
    return np.array(
        [
            WEIGHTS["BTC"][i] * (PRICES["BTC"][i + 1] / PRICES["BTC"][i] - 1.0)
            + WEIGHTS["ETH"][i] * (PRICES["ETH"][i + 1] / PRICES["ETH"][i] - 1.0)
            for i in range(7)
        ]
    )


# --------------------------------------------------------------------------- #
# Funding: the one leg both engines compute under a single shared convention
# --------------------------------------------------------------------------- #


def test_funding_leg_parity_is_exact(ledger_result, nautilus_result):
    expected = _closed_form_funding()
    ledger = ledger_result.funding_return.to_numpy()
    nautilus = nautilus_result.funding_return.to_numpy()
    np.testing.assert_allclose(ledger, expected, rtol=0.0, atol=EXACT)
    np.testing.assert_allclose(nautilus, expected, rtol=0.0, atol=EXACT)
    np.testing.assert_allclose(ledger, nautilus, rtol=0.0, atol=EXACT)


# --------------------------------------------------------------------------- #
# Cost and turnover: each engine must match its own documented convention
# --------------------------------------------------------------------------- #


def test_nautilus_cost_follows_half_turnover_convention(nautilus_result):
    cash = [1.0 - b - e for b, e in zip(WEIGHTS["BTC"], WEIGHTS["ETH"], strict=True)]
    expected_turnover = np.array(
        [
            0.5
            * (
                abs(WEIGHTS["BTC"][i + 1] - WEIGHTS["BTC"][i])
                + abs(WEIGHTS["ETH"][i + 1] - WEIGHTS["ETH"][i])
                + abs(cash[i + 1] - cash[i])
            )
            for i in range(7)
        ]
    )
    np.testing.assert_allclose(nautilus_result.turnover.to_numpy(), expected_turnover, rtol=0.0, atol=EXACT)
    np.testing.assert_allclose(
        nautilus_result.cost_return.to_numpy(), expected_turnover * COST_RATE, rtol=0.0, atol=EXACT
    )


def test_ledger_cost_follows_drifted_gross_convention(ledger_result):
    # Independent replay of the documented ledger recursion: all-CASH start,
    # targets sized from pre-trade equity, holdings drifting with returns.
    equity = ledger_result.equity.to_numpy()
    net = ledger_result.net_return.to_numpy()
    expected_turnover = np.empty(7)
    current = np.zeros(2)
    e = equity[0]
    for i in range(7):
        w = np.array([WEIGHTS["BTC"][i], WEIGHTS["ETH"][i]])
        rets = np.array(
            [PRICES["BTC"][i + 1] / PRICES["BTC"][i] - 1.0, PRICES["ETH"][i + 1] / PRICES["ETH"][i] - 1.0]
        )
        target = w * e
        expected_turnover[i] = float(np.abs(target - current).sum()) / e
        current = target * (1.0 + rets)
        e = e * (1.0 + net[i])
    turnover = ledger_result.turnover.to_numpy()
    np.testing.assert_allclose(turnover, expected_turnover, rtol=0.0, atol=EXACT)
    np.testing.assert_allclose(ledger_result.cost_return.to_numpy(), turnover * COST_RATE, rtol=0.0, atol=EXACT)


# --------------------------------------------------------------------------- #
# Price and net: closed form for the ledger, engine tolerance for Nautilus
# --------------------------------------------------------------------------- #


def test_ledger_price_leg_matches_closed_form(ledger_result):
    np.testing.assert_allclose(ledger_result.price_return.to_numpy(), _closed_form_price(), rtol=0.0, atol=EXACT)


def test_nautilus_price_leg_matches_closed_form_to_engine_tolerance(nautilus_result):
    np.testing.assert_allclose(
        nautilus_result.price_return.to_numpy(),
        _closed_form_price(),
        rtol=0.0,
        atol=NAUTILUS_PRICE_TOLERANCE,
    )


def test_net_leg_assembly_holds_for_both_engines(ledger_result, nautilus_result):
    for result in (ledger_result, nautilus_result):
        net = result.net_return.to_numpy()
        assembled = (
            result.price_return.to_numpy() + result.funding_return.to_numpy() - result.cost_return.to_numpy()
        )
        np.testing.assert_allclose(net, assembled, rtol=0.0, atol=EXACT)


def test_ledger_equity_compounds_net_returns(ledger_result):
    equity = ledger_result.equity.to_numpy()
    np.testing.assert_allclose(
        equity[1:] / equity[:-1] - 1.0, ledger_result.net_return.to_numpy(), rtol=0.0, atol=EXACT
    )
