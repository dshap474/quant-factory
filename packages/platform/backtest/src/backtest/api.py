"""Public API for the backtest package."""

from __future__ import annotations

import polars as pl

from .config import BacktestConfig
from .engines import run_ledger_backtest, run_nautilus_backtest
from .result import BacktestResult


def run_backtest(
    *,
    prices: pl.DataFrame,
    weights: pl.DataFrame,
    funding_rates: pl.DataFrame | None = None,
    config: BacktestConfig | None = None,
    timestamp_col: str = "timestamp",
) -> BacktestResult:
    """Run a backtest on the configured engine (default: Nautilus)."""
    cfg = config or BacktestConfig()

    if cfg.engine == "ledger":
        return run_ledger_backtest(
            prices=prices,
            weights=weights,
            funding_rates=funding_rates,
            config=cfg,
            timestamp_col=timestamp_col,
        )

    return run_nautilus_backtest(
        prices=prices,
        weights=weights,
        funding_rates=funding_rates,
        config=cfg,
        timestamp_col=timestamp_col,
    )
