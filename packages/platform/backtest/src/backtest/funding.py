"""Funding rate P&L computation."""

import numpy as np


def compute_funding_returns(*, weights: np.ndarray, funding_rates: np.ndarray) -> np.ndarray:
    """Compute portfolio returns from funding rates.

    Funding convention: positive funding_rate means longs pay shorts.
    - Long positions (positive weight) lose money when funding is positive
    - Short positions (negative weight) gain money when funding is positive

    P&L = -weight × funding_rate (negative sign converts "longs pay" to "longs lose")

    Args:
        weights: Weight matrix, shape (T, N).
        funding_rates: Funding rate matrix, shape (T, N). Per-period rates (not annualized).

    Returns:
        Portfolio funding returns, shape (T-1,).
    """
    # Use lagged weights (weights at period start)
    weight_view = weights[:-1]  # (T-1, N)
    funding_view = funding_rates[:-1]  # (T-1, N)

    # Weighted sum of funding rates (negated: positive funding = longs pay = longs lose)
    return -np.sum(weight_view * funding_view, axis=1)  # (T-1,)
