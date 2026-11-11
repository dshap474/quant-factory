"""Public entry point for the parent-order execution simulator.

Purpose: validate 1-minute OHLCV bars, parent orders, instrument specs and optional funding;
slice each asset's bars to numpy once; run every order under every policy through the pure
kernel; and assemble Polars ``fills`` and ``orders`` frames. Orders are simulated independently:
no interaction between orders and no self-competition for the same bar volume.

USAGE:
    >>> from backtest import simulate_execution, summarize_execution  # doctest: +SKIP
    >>> result = simulate_execution(bars=bars, orders=orders, specs={"BTC": btc_spec})  # doctest: +SKIP
    >>> summarize_execution(result)  # doctest: +SKIP

Performance: per-order Python loop over each window; vectorizing across orders is the next step
if wide alt universes prove slow.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import polars as pl

from execution import InstrumentSpec, ParentOrderPolicy

from ..errors import BacktestContractError
from .assumptions import FillAssumptions
from .fills import AssetArrays, InstrumentFloats, simulate_parent_order
from .report import ExecutionSimResult, OrderContext, below_minimum_row, build_order_rows

_MINUTE_US = 60_000_000
_UTC = pl.Datetime("us", "UTC")

# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def simulate_execution(
    *,
    bars: pl.DataFrame,
    orders: pl.DataFrame,
    specs: Mapping[str, InstrumentSpec],
    policies: Sequence[ParentOrderPolicy],
    assumptions: FillAssumptions = FillAssumptions(),
    funding: pl.DataFrame | None = None,
) -> ExecutionSimResult:
    """Simulate every order under every policy and return fills plus per-order costs.

    ``policies`` are ``execution.ParentOrderPolicy`` values; put the baseline first (it is the
    default ``summarize_execution`` baseline). Named presets live in the execution ``policies``
    extension.
    """
    policies = _validate_policies(policies)
    if not isinstance(assumptions, FillAssumptions):
        raise BacktestContractError("assumptions must be FillAssumptions")
    orders = _validate_orders(orders, specs)
    assets = sorted(set(orders["asset"].to_list()))
    floats = {asset: _spec_floats(asset, specs[asset]) for asset in assets}
    bars = _validate_bars(bars)
    has_quotes = "bid" in bars.columns
    by_asset = {key[0]: frame for key, frame in bars.partition_by("asset", as_dict=True, maintain_order=True).items()}
    arrays: dict[str, AssetArrays] = {}
    row_of: dict[str, dict[int, int]] = {}
    for asset in assets:
        if asset not in by_asset:
            raise BacktestContractError(f"bars contain no rows for asset {asset!r}")
        spread = None if has_quotes else assumptions.spread_bps_for(asset)
        arrays[asset] = _asset_arrays(by_asset[asset], tick=floats[asset].tick, spread_bps=spread)
        row_of[asset] = {ts: i for i, ts in enumerate(arrays[asset].timestamp_us.tolist())}
    funding_by_asset = _validate_funding(funding, assets)

    fill_rows: list[dict] = []
    order_rows: list[dict] = []
    for order in orders.iter_rows(named=True):
        asset = order["asset"]
        for policy in policies:
            fills, row = _simulate_one(
                order,
                policy=policy,
                arrays=arrays[asset],
                row_of=row_of[asset],
                spec=floats[asset],
                assumptions=assumptions,
                funding=funding_by_asset.get(asset),
            )
            fill_rows.extend(fills)
            order_rows.append(row)
    return ExecutionSimResult(
        fills=_fills_frame(fill_rows),
        orders=_orders_frame(order_rows, assumptions.markout_minutes),
        assumptions=assumptions,
        policies=policies,
    )


# --------------------------------------------------------------------------- #
# Per order × policy
# --------------------------------------------------------------------------- #


def _simulate_one(
    order: dict[str, Any],
    *,
    policy: ParentOrderPolicy,
    arrays: AssetArrays,
    row_of: Mapping[int, int],
    spec: InstrumentFloats,
    assumptions: FillAssumptions,
    funding: tuple[np.ndarray, np.ndarray] | None,
) -> tuple[list[dict], dict]:
    asset = order["asset"]
    decision_us = order["decision_us"]
    arrival_us = -(-decision_us // _MINUTE_US) * _MINUTE_US
    horizon = policy.horizon_minutes
    start = _require_grid(asset, arrays, row_of, first_us=arrival_us - _MINUTE_US, minutes=horizon + 2) + 1
    deadline = start + horizon
    ctx = OrderContext(
        order_id=order["order_id"],
        policy=policy.name,
        asset=asset,
        side=order["side"],
        notional=order["notional"],
        arrival_row=start,
        deadline_row=deadline,  # == start for market (horizon 0)
    )
    arrival_mid = float(arrays.mid_ref[start])
    target_lots = spec.floor_lots(order["notional"] / arrival_mid)
    target_qty = target_lots * spec.lot
    if (
        target_lots <= 0
        or target_qty < spec.min_quantity - spec.lot * 1e-9
        or target_qty * arrival_mid < spec.min_notional
    ):
        return [], below_minimum_row(ctx, target_qty=target_qty, arrival_mid=arrival_mid)
    kernel = simulate_parent_order(
        arrays=arrays,
        start=start,
        side=ctx.side,
        target_lots=target_lots,
        policy=policy,
        touch_fill_prob=float(assumptions.touch_fill_prob),
        participation=float(assumptions.participation),
        spec=spec,
    )
    return build_order_rows(
        ctx,
        kernel=kernel,
        arrays=arrays,
        row_of=row_of,
        spec=spec,
        target_lots=target_lots,
        funding=funding,
        markouts=assumptions.markout_minutes,
    )


def _require_grid(asset: str, arrays: AssetArrays, row_of: Mapping[int, int], *, first_us: int, minutes: int) -> int:
    """Return the row of ``first_us`` after checking ``minutes`` consecutive bars exist from it."""
    first = row_of.get(first_us)
    ts = arrays.timestamp_us
    last = -1 if first is None else first + minutes - 1
    if first is not None and last < len(ts) and int(ts[last]) - first_us == (minutes - 1) * _MINUTE_US:
        return first
    # Rows are sorted, unique and minute-aligned, so a span mismatch means some minute is absent.
    missing_us = next(first_us + k * _MINUTE_US for k in range(minutes) if first_us + k * _MINUTE_US not in row_of)
    missing = pl.Series([missing_us]).cast(_UTC).item()
    raise BacktestContractError(f"missing 1-minute bar for asset {asset!r} at {missing.isoformat()}")


# --------------------------------------------------------------------------- #
# Validation and slicing
# --------------------------------------------------------------------------- #


def _validate_policies(policies: Sequence[ParentOrderPolicy]) -> tuple[ParentOrderPolicy, ...]:
    items = tuple(policies)
    if not items:
        raise BacktestContractError("policies must not be empty")
    if any(not isinstance(policy, ParentOrderPolicy) for policy in items):
        raise BacktestContractError("policies must contain execution.ParentOrderPolicy values")
    names = [policy.name for policy in items]
    if len(set(names)) != len(names):
        raise BacktestContractError("policy names must be unique")
    return items


def _spec_floats(asset: str, spec: InstrumentSpec) -> InstrumentFloats:
    if not isinstance(spec, InstrumentSpec):
        raise BacktestContractError(f"specs[{asset!r}] must be InstrumentSpec")
    if spec.multiplier != 1:
        raise BacktestContractError(f"specs[{asset!r}] multiplier must be 1 (base-unit quantities)")
    return InstrumentFloats(
        tick=float(spec.price_increment),
        lot=float(spec.quantity_increment),
        min_quantity=float(spec.min_quantity),
        min_notional=float(spec.min_notional),
        maker_fee_rate=float(spec.maker_fee_rate),
        taker_fee_rate=float(spec.taker_fee_rate),
    )


def _require_columns(frame: object, name: str, columns: Sequence[str]) -> pl.DataFrame:
    if not isinstance(frame, pl.DataFrame):
        raise BacktestContractError(f"{name} must be a polars DataFrame")
    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise BacktestContractError(f"{name} missing columns: {missing}")
    return frame


def _require_utc(frame: pl.DataFrame, name: str, column: str) -> pl.Expr:
    dtype = frame.schema[column]
    if not isinstance(dtype, pl.Datetime) or dtype.time_zone != "UTC":
        raise BacktestContractError(f"{name}.{column} must be a UTC datetime")
    if frame[column].null_count():
        raise BacktestContractError(f"{name}.{column} must not contain nulls")
    return pl.col(column).dt.cast_time_unit("us")


def _require_finite(frame: pl.DataFrame, name: str, columns: Sequence[str]) -> None:
    for column in columns:
        if not frame.schema[column].is_numeric():
            raise BacktestContractError(f"{name}.{column} must be numeric")
        values = frame[column].cast(pl.Float64)
        if values.null_count() or not values.is_finite().all():
            raise BacktestContractError(f"{name}.{column} must be finite and non-null")


def _validate_bars(bars: pl.DataFrame) -> pl.DataFrame:
    frame = _require_columns(bars, "bars", ("asset", "timestamp", "open", "high", "low", "close", "volume"))
    if ("bid" in frame.columns) != ("ask" in frame.columns):
        raise BacktestContractError("bars must carry both bid and ask, or neither")
    if frame.schema["asset"] != pl.String or frame["asset"].null_count():
        raise BacktestContractError("bars.asset must be non-null strings")
    ts = _require_utc(frame, "bars", "timestamp")
    numeric = ["open", "high", "low", "close", "volume"] + (["bid", "ask"] if "bid" in frame.columns else [])
    _require_finite(frame, "bars", numeric)
    frame = frame.with_columns(ts.alias("timestamp"), *(pl.col(c).cast(pl.Float64) for c in numeric))
    checks = {
        "prices must be > 0": (pl.min_horizontal("open", "high", "low", "close") <= 0).any(),
        "volume must be >= 0": (pl.col("volume") < 0).any(),
        "high must be >= max(open, close)": (pl.col("high") < pl.max_horizontal("open", "close")).any(),
        "low must be <= min(open, close)": (pl.col("low") > pl.min_horizontal("open", "close")).any(),
        "timestamp must be an exact minute": (pl.col("timestamp").dt.epoch("us") % _MINUTE_US != 0).any(),
    }
    if "bid" in frame.columns:
        checks["quotes must satisfy 0 < bid < ask"] = ((pl.col("bid") <= 0) | (pl.col("bid") >= pl.col("ask"))).any()
    if "trade_count" in frame.columns:
        if not frame.schema["trade_count"].is_integer() or frame["trade_count"].null_count():
            raise BacktestContractError("bars.trade_count must be non-null integers")
        checks["trade_count must be >= 0"] = (pl.col("trade_count") < 0).any()
    failed = frame.select(**checks).row(0, named=True)
    for message, bad in failed.items():
        if bad:
            raise BacktestContractError(f"bars: {message}")
    keys = frame.select("asset", "timestamp")
    if keys.is_duplicated().any():
        raise BacktestContractError("bars must be unique on (asset, timestamp)")
    if not keys.equals(keys.sort("asset", "timestamp")):
        raise BacktestContractError("bars must be sorted by (asset, timestamp)")
    return frame


def _validate_orders(orders: pl.DataFrame, specs: Mapping[str, InstrumentSpec]) -> pl.DataFrame:
    frame = _require_columns(orders, "orders", ("order_id", "asset", "decision_at", "side", "notional"))
    if not isinstance(specs, Mapping):
        raise BacktestContractError("specs must be a mapping of asset -> InstrumentSpec")
    if frame.is_empty():
        raise BacktestContractError("orders must not be empty")
    for column in ("order_id", "asset"):
        if frame.schema[column] != pl.String or frame[column].null_count():
            raise BacktestContractError(f"orders.{column} must be non-null strings")
    if frame["order_id"].is_duplicated().any():
        raise BacktestContractError("orders.order_id must be unique")
    unknown = sorted(set(frame["asset"].to_list()) - set(specs))
    if unknown:
        raise BacktestContractError(f"orders reference assets without specs: {unknown}")
    if not frame.schema["side"].is_integer() or not frame["side"].is_in([1, -1]).all():
        raise BacktestContractError("orders.side must be integer +1 or -1")
    _require_finite(frame, "orders", ("notional",))
    if (frame["notional"] <= 0).any():
        raise BacktestContractError("orders.notional must be > 0")
    decision = _require_utc(frame, "orders", "decision_at")
    return frame.with_columns(
        decision.dt.epoch("us").alias("decision_us"),
        pl.col("side").cast(pl.Int64),
        pl.col("notional").cast(pl.Float64),
    )


def _validate_funding(funding: pl.DataFrame | None, assets: Sequence[str]) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    if funding is None:
        return {}
    frame = _require_columns(funding, "funding", ("asset", "timestamp", "rate"))
    if frame.schema["asset"] != pl.String or frame["asset"].null_count():
        raise BacktestContractError("funding.asset must be non-null strings")
    ts = _require_utc(frame, "funding", "timestamp")
    _require_finite(frame, "funding", ("rate",))
    frame = frame.select("asset", ts.dt.epoch("us").alias("ts_us"), pl.col("rate").cast(pl.Float64))
    if frame.select("asset", "ts_us").is_duplicated().any():
        raise BacktestContractError("funding must be unique on (asset, timestamp)")
    out: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for asset in assets:
        rows = frame.filter(pl.col("asset") == asset).sort("ts_us")
        out[asset] = (rows["ts_us"].to_numpy(), rows["rate"].to_numpy())
    return out


def _asset_arrays(frame: pl.DataFrame, *, tick: float, spread_bps: float | None) -> AssetArrays:
    """Slice one asset to numpy; reference quotes for row t come from row t-1 one minute earlier."""
    ts = frame["timestamp"].dt.epoch("us").to_numpy()
    high = frame["high"].to_numpy()
    low = frame["low"].to_numpy()
    volume = frame["volume"].to_numpy()
    no_trade = (frame["trade_count"].to_numpy() == 0) if "trade_count" in frame.columns else (volume == 0)
    prev_ok = np.zeros(len(ts), dtype=bool)
    prev_ok[1:] = np.diff(ts) == _MINUTE_US

    def shifted(values: np.ndarray) -> np.ndarray:
        out = np.full(len(values), math.nan)
        out[1:] = values[:-1]
        out[~prev_ok] = math.nan
        return out

    if spread_bps is None:
        bid_ref = shifted(frame["bid"].to_numpy())
        ask_ref = shifted(frame["ask"].to_numpy())
        mid_ref = (bid_ref + ask_ref) / 2
    else:
        # A tick-grid book around the last price before bar t opens: bid on the grid at or below
        # close - spread/2, ask the assumed spread (whole ticks, at least one) above it.
        close = shifted(frame["close"].to_numpy())
        spread = np.maximum(np.round(close * spread_bps / 1e4 / tick), 1) * tick
        bid_ref = np.floor((close - spread / 2) / tick + 1e-9) * tick
        ask_ref = bid_ref + spread
        mid_ref = (bid_ref + ask_ref) / 2
    return AssetArrays(
        timestamp_us=ts,
        open=frame["open"].to_numpy(),
        high=high,
        low=low,
        volume=volume,
        no_trade=no_trade,
        bid_ref=bid_ref,
        ask_ref=ask_ref,
        mid_ref=mid_ref,
    )


# --------------------------------------------------------------------------- #
# Frame assembly
# --------------------------------------------------------------------------- #


def _fills_frame(rows: list[dict]) -> pl.DataFrame:
    schema = {
        "order_id": pl.String,
        "policy": pl.String,
        "asset": pl.String,
        "timestamp_us": pl.Int64,
        "side": pl.Int64,
        "quantity": pl.Float64,
        "price": pl.Float64,
        "liquidity": pl.String,
        "fee": pl.Float64,
        "mid_ref": pl.Float64,
    }
    frame = pl.DataFrame(rows, schema=schema, orient="row") if rows else pl.DataFrame(schema=schema)
    return frame.with_columns(pl.col("timestamp_us").cast(_UTC).alias("timestamp")).select(
        "order_id", "policy", "asset", "timestamp", "side", "quantity", "price", "liquidity", "fee", "mid_ref"
    )


def _orders_frame(rows: list[dict], markouts: tuple[int, ...]) -> pl.DataFrame:
    schema: dict[str, Any] = {
        "order_id": pl.String,
        "policy": pl.String,
        "asset": pl.String,
        "side": pl.Int64,
        "notional": pl.Float64,
        "status": pl.String,
        "target_qty": pl.Float64,
        "filled_qty": pl.Float64,
        "unfilled_qty": pl.Float64,
        "maker_share": pl.Float64,
        "avg_price": pl.Float64,
        "arrival_mid": pl.Float64,
        "terminal_mid": pl.Float64,
        "first_fill_us": pl.Int64,
        "last_fill_us": pl.Int64,
        "minutes_to_complete": pl.Int64,
        "max_participation": pl.Float64,
        "cap_bound": pl.Boolean,
        "dust_forced": pl.Boolean,
        "fee_bps": pl.Float64,
        "spread_bps": pl.Float64,
        "drift_bps": pl.Float64,
        "unfilled_bps": pl.Float64,
        "funding_bps": pl.Float64,
        "total_bps": pl.Float64,
        **{f"markout_{h}m_bps": pl.Float64 for h in markouts},
    }
    frame = pl.DataFrame(rows, schema=schema)  # keys a row omits are null
    return frame.with_columns(
        pl.col("first_fill_us").cast(_UTC).alias("first_fill_us"),
        pl.col("last_fill_us").cast(_UTC).alias("last_fill_us"),
    ).rename({"first_fill_us": "first_fill_at", "last_fill_us": "last_fill_at"})
