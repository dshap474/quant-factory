"""Connector helpers from canonical strategy outputs to backtest inputs.

Purpose: materialize decision-time weights, normalize wide or panel prices, and
align the frames passed to the public backtest engine.

USAGE:
    result = run_backtest_from_strategy_weights(weights=weights, data=data)
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import TYPE_CHECKING

import polars as pl

from .api import run_backtest
from .config import BacktestConfig
from .result import BacktestResult

if TYPE_CHECKING:
    from strategies import StrategyWeights

    from .preparation import PreparedExecutionInput


def run_backtest_from_strategy_weights(
    *,
    weights: "StrategyWeights",
    data: pl.DataFrame | None = None,
    config: BacktestConfig | None = None,
    funding_rates: pl.DataFrame | None = None,
    timestamp_col: str = "timestamp",
    asset_col: str = "asset",
    price_col: str = "close",
    materialize_timing: bool = True,
    prepared_execution: "PreparedExecutionInput | None" = None,
) -> BacktestResult:
    """Run backtest directly from canonical ``StrategyWeights`` + strategy data.

    This is the stable interoperability seam for strategy packages:
    - Input: strategy output (`StrategyWeights`) and source data (panel or wide)
    - Output: canonical ``BacktestResult``

    When ``prepared_execution`` is provided, dispatch to the opt-in Nautilus
    path. ``data`` may be ``None`` only on that path. Legacy behavior is unchanged
    when ``prepared_execution`` is ``None``.
    """
    cfg = config or BacktestConfig()

    if getattr(weights, "quantity_limits", None) is not None or getattr(weights, "quantity_targets", None) is not None or (
        weights.weights.select(weights.assets).null_count().sum_horizontal().sum() > 0
    ):
        from .errors import BacktestUnsupportedFeatureError

        raise BacktestUnsupportedFeatureError(
            "nullable targets, quantity_limits and quantity_targets require the explicit run_intent_ledger path"
        )

    if prepared_execution is not None:
        from .engines.nautilus.runtime import run_isolated_prepared_execution
        from .errors import BacktestContractError, BacktestUnsupportedFeatureError
        from .preparation import (
            PreparedExecutionInput,
            prepared_execution_fingerprint,
            strategy_weights_fingerprint,
        )
        from .preparation.initial_state import initial_state_equity

        if cfg.engine != "nautilus":
            raise BacktestUnsupportedFeatureError(
                "prepared_execution requires engine='nautilus'; "
                f"got engine={cfg.engine!r}. The ordinary ledger cannot run prepared execution."
            )
        if not isinstance(prepared_execution, PreparedExecutionInput):
            raise BacktestContractError("prepared_execution must be PreparedExecutionInput")
        if strategy_weights_fingerprint(weights) != prepared_execution.strategy_weights_sha256:
            raise BacktestContractError("strategy weights do not match prepared_execution provenance")
        if prepared_execution_fingerprint(prepared_execution) != prepared_execution.prepared_payload_sha256:
            raise BacktestContractError("prepared execution integrity check failed")
        if prepared_execution.initial_state is not None:
            starting_equity = initial_state_equity(
                prepared_execution.initial_state,
                specs=prepared_execution.instrument_specs,
            )
            configured = Decimal(str(cfg.initial_capital))
            if starting_equity != configured:
                raise BacktestContractError(
                    f"initial state equity {starting_equity} does not match initial_capital {configured}"
                )
        return run_isolated_prepared_execution(prepared=prepared_execution, config=cfg)

    if data is None:
        raise ValueError("data is required when prepared_execution is None")

    prices = data_to_prices(
        data=data,
        assets=weights.assets,
        cash_col=weights.cash_col,
        timestamp_col=timestamp_col,
        asset_col=asset_col,
        price_col=price_col,
    )

    effective_weights = (
        materialize_effective_weights(
            weights=weights,
            prices=prices,
            timestamp_col=timestamp_col,
        )
        if materialize_timing
        else weights
    )

    aligned_prices, aligned_weights = align_prices_and_weights(
        prices=prices,
        weights=effective_weights.weights,
        timestamp_col=timestamp_col,
    )

    aligned_funding = None
    if funding_rates is not None:
        aligned_funding = align_frame_to_timestamps(
            frame=funding_rates,
            timestamps=aligned_prices.select(timestamp_col),
            timestamp_col=timestamp_col,
        )

    return run_backtest(
        prices=aligned_prices,
        weights=aligned_weights,
        funding_rates=aligned_funding,
        config=cfg,
        timestamp_col=timestamp_col,
    )


def data_to_prices(
    *,
    data: pl.DataFrame,
    assets: list[str],
    cash_col: str,
    timestamp_col: str,
    asset_col: str,
    price_col: str,
) -> pl.DataFrame:
    """Convert strategy data into wide price matrix consumed by backtest engines."""
    # Already wide format.
    if all(asset in data.columns for asset in assets):
        prices = data.select([timestamp_col] + assets)
        if cash_col not in prices.columns:
            prices = prices.with_columns(pl.lit(1.0).alias(cash_col))
        return prices

    # Panel format.
    if asset_col in data.columns and price_col in data.columns:
        panel = data.filter(pl.col(asset_col).is_in(assets))
        prices = panel.pivot(
            values=price_col,
            index=timestamp_col,
            on=asset_col,
        ).sort(timestamp_col)

        missing_assets = [asset for asset in assets if asset not in prices.columns]
        if missing_assets:
            raise ValueError(f"Panel data is missing price history for assets: {missing_assets}")

        value_cols = [c for c in prices.columns if c != timestamp_col]
        prices = prices.with_columns([pl.col(c).forward_fill().alias(c) for c in value_cols])
        leading_null_assets = [column for column in value_cols if prices.get_column(column).null_count() > 0]
        if leading_null_assets:
            names = ", ".join(leading_null_assets)
            raise ValueError(
                f"Panel prices contain leading null values for assets: {names}. "
                "Provide a price at or before the first backtest timestamp."
            )

        if cash_col not in prices.columns:
            prices = prices.with_columns(pl.lit(1.0).alias(cash_col))

        return prices

    raise ValueError(
        f"Data format not recognized. Expected either wide prices or panel [{timestamp_col}, {asset_col}, {price_col}]."
    )


def align_prices_and_weights(
    *,
    prices: pl.DataFrame,
    weights: pl.DataFrame,
    timestamp_col: str,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Align prices and weights on shared timestamps."""
    aligned_prices = align_frame_to_timestamps(
        frame=prices,
        timestamps=weights.select([timestamp_col]),
        timestamp_col=timestamp_col,
    )
    aligned_weights = align_frame_to_timestamps(
        frame=weights,
        timestamps=aligned_prices.select([timestamp_col]),
        timestamp_col=timestamp_col,
    )
    if aligned_prices.is_empty() or aligned_weights.is_empty():
        raise ValueError("No overlapping effective timestamps remain after aligning prices and weights")
    if aligned_prices.height != aligned_weights.height:
        raise ValueError("Aligned prices and weights must have identical row counts")
    return aligned_prices, aligned_weights


def align_frame_to_timestamps(
    *,
    frame: pl.DataFrame,
    timestamps: pl.DataFrame,
    timestamp_col: str,
) -> pl.DataFrame:
    """Filter a frame to an exact timestamp set and preserve sort order."""
    return frame.join(timestamps, on=timestamp_col, how="semi").sort(timestamp_col)


def materialize_effective_weights(
    *,
    weights: "StrategyWeights",
    prices: pl.DataFrame,
    timestamp_col: str = "timestamp",
) -> "StrategyWeights":
    """Expand decision-time target weights onto the effective price timeline."""
    if getattr(weights, "quantity_limits", None) is not None or getattr(weights, "quantity_targets", None) is not None or (
        weights.weights.select(weights.assets).null_count().sum_horizontal().sum() > 0
    ):
        from .errors import BacktestUnsupportedFeatureError

        raise BacktestUnsupportedFeatureError(
            "nullable targets, quantity_limits and quantity_targets require the explicit run_intent_ledger path"
        )

    price_ts = prices.select(timestamp_col).sort(timestamp_col)
    if price_ts.is_empty():
        raise ValueError("Cannot materialize effective weights without price timestamps")

    lag_bars = weights.execution.derive_lag_bars()
    decision = weights.weights.sort(timestamp_col)
    value_cols = [c for c in decision.columns if c != timestamp_col]

    effective = (
        decision.join(price_ts.with_row_index("__price_idx"), on=timestamp_col, how="inner")
        .with_columns((pl.col("__price_idx") + lag_bars).alias("__effective_idx"))
        .filter(pl.col("__effective_idx") < price_ts.height)
        .join(
            price_ts.with_row_index("__price_idx").rename({timestamp_col: "__effective_timestamp"}),
            left_on="__effective_idx",
            right_on="__price_idx",
            how="left",
        )
        .drop(["__price_idx", "__effective_idx", timestamp_col])
        .rename({"__effective_timestamp": timestamp_col})
        .select([timestamp_col] + value_cols)
        .group_by(timestamp_col, maintain_order=True)
        .agg([pl.col(c).last().alias(c) for c in value_cols])
        .sort(timestamp_col)
    )

    if effective.is_empty():
        raise ValueError("Execution timing removed all effective weight rows")

    expanded = (
        price_ts.join(effective, on=timestamp_col, how="left")
        .with_columns([pl.col(c).forward_fill() for c in value_cols])
        .drop_nulls()
        .sort(timestamp_col)
    )
    if expanded.is_empty():
        raise ValueError("Expanded effective weights are empty after applying execution timing")

    return replace(weights, weights=expanded, metadata=dict(weights.metadata))
