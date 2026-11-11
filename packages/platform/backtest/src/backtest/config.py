"""Backtest configuration.

USAGE: BacktestConfig(engine="ledger", rebalance_every_bars=7)
"""

from dataclasses import dataclass, field
from math import isfinite
from typing import Sequence

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class BacktestConfig:
    """Configuration for backtest simulation.

    Attributes:
        initial_capital: Starting portfolio value.
        trade_cost_bps: Transaction cost in basis points (e.g., 5.0 = 0.05%).
        include_funding: Whether to include funding rate contribution in PnL.
        frequency: Data frequency for annualization ("daily", "hourly", "4h", etc.).
        metrics: List of metric names to compute.
        benchmark: Asset to use for buy-and-hold benchmark (default: first asset).
        benchmark_asset: Deprecated alias for benchmark.
        collect_ledger_detail: Ordinary ledger only; also return the ledger's own per-interval
            positions, trades and asset cash flows as ``BacktestResult.ledger_detail``.
    """

    initial_capital: float = 100_000.0
    trade_cost_bps: float = 5.0
    include_funding: bool = True
    frequency: str = "daily"
    metrics: Sequence[str] = field(
        default_factory=lambda: [
            "sharpe",
            "max_drawdown",
            "total_return",
            "win_rate",
            "tracking_error",
            "information_ratio",
        ]
    )
    benchmark: str | None = None
    benchmark_asset: str | None = None
    engine: str = "nautilus"
    random_seed: int = 42
    allow_inactive_missing_prices: bool = False
    rebalance_every_bars: int = 1
    collect_ledger_detail: bool = False

    def __post_init__(self) -> None:
        """Validate numeric controls and keep the benchmark alias in sync."""
        if not isfinite(self.initial_capital) or self.initial_capital <= 0:
            raise ValueError("initial_capital must be finite and positive")
        if not isfinite(self.trade_cost_bps) or self.trade_cost_bps < 0:
            raise ValueError("trade_cost_bps must be finite and non-negative")
        if type(self.rebalance_every_bars) is not int or self.rebalance_every_bars < 1:
            raise ValueError("rebalance_every_bars must be a positive integer")
        if self.rebalance_every_bars != 1 and self.engine != "ledger":
            raise ValueError("rebalance_every_bars other than 1 requires engine='ledger'")
        if self.benchmark is None and self.benchmark_asset is not None:
            self.benchmark = self.benchmark_asset
        if self.benchmark_asset is None and self.benchmark is not None:
            self.benchmark_asset = self.benchmark
        if self.engine not in {"nautilus", "ledger"}:
            raise ValueError(
                "BacktestConfig.engine must be 'nautilus' or 'ledger'. Vectorized/auto engines were removed."
            )
        if not isinstance(self.allow_inactive_missing_prices, bool):
            raise ValueError("allow_inactive_missing_prices must be boolean")
        if self.allow_inactive_missing_prices and self.engine != "ledger":
            raise ValueError("allow_inactive_missing_prices requires engine='ledger'")
        if not isinstance(self.collect_ledger_detail, bool):
            raise ValueError("collect_ledger_detail must be boolean")
        if self.collect_ledger_detail and self.engine != "ledger":
            raise ValueError("collect_ledger_detail requires engine='ledger'")


# --------------------------------------------------------------------------- #
# Annualization
# --------------------------------------------------------------------------- #
ANNUALIZATION_FACTORS: dict[str, float] = {
    "daily": 252.0,
    "weekly": 52.0,
    "monthly": 12.0,
    "hourly": 24.0 * 252.0,
    "1h": 24.0 * 252.0,
    "5m": 12.0 * 24.0 * 252.0,
    "15m": 4.0 * 24.0 * 252.0,
    "30m": 2.0 * 24.0 * 252.0,
    "4h": 6.0 * 252.0,
    "8h": 3.0 * 252.0,
    "1d": 252.0,
    "minute": 60.0 * 24.0 * 252.0,
    "1m": 60.0 * 24.0 * 252.0,
}


def get_annualization_factor(frequency: str) -> float:
    """Get annualization factor for a given frequency."""
    if frequency not in ANNUALIZATION_FACTORS:
        raise ValueError(f"Unknown frequency: {frequency}. Use one of {list(ANNUALIZATION_FACTORS.keys())}")
    return ANNUALIZATION_FACTORS[frequency]
