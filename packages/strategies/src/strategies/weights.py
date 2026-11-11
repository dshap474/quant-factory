"""Canonical weights matrix for all strategies.

This module defines StrategyWeights, the unified output format
that ALL strategies produce regardless of type (time-series or cross-sectional).

The weights matrix is a wide DataFrame:
    [timestamp, ASSET1, ASSET2, ..., CASH]

Each row is one decision. Its timestamp is the decision time and the
information cutoff: the row uses nothing observed after it. Complete rows sum
to 1.0. On a partial row, a null asset target holds its actual quantity and
CASH must be null because its eventual weight depends on the account at
execution. ``strategy_id`` and ``version`` identify the producing strategy.
An optional ``observed_through`` series records, per row, the latest instant
the decision's inputs actually observed; each value must precede its row.
Optional ``quantity_targets`` request an absolute final held quantity per asset,
frozen at the decision (single risky asset, nonnegative; the weight on that asset
and CASH are null). A null quantity target leaves the weight/hold rules in force.
"""

from __future__ import annotations

import functools
import json
import math
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import polars as pl

_LIMITS_COLUMN = "__strategy_quantity_limits__"
_TARGETS_COLUMN = "__strategy_quantity_targets__"
_OBSERVED_COLUMN = "__strategy_observed_through__"
_METADATA_KEY = "strategy_weights"


def _validate_json_value(value: Any, label: str) -> None:
    """Reject values that JSON would silently coerce or serialize non-finitely."""
    if value is None or type(value) in (str, int, bool):
        return
    if type(value) is float:
        if math.isfinite(value):
            return
        raise ValueError(f"{label} must be finite")
    if type(value) is list:
        for index, item in enumerate(value):
            _validate_json_value(item, f"{label}[{index}]")
        return
    if type(value) is dict:
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{label} keys must be strings")
            _validate_json_value(item, f"{label}.{key}")
        return
    raise ValueError(f"{label} must contain JSON-native values")


def _require_numeric(frame: pl.DataFrame, columns: list[str], label: str) -> None:
    """Reject non-numeric value columns; Null-typed columns pass.

    The test depends only on the dtype class, so one instance per class is checked (a
    wide row can have hundreds of Float64 columns); the per-column pass runs only to name the first
    offending column.
    """
    dtypes = dict(zip(frame.columns, frame.dtypes, strict=True))
    selected = list(map(dtypes.__getitem__, columns))
    classes = dict(zip(map(type, selected), selected, strict=True))
    if all(dtype == pl.Null or dtype.is_numeric() for dtype in classes.values()):
        return
    for column in columns:
        dtype = dtypes[column]
        if dtype != pl.Null and not dtype.is_numeric():
            raise ValueError(f"{label}.{column} must be numeric")


def _require_finite(frame: pl.DataFrame, columns: list[str], label: str, row: dict | None = None) -> None:
    """Reject NaN/inf values; nulls pass. One-row frames skip per-column expressions."""
    if frame.height == 1:
        row = frame.row(0, named=True) if row is None else row
        bad = [c for c in columns if row[c] is not None and not math.isfinite(row[c])]
    else:
        flags = frame.select(
            [(~pl.col(c).cast(pl.Float64).is_finite().fill_null(True)).any().alias(c) for c in columns]
        ).row(0)
        bad = [c for c, flag in zip(columns, flags) if flag]
    if bad:
        raise ValueError(f"{label}.{bad[0]} must be finite")


@functools.lru_cache(maxsize=64)
def _plain_asset_names(assets: tuple[str, ...]) -> bool:
    """Whether str asset names pass every assets-only check in ``StrategyWeights.__post_init__``.

    Pure in the names, so memoized: a run builds thousands of one-row decisions over one asset list.
    """
    return (bool(assets) and all(asset.strip() for asset in assets)
            and len(set(assets)) == len(assets) and "timestamp" not in assets)


def _stack(frames: list[pl.DataFrame], columns: list[str]) -> pl.DataFrame:
    """Vertically join frames in ``columns`` order as one contiguous chunk."""
    frames = [f if f.columns == columns else f.select(columns) for f in frames]
    return pl.concat(frames, how="vertical_relaxed", rechunk=True)

if TYPE_CHECKING:
    from typing import Protocol

    class PortfolioWeights(Protocol):
        long_assets: list[str]
        short_assets: list[str]

        def to_wide(self) -> pl.DataFrame: ...



class ExecutionMode(StrEnum):
    """Shared timing contract for bar-based strategy execution."""

    SAME_BAR = "same_bar"
    NEXT_BAR = "next_bar"
    LAG_BARS = "lag_bars"


class RebalanceMode(StrEnum):
    """Position-transition contract owned by strategy decisions."""

    NET_TARGET = "net_target"
    FLAT_THEN_TARGET = "flat_then_target"


@dataclass(frozen=True, slots=True)
class ExecutionTiming:
    """Execution timing semantics for canonical strategy weights.

    ``weights.timestamp`` is always interpreted as the decision timestamp.
    The backtest seam materializes an effective schedule from this contract.
    """

    mode: ExecutionMode = ExecutionMode.NEXT_BAR
    lag_bars: int = 0
    timestamp_semantics: str = "decision"
    rebalance_mode: RebalanceMode = RebalanceMode.NET_TARGET
    entry_delay_seconds: int = 0

    def __post_init__(self) -> None:
        if self.timestamp_semantics != "decision":
            raise ValueError("ExecutionTiming.timestamp_semantics must be 'decision'")
        if self.mode == ExecutionMode.SAME_BAR and self.lag_bars != 0:
            raise ValueError("same_bar execution cannot specify lag_bars")
        if self.mode == ExecutionMode.NEXT_BAR and self.lag_bars != 0:
            raise ValueError("next_bar execution cannot specify lag_bars")
        if self.mode == ExecutionMode.LAG_BARS and self.lag_bars < 1:
            raise ValueError("lag_bars execution requires lag_bars >= 1")
        if self.entry_delay_seconds < 0:
            raise ValueError("entry_delay_seconds must be non-negative")

    @classmethod
    def same_bar(
        cls,
        *,
        rebalance_mode: RebalanceMode = RebalanceMode.NET_TARGET,
        entry_delay_seconds: int = 0,
    ) -> "ExecutionTiming":
        return cls(
            mode=ExecutionMode.SAME_BAR,
            rebalance_mode=rebalance_mode,
            entry_delay_seconds=entry_delay_seconds,
        )

    @classmethod
    def next_bar(
        cls,
        *,
        rebalance_mode: RebalanceMode = RebalanceMode.NET_TARGET,
        entry_delay_seconds: int = 0,
    ) -> "ExecutionTiming":
        return cls(
            mode=ExecutionMode.NEXT_BAR,
            rebalance_mode=rebalance_mode,
            entry_delay_seconds=entry_delay_seconds,
        )

    @classmethod
    def lagged(cls, lag_bars: int) -> "ExecutionTiming":
        return cls(mode=ExecutionMode.LAG_BARS, lag_bars=lag_bars)

    def derive_lag_bars(self) -> int:
        if self.mode == ExecutionMode.SAME_BAR:
            return 0
        if self.mode == ExecutionMode.NEXT_BAR:
            return 1
        return self.lag_bars


@dataclass
class StrategyWeights:
    """Canonical weights matrix for ALL strategies.

    This is the unified output format that all strategies produce.
    The backtest engine consumes this format directly.

    Format:
        Wide DataFrame with columns [timestamp, ASSET1, ASSET2, ..., CASH]
        - Complete rows sum to 1.0
        - A null asset target means hold actual quantity; CASH is null on
          every such partial row
        - Works for 1 asset (single-asset strategies) or N assets (cross-sectional)
        - CASH column represents uninvested capital

    Example:
        >>> # Single-asset strategy
        >>> weights = StrategyWeights(
        ...     weights=pl.DataFrame({
        ...         "timestamp": [t1, t2],
        ...         "BTC": [0.5, -0.3],
        ...         "CASH": [0.5, 1.3],  # 0.5 + 0.5 = 1.0, -0.3 + 1.3 = 1.0
        ...     }),
        ...     assets=["BTC"],
        ... )

        >>> # Multi-asset strategy
        >>> weights = StrategyWeights(
        ...     weights=pl.DataFrame({
        ...         "timestamp": [t1, t2],
        ...         "BTC": [0.2, 0.25],
        ...         "ETH": [0.2, 0.15],
        ...         "SOL": [-0.1, -0.15],
        ...         "CASH": [0.7, 0.75],
        ...     }),
        ...     assets=["BTC", "ETH", "SOL"],
        ... )

    Attributes:
        weights: Wide-format DataFrame with [timestamp, ASSET1, ..., CASH].
        assets: List of asset columns (excludes timestamp and cash_col).
        cash_col: Name of cash column. Default "CASH".
    execution: Shared execution timing semantics for these decision-time weights.
    metadata: Optional metadata (e.g., source strategy, creation time).
    quantity_limits: Optional aligned per-asset signed remaining quantities.
    observed_through: Optional per-row input watermark, same dtype as ``timestamp``.
    quantity_targets: Optional aligned per-asset absolute final quantities (see module doc).
    strategy_id: Producing strategy; ``StrategyRunner`` stamps it from its config.
    version: Producing strategy memory version (``vNNN``), stamped the same way.
    """

    weights: pl.DataFrame
    assets: list[str]
    cash_col: str = "CASH"
    execution: ExecutionTiming = field(default_factory=ExecutionTiming.next_bar)
    metadata: dict[str, Any] = field(default_factory=dict)
    # Signed, frozen remaining-position bounds at each decision. Positive q
    # allows final long quantity [0, min(current long, q)]; negative q allows
    # final short quantity [max(current short, q), 0]; zero forces flat; null
    # is unconstrained. Consumers intersect again with actual holdings at fill.
    quantity_limits: pl.DataFrame | None = None
    observed_through: pl.Series | None = None
    strategy_id: str | None = None
    version: str | None = None
    # Absolute final held quantity requested at the decision (long/cash, one risky
    # asset); executed against actual holdings and fee-affordable cash at the fill.
    quantity_targets: pl.DataFrame | None = None

    def __post_init__(self) -> None:
        """Validate DataFrame structure."""
        weight_columns = set(self.weights.columns)
        if not (isinstance(self.assets, (list, tuple)) and set(map(type, self.assets)) == {str}
                and _plain_asset_names(tuple(self.assets))):
            # Not a known-good list of plain str names: run each check so the first failure names itself.
            if not self.assets:
                raise ValueError("weights.assets must contain at least one asset")
            if any(not isinstance(asset, str) or not asset.strip() for asset in self.assets):
                raise ValueError("weights.assets must contain non-empty strings")
            if len(set(self.assets)) != len(self.assets):
                raise ValueError("weights.assets must be unique")
            if "timestamp" in self.assets:
                raise ValueError("weights.assets must not contain timestamp")
        if self.cash_col in self.assets:
            raise ValueError("weights.assets must not contain cash_col")
        if not isinstance(self.cash_col, str) or not self.cash_col.strip():
            raise ValueError("weights.cash_col must be a non-empty string")
        if self.cash_col == "timestamp":
            raise ValueError("weights.cash_col must not be timestamp")
        for reserved in (_LIMITS_COLUMN, _TARGETS_COLUMN, _OBSERVED_COLUMN):
            if reserved in weight_columns or reserved in self.assets:
                raise ValueError(f"weights may not use reserved column {reserved!r}")
        if not isinstance(self.execution, ExecutionTiming):
            raise ValueError("weights.execution must be ExecutionTiming")
        if not isinstance(self.execution.mode, ExecutionMode) or not isinstance(self.execution.rebalance_mode, RebalanceMode):
            raise ValueError("weights.execution modes must use declared enums")
        if not isinstance(self.metadata, dict):
            raise ValueError("weights.metadata must be a dict")
        for name in ("strategy_id", "version"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"weights.{name} must be a non-empty string or None")

        # Check timestamp column exists
        if "timestamp" not in weight_columns:
            raise ValueError("weights DataFrame must have 'timestamp' column")

        # Check for duplicate timestamps
        n_rows = len(self.weights)
        n_unique = self.weights["timestamp"].n_unique() if n_rows > 1 else n_rows
        if n_unique != n_rows:
            raise ValueError(
                f"weights DataFrame has duplicate timestamps: {n_rows} rows but only {n_unique} unique timestamps"
            )

        # Check cash column exists
        if self.cash_col not in weight_columns:
            raise ValueError(f"weights DataFrame must have '{self.cash_col}' column")

        if weight_columns != {"timestamp", *self.assets, self.cash_col}:
            missing = next((asset for asset in self.assets if asset not in weight_columns), None)
            if missing is not None:
                raise ValueError(f"Asset '{missing}' not found in weights columns")
            raise ValueError("weights columns must match timestamp, assets, and cash_col exactly")
        for name in ("quantity_limits", "quantity_targets"):
            aligned = getattr(self, name)
            if aligned is None:
                continue
            if not isinstance(aligned, pl.DataFrame):
                raise ValueError(f"{name} must be a Polars DataFrame")
            if set(aligned.columns) != {"timestamp", *self.assets}:
                raise ValueError(f"{name} columns must match timestamp and assets exactly")
            if len(aligned) != len(self.weights) or not aligned["timestamp"].equals(self.weights["timestamp"]):
                raise ValueError(f"{name} timestamps must align row-for-row with weights")
        if self.observed_through is not None:
            if not isinstance(self.observed_through, pl.Series) or len(self.observed_through) != len(self.weights):
                raise ValueError("observed_through must be a Series aligned row-for-row with weights")
            if self.observed_through.dtype != self.weights.schema["timestamp"]:
                raise ValueError("observed_through must share the timestamp dtype")

    def validate(self, tolerance: float = 1e-6) -> None:
        """Validate complete targets and partial hold rows.

        Args:
            tolerance: Maximum allowed deviation from 1.0.

        Raises:
            ValueError: If any row does not sum to 1.0 within tolerance.
        """
        timestamps = self.weights["timestamp"]
        if timestamps.dtype != pl.Date and not isinstance(timestamps.dtype, pl.Datetime):
            raise ValueError("weights.timestamp must be date/datetime")
        if timestamps.null_count() or not timestamps.is_sorted():
            raise ValueError("weights.timestamp must be non-null and strictly increasing")
        value_columns = [*self.assets, self.cash_col]
        _require_numeric(self.weights, value_columns, "weights")
        row = self.weights.row(0, named=True) if self.weights.height == 1 else None
        _require_finite(self.weights, value_columns, "weights", row)
        if row is not None:
            # Per-decision hot path: Python over one row beats ~850 polars expressions.
            targets, cash = [row[asset] for asset in self.assets], row[self.cash_col]
            partial_row = any(target is None for target in targets)
            if partial_row != (cash is None):
                raise ValueError("CASH must be null exactly when an asset target is null")
            row_sums = [] if partial_row else [sum(targets) + cash]
        else:
            partial = self.weights.select(pl.any_horizontal(pl.col(self.assets).is_null())).to_series()
            if not partial.equals(self.weights[self.cash_col].is_null()):
                raise ValueError("CASH must be null exactly when an asset target is null")
            row_sums = self.weights.filter(~partial).select(value_columns).sum_horizontal().to_list()
        invalid = [float(total) for total in row_sums if abs(float(total) - 1.0) > tolerance]
        if invalid:
            raise ValueError(
                f"Weights must sum to 1.0 per row (tolerance={tolerance}). "
                f"Found {len(invalid)} invalid rows. Sample sums: {invalid[:3]}"
            )
        if self.quantity_limits is not None:
            limits = self.quantity_limits
            _require_numeric(limits, self.assets, "quantity_limits")
            _require_finite(limits, self.assets, "quantity_limits")
        if self.quantity_targets is not None:
            self._validate_quantity_targets()
        if self.observed_through is not None and (self.observed_through >= timestamps).any():
            raise ValueError("observed_through must precede each decision timestamp")
        _validate_json_value(self.metadata, "weights.metadata")

    def _validate_quantity_targets(self) -> None:
        """Numeric targets: finite, nonnegative, one risky asset, null weight/CASH, no overlapping limit."""
        targets = self.quantity_targets
        assert targets is not None
        _require_numeric(targets, self.assets, "quantity_targets")
        _require_finite(targets, self.assets, "quantity_targets")
        numeric = targets.select(pl.col(self.assets).is_not_null())
        if not numeric.select(pl.any_horizontal(pl.all()).any()).item():
            return
        if len(self.assets) != 1:
            raise ValueError("quantity_targets support exactly one risky asset")
        if targets.select((pl.col(self.assets) < 0).any()).row(0) != (False,) * len(self.assets):
            raise ValueError("quantity_targets must be nonnegative (long/cash only)")
        rows = numeric.select(pl.any_horizontal(pl.all())).to_series()
        for asset in self.assets:
            if self.weights.filter(numeric[asset])[asset].null_count() != int(numeric[asset].sum()):
                raise ValueError(f"a numeric quantity target requires a null weight target on {asset}")
            if self.quantity_limits is not None and self.quantity_limits.filter(numeric[asset])[asset].null_count() != int(numeric[asset].sum()):
                raise ValueError(f"quantity_targets and quantity_limits cannot both be numeric on {asset}")
        if self.weights.filter(rows)[self.cash_col].null_count() != int(rows.sum()):
            raise ValueError("a numeric quantity target requires null CASH")

    @property
    def n_assets(self) -> int:
        """Number of tradeable assets (excluding cash)."""
        return len(self.assets)

    @property
    def n_timestamps(self) -> int:
        """Number of timestamps in weights matrix."""
        return len(self.weights)

    def get_asset_exposure(self, asset: str) -> pl.Series:
        """Get weight time series for a specific asset."""
        if asset not in self.assets:
            raise ValueError(f"Asset '{asset}' not in weights")
        return self.weights.get_column(asset)

    def get_gross_exposure(self) -> pl.Series:
        """Compute gross exposure (sum of absolute weights) per timestamp."""
        return self.weights.select(self.assets).select(pl.all().abs()).sum_horizontal(ignore_nulls=False)

    def get_net_exposure(self) -> pl.Series:
        """Compute net exposure (sum of weights, excluding cash) per timestamp."""
        return self.weights.select(self.assets).sum_horizontal(ignore_nulls=False)

    def is_market_neutral(self, tolerance: float = 0.01) -> bool:
        """Check if portfolio is market neutral (net exposure near 0)."""
        net = self.get_net_exposure()
        max_abs_net = net.abs().max()
        return net.null_count() == 0 and max_abs_net is not None and cast(float, max_abs_net) <= tolerance

    def save(self, path: str | Path) -> None:
        """Save the full decision contract in one Parquet file."""
        self.validate()
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "assets": self.assets,
            "cash_col": self.cash_col,
            "execution": {
                "mode": self.execution.mode.value,
                "lag_bars": self.execution.lag_bars,
                "timestamp_semantics": self.execution.timestamp_semantics,
                "rebalance_mode": self.execution.rebalance_mode.value,
                "entry_delay_seconds": self.execution.entry_delay_seconds,
            },
            "metadata": self.metadata,
            "quantity_limits": self.quantity_limits is not None,
            "observed_through": self.observed_through is not None,
            "identity": {"strategy_id": self.strategy_id, "version": self.version},
        }
        if self.quantity_targets is not None:
            payload["quantity_targets"] = True  # absent key: an artifact without quantity targets
        frame = self.weights
        for aligned, column in ((self.quantity_limits, _LIMITS_COLUMN), (self.quantity_targets, _TARGETS_COLUMN)):
            if aligned is not None:
                values = aligned.select(self.assets)
                frame = frame.with_columns(values.select(pl.struct(self.assets).alias(column)).to_series())
        if self.observed_through is not None:
            frame = frame.with_columns(self.observed_through.alias(_OBSERVED_COLUMN))
        frame.write_parquet(
            path,
            compression="zstd",
            compression_level=3,
            metadata={_METADATA_KEY: json.dumps(payload, allow_nan=False)},
        )

    @classmethod
    def from_parquet(
        cls,
        path: str | Path,
        cash_col: str = "CASH",
    ) -> "StrategyWeights":
        """Load weights from parquet file.

        Args:
            path: Path to parquet file.
            cash_col: Name of cash column.

        Returns:
            StrategyWeights instance.
        """
        weights = pl.read_parquet(path)
        raw = pl.read_parquet_metadata(path).get(_METADATA_KEY)
        if raw is None:
            if {_LIMITS_COLUMN, _TARGETS_COLUMN, _OBSERVED_COLUMN} & set(weights.columns):
                raise ValueError("quantity limits/targets and observed_through require StrategyWeights metadata")
            assets = [c for c in weights.columns if c not in ("timestamp", cash_col)]
            return cls(weights=weights, assets=assets, cash_col=cash_col)
        payload = json.loads(raw)
        if payload.get("version") != 1:
            raise ValueError("Unsupported StrategyWeights artifact version")
        saved_cash = payload["cash_col"]
        if cash_col != "CASH" and cash_col != saved_cash:
            raise ValueError("cash_col conflicts with saved StrategyWeights contract")
        assets = payload["assets"]
        limits = None
        if payload["quantity_limits"]:
            if _LIMITS_COLUMN not in weights.columns:
                raise ValueError("StrategyWeights artifact is missing quantity limits")
            limits = pl.concat([weights.select("timestamp"), weights[_LIMITS_COLUMN].struct.unnest()], how="horizontal")
            weights = weights.drop(_LIMITS_COLUMN)
        elif _LIMITS_COLUMN in weights.columns:
            raise ValueError("Unexpected quantity limits column in StrategyWeights artifact")
        targets = None
        if payload.get("quantity_targets", False) != (_TARGETS_COLUMN in weights.columns):
            raise ValueError("StrategyWeights artifact quantity_targets column disagrees with its metadata")
        if _TARGETS_COLUMN in weights.columns:
            targets = pl.concat([weights.select("timestamp"), weights[_TARGETS_COLUMN].struct.unnest()], how="horizontal")
            weights = weights.drop(_TARGETS_COLUMN)
        observed = None
        if payload.get("observed_through", False) != (_OBSERVED_COLUMN in weights.columns):
            raise ValueError("StrategyWeights artifact observed_through column disagrees with its metadata")
        if _OBSERVED_COLUMN in weights.columns:
            observed = weights[_OBSERVED_COLUMN].alias("observed_through")
            weights = weights.drop(_OBSERVED_COLUMN)
        timing = payload["execution"]
        execution = ExecutionTiming(
            mode=ExecutionMode(timing["mode"]),
            lag_bars=timing["lag_bars"],
            timestamp_semantics=timing["timestamp_semantics"],
            rebalance_mode=RebalanceMode(timing["rebalance_mode"]),
            entry_delay_seconds=timing["entry_delay_seconds"],
        )
        result = cls(
            weights=weights,
            assets=assets,
            cash_col=saved_cash,
            execution=execution,
            metadata=payload["metadata"],
            quantity_limits=limits,
            observed_through=observed,
            strategy_id=payload.get("identity", {}).get("strategy_id"),
            version=payload.get("identity", {}).get("version"),
            quantity_targets=targets,
        )
        result.validate()
        return result

    def slice(self, offset: int, length: int = 1) -> "StrategyWeights":
        """Return decision rows ``[offset, offset + length)`` with the same contract."""
        return replace(
            self,
            weights=self.weights.slice(offset, length),
            metadata=dict(self.metadata),
            quantity_limits=(self.quantity_limits.slice(offset, length)
                             if self.quantity_limits is not None else None),
            observed_through=(self.observed_through.slice(offset, length)
                              if self.observed_through is not None else None),
            quantity_targets=(self.quantity_targets.slice(offset, length)
                              if self.quantity_targets is not None else None),
        )

    @classmethod
    def concat(cls, parts: Sequence["StrategyWeights"]) -> "StrategyWeights":
        """Join decision histories that share one contract into one artifact.

        Usage: ``history = StrategyWeights.concat([yesterday, today])``.
        Parts must agree on assets, cash, timing, metadata and identity; a part
        without limits, quantity targets or ``observed_through`` contributes null rows for them.
        """
        if not parts:
            raise ValueError("concat requires at least one StrategyWeights")
        first = parts[0]
        for part in parts[1:]:
            if (part.assets != first.assets or part.cash_col != first.cash_col
                    or part.execution != first.execution or part.metadata != first.metadata
                    or part.strategy_id != first.strategy_id or part.version != first.version):
                raise ValueError("concat parts must share assets, cash, timing, metadata and identity")
        def aligned(name: str) -> pl.DataFrame | None:
            if all(getattr(part, name) is None for part in parts):
                return None
            return _stack(
                [getattr(part, name) if getattr(part, name) is not None else
                 part.weights.select("timestamp", *[pl.lit(None, pl.Float64).alias(a) for a in first.assets])
                 for part in parts],
                ["timestamp", *first.assets],
            )

        limits, targets = aligned("quantity_limits"), aligned("quantity_targets")
        observed = None
        if any(part.observed_through is not None for part in parts):
            observed = pl.concat(
                [part.observed_through if part.observed_through is not None else
                 pl.Series("observed_through", [None] * part.n_timestamps, part.weights.schema["timestamp"])
                 for part in parts],
                rechunk=True,
            )
        result = replace(
            first,
            weights=_stack([part.weights for part in parts], first.weights.columns),
            metadata=dict(first.metadata),
            quantity_limits=limits,
            observed_through=observed,
            quantity_targets=targets,
        )
        result.validate()
        return result

    @classmethod
    def from_portfolio_weights(
        cls,
        pw: "PortfolioWeights",
        cash_col: str = "CASH",
        neutrality_tolerance: float = 0.01,
        target_gross_exposure: float | None = None,
    ) -> "StrategyWeights":
        """Convert from cross-sectional PortfolioWeights.

        Cross-sectional portfolios are market-neutral (weights sum to 0).
        We optionally scale weights to a target gross exposure and add a CASH
        column so rows sum to 1.0.

        Args:
            pw: PortfolioWeights from cross-sectional pipeline.
            cash_col: Name of cash column to add.
            neutrality_tolerance: Max allowed net exposure before warning.
            target_gross_exposure: Optional gross exposure target. If None,
                weights are left as-is (no rescaling).

        Returns:
            StrategyWeights with normalized rows and 1x leverage.

        Warns:
            If portfolio is not market-neutral (net exposure > tolerance).
        """
        import warnings

        # Pivot to wide format
        wide = pw.to_wide()

        # Identify asset columns
        assets = [c for c in wide.columns if c != "timestamp"]

        # Optionally scale weights so gross exposure = target_gross_exposure
        # If target_gross_exposure is None, preserve optimizer output.
        if target_gross_exposure is not None:
            gross_exposure = wide.select(assets).select(pl.all().abs()).sum_horizontal()

            wide = wide.with_columns(
                [
                    pl.when(gross_exposure > 1e-9)
                    .then(pl.col(col) * target_gross_exposure / gross_exposure)
                    .otherwise(pl.col(col))
                    .alias(col)
                    for col in assets
                ]
            )

        # Validate market neutrality after scaling
        net_exposure = wide.select(assets).sum_horizontal()
        max_net = net_exposure.abs().max()
        if max_net is not None and cast(float, max_net) > neutrality_tolerance:
            warnings.warn(
                f"Portfolio not market-neutral: max net exposure = {max_net:.4f}. "
                f"This may cause unintended directional bias. "
                f"Check portfolio optimizer output.",
                UserWarning,
                stacklevel=2,
            )

        # Compute net exposure after scaling (should still be ~0 for market-neutral)
        asset_sum = net_exposure

        # Compute cash to make rows sum to 1.0
        wide = wide.with_columns((1.0 - asset_sum).alias(cash_col))

        return cls(
            weights=wide,
            assets=assets,
            cash_col=cash_col,
            execution=ExecutionTiming.next_bar(),
            metadata={"source": "cross_sectional", "long_assets": pw.long_assets, "short_assets": pw.short_assets},
        )

    def summary(self) -> str:
        """Return human-readable summary."""
        gross = self.get_gross_exposure()
        net = self.get_net_exposure()
        gross_mean = gross.mean()
        net_mean = net.mean()
        gross_label = f"{gross_mean:.3f}" if gross_mean is not None else "unknown"
        net_label = f"{net_mean:.3f}" if net_mean is not None else "unknown"
        return (
            f"StrategyWeights(\n"
            f"  n_timestamps={self.n_timestamps},\n"
            f"  assets={self.assets},\n"
            f"  execution={self.execution.mode.value}:{self.execution.derive_lag_bars()},\n"
            f"  avg_gross_exposure={gross_label},\n"
            f"  avg_net_exposure={net_label},\n"
            f"  market_neutral={self.is_market_neutral()}\n"
            f")"
        )
