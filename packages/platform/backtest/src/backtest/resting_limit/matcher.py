"""Pure deterministic OHLC matcher for prepared resting-limit plans.

Purpose: map completed bar primitives to terminal outcomes and shared Fill
records without Polars, Nautilus, projection, reporting, or I/O.

USAGE:
    >>> from backtest.resting_limit.matcher import match_resting_limit_orders  # doctest: +SKIP
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Mapping, Sequence

from execution import (
    Fill,
    InstrumentKey,
    InstrumentSpec,
    OrderStatus,
    RestingLimitOrder,
    RestingLimitOutcome,
    RestingLimitPlan,
)

# --------------------------------------------------------------------------- #
# Result
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class RestingLimitMatchResult:
    """Pure matching output before account projection and reporting."""

    outcomes: tuple[RestingLimitOutcome, ...]
    fills: tuple[Fill, ...]
    ambiguous_double_touch_count: int


# --------------------------------------------------------------------------- #
# Public matcher
# --------------------------------------------------------------------------- #


def match_resting_limit_orders(
    *,
    plan: RestingLimitPlan,
    bar_rows: Sequence[Mapping[str, object]],
    instrument_specs: Mapping[InstrumentKey, InstrumentSpec],
    execution_calendar: Sequence[datetime],
) -> RestingLimitMatchResult:
    """Match one validated plan using only deterministic completed-bar facts."""
    bars = _index_bars(bar_rows, instrument_specs)
    outcomes: dict[str, RestingLimitOutcome] = {}
    fills: list[Fill] = []
    ambiguity_count = 0

    for timestamp in execution_calendar:
        active = [
            order
            for order in plan.orders
            if order.order_id not in outcomes and order.activate_at < timestamp <= order.expires_at
        ]
        grouped = _active_groups(active)
        for members in grouped:
            bar = bars[(members[0].instrument, timestamp)]
            if len(members) == 1:
                order = members[0]
                fill = _match_one(order, bar=bar, plan=plan, spec=instrument_specs[order.instrument])
                if fill is not None:
                    fills.append(fill)
                    outcomes[order.order_id] = _filled_outcome(order, fill)
                elif timestamp == order.expires_at:
                    outcomes[order.order_id] = _unfilled_outcome(
                        order,
                        status=OrderStatus.EXPIRED,
                        terminal_at=timestamp,
                        reason="expiry",
                    )
                continue

            group_outcomes, group_fills, ambiguous = _match_oco(
                members,
                bar=bar,
                plan=plan,
                spec=instrument_specs[members[0].instrument],
            )
            if group_outcomes:
                outcomes.update((outcome.order.order_id, outcome) for outcome in group_outcomes)
                fills.extend(group_fills)
                ambiguity_count += int(ambiguous)
            elif timestamp == members[0].expires_at:
                for order in members:
                    outcomes[order.order_id] = _unfilled_outcome(
                        order,
                        status=OrderStatus.EXPIRED,
                        terminal_at=timestamp,
                        reason="expiry",
                    )

    if set(outcomes) != {order.order_id for order in plan.orders}:
        missing = sorted({order.order_id for order in plan.orders} - set(outcomes))
        raise ValueError(f"orders did not reach a terminal outcome: {', '.join(missing)}")
    ordered_outcomes = tuple(outcomes[order.order_id] for order in plan.orders)
    ordered_fills = tuple(sorted(fills, key=lambda fill: (fill.filled_at, fill.fill_id)))
    return RestingLimitMatchResult(
        outcomes=ordered_outcomes,
        fills=ordered_fills,
        ambiguous_double_touch_count=ambiguity_count,
    )


# --------------------------------------------------------------------------- #
# OCO and single-order matching
# --------------------------------------------------------------------------- #


def _match_oco(
    orders: tuple[RestingLimitOrder, ...],
    *,
    bar: "_Bar",
    plan: RestingLimitPlan,
    spec: InstrumentSpec,
) -> tuple[tuple[RestingLimitOutcome, ...], tuple[Fill, ...], bool]:
    if len(orders) != 2:
        raise ValueError("validated OCO group must contain exactly two active orders")
    buy = orders[0] if orders[0].quantity > 0 else orders[1]
    sell = orders[1] if orders[1].quantity < 0 else orders[0]
    buy_touch = _touches(buy, bar=bar, penetration_bps=plan.penetration_bps)
    sell_touch = _touches(sell, bar=bar, penetration_bps=plan.penetration_bps)

    open_hits_buy = bar.open <= _threshold(buy, plan.penetration_bps)
    open_hits_sell = bar.open >= _threshold(sell, plan.penetration_bps)
    if open_hits_buy:
        return _fill_oco_side(buy, sell, bar=bar, plan=plan, spec=spec, liquidity="taker")
    if open_hits_sell:
        return _fill_oco_side(sell, buy, bar=bar, plan=plan, spec=spec, liquidity="taker")
    if buy_touch and sell_touch:
        outcomes = tuple(
            _unfilled_outcome(
                order,
                status=OrderStatus.CANCELED,
                terminal_at=bar.timestamp,
                reason="ambiguous_double_touch",
            )
            for order in orders
        )
        return outcomes, (), True
    if buy_touch:
        return _fill_oco_side(buy, sell, bar=bar, plan=plan, spec=spec, liquidity="maker")
    if sell_touch:
        return _fill_oco_side(sell, buy, bar=bar, plan=plan, spec=spec, liquidity="maker")
    return (), (), False


def _fill_oco_side(
    filled_order: RestingLimitOrder,
    canceled_order: RestingLimitOrder,
    *,
    bar: "_Bar",
    plan: RestingLimitPlan,
    spec: InstrumentSpec,
    liquidity: str,
) -> tuple[tuple[RestingLimitOutcome, ...], tuple[Fill, ...], bool]:
    fill = _make_fill(filled_order, bar=bar, plan=plan, spec=spec, liquidity=liquidity)
    outcomes = (
        _filled_outcome(filled_order, fill),
        _unfilled_outcome(
            canceled_order,
            status=OrderStatus.CANCELED,
            terminal_at=bar.timestamp,
            reason="oco_peer_filled",
        ),
    )
    outcomes = tuple(sorted(outcomes, key=lambda outcome: outcome.order.order_id))
    return outcomes, (fill,), False


def _match_one(
    order: RestingLimitOrder,
    *,
    bar: "_Bar",
    plan: RestingLimitPlan,
    spec: InstrumentSpec,
) -> Fill | None:
    if not _touches(order, bar=bar, penetration_bps=plan.penetration_bps):
        return None
    open_through = bar.open <= order.limit_price if order.quantity > 0 else bar.open >= order.limit_price
    return _make_fill(
        order,
        bar=bar,
        plan=plan,
        spec=spec,
        liquidity="taker" if open_through else "maker",
    )


# --------------------------------------------------------------------------- #
# Fill and outcome construction
# --------------------------------------------------------------------------- #


def _make_fill(
    order: RestingLimitOrder,
    *,
    bar: "_Bar",
    plan: RestingLimitPlan,
    spec: InstrumentSpec,
    liquidity: str,
) -> Fill:
    fee_rate = spec.taker_fee_rate if liquidity == "taker" else spec.maker_fee_rate
    fee = abs(order.quantity) * order.limit_price * spec.multiplier * fee_rate
    return Fill(
        target_id=plan.plan_id,
        slice_id=order.order_id,
        instrument=order.instrument,
        fill_id=f"{plan.plan_id}:{order.order_id}:fill",
        quantity=order.quantity,
        price=order.limit_price,
        fee=fee,
        fee_currency=spec.settlement_currency,
        filled_at=bar.timestamp,
    )


def _filled_outcome(order: RestingLimitOrder, fill: Fill) -> RestingLimitOutcome:
    return RestingLimitOutcome(
        order=order,
        status=OrderStatus.FILLED,
        fills=(fill,),
        terminal_at=fill.filled_at,
        unfilled_quantity=Decimal(0),
    )


def _unfilled_outcome(
    order: RestingLimitOrder,
    *,
    status: OrderStatus,
    terminal_at: datetime,
    reason: str,
) -> RestingLimitOutcome:
    return RestingLimitOutcome(
        order=order,
        status=status,
        fills=(),
        terminal_at=terminal_at,
        unfilled_quantity=order.quantity,
        reason=reason,
    )


# --------------------------------------------------------------------------- #
# Primitive bar indexing
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class _Bar:
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal


def _index_bars(
    rows: Sequence[Mapping[str, object]],
    specs: Mapping[InstrumentKey, InstrumentSpec],
) -> dict[tuple[InstrumentKey, datetime], _Bar]:
    wire_to_key = {f"{key.venue}:{key.symbol}": key for key in specs}
    indexed: dict[tuple[InstrumentKey, datetime], _Bar] = {}
    for row in rows:
        key = wire_to_key[str(row["instrument"])]
        timestamp = row["ts_init"]
        if not isinstance(timestamp, datetime):
            raise TypeError("bar ts_init must be datetime")
        indexed[(key, timestamp)] = _Bar(
            timestamp=timestamp,
            open=_decimal(row["open"]),
            high=_decimal(row["high"]),
            low=_decimal(row["low"]),
        )
    return indexed


def _active_groups(active: Sequence[RestingLimitOrder]) -> tuple[tuple[RestingLimitOrder, ...], ...]:
    grouped: dict[tuple[InstrumentKey, str], list[RestingLimitOrder]] = {}
    for order in active:
        group_key = order.oco_group_id or f"order:{order.order_id}"
        grouped.setdefault((order.instrument, group_key), []).append(order)
    ordered: list[tuple[RestingLimitOrder, ...]] = []
    for key in sorted(grouped, key=lambda item: (item[0].sort_key(), item[1])):
        members = tuple(sorted(grouped[key], key=lambda order: order.order_id))
        ordered.append(members)
    return tuple(ordered)


def _touches(order: RestingLimitOrder, *, bar: _Bar, penetration_bps: Decimal) -> bool:
    threshold = _threshold(order, penetration_bps)
    return bar.low <= threshold if order.quantity > 0 else bar.high >= threshold


def _threshold(order: RestingLimitOrder, penetration_bps: Decimal) -> Decimal:
    penetration = penetration_bps / Decimal(10_000)
    direction = Decimal(-1) if order.quantity > 0 else Decimal(1)
    return order.limit_price * (Decimal(1) + direction * penetration)


def _decimal(value: object) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


__all__ = ["RestingLimitMatchResult", "match_resting_limit_orders"]
