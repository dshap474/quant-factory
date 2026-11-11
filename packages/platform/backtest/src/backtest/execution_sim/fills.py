"""Pure numpy fill kernel for one parent order over 1-minute OHLCV bars.

Purpose: work one ``ParentOrderPolicy`` (market at open, or a post-only maker schedule with a
market deadline) over one asset's pre-sliced arrays. The policy's decisions (child size, price)
come from the shared execution core (``maker_child_lots``, ``maker_price``), the same functions
live executors call; this module only decides fills from bars. No Polars, no I/O. Quantities are
tracked in integer lots so rounding never drifts. Reference quotes for bar t come from bar t-1
only (no lookahead).

USAGE:
    >>> from backtest.execution_sim.fills import AssetArrays, simulate_parent_order  # doctest: +SKIP
    >>> result = simulate_parent_order(arrays=arrays, start=row, side=1, target_lots=100, policy=policy, ...)  # doctest: +SKIP

Performance: one Python loop per order over its window. Vectorizing across orders is the next step
if wide alt universes prove slow.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from execution import ParentOrderPolicy, maker_child_lots, maker_price

# Comparison slack, in ticks/lots, so float grid prices compare as exact grid values.
_EPS = 1e-9

# --------------------------------------------------------------------------- #
# Inputs and outputs
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class AssetArrays:
    """One asset's bars as aligned arrays; ``*_ref[t]`` derive from bar t-1 (NaN when unavailable)."""

    timestamp_us: np.ndarray
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    volume: np.ndarray
    no_trade: np.ndarray
    bid_ref: np.ndarray
    ask_ref: np.ndarray
    mid_ref: np.ndarray


@dataclass(frozen=True, slots=True)
class InstrumentFloats:
    """Float view of the ``InstrumentSpec`` fields the kernel needs."""

    tick: float
    lot: float
    min_quantity: float
    min_notional: float
    maker_fee_rate: float
    taker_fee_rate: float

    def min_lots(self, ref_price: float) -> int:
        """Venue minimum in lots at a reference price."""
        by_qty = math.ceil(self.min_quantity / self.lot - _EPS)
        by_notional = math.ceil(self.min_notional / ref_price / self.lot - _EPS)
        return max(by_qty, by_notional, 0)

    def floor_lots(self, quantity: float) -> int:
        """Quantity rounded down to whole lots."""
        return max(math.floor(quantity / self.lot + _EPS), 0)


@dataclass(slots=True)
class KernelResult:
    """Fills and flags for one parent order under one policy."""

    rows: list[int] = field(default_factory=list)
    lots: list[int] = field(default_factory=list)
    prices: list[float] = field(default_factory=list)
    maker: list[bool] = field(default_factory=list)
    fees: list[float] = field(default_factory=list)
    cap_bound: bool = False
    dust_forced: bool = False
    unfilled_lots: int = 0

    def add(self, *, row: int, lots: int, price: float, maker: bool, fee_rate: float, lot: float) -> None:
        self.rows.append(row)
        self.lots.append(lots)
        self.prices.append(price)
        self.maker.append(maker)
        self.fees.append(lots * lot * price * fee_rate)


# --------------------------------------------------------------------------- #
# Kernel
# --------------------------------------------------------------------------- #


def taker_price(arrays: AssetArrays, row: int, side: int) -> float:
    """Gap-adjusted taker price: buy max(open, ask_ref), sell min(open, bid_ref)."""
    if side > 0:
        return max(float(arrays.open[row]), float(arrays.ask_ref[row]))
    return min(float(arrays.open[row]), float(arrays.bid_ref[row]))


def simulate_parent_order(
    *,
    arrays: AssetArrays,
    start: int,
    side: int,
    target_lots: int,
    policy: ParentOrderPolicy,
    touch_fill_prob: float,
    participation: float,
    spec: InstrumentFloats,
) -> KernelResult:
    """Run one parent order from arrival row ``start``; the caller guarantees a complete grid."""
    result = KernelResult()
    if policy.style == "market":
        price = taker_price(arrays, start, side)
        result.add(row=start, lots=target_lots, price=price, maker=False, fee_rate=spec.taker_fee_rate, lot=spec.lot)
        return result

    horizon = policy.horizon_minutes
    child_minutes = policy.child_minutes
    price_rule = policy.price_rule
    repeg_minutes = policy.repeg_minutes
    end = start + horizon
    o = arrays.open[start:end].tolist()
    hi = arrays.high[start:end].tolist()
    lo = arrays.low[start:end].tolist()
    vol = arrays.volume[start:end].tolist()
    dead = arrays.no_trade[start:end].tolist()
    bid = arrays.bid_ref[start:end].tolist()
    ask = arrays.ask_ref[start:end].tolist()
    tick, lot = spec.tick, spec.lot
    slack = tick * 1e-6

    remaining = target_lots
    child_left = 0
    price = 0.0
    resting = False
    for k in range(horizon):
        post = maker_price(side=side, bid=bid[k], ask=ask[k], tick=tick, price_rule=price_rule)
        new_child = maker_child_lots(
            minute=k,
            horizon_minutes=horizon,
            child_minutes=child_minutes,
            remaining_lots=remaining,
            min_lots=spec.min_lots(post),
        )
        if new_child is not None:
            child_left = new_child
            resting = False
        if child_left <= 0:
            continue
        if not resting or (repeg_minutes is not None and k % repeg_minutes == 0):
            price = post
            # Post-only: a new post that would cross at the open is rejected for this minute (and
            # retried next minute). An open exactly at our price is a trade at our level (it rests
            # and can fill). A resting order is never rejected; an open through it is a through fill.
            resting = not ((side > 0 and o[k] < price - slack) or (side < 0 and o[k] > price + slack))
            if not resting:
                continue
        if dead[k]:
            continue
        if side > 0:
            through = lo[k] <= price - tick + slack
            touch = not through and lo[k] <= price + slack
        else:
            through = hi[k] >= price + tick - slack
            touch = not through and hi[k] >= price - slack
        phi = 1.0 if through else (touch_fill_prob if touch else 0.0)
        if phi <= 0.0:
            continue
        cap = participation * vol[k]
        if cap < child_left * lot:
            result.cap_bound = True
        q = min(spec.floor_lots(phi * min(child_left * lot, cap)), child_left)
        if q > 0:
            result.add(row=start + k, lots=q, price=price, maker=True, fee_rate=spec.maker_fee_rate, lot=lot)
            child_left -= q
            remaining -= q
            if remaining == 0:
                break

    if remaining > 0:
        if policy.at_deadline == "market":
            ref = float(arrays.ask_ref[end] if side > 0 else arrays.bid_ref[end])
            result.dust_forced = remaining < spec.min_lots(ref)
            deadline_price = taker_price(arrays, end, side)
            result.add(
                row=end, lots=remaining, price=deadline_price, maker=False, fee_rate=spec.taker_fee_rate, lot=lot
            )
        else:
            result.unfilled_lots = remaining
    return result
