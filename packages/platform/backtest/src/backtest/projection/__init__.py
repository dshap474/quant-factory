"""Public execution-ledger projection surface.

USAGE:
    >>> from backtest.projection import LinearPerpetualProjection
"""

# --------------------------------------------------------------------------- #
# Public surface
# --------------------------------------------------------------------------- #

from .linear_perpetual import LinearPerpetualProjection, ProjectionError
from .reporting import replay_reporting
from .streams import ResultStreams, build_result_streams

__all__ = [
    "LinearPerpetualProjection",
    "ProjectionError",
    "ResultStreams",
    "build_result_streams",
    "replay_reporting",
]
