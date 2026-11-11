"""Aggregation of return streams into equity curves."""

from dataclasses import dataclass

import numpy as np


@dataclass(slots=True)
class AggregatedSeries:
    """Aggregated return streams and equity curve."""

    price_return: np.ndarray
    funding_return: np.ndarray
    cost_return: np.ndarray
    net_return: np.ndarray
    equity_curve: np.ndarray
    turnover: np.ndarray


def aggregate_series(
    *,
    price_return: np.ndarray,
    funding_return: np.ndarray,
    cost_return: np.ndarray,
    turnover: np.ndarray,
    initial_equity: float,
) -> AggregatedSeries:
    """Aggregate return streams into an equity curve."""
    net_return = price_return + funding_return - cost_return
    equity_curve = build_equity_curve(net_return, initial_equity)
    return AggregatedSeries(
        price_return=price_return,
        funding_return=funding_return,
        cost_return=cost_return,
        net_return=net_return,
        equity_curve=equity_curve,
        turnover=turnover,
    )


def build_equity_curve(net_return: np.ndarray, initial_equity: float) -> np.ndarray:
    """Build cumulative equity curve from net returns."""
    equity_curve = np.empty(net_return.shape[0] + 1, dtype=np.float64)
    equity_curve[0] = float(initial_equity)
    if net_return.size > 0:
        equity_curve[1:] = initial_equity * np.cumprod(1.0 + net_return)
    return equity_curve
