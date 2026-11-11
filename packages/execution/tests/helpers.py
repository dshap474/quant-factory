"""Shared hermetic builders for packages/execution tests.

Purpose: construct neutral linear instruments, targets, and
account snapshots without DB, Nautilus, or strategy dependencies.

USAGE:
    >>> from helpers import make_spec
    >>> make_spec("BTCUSDT").key.symbol
    'BTCUSDT'
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from execution import (
    AccountSnapshot,
    InstrumentKey,
    InstrumentSpec,
    PortfolioTarget,
    PositionSnapshot,
    ReferencePrice,
    TargetWeight,
)

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

UTC = timezone.utc
DECISION = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
EARLIEST = DECISION + timedelta(minutes=1)
AS_OF = DECISION

# --------------------------------------------------------------------------- #
# Builders
# --------------------------------------------------------------------------- #


def make_key(symbol: str, venue: str = "EXAMPLE") -> InstrumentKey:
    return InstrumentKey(venue=venue, symbol=symbol)


def make_spec(
    symbol: str,
    *,
    quantity_increment: str = "0.001",
    price_increment: str = "0.01",
    base: str | None = None,
) -> InstrumentSpec:
    return InstrumentSpec(
        key=make_key(symbol),
        product="perpetual",
        base_currency=base or symbol.replace("USDT", ""),
        quote_currency="USDT",
        settlement_currency="USDT",
        is_inverse=False,
        multiplier=Decimal("1"),
        price_increment=Decimal(price_increment),
        quantity_increment=Decimal(quantity_increment),
        min_quantity=Decimal(quantity_increment),
        max_quantity=Decimal("1000000"),
        min_notional=Decimal("5"),
        max_notional=Decimal("100000000"),
        maker_fee_rate=Decimal("0.0002"),
        taker_fee_rate=Decimal("0.0004"),
    )


def make_target(
    *,
    target_id: str = "t1",
    weights: list[tuple[str, str]] | None = None,
    cash_weight: str = "0.0",
    prices: dict[str, str] | None = None,
    decision_at: datetime = DECISION,
    earliest_execution_at: datetime = EARLIEST,
) -> PortfolioTarget:
    if weights is None:
        weights = [("BTCUSDT", "0.5"), ("ETHUSDT", "0.5")]
    if prices is None:
        prices = {"BTCUSDT": "50000", "ETHUSDT": "3000"}

    target_weights = tuple(TargetWeight(instrument=make_key(sym), weight=Decimal(w)) for sym, w in weights)
    refs = tuple(
        ReferencePrice(
            instrument=make_key(sym),
            price=Decimal(prices[sym]),
            observed_at=decision_at,
        )
        for sym, _ in weights
    )
    return PortfolioTarget(
        target_id=target_id,
        decision_at=decision_at,
        earliest_execution_at=earliest_execution_at,
        weights=target_weights,
        cash_weight=Decimal(cash_weight),
        reference_prices=refs,
    )


def make_account(
    *,
    equity: str = "100000",
    cash: str | None = None,
    positions: list[tuple[str, str, str]] | None = None,
    as_of: datetime = AS_OF,
) -> AccountSnapshot:
    pos = tuple(
        PositionSnapshot(
            instrument=make_key(sym),
            quantity=Decimal(qty),
            average_price=Decimal(avg),
        )
        for sym, qty, avg in (positions or [])
    )
    marks = tuple(
        ReferencePrice(
            instrument=p.instrument,
            price=p.average_price if p.average_price > 0 else Decimal("1"),
            observed_at=as_of,
        )
        for p in pos
    )
    cash_d = Decimal(cash) if cash is not None else Decimal(equity)
    return AccountSnapshot(
        as_of=as_of,
        cash=cash_d,
        equity=Decimal(equity),
        positions=pos,
        marks=marks,
        cumulative_fees=Decimal("0"),
        cumulative_funding=Decimal("0"),
    )
