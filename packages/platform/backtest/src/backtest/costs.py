"""Turnover and transaction cost computation."""

import numpy as np


def compute_turnover(*, weights: np.ndarray) -> np.ndarray:
    """Compute portfolio turnover from weight changes.

    Turnover = 0.5 × sum(|weight_delta|) because buying one asset requires selling another.

    Args:
        weights: Weight matrix, shape (T, N).

    Returns:
        Turnover per period, shape (T-1,). Values in [0, 1] range.
    """
    # Weight changes between periods
    deltas = np.diff(weights, axis=0)  # (T-1, N)

    # Half the sum of absolute changes (double-counting adjustment)
    return 0.5 * np.sum(np.abs(deltas), axis=1)  # (T-1,)


def compute_cost_returns(*, turnover: np.ndarray, trade_cost_bps: float) -> np.ndarray:
    """Compute transaction cost impact on returns.

    Args:
        turnover: Turnover per period, shape (T-1,).
        trade_cost_bps: Cost in basis points (e.g., 5.0 = 0.05%).

    Returns:
        Cost impact per period (negative values), shape (T-1,).
    """
    cost_rate = trade_cost_bps / 10_000.0
    return turnover * cost_rate
