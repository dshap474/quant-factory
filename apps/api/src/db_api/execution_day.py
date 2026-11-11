"""One rebalance day worked intraday: a run's parent orders simulated over 1-minute bars under each policy.

An API extension supplies the inputs (``ExecutionInputs``: the day's parent orders, the bars they
trade on, instrument specs, the policies to compare and the fill assumptions); this module runs
``backtest.simulate_execution`` and shapes the result for the Backtest Engine's Rebalance day page:
cost per policy (notional-weighted bps against arrival mid), each order's cost per policy, each
policy's book path in dollars (notional still to buy and to sell, and the running cost against
trading everything at arrival mid), and, served one asset at a time, the day's 1-minute close and
volume with every fill and the running average fill price.

Running cost of one order at time t: what its fills so far cost against arrival mid (plus fees),
plus the unfilled quantity marked at the last close against arrival mid. It starts near zero and
ends at the order's total cost, so the path shows the price risk a slow policy carries.

USAGE::

    day, assets = build_execution_day(inputs)   # inputs from an extension's execution source
    day.summary[0].total_bps                    # the first (baseline) policy's cost
    assets["BTC"].close                         # BTC's 1-minute closes from arrival
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports and constants
# --------------------------------------------------------------------------- #
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np
import polars as pl
from backtest import FillAssumptions, simulate_execution
from pydantic import BaseModel

from execution import InstrumentSpec, ParentOrderPolicy

_MINUTE = timedelta(minutes=1)
_DAY = timedelta(days=1)
_BOOK_STEP = timedelta(minutes=5)
_US = 1_000_000


def arrival_minute(decision: datetime) -> datetime:
    """Where an order decided at ``decision`` starts working: the first whole minute at or after it."""
    return (decision - timedelta(microseconds=1) + _MINUTE).replace(second=0, microsecond=0)


# --------------------------------------------------------------------------- #
# Inputs and response models
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ExecutionInputs:
    """Everything one simulated rebalance day needs; ``orders`` is ``simulate_execution``'s frame."""

    bars: pl.DataFrame
    orders: pl.DataFrame
    specs: Mapping[str, InstrumentSpec]
    policies: Sequence[ParentOrderPolicy]
    assumptions: FillAssumptions
    venue: str
    skipped: Sequence[str] = field(default_factory=tuple)


class ExecutionPolicy(BaseModel):
    name: str
    horizon_minutes: int


class ExecutionPolicySummary(BaseModel):
    policy: str
    below_minimum: int
    filled_share: float | None
    maker_share: float | None
    minutes_to_complete: float | None
    total_bps: float | None
    fee_bps: float | None
    spread_bps: float | None
    drift_bps: float | None
    unfilled_bps: float | None
    markouts_bps: dict[str, float | None]


class ExecutionBook(BaseModel):
    """One policy's whole-book path on ``book_times``, in dollars (sells to go are negative)."""

    to_buy: list[float]
    to_sell: list[float]
    cost: list[float]


class ExecutionOrder(BaseModel):
    """One parent order; ``cost_bps`` per policy, None where it was below the venue minimum."""

    asset: str
    side: int
    notional: float
    arrival_mid: float | None
    cost_bps: dict[str, float | None]


class ExecutionDay(BaseModel):
    decision_at: str
    venue: str
    assumptions: dict[str, float]
    policies: list[ExecutionPolicy]
    book_times: list[str]
    book: dict[str, ExecutionBook]
    summary: list[ExecutionPolicySummary]
    orders: list[ExecutionOrder]
    skipped: list[str]


class ExecutionFills(BaseModel):
    """One policy's fills of one order, columnar; ``avg_price`` is the running average after each fill."""

    time_ms: list[int]
    quantity: list[float]
    price: list[float]
    maker: list[bool]
    avg_price: list[float]


class ExecutionAsset(BaseModel):
    """One asset's day: ``close`` and ``volume`` per minute from ``start_ms`` (arrival), fills per policy."""

    start_ms: int
    close: list[float | None]
    volume: list[float | None]
    fills: dict[str, ExecutionFills]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _finite(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) and math.isfinite(value) else None


def _weighted(frame: pl.DataFrame, column: str) -> float | None:
    """Mean of ``column`` weighted by each order's arrival notional, over rows where it is known."""
    known = frame.filter(pl.col(column).is_not_null() & pl.col(column).is_finite())
    if known.is_empty() or known["_base"].sum() <= 0:
        return None
    return _finite((known[column] * known["_base"]).sum() / known["_base"].sum())


def _grid_us(start: datetime, end: datetime, step: timedelta) -> np.ndarray:
    count = int((end - start) / step) + 1
    first = int(start.timestamp() * _US)
    return first + np.arange(count, dtype=np.int64) * int(step.total_seconds() * _US)


def _order_path(fills: pl.DataFrame, row: dict, marks: tuple[np.ndarray, np.ndarray], grid: np.ndarray):
    """(quantity still to fill, running dollar cost) at each grid time; a fill in the bar at t counts from t + 1m."""
    side, arrival, target = row["side"], row["arrival_mid"], row["target_qty"]
    done = fills["timestamp"].dt.epoch("us").to_numpy() + 60 * _US
    qty = fills["quantity"].to_numpy()
    paid = side * (fills["price"].to_numpy() - arrival) * qty + fills["fee"].to_numpy()
    order = np.argsort(done, kind="stable")
    count = np.searchsorted(done[order], grid, side="right")
    filled = np.concatenate([[0.0], np.cumsum(qty[order])])[count]
    realized = np.concatenate([[0.0], np.cumsum(paid[order])])[count]
    # Mark: the close of the last bar completed by t (the bar that started a minute earlier).
    bar_us, close = marks
    last = np.clip(np.searchsorted(bar_us, grid - 60 * _US, side="right") - 1, 0, len(close) - 1)
    remaining = np.maximum(target - filled, 0.0)
    return remaining, realized + side * (close[last] - arrival) * remaining


def _fills(frame: pl.DataFrame) -> ExecutionFills:
    frame = frame.sort("timestamp")
    qty = frame["quantity"].to_numpy()
    notional = np.cumsum(qty * frame["price"].to_numpy())
    return ExecutionFills(
        time_ms=frame["timestamp"].dt.epoch("ms").to_list(),
        quantity=qty.tolist(),
        price=frame["price"].to_list(),
        maker=(frame["liquidity"] == "maker").to_list(),
        avg_price=(notional / np.cumsum(qty)).tolist(),
    )


def _on_grid(bar_us: np.ndarray, values: np.ndarray, grid: np.ndarray) -> list[float | None]:
    """``values`` at each grid minute; None where no bar starts there."""
    at = np.minimum(np.searchsorted(bar_us, grid), len(bar_us) - 1)
    hit = bar_us[at] == grid
    return [_finite(value) if ok else None for value, ok in zip(values[at].tolist(), hit.tolist(), strict=True)]


# --------------------------------------------------------------------------- #
# Assembly
# --------------------------------------------------------------------------- #


def build_execution_day(inputs: ExecutionInputs) -> tuple[ExecutionDay, dict[str, ExecutionAsset]]:
    """Simulate every order under every policy: the day's costs and book paths, and each asset's day."""
    result = simulate_execution(
        bars=inputs.bars,
        orders=inputs.orders,
        specs=inputs.specs,
        policies=inputs.policies,
        assumptions=inputs.assumptions,
    )
    names = [policy.name for policy in inputs.policies]
    decision = inputs.orders["decision_at"].min()
    start = arrival_minute(decision)
    end = start + _DAY
    orders = result.orders.with_columns(
        _base=pl.col("target_qty") * pl.col("arrival_mid"),
        filled_share=pl.when(pl.col("target_qty") > 0).then(pl.col("filled_qty") / pl.col("target_qty")),
    )
    working = orders.filter(pl.col("status") != "below_minimum")
    markouts = [column for column in orders.columns if column.startswith("markout_")]

    summary = []
    for name in names:
        live = working.filter(pl.col("policy") == name)
        summary.append(
            ExecutionPolicySummary(
                policy=name,
                below_minimum=orders.filter(pl.col("policy") == name).height - live.height,
                filled_share=_weighted(live, "filled_share"),
                maker_share=_weighted(live, "maker_share"),
                minutes_to_complete=_finite(live["minutes_to_complete"].median()),
                total_bps=_weighted(live, "total_bps"),
                fee_bps=_weighted(live, "fee_bps"),
                spread_bps=_weighted(live, "spread_bps"),
                drift_bps=_weighted(live, "drift_bps"),
                unfilled_bps=_weighted(live, "unfilled_bps"),
                markouts_bps={
                    column.removeprefix("markout_").removesuffix("_bps"): _weighted(live, column) for column in markouts
                },
            )
        )

    # One step past the day, so a policy whose deadline is the day's last minute lands on the grid.
    book_grid = _grid_us(start, end + _BOOK_STEP, _BOOK_STEP)
    minute_grid = _grid_us(start, end, _MINUTE)
    fills = result.fills.partition_by("order_id", "policy", as_dict=True)
    rows_by_order = orders.partition_by("order_id", as_dict=True)
    paths = {name: np.zeros((3, len(book_grid))) for name in names}  # to buy, to sell, cost
    bars = inputs.bars.with_columns(us=pl.col("timestamp").dt.epoch("us")).partition_by("asset", as_dict=True)
    order_rows, assets = [], {}
    for order in inputs.orders.sort("notional", descending=True).iter_rows(named=True):
        frame = bars[(order["asset"],)]
        bar_us = frame["us"].to_numpy()
        marks = (bar_us, frame["close"].to_numpy())
        rows = rows_by_order[(order["order_id"],)]
        asset_fills = {}
        for row in rows.filter(pl.col("status") != "below_minimum").iter_rows(named=True):
            mine = fills.get((order["order_id"], row["policy"]))
            if mine is None:
                mine = result.fills.clear()
            else:
                asset_fills[row["policy"]] = _fills(mine)
            remaining, cost = _order_path(mine, row, marks, book_grid)
            paths[row["policy"]][0 if row["side"] > 0 else 1] += row["side"] * remaining * row["arrival_mid"]
            paths[row["policy"]][2] += cost
        order_rows.append(
            ExecutionOrder(
                asset=order["asset"],
                side=order["side"],
                notional=order["notional"],
                arrival_mid=_finite(rows["arrival_mid"].drop_nulls().first()),
                cost_bps={
                    row["policy"]: None if row["status"] == "below_minimum" else _finite(row["total_bps"])
                    for row in rows.iter_rows(named=True)
                },
            )
        )
        assets[order["asset"]] = ExecutionAsset(
            start_ms=int(start.timestamp() * 1000),
            close=_on_grid(bar_us, frame["close"].to_numpy(), minute_grid),
            volume=_on_grid(bar_us, frame["volume"].to_numpy(), minute_grid),
            fills=asset_fills,
        )

    assumptions = inputs.assumptions
    spread = assumptions.assumed_spread_bps
    day = ExecutionDay(
        decision_at=decision.isoformat(),
        venue=inputs.venue,
        assumptions={
            "touch_fill_prob": float(assumptions.touch_fill_prob),
            "participation": float(assumptions.participation),
            **({"assumed_spread_bps": float(spread)} if isinstance(spread, (int, float)) else {}),
        },
        policies=[
            ExecutionPolicy(name=policy.name, horizon_minutes=policy.horizon_minutes) for policy in inputs.policies
        ],
        book_times=pl.Series(book_grid).cast(pl.Datetime("us", "UTC")).dt.to_string("%Y-%m-%dT%H:%M:%SZ").to_list(),
        book={
            name: ExecutionBook(
                to_buy=paths[name][0].round(2).tolist(),
                to_sell=paths[name][1].round(2).tolist(),
                cost=paths[name][2].round(2).tolist(),
            )
            for name in names
        },
        summary=summary,
        orders=order_rows,
        skipped=list(inputs.skipped),
    )
    return day, assets
