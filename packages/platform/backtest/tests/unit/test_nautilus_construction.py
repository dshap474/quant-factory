"""Actual-Nautilus tests for construction primitives.

Purpose: prove pinned-version rejection, exact CryptoPerpetual metadata, exact
normalized-row Bar values/timestamps, and that an IOC market primary routed
through the project ExecAlgorithm fills at the submission close with real
taker commission without being capped by bar volume 1 for quantity 100.

USAGE:
    uv run --project packages/platform/backtest pytest \\
      packages/platform/backtest/tests/unit/test_nautilus_construction.py -v
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import pytest
from backtest.engines.nautilus.construction import (
    REQUIRED_NAUTILUS_VERSION,
    QF_IMMEDIATE_EXEC_ALGORITHM_ID,
    build_bar,
    build_crypto_perpetual,
    build_immediate_ioc_exec_algorithm,
    calendar_last_bar_type,
    import_nautilus_bundle,
    require_nautilus_version,
)
from backtest.errors import BacktestContractError, BacktestEngineUnavailableError

from execution import InstrumentKey, InstrumentSpec

# --------------------------------------------------------------------------- #
# Fixtures / builders
# --------------------------------------------------------------------------- #

UTC = timezone.utc
TS_CLOSE = datetime(2024, 6, 1, 12, 1, 0, tzinfo=UTC)


def _btc_spec() -> InstrumentSpec:
    return InstrumentSpec(
        key=InstrumentKey(venue="BINANCE", symbol="BTCUSDT"),
        product="perpetual",
        base_currency="BTC",
        quote_currency="USDT",
        settlement_currency="USDT",
        is_inverse=False,
        multiplier=Decimal("1"),
        price_increment=Decimal("0.01"),
        quantity_increment=Decimal("0.001"),
        min_quantity=Decimal("0.001"),
        max_quantity=Decimal("1000000"),
        min_notional=Decimal("5"),
        max_notional=Decimal("100000000"),
        maker_fee_rate=Decimal("0.0002"),
        taker_fee_rate=Decimal("0.0004"),
    )


@pytest.fixture(scope="module")
def nt() -> dict:
    pytest.importorskip("nautilus_trader")
    return import_nautilus_bundle()


# --------------------------------------------------------------------------- #
# Version pin
# --------------------------------------------------------------------------- #


def test_require_nautilus_version_accepts_exact_pin() -> None:
    assert require_nautilus_version(REQUIRED_NAUTILUS_VERSION) == REQUIRED_NAUTILUS_VERSION


def test_require_nautilus_version_rejects_other_versions() -> None:
    with pytest.raises(BacktestEngineUnavailableError, match="1\\.224\\.0"):
        require_nautilus_version("1.230.0")


def test_import_bundle_reports_exact_pinned_version(nt: dict) -> None:
    assert nt["nautilus_version"] == REQUIRED_NAUTILUS_VERSION


# --------------------------------------------------------------------------- #
# CryptoPerpetual metadata
# --------------------------------------------------------------------------- #


def test_build_crypto_perpetual_exact_metadata(nt: dict) -> None:
    instrument = build_crypto_perpetual(_btc_spec(), nt=nt)

    assert str(instrument.id) == "BTCUSDT.BINANCE"
    assert str(instrument.raw_symbol) == "BTCUSDT"
    assert str(instrument.id.venue) == "BINANCE"
    assert str(instrument.base_currency) == "BTC"
    assert str(instrument.quote_currency) == "USDT"
    assert str(instrument.settlement_currency) == "USDT"
    assert instrument.is_inverse is False
    assert instrument.price_precision == 2
    assert instrument.size_precision == 3
    assert str(instrument.price_increment) == "0.01"
    assert str(instrument.size_increment) == "0.001"
    assert str(instrument.multiplier) == "1"
    assert str(instrument.min_quantity) == "0.001"
    assert str(instrument.max_quantity) == "1000000"
    assert str(instrument.min_notional) == "5.00000000 USDT"
    assert str(instrument.max_notional) == "100000000.00000000 USDT"
    assert instrument.maker_fee == Decimal("0.0002")
    assert instrument.taker_fee == Decimal("0.0004")


# --------------------------------------------------------------------------- #
# Bar construction
# --------------------------------------------------------------------------- #


def test_build_bar_preserves_ohlcv_and_utc_ns(nt: dict) -> None:
    instrument = build_crypto_perpetual(_btc_spec(), nt=nt)
    bar_type = calendar_last_bar_type(
        instrument.id,
        (TS_CLOSE - timedelta(minutes=1), TS_CLOSE),
        nt=nt,
    )
    ts_event = TS_CLOSE.replace(second=0)
    ts_init = TS_CLOSE
    row = {
        "open": Decimal("100.00"),
        "high": Decimal("106.00"),
        "low": Decimal("99.00"),
        "close": Decimal("105.00"),
        "volume": Decimal("1.000"),
        "ts_event": ts_event,
        "ts_init": ts_init,
    }

    bar = build_bar(row, instrument=instrument, bar_type=bar_type, nt=nt)

    assert bar.bar_type == bar_type
    assert str(bar.open) == "100.00"
    assert str(bar.high) == "106.00"
    assert str(bar.low) == "99.00"
    assert str(bar.close) == "105.00"
    assert str(bar.volume) == "1.000"
    assert int(bar.ts_event) == int(nt["dt_to_unix_nanos"](ts_event))
    assert int(bar.ts_init) == int(nt["dt_to_unix_nanos"](ts_init))
    assert int(bar.ts_init) == 1_717_243_260_000_000_000


def test_calendar_bar_type_rejects_irregular_spacing(nt: dict) -> None:
    instrument = build_crypto_perpetual(_btc_spec(), nt=nt)
    with pytest.raises(BacktestContractError, match="regular execution_calendar"):
        calendar_last_bar_type(
            instrument.id,
            (
                TS_CLOSE - timedelta(minutes=3),
                TS_CLOSE - timedelta(minutes=2),
                TS_CLOSE,
            ),
            nt=nt,
        )


# --------------------------------------------------------------------------- #
# ExecAlgorithm fill path (no mocks)
# --------------------------------------------------------------------------- #


def test_ioc_market_via_exec_algorithm_fills_qty_100_on_close_with_taker_fee(nt: dict) -> None:
    instrument = build_crypto_perpetual(_btc_spec(), nt=nt)
    bar_type = calendar_last_bar_type(
        instrument.id,
        (TS_CLOSE - timedelta(minutes=1), TS_CLOSE),
        nt=nt,
    )
    close_px = Decimal("105.00")
    qty = Decimal("100.000")
    bar_volume = Decimal("1.000")
    ts_ns = int(nt["dt_to_unix_nanos"](TS_CLOSE))

    bar = build_bar(
        {
            "open": Decimal("100.00"),
            "high": Decimal("106.00"),
            "low": Decimal("99.00"),
            "close": close_px,
            "volume": bar_volume,
            "ts_event": ts_ns,
            "ts_init": ts_ns,
        },
        instrument=instrument,
        bar_type=bar_type,
        nt=nt,
    )

    StrategyConfig = nt["StrategyConfig"]
    Strategy = nt["Strategy"]
    OrderSide = nt["OrderSide"]
    TimeInForce = nt["TimeInForce"]
    LiquiditySide = nt["LiquiditySide"]
    exec_id = nt["ExecAlgorithmId"](QF_IMMEDIATE_EXEC_ALGORITHM_ID)
    fill_events: list[Any] = []
    submitted = {"value": False}

    class _ProbeConfig(StrategyConfig, frozen=True):
        instrument_id: object | None = None
        bar_type: object | None = None

    class _ProbeStrategy(Strategy):
        def on_start(self) -> None:
            self.subscribe_bars(self.config.bar_type)

        def on_bar(self, _bar: object) -> None:
            if submitted["value"]:
                return
            submitted["value"] = True
            order = self.order_factory.market(
                instrument_id=self.config.instrument_id,
                order_side=OrderSide.BUY,
                quantity=instrument.make_qty(str(qty)),
                time_in_force=TimeInForce.IOC,
                exec_algorithm_id=exec_id,
            )
            self.submit_order(order)

        def on_order_filled(self, event: object) -> None:
            fill_events.append(event)

    engine = nt["BacktestEngine"](
        config=nt["BacktestEngineConfig"](
            trader_id=nt["TraderId"]("QF-CONSTRUCTION-001"),
            logging=nt["LoggingConfig"](log_level="ERROR"),
        )
    )
    try:
        engine.add_venue(
            venue=nt["Venue"]("BINANCE"),
            oms_type=nt["OmsType"].NETTING,
            account_type=nt["AccountType"].MARGIN,
            base_currency=nt["USDT"],
            starting_balances=[nt["Money"](10_000_000, nt["USDT"])],
            default_leverage=Decimal("10"),
            bar_execution=True,
            use_random_ids=False,
            fee_model=nt["MakerTakerFeeModel"](),
            fill_model=nt["BestPriceFillModel"](),
        )
        engine.add_instrument(instrument)
        engine.add_data([bar])
        algo = build_immediate_ioc_exec_algorithm(nt=nt)
        assert str(algo.id) == QF_IMMEDIATE_EXEC_ALGORITHM_ID
        engine.add_exec_algorithm(algo)
        strategy = _ProbeStrategy(_ProbeConfig(instrument_id=instrument.id, bar_type=bar_type))
        engine.add_strategy(strategy)
        engine.run()

        orders = engine.cache.orders()
        assert len(orders) == 1
        order = orders[0]
        assert str(order.filled_qty) == "100.000"
        assert float(order.filled_qty) > float(bar_volume)
        assert Decimal(str(order.avg_px)) == close_px

        assert len(fill_events) == 1
        fill = fill_events[0]
        assert int(fill.ts_event) == ts_ns
        assert str(fill.last_px) == "105.00"
        assert str(fill.last_qty) == "100.000"
        assert fill.liquidity_side == LiquiditySide.TAKER
        expected_commission = qty * close_px * Decimal("0.0004")
        assert Decimal(str(fill.commission).split()[0]) == expected_commission
        assert str(fill.commission).endswith("USDT")
    finally:
        engine.dispose()
