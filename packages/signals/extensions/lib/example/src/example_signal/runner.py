"""Registered runner for the example family: BTC 30-day momentum sign and its volatility-scaled variant.

Registered ``planned`` so ``qf-signals list``, ``smoke`` and ``publish`` skip it; it is the
copyable scaffold, never production. Inputs are the daily BTC close from the public ``example``
feature panel (Yahoo Finance, credential-free) through the shared FeatureStore.

Point-in-time (AGENTS.md §2): the row stamped ``T`` uses closes through ``T`` and carries label
``T``; no shift. Consumers own the decision lag.

- ``vol_scaled=False``: ``prediction = sign(close_T / close_{T-30} - 1)``, the v002 control
  (v001's raw momentum sign).
- ``vol_scaled=True``: that sign times the inverse 20-day realized volatility relative to its
  expanding mean, winsorized at +/-3 (the v002 candidate).

USAGE:
    runner = ExampleRunner.from_preset("default", save=False, memory_version="v002")
    result = runner.run()   # in-process, nothing persisted
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports and constants
# --------------------------------------------------------------------------- #
from pathlib import Path
from typing import Any

import polars as pl
import yaml
from config import QUANT_DB_ROOT

from signals import SignalRegistry, SignalRunConfig, SignalRunner

FAMILY = "example"
PRESETS_DIR = Path(__file__).resolve().parents[2] / "presets"
VOL_SCALED = {"v001": False, "v002": True}

# --------------------------------------------------------------------------- #
# Prediction
# --------------------------------------------------------------------------- #


def predict(data: pl.DataFrame, config: dict[str, Any], vol_scaled: bool) -> pl.DataFrame:
    """``[timestamp, prediction]`` from ``[timestamp, close]``; warmup rows are dropped."""
    close = pl.col("close")
    prediction = (close / close.shift(config["lookback_days"]) - 1.0).sign()
    if vol_scaled:
        vol = (close / close.shift(1)).log().rolling_std(config["vol_lookback_days"]).shift(1)  # prior window
        prediction = (prediction * vol.cum_sum() / vol.cum_count() / vol).clip(-config["winsor"], config["winsor"])
    return data.select("timestamp", prediction.alias("prediction")).drop_nulls().filter(pl.col("prediction").is_finite())


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #


@SignalRegistry.register(
    FAMILY,
    description="Reference scaffold: BTC 30-day momentum sign, optionally scaled by inverse volatility",
    presets_dir="extensions/lib/example/presets",
    default_preset="default",
    output_type="time_series",
    runner_module="example_signal.runner",
    status="planned",
)
class ExampleRunner(SignalRunner):
    def __init__(self, config: dict[str, Any], *, version: str = "v002", save: bool = False,
                 db_root: Path | None = None) -> None:
        if version not in VOL_SCALED:
            raise ValueError(f"unknown example version {version!r}")
        self.config, self.vol_scaled = config, VOL_SCALED[version]
        super().__init__(SignalRunConfig(signal_id=config["name"], signal_type=FAMILY, save=save,
                                         db_root=db_root or QUANT_DB_ROOT))

    @classmethod
    def from_preset(cls, name: str, save: bool = False, db_root: Path | None = None,
                    memory_version: str = "v002") -> "ExampleRunner":
        config = yaml.safe_load((PRESETS_DIR / f"{name}.yaml").read_text(encoding="utf-8"))
        return cls(config, version=memory_version, save=save, db_root=db_root)

    def load_data(self) -> pl.DataFrame:
        """``[timestamp, close]`` for BTC, non-null closes only, sorted."""
        from data.api import FeatureStore, FeatureStoreConfig

        store = FeatureStore(FeatureStoreConfig(db_root=self.run_config.db_root))
        panel = store.read(
            "1d", self.config["feature_category"], columns=[self.config["close_column"]], assets=[self.config["asset"]]
        )
        return (
            panel.select(pl.col("timestamp").cast(pl.Datetime("us")), pl.col(self.config["close_column"]).alias("close"))
            .drop_nulls()
            .sort("timestamp")
        )

    def compute(self, data: pl.DataFrame) -> pl.DataFrame:
        return predict(data, self.config, self.vol_scaled)

    def get_config_dict(self) -> dict[str, Any]:
        return {**self.config, "vol_scaled": self.vol_scaled}


__all__ = ["ExampleRunner", "VOL_SCALED", "predict"]
