"""Error types for backtest runtime selection and execution."""

from __future__ import annotations


class BacktestError(Exception):
    """Base class for backtest errors."""


class BacktestContractError(ValueError, BacktestError):
    """Raised when backtest input or output contracts are violated."""


class BacktestEngineUnavailableError(BacktestError):
    """Raised when a requested engine is unavailable in the environment."""


class BacktestUnsupportedFeatureError(BacktestError):
    """Raised when an engine cannot support the requested feature set."""


class BacktestEngineExecutionError(BacktestError):
    """Raised when an engine fails during execution."""
