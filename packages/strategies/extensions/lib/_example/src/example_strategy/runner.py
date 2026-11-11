"""Registered runner for the example family: an equal-weight ETF book and its momentum tilt.

Each daily decision is formed from closes through day t, stamped t, and acts on the next bar
(the default ``ExecutionTiming.next_bar``). Prices are the dividend-adjusted closes of four ETFs
from the public ``example`` feature panel; the window is every date on which all four have a row, through
the newest complete row.

- ``control``: equal weight, 1/4 each (the control in every SPEC).
- ``candidate``: equal weight scaled by ``1 + tilt``, where the tilt is 30-session momentum demeaned
  across the four ETFs and capped at +/-10% of equal weight, then renormalized so the book
  stays fully invested. v002 scales each asset's raw tilt by its inverse 20-session realized
  volatility (relative to the cross-sectional mean) before the cap.

USAGE:
    runner = ExampleRunner.from_preset("candidate", memory_version="v002")
    weights = runner.decide()     # decision history as StrategyWeights
    result = runner.run()         # the same book through the platform ledger at 5 bps
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports and constants
# --------------------------------------------------------------------------- #
from typing import Any

import polars as pl
from backtest import BacktestConfig

from strategies import StrategyRegistry, StrategyRunConfig, StrategyRunner, StrategyWeights

FAMILY = "example"
FEATURE_CATEGORY = "example"
ASSETS = ["us:SPY", "us:QQQ", "us:GLD", "us:TLT"]
LOOKBACK, VOL_LOOKBACK, CAP = 30, 20, 0.10

PRESETS = ("control", "candidate")
VOL_SCALED = {"v001": False, "v002": True}  # the one parameter the versions differ in

# --------------------------------------------------------------------------- #
# Weights
# --------------------------------------------------------------------------- #


def book_weights(prices: pl.DataFrame, preset: str, vol_scaled: bool) -> pl.DataFrame:
    """``[timestamp, ASSET..., CASH]`` from wide prices; rows before the lookbacks fill are dropped."""
    n = len(ASSETS)
    if preset == "control":
        return prices.select("timestamp", *[pl.lit(1.0 / n).alias(a) for a in ASSETS], pl.lit(0.0).alias("CASH"))
    momentum = prices.select("timestamp", *[(pl.col(a) / pl.col(a).shift(LOOKBACK) - 1.0).alias(a) for a in ASSETS])
    raw = momentum.select("timestamp", *[(pl.col(a) - pl.mean_horizontal(ASSETS)).alias(a) for a in ASSETS])
    if vol_scaled:
        vol = prices.select(*[(pl.col(a) / pl.col(a).shift(1)).log().rolling_std(VOL_LOOKBACK).shift(1).alias(a) for a in ASSETS])  # prior window
        inverse = vol.select(*[(pl.mean_horizontal(ASSETS) / pl.col(a)).alias(a) for a in ASSETS])
        raw = raw.select("timestamp", *[raw[a] * inverse[a] for a in ASSETS])
    held = raw.drop_nulls().select("timestamp", *[((1.0 + pl.col(a).clip(-CAP, CAP)) / n).alias(a) for a in ASSETS])
    total = pl.sum_horizontal(ASSETS)
    return held.select("timestamp", *[(pl.col(a) / total).alias(a) for a in ASSETS], pl.lit(0.0).alias("CASH"))


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
@StrategyRegistry.register(
    FAMILY,
    description="Reference scaffold: equal-weight ETF book and a capped 30-session momentum tilt",
    output_type="directional",
)
class ExampleRunner(StrategyRunner):
    def __init__(self, preset: str, *, version: str = "v002", save: bool = False) -> None:
        if preset not in PRESETS or version not in VOL_SCALED:
            raise ValueError(f"unknown example preset {preset!r} / version {version!r}")
        self.preset, self.vol_scaled = preset, VOL_SCALED[version]
        super().__init__(StrategyRunConfig(
            strategy_id=preset, preset_name=preset, strategy_type=FAMILY, save=save, memory_version=version,
            backtest_config=BacktestConfig(engine="ledger", trade_cost_bps=5.0,
                                           metrics=["sharpe", "max_drawdown", "total_return"]),
        ))

    @classmethod
    def from_preset(cls, preset: str, *, save: bool = False, memory_version: str = "v002") -> "ExampleRunner":
        return cls(preset, version=memory_version, save=save)

    def load_data(self) -> pl.DataFrame:
        """Wide adjusted closes ``[timestamp, us:SPY, us:QQQ, us:GLD, us:TLT]`` on common dates."""
        from data.api import FeatureStore, FeatureStoreConfig

        panel = FeatureStore(FeatureStoreConfig()).read("1d", FEATURE_CATEGORY, columns=["close"], assets=ASSETS)
        return panel.pivot(on="asset", index="timestamp", values="close").select("timestamp", *ASSETS).drop_nulls().sort("timestamp")

    def generate_weights(self, data: pl.DataFrame) -> StrategyWeights:
        return StrategyWeights(weights=book_weights(data, self.preset, self.vol_scaled), assets=list(ASSETS))

    def get_config_dict(self) -> dict[str, Any]:
        return dict(preset=self.preset, vol_scaled=self.vol_scaled, assets=ASSETS, lookback=LOOKBACK,
                    vol_lookback=VOL_LOOKBACK, cap=CAP)


__all__ = ["ASSETS", "ExampleRunner", "PRESETS", "VOL_SCALED", "book_weights"]
