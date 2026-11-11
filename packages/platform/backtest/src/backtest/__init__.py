"""Nautilus-backed backtest engine for portfolio simulation.

This module provides a high-performance backtest engine that simulates
portfolio returns from pre-computed weights. It's designed for rapid
strategy iteration where signal generation is decoupled from simulation.

Example:
    >>> import polars as pl
    >>> from backtest import run_backtest, BacktestConfig
    >>>
    >>> prices = pl.DataFrame({
    ...     "timestamp": ["2024-01-01", "2024-01-02", "2024-01-03"],
    ...     "BTC": [100.0, 110.0, 105.0],
    ...     "CASH": [1.0, 1.0, 1.0],
    ... })
    >>> weights = pl.DataFrame({
    ...     "timestamp": ["2024-01-01", "2024-01-02", "2024-01-03"],
    ...     "BTC": [0.6, 0.8, 0.5],
    ...     "CASH": [0.4, 0.2, 0.5],
    ... })
    >>> result = run_backtest(prices=prices, weights=weights)
    >>> print(result.metrics["sharpe"])
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

from execution import ExecutionResult, InstrumentSpec

__version__ = "0.1.0"

from .api import run_backtest
from .config import BacktestConfig, get_annualization_factor
from .connectors import materialize_effective_weights, run_backtest_from_strategy_weights
from .execution_sim import (
    ExecutionSimResult,
    FillAssumptions,
    simulate_execution,
    summarize_execution,
)
from .intent_ledger import IntentLedgerResult, run_intent_ledger
from .path_metrics import robust_sortino_ratio, sortino_ratio, summarize_path_risk
from .preparation import (
    PreparedExecutionInput,
    instrument_key_wire,
    prepare_execution_from_strategy_weights,
)
from .resting_limit import (
    PreparedRestingLimitInput,
    prepare_resting_limit_execution,
    prepared_resting_limit_fingerprint,
    run_resting_limit_backtest,
)
from .result import BacktestResult

# --------------------------------------------------------------------------- #
# Lazy chart export
# --------------------------------------------------------------------------- #


def render_execution_png(
    *,
    execution: ExecutionResult,
    bars: pl.DataFrame,
    instrument_spec: InstrumentSpec,
    output: Path,
    target_id: str | None = None,
    overwrite: bool = False,
) -> Path:
    """Render a prepared-execution chart without loading Matplotlib on import."""
    from .execution_charts import render_execution_png as render

    return render(
        execution=execution,
        bars=bars,
        instrument_spec=instrument_spec,
        output=output,
        target_id=target_id,
        overwrite=overwrite,
    )


__all__ = [
    "robust_sortino_ratio",
    "sortino_ratio",
    "summarize_path_risk",
    # Core API
    "run_backtest",
    "BacktestConfig",
    "BacktestResult",
    "get_annualization_factor",
    "run_backtest_from_strategy_weights",
    "materialize_effective_weights",
    "IntentLedgerResult",
    "run_intent_ledger",
    # Execution preparation (opt-in)
    "PreparedExecutionInput",
    "prepare_execution_from_strategy_weights",
    "instrument_key_wire",
    "render_execution_png",
    # Deterministic OHLC resting-limit execution
    "PreparedRestingLimitInput",
    "prepare_resting_limit_execution",
    "prepared_resting_limit_fingerprint",
    "run_resting_limit_backtest",
    # Parent-order execution simulator (1m OHLCV)
    "simulate_execution",
    "summarize_execution",
    "FillAssumptions",
    "ExecutionSimResult",
    # Runner (strategy integration)
]
