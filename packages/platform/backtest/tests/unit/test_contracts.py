"""Contract tests for backtest configuration and input invariants."""

from __future__ import annotations

from datetime import datetime

import polars as pl
import pytest
from backtest import BacktestConfig, get_annualization_factor, run_backtest


def _sample_prices() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "timestamp": [datetime(2024, 1, 1), datetime(2024, 1, 2), datetime(2024, 1, 3)],
            "BTC": [100.0, 100.0, 100.0],
            "CASH": [1.0, 1.0, 1.0],
        }
    )


def _sample_weights() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "timestamp": [datetime(2024, 1, 1), datetime(2024, 1, 2), datetime(2024, 1, 3)],
            "BTC": [1.0, 1.0, 1.0],
            "CASH": [0.0, 0.0, 0.0],
        }
    )


def test_backtest_defaults_match_contract():
    """Backtest defaults should reflect contract values."""
    config = BacktestConfig()
    assert config.initial_capital == 100_000.0
    assert config.trade_cost_bps == 5.0
    assert config.include_funding is True
    assert config.benchmark_asset is None
    assert "win_rate" in config.metrics
    assert "tracking_error" in config.metrics
    assert "information_ratio" in config.metrics


def test_annualization_factors_use_trading_calendar():
    """Hourly and 4h annualization should use 252-trading-day scaling."""
    assert get_annualization_factor("hourly") == 6048.0
    assert get_annualization_factor("4h") == 1512.0
    assert get_annualization_factor("1d") == 252.0


def test_include_funding_toggle_controls_funding_pnl():
    """Funding contribution should be zeroed when include_funding is disabled."""
    prices = _sample_prices()
    weights = _sample_weights()
    funding = pl.DataFrame(
        {
            "timestamp": [datetime(2024, 1, 1), datetime(2024, 1, 2), datetime(2024, 1, 3)],
            "BTC": [0.01, 0.01, 0.01],
            "CASH": [0.0, 0.0, 0.0],
        }
    )

    with_funding = run_backtest(
        prices=prices,
        weights=weights,
        funding_rates=funding,
        config=BacktestConfig(include_funding=True, trade_cost_bps=0.0),
    )
    without_funding = run_backtest(
        prices=prices,
        weights=weights,
        funding_rates=funding,
        config=BacktestConfig(include_funding=False, trade_cost_bps=0.0),
    )

    assert with_funding.funding_return.abs().sum() > 0
    assert without_funding.funding_return.abs().sum() == 0


def test_prepare_inputs_requires_cash_column():
    """Backtest input contract requires CASH in prices/weights."""
    prices = _sample_prices().drop("CASH")
    weights = _sample_weights().drop("CASH")

    with pytest.raises(ValueError, match="prices must include CASH column"):
        run_backtest(prices=prices, weights=weights)


def test_prepare_inputs_requires_exact_timestamp_alignment():
    """Prices and weights timestamps must match exactly."""
    prices = _sample_prices()
    weights = _sample_weights().with_columns(
        pl.Series(
            "timestamp",
            [datetime(2024, 1, 1), datetime(2024, 1, 2), datetime(2024, 1, 4)],
        )
    )

    with pytest.raises(ValueError, match="must exactly match prices.timestamp"):
        run_backtest(prices=prices, weights=weights)


def test_backtest_result_dataframe_schema_remains_frozen():
    """Backtest result dataframe contract should not change when metrics expand."""
    result = run_backtest(
        prices=_sample_prices(),
        weights=_sample_weights(),
        config=BacktestConfig(include_funding=False, trade_cost_bps=0.0),
    )

    assert result.to_dataframe().columns == [
        "equity",
        "benchmark_equity",
        "price_return",
        "funding_return",
        "cost_return",
        "net_return",
        "turnover",
    ]
