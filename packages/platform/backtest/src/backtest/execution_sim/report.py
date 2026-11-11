"""Order-level cost decomposition and policy summaries for the parent-order simulator.

Purpose: turn one kernel result into a fills block and an order row with costs in bps of
``target_qty * arrival_mid`` (positive = worse), check the shortfall identity, and summarize
policies per asset with a paired difference against a baseline policy.

USAGE:
    >>> from backtest import simulate_execution, summarize_execution  # doctest: +SKIP
    >>> summary = summarize_execution(simulate_execution(bars=bars, orders=orders, specs=specs))  # doctest: +SKIP
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np
import polars as pl

from execution import ParentOrderPolicy

from ..errors import BacktestContractError
from .assumptions import FillAssumptions
from .fills import AssetArrays, InstrumentFloats, KernelResult

_MINUTE_US = 60_000_000

# --------------------------------------------------------------------------- #
# Result
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class ExecutionSimResult:
    """Fills, order × policy cost rows, and the assumptions/policies that produced them."""

    fills: pl.DataFrame
    orders: pl.DataFrame
    assumptions: FillAssumptions
    policies: tuple[ParentOrderPolicy, ...]


@dataclass(frozen=True, slots=True)
class OrderContext:
    """Per order × policy facts the report needs beyond the kernel result."""

    order_id: str
    policy: str
    asset: str
    side: int
    notional: float
    arrival_row: int
    deadline_row: int


# --------------------------------------------------------------------------- #
# Order rows
# --------------------------------------------------------------------------- #


def below_minimum_row(ctx: OrderContext, *, target_qty: float, arrival_mid: float) -> dict:
    """Order row for a parent order too small for the venue: no fills; costs stay null."""
    row: dict[str, Any] = _base_row(ctx, status="below_minimum", target_qty=target_qty, arrival_mid=arrival_mid)
    row.update(filled_qty=0.0, unfilled_qty=target_qty, cap_bound=False, dust_forced=False)
    return row


def build_order_rows(
    ctx: OrderContext,
    *,
    kernel: KernelResult,
    arrays: AssetArrays,
    row_of: Mapping[int, int],
    spec: InstrumentFloats,
    target_lots: int,
    funding: tuple[np.ndarray, np.ndarray] | None,
    markouts: tuple[int, ...],
) -> tuple[list[dict], dict]:
    """Return (fill rows, order row) for one simulated parent order."""
    lot = spec.lot
    side = ctx.side
    arrival_mid = float(arrays.mid_ref[ctx.arrival_row])
    terminal_mid = float(arrays.mid_ref[ctx.deadline_row])
    target_qty = target_lots * lot
    base = target_qty * arrival_mid

    qtys = [n * lot for n in kernel.lots]
    mids = [float(arrays.mid_ref[r]) for r in kernel.rows]
    fill_rows = [
        {
            "order_id": ctx.order_id,
            "policy": ctx.policy,
            "asset": ctx.asset,
            "timestamp_us": int(arrays.timestamp_us[r]),
            "side": side,
            "quantity": q,
            "price": p,
            "liquidity": "maker" if m else "taker",
            "fee": f,
            "mid_ref": mid,
        }
        for r, q, p, m, f, mid in zip(kernel.rows, qtys, kernel.prices, kernel.maker, kernel.fees, mids, strict=True)
    ]

    filled_lots = sum(kernel.lots)
    filled_qty = filled_lots * lot
    unfilled_qty = kernel.unfilled_lots * lot
    if filled_lots + kernel.unfilled_lots != target_lots:
        raise BacktestContractError(f"order {ctx.order_id!r}/{ctx.policy}: filled + unfilled != target")
    fee = sum(kernel.fees)
    spread = sum(side * (p - mid) * q for p, mid, q in zip(kernel.prices, mids, qtys, strict=True))
    drift = sum(side * (mid - arrival_mid) * q for mid, q in zip(mids, qtys, strict=True))
    unfilled = side * (terminal_mid - arrival_mid) * unfilled_qty
    funding_extra = _funding_extra(
        ctx, kernel=kernel, arrays=arrays, row_of=row_of, lot=lot, target_qty=target_qty, funding=funding
    )
    total = fee + spread + drift + unfilled + funding_extra
    notional_paid = sum(p * q for p, q in zip(kernel.prices, qtys, strict=True))
    shortfall = side * (notional_paid - arrival_mid * filled_qty) + fee + unfilled + funding_extra
    if abs(total - shortfall) > 1e-9 * max(abs(base), abs(shortfall)):
        raise BacktestContractError(f"order {ctx.order_id!r}/{ctx.policy}: cost identity violated")

    maker_qty = sum(q for q, m in zip(qtys, kernel.maker, strict=True) if m)
    completed = kernel.unfilled_lots == 0
    row: dict[str, Any] = _base_row(
        ctx, status="completed" if completed else "partial", target_qty=target_qty, arrival_mid=arrival_mid
    )
    vols = [float(arrays.volume[r]) for r in kernel.rows]
    participations = [q / v if v > 0 else math.inf for q, v in zip(qtys, vols, strict=True)]
    row.update(
        filled_qty=filled_qty,
        unfilled_qty=unfilled_qty,
        maker_share=maker_qty / filled_qty if filled_qty > 0 else None,
        avg_price=notional_paid / filled_qty if filled_qty > 0 else None,
        terminal_mid=terminal_mid,
        first_fill_us=int(arrays.timestamp_us[kernel.rows[0]]) if kernel.rows else None,
        last_fill_us=int(arrays.timestamp_us[kernel.rows[-1]]) if kernel.rows else None,
        minutes_to_complete=(kernel.rows[-1] - ctx.arrival_row) if completed and kernel.rows else None,
        max_participation=max(participations) if participations else None,
        cap_bound=kernel.cap_bound,
        dust_forced=kernel.dust_forced,
        fee_bps=fee / base * 1e4,
        spread_bps=spread / base * 1e4,
        drift_bps=drift / base * 1e4,
        unfilled_bps=unfilled / base * 1e4,
        funding_bps=funding_extra / base * 1e4,
        total_bps=total / base * 1e4,
    )
    for h in markouts:
        row[f"markout_{h}m_bps"] = _markout(kernel, arrays=arrays, row_of=row_of, side=side, horizon=h)
    return fill_rows, row


def _base_row(ctx: OrderContext, *, status: str, target_qty: float, arrival_mid: float) -> dict[str, Any]:
    return {
        "order_id": ctx.order_id,
        "policy": ctx.policy,
        "asset": ctx.asset,
        "side": ctx.side,
        "notional": ctx.notional,
        "status": status,
        "target_qty": target_qty,
        "arrival_mid": arrival_mid,
    }


def _funding_extra(
    ctx: OrderContext,
    *,
    kernel: KernelResult,
    arrays: AssetArrays,
    row_of: Mapping[int, int],
    lot: float,
    target_qty: float,
    funding: tuple[np.ndarray, np.ndarray] | None,
) -> float:
    """Extra funding vs. full fill at arrival over settlements in (arrival open, end]."""
    if funding is None or len(funding[0]) == 0:
        return 0.0
    times, rates = funding
    start_us = int(arrays.timestamp_us[ctx.arrival_row])
    end_us = int(arrays.timestamp_us[ctx.deadline_row])
    lo, hi = np.searchsorted(times, [start_us, end_us], side="right")  # settlements in (start, end]
    fill_us = [int(arrays.timestamp_us[r]) for r in kernel.rows]
    extra = 0.0
    for s_us, rate in zip(times[lo:hi].tolist(), rates[lo:hi].tolist(), strict=True):
        held = sum(n * lot for t, n in zip(fill_us, kernel.lots, strict=True) if t < s_us)
        price = float(arrays.mid_ref[row_of[s_us - s_us % _MINUTE_US]])
        extra += rate * price * ctx.side * (held - target_qty)
    return extra


def _markout(
    kernel: KernelResult,
    *,
    arrays: AssetArrays,
    row_of: Mapping[int, int],
    side: int,
    horizon: int,
) -> float | None:
    """Quantity-weighted maker-fill markout in bps; null when no maker fills or data is missing."""
    weighted = 0.0
    weight = 0
    for r, n, p, m in zip(kernel.rows, kernel.lots, kernel.prices, kernel.maker, strict=True):
        if not m:
            continue
        later = row_of.get(int(arrays.timestamp_us[r]) + horizon * _MINUTE_US)
        mid = float(arrays.mid_ref[later]) if later is not None else math.nan
        if not math.isfinite(mid):
            return None
        weighted += n * side * (mid - p) / p * 1e4
        weight += n
    return weighted / weight if weight > 0 else None


# --------------------------------------------------------------------------- #
# Summary
# --------------------------------------------------------------------------- #


def summarize_execution(result: ExecutionSimResult, *, baseline: str | None = None) -> pl.DataFrame:
    """One row per (policy, asset): mean costs, completion, and paired diff vs. ``baseline``.

    ``baseline`` names a policy in the run; it defaults to the first policy passed.
    """
    if not isinstance(result, ExecutionSimResult):
        raise BacktestContractError("result must be ExecutionSimResult")
    names = [policy.name for policy in result.policies]
    baseline = names[0] if baseline is None else baseline
    if baseline not in names:
        raise BacktestContractError(f"baseline policy {baseline!r} is not in result.policies")
    rows = result.orders.filter(pl.col("status") != "below_minimum")
    base = rows.filter(pl.col("policy") == baseline).select("order_id", pl.col("total_bps").alias("_base_total"))
    paired = rows.join(base, on="order_id", how="left").with_columns(
        (pl.col("total_bps") - pl.col("_base_total")).alias("_diff")
    )
    summary = paired.group_by("policy", "asset").agg(
        pl.len().alias("n"),
        pl.col("total_bps").mean().alias("mean_total_bps"),
        pl.col("total_bps").std().alias("std_total_bps"),
        *(pl.col(f"{c}_bps").mean().alias(f"mean_{c}_bps") for c in ("fee", "spread", "drift", "unfilled", "funding")),
        pl.col("maker_share").mean().alias("mean_maker_share"),
        (pl.col("status") == "completed").mean().alias("completion_rate"),
        pl.col("cap_bound").mean().alias("cap_bound_rate"),
        pl.col("_diff").mean().alias("mean_diff_vs_baseline_bps"),
        (pl.col("_diff").std() / pl.col("_diff").count().sqrt()).alias("se_diff_vs_baseline_bps"),
    )
    order = pl.DataFrame({"policy": names, "_rank": list(range(len(names)))})
    return summary.join(order, on="policy").sort("_rank", "asset").drop("_rank")
