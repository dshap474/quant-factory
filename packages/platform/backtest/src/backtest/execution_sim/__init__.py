"""Parent-order execution simulator: policy cost versus a market order at the open.

USAGE:
    >>> from backtest.execution_sim import simulate_execution, summarize_execution  # doctest: +SKIP
"""

# --------------------------------------------------------------------------- #
# Public surface
# --------------------------------------------------------------------------- #

from .api import simulate_execution
from .assumptions import FillAssumptions
from .report import ExecutionSimResult, summarize_execution

__all__ = [
    "ExecutionSimResult",
    "FillAssumptions",
    "simulate_execution",
    "summarize_execution",
]
