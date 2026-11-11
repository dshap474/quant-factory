"""Nautilus construction primitives for the prepared-execution path.

Purpose: lazy-load the pinned ``nautilus_trader`` runtime, map validated
``InstrumentSpec`` values to ``CryptoPerpetual``, map prepared normalized bar rows to
Nautilus ``Bar`` objects, and provide a minimal immediate-IOC ``ExecAlgorithm``.

USAGE:
    >>> from backtest.engines.nautilus.construction import (  # doctest: +SKIP
    ...     import_nautilus_bundle,
    ...     build_crypto_perpetual,
    ...     build_bar,
    ...     build_immediate_ioc_exec_algorithm,
    ... )
    >>> nt = import_nautilus_bundle()  # doctest: +SKIP
    >>> instrument = build_crypto_perpetual(spec, nt=nt)  # doctest: +SKIP
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping, Sequence

from execution import InstrumentSpec

from ...errors import BacktestContractError, BacktestEngineUnavailableError

# --------------------------------------------------------------------------- #
# Version pin
# --------------------------------------------------------------------------- #

REQUIRED_NAUTILUS_VERSION = "1.224.0"
QF_IMMEDIATE_EXEC_ALGORITHM_ID = "QF-IMMEDIATE"
_BINANCE_VENUE = "BINANCE"

# --------------------------------------------------------------------------- #
# Lazy import bundle
# --------------------------------------------------------------------------- #


def import_nautilus_bundle() -> dict[str, Any]:
    """Import and return the pinned Nautilus construction surface.

    Raises
    ------
    BacktestEngineUnavailableError
        If ``nautilus_trader`` is missing or not exactly
        ``REQUIRED_NAUTILUS_VERSION``.
    """
    try:
        import nautilus_trader
        from nautilus_trader.backtest.engine import BacktestEngine  # ty: ignore[unresolved-import]
        from nautilus_trader.backtest.models import BestPriceFillModel, MakerTakerFeeModel
        from nautilus_trader.config import (
            BacktestEngineConfig,
            ExecAlgorithmConfig,
            LoggingConfig,
            StrategyConfig,
        )
        from nautilus_trader.core.datetime import dt_to_unix_nanos
        from nautilus_trader.core.uuid import UUID4
        from nautilus_trader.execution.algorithm import ExecAlgorithm  # ty: ignore[unresolved-import]
        from nautilus_trader.model.currencies import USDT
        from nautilus_trader.model.data import Bar, BarSpecification, BarType  # ty: ignore[unresolved-import]
        from nautilus_trader.model.enums import (
            AccountType,
            BarAggregation,
            LiquiditySide,
            OmsType,
            OrderSide,
            OrderType,
            PriceType,
            TimeInForce,
        )
        from nautilus_trader.model.events import OrderFilled
        from nautilus_trader.model.identifiers import (  # ty: ignore[unresolved-import]
            AccountId,
            ClientOrderId,
            ExecAlgorithmId,
            InstrumentId,
            PositionId,
            StrategyId,
            Symbol,
            TradeId,
            TraderId,
            Venue,
            VenueOrderId,
        )
        from nautilus_trader.model.instruments import CryptoPerpetual
        from nautilus_trader.model.objects import Currency, Money, Price, Quantity  # ty: ignore[unresolved-import]
        from nautilus_trader.model.position import Position  # ty: ignore[unresolved-import]
        from nautilus_trader.trading.strategy import Strategy  # ty: ignore[unresolved-import]
    except ImportError as exc:
        raise BacktestEngineUnavailableError(
            "Nautilus construction requires `nautilus_trader`. "
            f"Install the pinned runtime: nautilus-trader=={REQUIRED_NAUTILUS_VERSION}"
        ) from exc

    version = str(getattr(nautilus_trader, "__version__", "unknown"))
    require_nautilus_version(version)

    return {
        "nautilus_version": version,
        "BacktestEngine": BacktestEngine,
        "BacktestEngineConfig": BacktestEngineConfig,
        "BestPriceFillModel": BestPriceFillModel,
        "MakerTakerFeeModel": MakerTakerFeeModel,
        "ExecAlgorithmConfig": ExecAlgorithmConfig,
        "LoggingConfig": LoggingConfig,
        "StrategyConfig": StrategyConfig,
        "dt_to_unix_nanos": dt_to_unix_nanos,
        "UUID4": UUID4,
        "ExecAlgorithm": ExecAlgorithm,
        "USDT": USDT,
        "Bar": Bar,
        "BarSpecification": BarSpecification,
        "BarType": BarType,
        "AccountType": AccountType,
        "BarAggregation": BarAggregation,
        "LiquiditySide": LiquiditySide,
        "OmsType": OmsType,
        "OrderSide": OrderSide,
        "OrderType": OrderType,
        "PriceType": PriceType,
        "TimeInForce": TimeInForce,
        "ExecAlgorithmId": ExecAlgorithmId,
        "AccountId": AccountId,
        "ClientOrderId": ClientOrderId,
        "InstrumentId": InstrumentId,
        "PositionId": PositionId,
        "StrategyId": StrategyId,
        "Symbol": Symbol,
        "TradeId": TradeId,
        "TraderId": TraderId,
        "Venue": Venue,
        "VenueOrderId": VenueOrderId,
        "OrderFilled": OrderFilled,
        "Position": Position,
        "CryptoPerpetual": CryptoPerpetual,
        "Currency": Currency,
        "Money": Money,
        "Price": Price,
        "Quantity": Quantity,
        "Strategy": Strategy,
    }


def require_nautilus_version(version: str) -> str:
    """Reject any runtime that is not exactly the pinned Nautilus version."""
    if version != REQUIRED_NAUTILUS_VERSION:
        raise BacktestEngineUnavailableError(f"nautilus_trader=={REQUIRED_NAUTILUS_VERSION} required, got {version!r}")
    return version


# --------------------------------------------------------------------------- #
# Instrument construction
# --------------------------------------------------------------------------- #


def build_crypto_perpetual(
    spec: InstrumentSpec,
    *,
    nt: Mapping[str, Any] | None = None,
    ts_event: int = 0,
    ts_init: int = 0,
) -> Any:
    """Map a validated Binance linear-perpetual ``InstrumentSpec`` to CryptoPerpetual."""
    if not isinstance(spec, InstrumentSpec):
        raise BacktestContractError("spec must be InstrumentSpec")
    if spec.key.venue != _BINANCE_VENUE:
        raise BacktestContractError(
            f"CryptoPerpetual construction requires venue {_BINANCE_VENUE}, got {spec.key.venue!r}"
        )

    bundle = dict(nt) if nt is not None else import_nautilus_bundle()
    price_increment = bundle["Price"].from_str(_decimal_str(spec.price_increment))
    size_increment = bundle["Quantity"].from_str(_decimal_str(spec.quantity_increment))
    settlement = bundle["Currency"].from_str(spec.settlement_currency)

    return bundle["CryptoPerpetual"](
        instrument_id=bundle["InstrumentId"](
            symbol=bundle["Symbol"](spec.key.symbol),
            venue=bundle["Venue"](spec.key.venue),
        ),
        raw_symbol=bundle["Symbol"](spec.key.symbol),
        base_currency=bundle["Currency"].from_str(spec.base_currency),
        quote_currency=bundle["Currency"].from_str(spec.quote_currency),
        settlement_currency=settlement,
        is_inverse=spec.is_inverse,
        price_precision=int(price_increment.precision),
        size_precision=int(size_increment.precision),
        price_increment=price_increment,
        size_increment=size_increment,
        multiplier=bundle["Quantity"].from_str(_decimal_str(spec.multiplier)),
        max_quantity=bundle["Quantity"].from_str(_decimal_str(spec.max_quantity)),
        min_quantity=bundle["Quantity"].from_str(_decimal_str(spec.min_quantity)),
        max_notional=bundle["Money"](spec.max_notional, settlement),
        min_notional=bundle["Money"](spec.min_notional, settlement),
        maker_fee=Decimal(spec.maker_fee_rate),
        taker_fee=Decimal(spec.taker_fee_rate),
        ts_event=int(ts_event),
        ts_init=int(ts_init),
    )


# --------------------------------------------------------------------------- #
# Bar construction
# --------------------------------------------------------------------------- #


def build_bar(
    row: Mapping[str, Any],
    *,
    instrument: Any,
    bar_type: Any,
    nt: Mapping[str, Any] | None = None,
) -> Any:
    """Map one prepared normalized OHLCV row onto a Nautilus ``Bar``.

    ``bar_type`` must already carry the caller-supplied minute ``BarSpecification``.
    ``ts_event`` / ``ts_init`` are preserved as UTC nanoseconds.
    """
    required = ("open", "high", "low", "close", "volume", "ts_event", "ts_init")
    missing = [name for name in required if name not in row]
    if missing:
        raise BacktestContractError(f"bar row missing fields: {', '.join(missing)}")

    bundle = dict(nt) if nt is not None else import_nautilus_bundle()
    return bundle["Bar"](
        bar_type=bar_type,
        open=instrument.make_price(_decimal_str(row["open"])),
        high=instrument.make_price(_decimal_str(row["high"])),
        low=instrument.make_price(_decimal_str(row["low"])),
        close=instrument.make_price(_decimal_str(row["close"])),
        volume=instrument.make_qty(_decimal_str(row["volume"])),
        ts_event=_to_unix_nanos(row["ts_event"], bundle),
        ts_init=_to_unix_nanos(row["ts_init"], bundle),
    )


def calendar_last_bar_type(
    instrument_id: Any,
    execution_calendar: Sequence[datetime],
    *,
    nt: Mapping[str, Any] | None = None,
) -> Any:
    """Build a LAST external bar type from a proven regular execution calendar."""
    bundle = dict(nt) if nt is not None else import_nautilus_bundle()
    step, aggregation = _calendar_bar_interval(execution_calendar, bundle)
    return bundle["BarType"](
        instrument_id,
        bundle["BarSpecification"](
            step=step,
            aggregation=aggregation,
            price_type=bundle["PriceType"].LAST,
        ),
    )


# --------------------------------------------------------------------------- #
# Immediate IOC ExecAlgorithm
# --------------------------------------------------------------------------- #


def build_immediate_ioc_exec_algorithm(*, nt: Mapping[str, Any] | None = None) -> Any:
    """Return the project-owned immediate MARKET+IOC execution algorithm."""
    bundle = dict(nt) if nt is not None else import_nautilus_bundle()
    ExecAlgorithm = bundle["ExecAlgorithm"]
    ExecAlgorithmConfig = bundle["ExecAlgorithmConfig"]
    ExecAlgorithmId = bundle["ExecAlgorithmId"]
    OrderType = bundle["OrderType"]
    TimeInForce = bundle["TimeInForce"]
    exec_id = ExecAlgorithmId(QF_IMMEDIATE_EXEC_ALGORITHM_ID)

    class ImmediateIocExecAlgorithm(ExecAlgorithm):
        """Submit a primary order unchanged after validating MARKET+IOC."""

        def __init__(self) -> None:
            super().__init__(ExecAlgorithmConfig(exec_algorithm_id=exec_id))

        def on_start(self) -> None:
            return None

        def on_order(self, order: Any) -> None:
            if order.order_type != OrderType.MARKET:
                raise ValueError(f"{QF_IMMEDIATE_EXEC_ALGORITHM_ID} requires MARKET orders, got {order.order_type!r}")
            if order.time_in_force != TimeInForce.IOC:
                raise ValueError(
                    f"{QF_IMMEDIATE_EXEC_ALGORITHM_ID} requires IOC time-in-force, got {order.time_in_force!r}"
                )
            self.submit_order(order)

    return ImmediateIocExecAlgorithm()


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _decimal_str(value: Any) -> str:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return format(Decimal(str(value)), "f")
    text = str(value).strip()
    if not text:
        raise BacktestContractError("numeric bar/instrument field must be non-empty")
    return format(Decimal(text), "f")


def _to_unix_nanos(value: Any, bundle: Mapping[str, Any]) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise BacktestContractError("bar datetime timestamp must be timezone-aware UTC")
        return int(bundle["dt_to_unix_nanos"](value))
    raise BacktestContractError(f"bar timestamp must be datetime or int nanoseconds, got {type(value).__name__}")


def _calendar_bar_interval(
    execution_calendar: Sequence[datetime],
    bundle: Mapping[str, Any],
) -> tuple[int, Any]:
    """Return an exact Nautilus step/aggregation for a regular calendar."""
    values = tuple(execution_calendar)
    if len(values) < 2:
        raise BacktestContractError("execution_calendar needs at least two closes for a bar type")
    deltas = tuple(right - left for left, right in zip(values, values[1:]))
    interval = deltas[0]
    if interval.total_seconds() <= 0 or any(delta != interval for delta in deltas[1:]):
        raise BacktestContractError("Prepared execution requires a regular execution_calendar to construct an exact Nautilus BarType")

    micros = ((interval.days * 86_400) + interval.seconds) * 1_000_000 + interval.microseconds
    units = (
        (86_400_000_000, bundle["BarAggregation"].DAY),
        (3_600_000_000, bundle["BarAggregation"].HOUR),
        (60_000_000, bundle["BarAggregation"].MINUTE),
        (1_000_000, bundle["BarAggregation"].SECOND),
        (1_000, bundle["BarAggregation"].MILLISECOND),
    )
    for unit_micros, aggregation in units:
        step, remainder = divmod(micros, unit_micros)
        if remainder == 0 and step > 0:
            return step, aggregation
    raise BacktestContractError("execution_calendar interval must resolve exactly to milliseconds or a larger unit")
