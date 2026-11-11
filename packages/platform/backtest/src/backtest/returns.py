"""Price-return and benchmark equity helpers.

``compute_price_returns`` remains the Nautilus/external lagged-weight formulation.
``compute_benchmark_equity`` is shared by Nautilus and the ordinary ledger.

USAGE:
    from backtest.returns import compute_benchmark_equity, compute_price_returns
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
import polars as pl

from .errors import BacktestContractError

# --------------------------------------------------------------------------- #
# Price returns (Nautilus / external callers)
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class PriceReturns:
    """Price return computation results."""

    asset_returns: np.ndarray
    portfolio_returns: np.ndarray


def compute_price_returns(*, prices: np.ndarray, weights: np.ndarray) -> PriceReturns:
    """Compute portfolio returns from prices and lagged weights."""
    asset_returns = (prices[1:] / prices[:-1]) - 1.0
    portfolio_returns = np.sum(weights[:-1] * asset_returns, axis=1)
    return PriceReturns(
        asset_returns=asset_returns,
        portfolio_returns=portfolio_returns,
    )


# --------------------------------------------------------------------------- #
# Benchmark equity (shared)
# --------------------------------------------------------------------------- #


def compute_benchmark_equity(
    *,
    prices_df: pl.DataFrame,
    asset_cols: Sequence[str],
    initial_capital: float,
    benchmark: str | None,
) -> pl.Series:
    """Buy-and-hold equity on the configured benchmark, else first non-CASH asset.

    Args:
        prices_df: Price frame including asset columns (CASH may be present).
        asset_cols: Non-CASH asset column names in price-column order.
        initial_capital: Starting capital for the benchmark path.
        benchmark: Optional explicit asset name; defaults to ``asset_cols[0]``.

    Returns:
        Series named ``benchmark_equity`` with one point per price row.

    Raises:
        BacktestContractError: If no non-CASH assets exist or the benchmark is missing.
    """
    if not asset_cols:
        raise BacktestContractError("Benchmark requires at least one non-CASH asset column.")
    benchmark_col = benchmark or asset_cols[0]
    if benchmark_col not in prices_df.columns:
        raise BacktestContractError(f"Benchmark asset '{benchmark_col}' not available in prices columns.")
    prices = prices_df.get_column(benchmark_col).to_numpy().astype(np.float64)
    if not np.all(np.isfinite(prices)) or np.any(prices <= 0.0):
        raise BacktestContractError(f"Benchmark asset '{benchmark_col}' has non-positive or non-finite prices.")
    equity = initial_capital * (prices / prices[0])
    return pl.Series("benchmark_equity", equity)
