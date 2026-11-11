"""Public Nautilus-backed portfolio engine surface.

USAGE:
    >>> from backtest.engines.nautilus import run_nautilus_backtest
"""

# --------------------------------------------------------------------------- #
# Public surface
# --------------------------------------------------------------------------- #

from .portfolio import run_nautilus_backtest

__all__ = ["run_nautilus_backtest"]
