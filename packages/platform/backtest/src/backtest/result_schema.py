"""Canonical backtest result dataframe schema."""

from __future__ import annotations

import polars as pl

from .errors import BacktestContractError

BACKTEST_RESULT_COLUMNS: tuple[str, ...] = (
    "equity",
    "benchmark_equity",
    "price_return",
    "funding_return",
    "cost_return",
    "net_return",
    "turnover",
)


def validate_result_dataframe(df: pl.DataFrame) -> None:
    """Validate dataframe contract used by results persistence.

    This contract must remain stable because downstream systems and tests
    consume these exact columns.
    """
    cols = tuple(df.columns)
    if cols != BACKTEST_RESULT_COLUMNS:
        raise BacktestContractError(
            f"BacktestResult.to_dataframe() columns changed. Expected {BACKTEST_RESULT_COLUMNS}, got {cols}."
        )
