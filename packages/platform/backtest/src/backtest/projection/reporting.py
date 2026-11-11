"""Event-ordered reporting replay for the linear-perpetual projection.

Purpose: fold completed-bar marks, funding settlements, and accepted fills in
equal-time order mark -> funding -> fills -> report into HoldingPoint and
AccountPoint series. Does not invent marks or events.

USAGE:
    >>> from backtest.projection import replay_reporting  # doctest: +SKIP
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Mapping, Sequence

from execution import (
    AccountPoint,
    Fill,
    FundingSettlement,
    HoldingPoint,
    InstrumentKey,
    equity_from_components,
)

from .linear_perpetual import LinearPerpetualProjection, ProjectionError

# --------------------------------------------------------------------------- #
# Public replay
# --------------------------------------------------------------------------- #


def replay_reporting(
    projection: LinearPerpetualProjection,
    *,
    marks: Sequence[tuple[datetime, Mapping[InstrumentKey, Decimal]]],
    funding: Sequence[FundingSettlement],
    fills: Sequence[Fill],
    reporting_times: Sequence[datetime],
) -> tuple[tuple[HoldingPoint, ...], tuple[AccountPoint, ...]]:
    """Replay events in deterministic equal-time order and sample reports.

    At each distinct event timestamp:
      1. completed bar mark updates for that timestamp;
      2. funding settlements against the carried position;
      3. accepted fills/fees;
      4. if the timestamp is a reporting time, emit holdings and account point.

    Reporting occurs after all same-time fills. Missing input marks or events are
    never synthesized.
    """
    if not isinstance(projection, LinearPerpetualProjection):
        raise TypeError("projection must be LinearPerpetualProjection")
    if not reporting_times:
        raise ProjectionError("reporting_times must be non-empty")
    _require_strictly_increasing(reporting_times, "reporting_times")

    mark_by_time = _index_marks(marks)
    funding_by_time = _index_funding(funding)
    fills_by_time = _index_fills(fills)

    event_times = sorted(set(mark_by_time) | set(funding_by_time) | set(fills_by_time) | set(reporting_times))

    holdings: list[HoldingPoint] = []
    account_path: list[AccountPoint] = []
    report_set = set(reporting_times)

    for ts in event_times:
        if ts in mark_by_time:
            projection.update_marks(mark_by_time[ts], observed_at=ts)

        for settlement in funding_by_time.get(ts, ()):
            projection.apply_funding(settlement)

        for fill in fills_by_time.get(ts, ()):
            projection.apply_fill(fill)

        if ts in report_set:
            holdings.extend(_holding_points(projection, timestamp=ts))
            account_path.append(_account_point(projection, timestamp=ts))

    return tuple(holdings), tuple(account_path)


# --------------------------------------------------------------------------- #
# Indexing and ordering
# --------------------------------------------------------------------------- #


def _index_marks(
    marks: Sequence[tuple[datetime, Mapping[InstrumentKey, Decimal]]],
) -> dict[datetime, dict[InstrumentKey, Decimal]]:
    out: dict[datetime, dict[InstrumentKey, Decimal]] = {}
    for item in marks:
        if not isinstance(item, tuple) or len(item) != 2:
            raise ProjectionError("each marks entry must be (timestamp, mapping)")
        ts, mapping = item
        if ts in out:
            raise ProjectionError(f"duplicate mark timestamp: {ts.isoformat()}")
        if not mapping:
            raise ProjectionError(f"empty mark mapping at {ts.isoformat()}")
        ordered = {key: mapping[key] for key in sorted(mapping, key=lambda instrument: instrument.sort_key())}
        out[ts] = ordered
    return out


def _index_funding(
    funding: Sequence[FundingSettlement],
) -> dict[datetime, tuple[FundingSettlement, ...]]:
    buckets: dict[datetime, list[FundingSettlement]] = {}
    for settlement in funding:
        if not isinstance(settlement, FundingSettlement):
            raise TypeError("funding must contain FundingSettlement values")
        buckets.setdefault(settlement.settled_at, []).append(settlement)
    ordered: dict[datetime, tuple[FundingSettlement, ...]] = {}
    for ts, items in buckets.items():
        items.sort(
            key=lambda s: (
                s.instrument.sort_key(),
                s.settlement_id,
            )
        )
        ordered[ts] = tuple(items)
    return ordered


def _index_fills(fills: Sequence[Fill]) -> dict[datetime, tuple[Fill, ...]]:
    buckets: dict[datetime, list[Fill]] = {}
    for fill in fills:
        if not isinstance(fill, Fill):
            raise TypeError("fills must contain Fill values")
        buckets.setdefault(fill.filled_at, []).append(fill)
    ordered: dict[datetime, tuple[Fill, ...]] = {}
    for ts, items in buckets.items():
        items.sort(key=lambda f: (f.instrument.sort_key(), f.fill_id))
        ordered[ts] = tuple(items)
    return ordered


def _require_strictly_increasing(values: Sequence[datetime], name: str) -> None:
    previous: datetime | None = None
    for value in values:
        if previous is not None and value <= previous:
            raise ProjectionError(f"{name} must be strictly increasing")
        previous = value


# --------------------------------------------------------------------------- #
# Point builders
# --------------------------------------------------------------------------- #


def _holding_points(
    projection: LinearPerpetualProjection,
    *,
    timestamp: datetime,
) -> list[HoldingPoint]:
    points: list[HoldingPoint] = []
    for key in projection.instrument_keys():
        qty = projection.signed_quantity(key)
        mark = projection.mark_price(key)
        if qty == 0 and mark is None:
            continue
        if mark is None:
            raise ProjectionError(f"missing mark for open position at report: {key.venue}:{key.symbol}")
        mult = projection.multiplier(key)
        notional = qty * mark * mult
        points.append(
            HoldingPoint(
                timestamp=timestamp,
                instrument=key,
                quantity=qty,
                mark_price=mark,
                notional=notional,
            )
        )
    return points


def _account_point(
    projection: LinearPerpetualProjection,
    *,
    timestamp: datetime,
) -> AccountPoint:
    unrealized = projection.unrealized_pnl()
    cash = projection.cash()
    equity = equity_from_components(cash, unrealized)
    return AccountPoint(
        timestamp=timestamp,
        cash=cash,
        equity=equity,
        realized_pnl=projection.realized_pnl(),
        unrealized_pnl=unrealized,
        fees=projection.cumulative_fees(),
        funding=projection.cumulative_funding(),
    )
