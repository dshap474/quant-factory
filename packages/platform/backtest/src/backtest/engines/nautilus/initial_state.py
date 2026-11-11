"""Reconstruct carried positions in Nautilus without submitting setup trades.

Purpose: translate a validated InitialAccountState into deterministic
reconciliation fills processed before strategies and market data start.

USAGE:
    >>> seed_initial_positions(engine, state=state, instruments=instruments, nt=nt)  # doctest: +SKIP
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Mapping

from execution import InitialAccountState, InstrumentKey

from ...errors import BacktestEngineExecutionError

# --------------------------------------------------------------------------- #
# Reconciliation seeding
# --------------------------------------------------------------------------- #


def seed_initial_positions(
    engine: Any,
    *,
    state: InitialAccountState | None,
    instruments: Mapping[InstrumentKey, Any],
    nt: Mapping[str, Any],
) -> None:
    """Process deterministic reconciliation fills for carried positions."""
    if state is None:
        return
    account_id = engine.cache.account_id(nt["Venue"]("BINANCE"))
    if account_id is None:
        account_id = nt["AccountId"]("BINANCE-001")
    timestamp = int(nt["dt_to_unix_nanos"](state.as_of))
    for index, position in enumerate(
        sorted(state.positions, key=lambda item: item.instrument.sort_key()),
        start=1,
    ):
        instrument = instruments[position.instrument]
        side = nt["OrderSide"].BUY if position.quantity > 0 else nt["OrderSide"].SELL
        suffix = f"{index:06d}"
        event = nt["OrderFilled"](
            trader_id=nt["TraderId"]("QF-EXEC-001"),
            strategy_id=nt["StrategyId"]("QF-EXEC"),
            instrument_id=instrument.id,
            client_order_id=nt["ClientOrderId"](f"INITIAL-{suffix}"),
            venue_order_id=nt["VenueOrderId"](f"INITIAL-{suffix}"),
            account_id=account_id,
            trade_id=nt["TradeId"](f"INITIAL-{suffix}"),
            position_id=nt["PositionId"](f"INITIAL-{position.instrument.symbol}"),
            order_side=side,
            order_type=nt["OrderType"].MARKET,
            last_qty=instrument.make_qty(format(abs(position.quantity), "f")),
            last_px=instrument.make_price(format(position.average_price, "f")),
            currency=nt["USDT"],
            commission=nt["Money"](Decimal(0), nt["USDT"]),
            liquidity_side=nt["LiquiditySide"].NO_LIQUIDITY_SIDE,
            event_id=nt["UUID4"].from_str(f"00000000-0000-4000-8000-{index:012d}"),
            ts_event=timestamp,
            ts_init=timestamp,
            reconciliation=True,
        )
        engine.cache.add_position(nt["Position"](instrument, event), nt["OmsType"].NETTING)

    expected = {position.instrument: position.quantity for position in state.positions}
    for key, expected_quantity in expected.items():
        actual = _cache_net_quantity(engine, instruments[key].id)
        if actual != expected_quantity:
            raise BacktestEngineExecutionError(
                f"initial Nautilus position reconcile failed for {key.venue}:{key.symbol}: "
                f"expected={expected_quantity} actual={actual}"
            )


def _cache_net_quantity(engine: Any, instrument_id: Any) -> Decimal:
    positions = [position for position in engine.cache.positions_open() if position.instrument_id == instrument_id]
    return sum((Decimal(str(position.signed_qty)) for position in positions), Decimal(0))


__all__ = ["seed_initial_positions"]
