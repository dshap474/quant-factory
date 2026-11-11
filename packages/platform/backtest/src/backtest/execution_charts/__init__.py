"""Public execution-chart assembly and rendering surface.

USAGE:
    >>> from backtest.execution_charts import render_execution_png
"""

# --------------------------------------------------------------------------- #
# Public surface
# --------------------------------------------------------------------------- #

from .api import (
    _assemble_chart_data as assemble_chart_data,
)
from .api import (
    _ExecutionChartData as ExecutionChartData,
)
from .api import (
    _RawFill as RawFill,
)
from .api import render_execution_png
from .rendering import render_chart_data

__all__ = [
    "ExecutionChartData",
    "RawFill",
    "assemble_chart_data",
    "render_chart_data",
    "render_execution_png",
]
