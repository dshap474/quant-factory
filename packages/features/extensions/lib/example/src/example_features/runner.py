"""Compute or publish the example feature panel.

USAGE: ExampleRunner.from_preset(overrides={"save": True}).run()
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import polars as pl
from features.blocks import FeatureBlocks
from features.publication import run_feature_publication
from features.registry import FeatureRegistry

from .compute import SOURCE_RELPATH, compute_features
from .config import ExampleConfig

# --------------------------------------------------------------------------- #
# Publication entry point
# --------------------------------------------------------------------------- #

EXAMPLE_BLOCKS = FeatureBlocks(
    labels={"price": "Price", "returns": "Returns"},
    rules=(("price", ("close",)), ("returns", ("ret_*", "mom_*"))),
)


@FeatureRegistry.register(
    "example",
    asset_column=True,
    feature_blocks=EXAMPLE_BLOCKS,
    description="Example daily close, 1-day return and 30-day momentum (Yahoo BTC and four ETFs)",
)
class ExampleRunner:
    def __init__(self, config: ExampleConfig):
        self.config = config
        self.run_config = SimpleNamespace(
            category=config.category,
            resolution=config.resolution,
            save=config.save,
            force=config.force,
            description=config.description,
            require_asset_column=True,
            db_root=config.resolved_db_root(),
        )

    @classmethod
    def from_preset(cls, name: str | None = None, overrides: dict[str, Any] | None = None) -> "ExampleRunner":
        if name is not None:
            raise ValueError(f"example has no curated presets: {name!r}")
        return cls(ExampleConfig(**(overrides or {})))

    def load_data(self) -> None:
        return None

    def compute(self, data: None) -> pl.DataFrame:
        del data
        return compute_features(self.config)

    def get_config_dict(self) -> dict[str, Any]:
        return self.config.to_dict()

    def run(self):
        return run_feature_publication(self, require_asset_column=True)

    def get_meta_overrides(self, features: pl.DataFrame) -> dict[str, Any] | None:
        feature_columns = [c for c in features.columns if c not in {"timestamp", "asset"}]
        return {
            "lineage": {
                "sources": [SOURCE_RELPATH],
                "reporting_clock": {"row_date": "source bar close; no lag, no forward-fill"},
            },
            "viz": {"x_column": "timestamp", "y_default": "close", "y_candidates": feature_columns},
        }
