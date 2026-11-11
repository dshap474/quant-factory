"""Public execution-input preparation surface.

USAGE:
    >>> from backtest.preparation import prepare_execution_from_strategy_weights
"""

# --------------------------------------------------------------------------- #
# Public surface
# --------------------------------------------------------------------------- #

from .api import (
    PreparedExecutionInput,
    instrument_key_wire,
    prepare_execution_from_strategy_weights,
    prepared_execution_fingerprint,
    strategy_weights_fingerprint,
)
from .targets import ExecutionPolicy

__all__ = [
    "ExecutionPolicy",
    "PreparedExecutionInput",
    "instrument_key_wire",
    "prepare_execution_from_strategy_weights",
    "prepared_execution_fingerprint",
    "strategy_weights_fingerprint",
]
