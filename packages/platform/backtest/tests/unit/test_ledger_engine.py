"""Focused ordinary-ledger engine tests through public APIs.

Expected values are hand-derived or use standard-library arithmetic only.
Production accounting helpers are not imported into expectations.

USAGE:
    uv run --project packages/platform/backtest pytest \\
      packages/platform/backtest/tests/unit/test_ledger_engine.py -q
"""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

import numpy as np
import polars as pl
import pytest
from backtest import BacktestConfig, run_backtest, run_backtest_from_strategy_weights
from backtest.errors import BacktestContractError, BacktestEngineExecutionError, BacktestUnsupportedFeatureError
from backtest.result_schema import BACKTEST_RESULT_COLUMNS

from strategies import ExecutionTiming, StrategyWeights

# --------------------------------------------------------------------------- #
# Tolerances and helpers
# --------------------------------------------------------------------------- #

# Float64 product chains over short fixtures stay within a few ULPs of exact
# rational results; 1e-12 is generous for ≤20 multiplies on O(1) numbers.
RTOL = 1e-12
ATOL = 1e-12


def _ts(n: int, start: datetime | None = None) -> list[datetime]:
    base = start or datetime(2024, 1, 1)
    return [base + timedelta(days=i) for i in range(n)]


def _frame(timestamps: list[datetime], **cols: list[float]) -> pl.DataFrame:
    return pl.DataFrame({"timestamp": timestamps, **cols})


def _ledger_cfg(**kwargs) -> BacktestConfig:
    return BacktestConfig(engine="ledger", **kwargs)


# --------------------------------------------------------------------------- #
# Engine selection
# --------------------------------------------------------------------------- #


def test_ledger_selection_reports_engine_used():
    ts = _ts(3)
    prices = _frame(ts, BTC=[100.0, 100.0, 100.0], CASH=[1.0, 1.0, 1.0])
    weights = _frame(ts, BTC=[0.5, 0.5, 0.5], CASH=[0.5, 0.5, 0.5])

    result = run_backtest(
        prices=prices,
        weights=weights,
        config=_ledger_cfg(include_funding=False, trade_cost_bps=0.0),
    )

    assert result.engine_used == "ledger"
    assert result.engine_meta["accounting"] == "ordinary_ledger"


def test_explicit_nautilus_selection_still_dispatches():
    pytest.importorskip("nautilus_trader")
    ts = _ts(3)
    prices = _frame(ts, BTC=[100.0, 101.0, 102.0], CASH=[1.0, 1.0, 1.0])
    weights = _frame(ts, BTC=[0.5, 0.5, 0.5], CASH=[0.5, 0.5, 0.5])

    result = run_backtest(
        prices=prices,
        weights=weights,
        config=BacktestConfig(engine="nautilus", include_funding=False, trade_cost_bps=0.0),
    )
    assert result.engine_used == "nautilus"


def test_prepared_execution_rejects_ledger_engine():
    weights = StrategyWeights(
        weights=_frame(_ts(2), BTC=[0.5, 0.5], CASH=[0.5, 0.5]),
        assets=["BTC"],
        execution=ExecutionTiming.next_bar(),
    )
    with pytest.raises(BacktestUnsupportedFeatureError, match="prepared_execution requires engine='nautilus'"):
        run_backtest_from_strategy_weights(
            weights=weights,
            data=None,
            config=_ledger_cfg(),
            prepared_execution=SimpleNamespace(),  # ty: ignore[invalid-argument-type]
        )


# --------------------------------------------------------------------------- #
# Initial entry / cost placement
# --------------------------------------------------------------------------- #


def test_flat_price_initial_entry_gross_cost_at_dataframe_row_1():
    """All-cash → 50% BTC on flat prices: gross turnover 0.5, cost at df row 1."""
    # E0=100_000, target notional BTC=50_000, traded=50_000, turnover=0.5
    # cost_rate=10 bps → cost=50, cost_return=0.0005
    # flat prices → price_return=0; equity[1]=99_950
    ts = _ts(3)
    prices = _frame(ts, BTC=[100.0, 100.0, 100.0], CASH=[1.0, 1.0, 1.0])
    weights = _frame(ts, BTC=[0.5, 0.5, 0.5], CASH=[0.5, 0.5, 0.5])
    capital = 100_000.0
    bps = 10.0

    result = run_backtest(
        prices=prices,
        weights=weights,
        config=_ledger_cfg(
            initial_capital=capital,
            trade_cost_bps=bps,
            include_funding=False,
        ),
    )

    expected_turnover0 = 0.5
    expected_cost0 = expected_turnover0 * (bps / 10_000.0)
    assert result.turnover[0] == pytest.approx(expected_turnover0, rel=RTOL, abs=ATOL)
    assert result.cost_return[0] == pytest.approx(expected_cost0, rel=RTOL, abs=ATOL)
    assert result.price_return[0] == pytest.approx(0.0, abs=ATOL)
    assert result.equity[0] == capital
    assert result.equity[1] == pytest.approx(capital * (1.0 - expected_cost0), rel=RTOL, abs=ATOL)

    df = result.to_dataframe()
    # to_dataframe prepends a zero return/turnover row; interval-0 cost lands at df row 1.
    assert df["cost_return"][0] == 0.0
    assert df["turnover"][0] == 0.0
    assert df["cost_return"][1] == pytest.approx(expected_cost0, rel=RTOL, abs=ATOL)
    assert df["turnover"][1] == pytest.approx(expected_turnover0, rel=RTOL, abs=ATOL)


# --------------------------------------------------------------------------- #
# NEXT_BAR no-lookahead via strategy connector
# --------------------------------------------------------------------------- #


def test_next_bar_connector_has_no_lookahead():
    """Decision at t0 with NEXT_BAR becomes effective at t1; first interval is cash."""
    # Distinct moves: decision bar +10%, first effective interval +20%.
    data = pl.DataFrame(
        {
            "timestamp": [
                datetime(2024, 1, 1),
                datetime(2024, 1, 1),
                datetime(2024, 1, 2),
                datetime(2024, 1, 2),
                datetime(2024, 1, 3),
                datetime(2024, 1, 3),
            ],
            "asset": ["BTC", "ETH"] * 3,
            "close": [100.0, 50.0, 110.0, 55.0, 132.0, 66.0],
        }
    )
    # Decision only on first bar: 100% BTC. NEXT_BAR → effective from row 1.
    weights = StrategyWeights(
        weights=pl.DataFrame(
            {
                "timestamp": [datetime(2024, 1, 1)],
                "BTC": [1.0],
                "ETH": [0.0],
                "CASH": [0.0],
            }
        ),
        assets=["BTC", "ETH"],
        execution=ExecutionTiming.next_bar(),
    )

    result = run_backtest_from_strategy_weights(
        weights=weights,
        data=data,
        config=_ledger_cfg(include_funding=False, trade_cost_bps=0.0, initial_capital=100_000.0),
    )

    # Effective timeline starts at 2024-01-02 (lag 1). First interval: enter BTC at 110,
    # hold through 132 → price return = 132/110 - 1 = 0.20 (not decision-bar 0.10).
    assert result.equity[0] == 100_000.0
    assert result.turnover[0] == pytest.approx(1.0, rel=RTOL, abs=ATOL)
    expected_price = 132.0 / 110.0 - 1.0
    assert result.price_return[0] == pytest.approx(expected_price, rel=RTOL, abs=ATOL)
    lookahead = 110.0 / 100.0 - 1.0
    assert result.price_return[0] == pytest.approx(0.20, rel=RTOL, abs=ATOL)
    assert abs(result.price_return[0] - lookahead) > 1e-9


# --------------------------------------------------------------------------- #
# Drift rebalance and current-equity sizing
# --------------------------------------------------------------------------- #


def test_constant_target_rebalances_price_drift():
    """Constant 50% BTC rebalances after a price move; second-interval turnover > 0."""
    ts = _ts(3)
    prices = _frame(ts, BTC=[100.0, 200.0, 200.0], CASH=[1.0, 1.0, 1.0])
    weights = _frame(ts, BTC=[0.5, 0.5, 0.5], CASH=[0.5, 0.5, 0.5])
    capital = 100_000.0

    result = run_backtest(
        prices=prices,
        weights=weights,
        config=_ledger_cfg(initial_capital=capital, trade_cost_bps=0.0, include_funding=False),
    )

    # Interval 0: enter 50k notional @100, price doubles → price_return=0.5
    assert result.turnover[0] == pytest.approx(0.5, rel=RTOL, abs=ATOL)
    assert result.price_return[0] == pytest.approx(0.5, rel=RTOL, abs=ATOL)
    e1 = capital * 1.5
    assert result.equity[1] == pytest.approx(e1, rel=RTOL, abs=ATOL)

    # Pre-trade at t1: BTC notional drifted to 100k, cash 50k, equity 150k.
    # Target BTC notional 75k → trade |100k-75k|=25k → turnover=25k/150k.
    expected_to1 = 25_000.0 / e1
    assert result.turnover[1] == pytest.approx(expected_to1, rel=RTOL, abs=ATOL)
    assert result.price_return[1] == pytest.approx(0.0, abs=ATOL)


def test_profitable_rebalance_sized_from_current_equity():
    """After a gain, a weight increase is sized on current equity, not initial capital."""
    ts = _ts(3)
    prices = _frame(ts, BTC=[100.0, 200.0, 200.0], CASH=[1.0, 1.0, 1.0])
    # t0: 50% BTC; t1: 100% BTC (sized on post-gain equity)
    weights = _frame(ts, BTC=[0.5, 1.0, 1.0], CASH=[0.5, 0.0, 0.0])
    capital = 100_000.0

    result = run_backtest(
        prices=prices,
        weights=weights,
        config=_ledger_cfg(initial_capital=capital, trade_cost_bps=0.0, include_funding=False),
    )

    e1 = capital * 1.5  # 50% exposure * +100% move
    # Pre-trade notional BTC=100k; target=150k; trade=50k; turnover=50k/150k
    assert result.equity[1] == pytest.approx(e1, rel=RTOL, abs=ATOL)
    assert result.turnover[1] == pytest.approx(50_000.0 / e1, rel=RTOL, abs=ATOL)
    # Flat second interval after rebalance to 100%
    assert result.price_return[1] == pytest.approx(0.0, abs=ATOL)
    assert result.equity[2] == pytest.approx(e1, rel=RTOL, abs=ATOL)


# --------------------------------------------------------------------------- #
# Rotation and reversal
# --------------------------------------------------------------------------- #


def test_a_to_b_rotation_gross_both_legs():
    """Rotate 100% A → 100% B: gross turnover 2.0 (both legs, no half-convention)."""
    ts = _ts(3)
    prices = _frame(
        ts,
        A=[10.0, 10.0, 10.0],
        B=[20.0, 20.0, 20.0],
        CASH=[1.0, 1.0, 1.0],
    )
    weights = _frame(
        ts,
        A=[1.0, 0.0, 0.0],
        B=[0.0, 1.0, 1.0],
        CASH=[0.0, 0.0, 0.0],
    )
    capital = 100_000.0

    result = run_backtest(
        prices=prices,
        weights=weights,
        config=_ledger_cfg(initial_capital=capital, trade_cost_bps=0.0, include_funding=False),
    )

    assert result.turnover[0] == pytest.approx(1.0, rel=RTOL, abs=ATOL)  # cash → A
    # At t1: exit A (100k) + enter B (100k) = 200k / 100k = 2.0
    assert result.turnover[1] == pytest.approx(2.0, rel=RTOL, abs=ATOL)


def test_long_to_short_reversal_full_gross():
    """+1 → −1 on one asset: gross turnover 2.0 of equity."""
    ts = _ts(3)
    prices = _frame(ts, BTC=[100.0, 100.0, 100.0], CASH=[1.0, 1.0, 1.0])
    weights = _frame(ts, BTC=[1.0, -1.0, -1.0], CASH=[0.0, 2.0, 2.0])
    capital = 100_000.0

    result = run_backtest(
        prices=prices,
        weights=weights,
        config=_ledger_cfg(initial_capital=capital, trade_cost_bps=0.0, include_funding=False),
    )

    assert result.turnover[0] == pytest.approx(1.0, rel=RTOL, abs=ATOL)
    assert result.turnover[1] == pytest.approx(2.0, rel=RTOL, abs=ATOL)


# --------------------------------------------------------------------------- #
# Benchmark column order independence
# --------------------------------------------------------------------------- #


def test_explicit_benchmark_independent_of_column_order():
    ts = _ts(4)
    prices_ab = _frame(
        ts,
        A=[100.0, 101.0, 102.0, 103.0],
        B=[50.0, 40.0, 30.0, 20.0],
        CASH=[1.0, 1.0, 1.0, 1.0],
    )
    weights_ab = _frame(
        ts,
        A=[0.4, 0.4, 0.4, 0.4],
        B=[0.4, 0.4, 0.4, 0.4],
        CASH=[0.2, 0.2, 0.2, 0.2],
    )
    prices_ba = prices_ab.select("timestamp", "B", "A", "CASH")
    weights_ba = weights_ab.select("timestamp", "B", "A", "CASH")
    cfg = _ledger_cfg(
        include_funding=False,
        trade_cost_bps=0.0,
        benchmark="B",
        metrics=["tracking_error", "information_ratio", "total_return"],
    )

    a = run_backtest(prices=prices_ab, weights=weights_ab, config=cfg)
    b = run_backtest(prices=prices_ba, weights=weights_ba, config=cfg)

    assert a.equity.to_list() == pytest.approx(b.equity.to_list(), rel=RTOL, abs=ATOL)
    assert a.benchmark_equity.to_list() == pytest.approx(b.benchmark_equity.to_list(), rel=RTOL, abs=ATOL)
    assert a.metrics["tracking_error"] == pytest.approx(b.metrics["tracking_error"], rel=RTOL, abs=ATOL)
    assert a.metrics["information_ratio"] == pytest.approx(b.metrics["information_ratio"], rel=RTOL, abs=ATOL)


# --------------------------------------------------------------------------- #
# Funding
# --------------------------------------------------------------------------- #


def test_funding_long_short_signs_row_placement_and_toggle():
    ts = _ts(3)
    prices = _frame(
        ts,
        LONG=[100.0, 100.0, 100.0],
        SHORT=[100.0, 100.0, 100.0],
        CASH=[1.0, 1.0, 1.0],
    )
    weights = _frame(
        ts,
        LONG=[0.5, 0.5, 0.5],
        SHORT=[-0.5, -0.5, -0.5],
        CASH=[1.0, 1.0, 1.0],
    )
    # Positive funding on both; longs pay, shorts receive. Interval 0 uses row 0 rates.
    funding = _frame(
        ts,
        LONG=[0.01, 0.99, 0.99],
        SHORT=[0.01, 0.99, 0.99],
        CASH=[0.0, 0.0, 0.0],
    )
    capital = 100_000.0

    with_f = run_backtest(
        prices=prices,
        weights=weights,
        funding_rates=funding,
        config=_ledger_cfg(initial_capital=capital, trade_cost_bps=0.0, include_funding=True),
    )
    without_f = run_backtest(
        prices=prices,
        weights=weights,
        funding_rates=funding,
        config=_ledger_cfg(initial_capital=capital, trade_cost_bps=0.0, include_funding=False),
    )

    # target notionals: +50k long, −50k short; funding_pnl = −(+50k*0.01 + (−50k)*0.01) = 0
    assert with_f.funding_return[0] == pytest.approx(0.0, abs=ATOL)

    # Pure long: funding_return = −0.5 * 0.01 = −0.005 using row 0, not row 1's 0.99.
    long_only_w = _frame(ts, LONG=[0.5, 0.5, 0.5], SHORT=[0.0, 0.0, 0.0], CASH=[0.5, 0.5, 0.5])
    long_only = run_backtest(
        prices=prices,
        weights=long_only_w,
        funding_rates=funding,
        config=_ledger_cfg(initial_capital=capital, trade_cost_bps=0.0, include_funding=True),
    )
    assert long_only.funding_return[0] == pytest.approx(-0.005, rel=RTOL, abs=ATOL)

    short_only_w = _frame(ts, LONG=[0.0, 0.0, 0.0], SHORT=[-0.5, -0.5, -0.5], CASH=[1.5, 1.5, 1.5])
    short_only = run_backtest(
        prices=prices,
        weights=short_only_w,
        funding_rates=funding,
        config=_ledger_cfg(initial_capital=capital, trade_cost_bps=0.0, include_funding=True),
    )
    assert short_only.funding_return[0] == pytest.approx(0.005, rel=RTOL, abs=ATOL)

    assert without_f.funding_return.abs().sum() == 0.0


def test_rejects_non_zero_cash_funding_when_enabled():
    ts = _ts(2)
    with pytest.raises(BacktestContractError, match=r"funding_rates\.CASH must be zero"):
        run_backtest(
            prices=_frame(ts, BTC=[100.0, 100.0], CASH=[1.0, 1.0]),
            weights=_frame(ts, BTC=[0.5, 0.5], CASH=[0.5, 0.5]),
            funding_rates=_frame(ts, BTC=[0.0, 0.0], CASH=[0.01, 0.0]),
            config=_ledger_cfg(include_funding=True, trade_cost_bps=0.0),
        )


# --------------------------------------------------------------------------- #
# Fail-closed inputs
# --------------------------------------------------------------------------- #


def test_rejects_single_row():
    ts = _ts(1)
    with pytest.raises(BacktestContractError, match="at least two rows"):
        run_backtest(
            prices=_frame(ts, BTC=[100.0], CASH=[1.0]),
            weights=_frame(ts, BTC=[1.0], CASH=[0.0]),
            config=_ledger_cfg(),
        )


def test_rejects_non_finite_price():
    ts = _ts(2)
    with pytest.raises(BacktestContractError, match="finite prices"):
        run_backtest(
            prices=_frame(ts, BTC=[100.0, float("nan")], CASH=[1.0, 1.0]),
            weights=_frame(ts, BTC=[1.0, 1.0], CASH=[0.0, 0.0]),
            config=_ledger_cfg(),
        )


def test_rejects_non_positive_non_cash_price():
    ts = _ts(2)
    with pytest.raises(BacktestContractError, match="positive non-CASH"):
        run_backtest(
            prices=_frame(ts, BTC=[100.0, 0.0], CASH=[1.0, 1.0]),
            weights=_frame(ts, BTC=[1.0, 1.0], CASH=[0.0, 0.0]),
            config=_ledger_cfg(),
        )


def test_rejects_missing_benchmark():
    ts = _ts(2)
    with pytest.raises(BacktestContractError, match="Benchmark asset"):
        run_backtest(
            prices=_frame(ts, BTC=[100.0, 101.0], CASH=[1.0, 1.0]),
            weights=_frame(ts, BTC=[1.0, 1.0], CASH=[0.0, 0.0]),
            config=_ledger_cfg(benchmark="ETH", include_funding=False, trade_cost_bps=0.0),
        )


def test_equity_exhaustion_names_row_and_components():
    # Flat prices, 100% long, funding rate 2.0 → funding_return = −2 → next equity negative.
    ts = _ts(2)
    prices = _frame(ts, BTC=[100.0, 100.0], CASH=[1.0, 1.0])
    weights = _frame(ts, BTC=[1.0, 1.0], CASH=[0.0, 0.0])
    funding = _frame(ts, BTC=[2.0, 0.0], CASH=[0.0, 0.0])
    with pytest.raises(BacktestEngineExecutionError, match=r"row 0.*pre-trade equity=.*next equity=.*dominant component="):
        run_backtest(
            prices=prices,
            weights=weights,
            funding_rates=funding,
            config=_ledger_cfg(initial_capital=1000.0, trade_cost_bps=0.0, include_funding=True),
        )


# --------------------------------------------------------------------------- #
# Invariants
# --------------------------------------------------------------------------- #


def test_deterministic_repeats():
    ts = _ts(5)
    prices = _frame(
        ts,
        BTC=[100.0, 101.0, 99.0, 105.0, 110.0],
        ETH=[50.0, 51.0, 49.0, 52.0, 53.0],
        CASH=[1.0, 1.0, 1.0, 1.0, 1.0],
    )
    weights = _frame(
        ts,
        BTC=[0.4, 0.5, 0.3, 0.6, 0.4],
        ETH=[0.3, 0.2, 0.4, 0.1, 0.3],
        CASH=[0.3, 0.3, 0.3, 0.3, 0.3],
    )
    cfg = _ledger_cfg(include_funding=False, trade_cost_bps=5.0)
    a = run_backtest(prices=prices, weights=weights, config=cfg)
    b = run_backtest(prices=prices, weights=weights, config=cfg)
    assert a.equity.to_list() == b.equity.to_list()
    assert a.net_return.to_list() == b.net_return.to_list()
    assert a.turnover.to_list() == b.turnover.to_list()


def test_initial_capital_scale_invariance():
    ts = _ts(4)
    prices = _frame(
        ts,
        BTC=[100.0, 110.0, 105.0, 120.0],
        CASH=[1.0, 1.0, 1.0, 1.0],
    )
    weights = _frame(ts, BTC=[0.6, 0.7, 0.5, 0.5], CASH=[0.4, 0.3, 0.5, 0.5])
    small = run_backtest(
        prices=prices,
        weights=weights,
        config=_ledger_cfg(initial_capital=1_000.0, trade_cost_bps=5.0, include_funding=False),
    )
    large = run_backtest(
        prices=prices,
        weights=weights,
        config=_ledger_cfg(initial_capital=1_000_000.0, trade_cost_bps=5.0, include_funding=False),
    )
    scale = 1_000_000.0 / 1_000.0
    assert large.equity.to_list() == pytest.approx([v * scale for v in small.equity.to_list()], rel=RTOL, abs=ATOL)
    assert large.net_return.to_list() == pytest.approx(small.net_return.to_list(), rel=RTOL, abs=ATOL)
    assert large.turnover.to_list() == pytest.approx(small.turnover.to_list(), rel=RTOL, abs=ATOL)


def test_return_decomposition_and_equity_recursion():
    ts = _ts(4)
    prices = _frame(
        ts,
        BTC=[100.0, 102.0, 101.0, 104.0],
        ETH=[40.0, 41.0, 39.0, 42.0],
        CASH=[1.0, 1.0, 1.0, 1.0],
    )
    weights = _frame(
        ts,
        BTC=[0.5, 0.4, 0.6, 0.5],
        ETH=[0.3, 0.4, 0.2, 0.3],
        CASH=[0.2, 0.2, 0.2, 0.2],
    )
    funding = _frame(
        ts,
        BTC=[0.001, 0.002, -0.001, 0.0],
        ETH=[-0.0005, 0.001, 0.0005, 0.0],
        CASH=[0.0, 0.0, 0.0, 0.0],
    )
    result = run_backtest(
        prices=prices,
        weights=weights,
        funding_rates=funding,
        config=_ledger_cfg(initial_capital=50_000.0, trade_cost_bps=3.0, include_funding=True),
    )

    net = (
        np.asarray(result.price_return.to_list())
        + np.asarray(result.funding_return.to_list())
        - np.asarray(result.cost_return.to_list())
    )
    assert result.net_return.to_list() == pytest.approx(net.tolist(), rel=RTOL, abs=ATOL)

    equity = np.asarray(result.equity.to_list())
    for i, r in enumerate(result.net_return.to_list()):
        assert equity[i + 1] == pytest.approx(equity[i] * (1.0 + r), rel=RTOL, abs=ATOL)


def test_frozen_seven_column_schema():
    ts = _ts(3)
    result = run_backtest(
        prices=_frame(ts, BTC=[100.0, 101.0, 102.0], CASH=[1.0, 1.0, 1.0]),
        weights=_frame(ts, BTC=[0.5, 0.5, 0.5], CASH=[0.5, 0.5, 0.5]),
        config=_ledger_cfg(include_funding=False, trade_cost_bps=0.0),
    )
    assert tuple(result.to_dataframe().columns) == BACKTEST_RESULT_COLUMNS


# --------------------------------------------------------------------------- #
# External price-only oracle (frozen cvxportfolio values)
# --------------------------------------------------------------------------- #

# Generated offline by tests/oracles/generate_cvxportfolio_fixture.py with
# cvxportfolio==1.5.1 (wheel SHA-256
# 9c02954c23c095b59a97959eff8b757f164f78e159a5d630ce43ea36c14d0619).
# Price-only, cash returns forced to zero. cvxportfolio does not verify ledger
# costs or perpetual funding.
_CVX_PRICES = {
    "A": [100.0, 101.0, 103.0, 102.0, 105.0],
    "B": [50.0, 49.0, 51.0, 52.0, 50.0],
}
_CVX_WEIGHTS = {
    "A": [0.6, 0.5, 0.4, 0.55, 0.55],
    "B": [0.4, 0.5, 0.6, 0.45, 0.45],
}
_CVX_INITIAL = 1_000_000.0
# Full equity curve from the committed fixture (price-only, zero cash return).
_CVX_EQUITY_CURVE = [
    1_000_000.0,
    998_000.0,
    1_028_248.5350575874,
    1_036_352.3784521017,
    1_035_180.0341325859,
]


def test_cvxportfolio_frozen_price_only_equity_curve():
    ts = _ts(5)
    prices = _frame(
        ts,
        A=_CVX_PRICES["A"],
        B=_CVX_PRICES["B"],
        CASH=[1.0] * 5,
    )
    weights = _frame(
        ts,
        A=_CVX_WEIGHTS["A"],
        B=_CVX_WEIGHTS["B"],
        CASH=[0.0] * 5,
    )
    result = run_backtest(
        prices=prices,
        weights=weights,
        config=_ledger_cfg(
            initial_capital=_CVX_INITIAL,
            trade_cost_bps=0.0,
            include_funding=False,
        ),
    )
    assert result.equity.to_list() == pytest.approx(_CVX_EQUITY_CURVE, rel=1e-10, abs=1e-6)
