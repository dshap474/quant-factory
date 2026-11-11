"""Fill assumptions for the parent-order simulator.

Purpose: the simulator-only assumptions the OHLCV kernel applies to every policy in one run. The
policies themselves (``execution.ParentOrderPolicy``) and their per-minute decisions live in the
execution core so backtest and live share one copy; named presets live in the execution
``policies`` extension.

USAGE:
    >>> from backtest.execution_sim.assumptions import FillAssumptions
    >>> FillAssumptions(touch_fill_prob=0.25, assumed_spread_bps=1.0).participation
    0.05
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from ..errors import BacktestContractError

# --------------------------------------------------------------------------- #
# Validation helpers
# --------------------------------------------------------------------------- #


def _finite_spread(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BacktestContractError(f"{name} must be a number")
    if not math.isfinite(value) or value < 0:
        raise BacktestContractError(f"{name} must be finite and non-negative")
    return float(value)


# --------------------------------------------------------------------------- #
# Fill assumptions
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class FillAssumptions:
    """Deterministic expected-value fill assumptions shared by every policy in one run."""

    touch_fill_prob: float = 0.5
    participation: float = 0.05
    assumed_spread_bps: float | Mapping[str, float] | None = None
    markout_minutes: tuple[int, ...] = (5, 15, 60)

    def __post_init__(self) -> None:
        prob = self.touch_fill_prob
        if isinstance(prob, bool) or not isinstance(prob, (int, float)) or not 0.0 <= prob <= 1.0:
            raise BacktestContractError("touch_fill_prob must be in [0, 1]")
        part = self.participation
        if isinstance(part, bool) or not isinstance(part, (int, float)) or not 0.0 < part <= 1.0:
            raise BacktestContractError("participation must be in (0, 1]")
        spread = self.assumed_spread_bps
        if isinstance(spread, Mapping):
            frozen = {str(k): _finite_spread(v, f"assumed_spread_bps[{k!r}]") for k, v in spread.items()}
            object.__setattr__(self, "assumed_spread_bps", MappingProxyType(frozen))
        elif spread is not None:
            object.__setattr__(self, "assumed_spread_bps", _finite_spread(spread, "assumed_spread_bps"))
        horizons = tuple(self.markout_minutes)
        if any(isinstance(h, bool) or not isinstance(h, int) or h <= 0 for h in horizons):
            raise BacktestContractError("markout_minutes must contain positive integers")
        if len(set(horizons)) != len(horizons):
            raise BacktestContractError("markout_minutes must be unique")
        object.__setattr__(self, "markout_minutes", horizons)

    def spread_bps_for(self, asset: str) -> float:
        """Assumed full spread in bps for one asset; raises when none applies."""
        spread = self.assumed_spread_bps
        if spread is None:
            raise BacktestContractError(f"bars lack bid/ask and assumed_spread_bps is unset (asset {asset!r})")
        if isinstance(spread, (int, float)):
            return float(spread)
        value = spread.get(asset)
        if value is None:
            raise BacktestContractError(f"assumed_spread_bps has no entry for asset {asset!r}")
        return float(value)
