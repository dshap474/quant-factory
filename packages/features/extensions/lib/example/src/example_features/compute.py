"""Build the example feature panel from the derived example price table.

Row ``T`` uses only closes through ``T``: the data layer already stamps each bar at its
own close, so no lag is applied here.

USAGE: compute_features(ExampleConfig(db_root="/tmp/db"))
"""

from __future__ import annotations

import polars as pl

from .config import ExampleConfig

# --------------------------------------------------------------------------- #
# Source contract
# --------------------------------------------------------------------------- #

SOURCE_RELPATH = "data/derived/1d/example/prices/data.parquet"


# --------------------------------------------------------------------------- #
# Panel assembly
# --------------------------------------------------------------------------- #


def compute_features(config: ExampleConfig) -> pl.DataFrame:
    window = config.momentum_window
    panel = (
        pl.scan_parquet(config.resolved_db_root() / SOURCE_RELPATH)
        .select(
            pl.col("timestamp").dt.replace_time_zone(None),
            "asset",
            pl.col("close").cast(pl.Float64),
        )
        .sort("asset", "timestamp")
        .with_columns(
            (pl.col("close") / pl.col("close").shift(1) - 1).over("asset").alias("ret_1d"),
            (pl.col("close") / pl.col("close").shift(window) - 1).over("asset").alias(f"mom_{window}d"),
        )
        .collect()
    )
    duplicates = panel.select(pl.struct("timestamp", "asset").is_duplicated().sum()).item()
    if duplicates:
        raise ValueError(f"example panel has {duplicates} duplicate (timestamp, asset) rows")
    return panel
