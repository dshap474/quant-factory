"""Implementation regressions for explicit weekly ledger holdings.

USAGE: .venv/bin/python -m pytest <this-file> -q
"""

from datetime import UTC, datetime, timedelta

import numpy as np
import polars as pl
import pytest
from backtest import BacktestConfig, run_backtest

# --------------------------------------------------------------------------- #
# Public accounting boundary
# --------------------------------------------------------------------------- #


def test_fixed_shares_and_rebalance_cost():
    dates = [datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=i) for i in range(4)]
    prices = pl.DataFrame({"timestamp": dates, "BTC": [10.0, 20.0, 30.0, 40.0], "CASH": [1.0] * 4})
    weights = pl.DataFrame({"timestamp": dates, "BTC": [0.5, 0.0, 0.0, 0.9], "CASH": [0.5, 1.0, 1.0, 0.1]})
    result = run_backtest(
        prices=prices,
        weights=weights,
        config=BacktestConfig(
            engine="ledger",
            initial_capital=100.0,
            trade_cost_bps=100.0,
            include_funding=False,
            metrics=(),
            rebalance_every_bars=2,
        ),
    )
    # Buy 5 shares for $50 plus $.50 fee, hold through doubling/tripling,
    # then sell 5 shares for $150 less $1.50; terminal target is not traded.
    np.testing.assert_allclose(result.equity, [100.0, 149.5, 199.5, 198.0], rtol=0, atol=1e-12)
    assert result.turnover[1] == 0
    assert result.cost_return[1] == 0


@pytest.mark.parametrize("value", [0, -1, 1.5, True, "7"])
def test_invalid_rebalance_interval(value):
    with pytest.raises(ValueError, match="rebalance_every_bars"):
        BacktestConfig(engine="ledger", rebalance_every_bars=value)


def test_nautilus_rejects_nondefault_interval():
    with pytest.raises(ValueError, match="ledger"):
        BacktestConfig(rebalance_every_bars=7)
