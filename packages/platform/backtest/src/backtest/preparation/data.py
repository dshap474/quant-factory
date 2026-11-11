"""Normalized market-data validation for execution preparation.

Purpose: validate prepared bars, completed-close reference vectors, and explicit
funding settlements before any Nautilus or account-state work begins.

USAGE:
    >>> from backtest.preparation.data import validate_bars  # doctest: +SKIP
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Mapping, Sequence

import polars as pl

from execution import FundingSettlement, InstrumentKey, ReferencePrice

from ..errors import BacktestContractError
from .validation import require_utc_datetime, to_decimal

# --------------------------------------------------------------------------- #
# Normalized schemas
# --------------------------------------------------------------------------- #

REFERENCE_REQUIRED_COLUMNS = ("decision_at", "instrument", "observed_at", "price")
BAR_REQUIRED_COLUMNS = (
    "instrument",
    "source_timestamp",
    "ts_event",
    "ts_init",
    "open",
    "high",
    "low",
    "close",
    "volume",
)
FUNDING_REQUIRED_COLUMNS = (
    "settlement_id",
    "instrument",
    "settled_at",
    "rate",
    "mark_price",
)

BarCloseIndex = dict[tuple[str, datetime], Decimal]


# --------------------------------------------------------------------------- #
# Bars
# --------------------------------------------------------------------------- #


def validate_bars(
    bars: pl.DataFrame,
    known_wires: set[str],
) -> tuple[pl.DataFrame, BarCloseIndex]:
    """Validate normalized completed bars while preserving their input dtypes."""
    if not isinstance(bars, pl.DataFrame):
        raise BacktestContractError("bars must be a polars DataFrame")
    missing = [column for column in BAR_REQUIRED_COLUMNS if column not in bars.columns]
    if missing:
        raise BacktestContractError(f"bars missing required columns: {', '.join(missing)}")

    frame = bars.select(list(BAR_REQUIRED_COLUMNS))
    if frame.is_empty():
        raise BacktestContractError("bars must be non-empty")
    if frame.null_count().sum_horizontal().item() > 0:
        raise BacktestContractError("bars must not contain nulls")
    if frame.select(["instrument", "ts_init"]).n_unique() != frame.height:
        raise BacktestContractError("bars must be unique on (instrument, ts_init)")
    numeric_columns = ("open", "high", "low", "close", "volume")
    invalid_numeric = [column for column in numeric_columns if not frame.schema[column].is_numeric()]
    if invalid_numeric:
        raise BacktestContractError(f"bars numeric columns have non-numeric dtypes: {', '.join(invalid_numeric)}")

    close_index: BarCloseIndex = {}
    for row in frame.iter_rows(named=True):
        instrument = row["instrument"]
        if not isinstance(instrument, str) or not instrument:
            raise BacktestContractError("bars.instrument must be a non-empty string")
        if instrument not in known_wires:
            raise BacktestContractError(f"bars contain unknown instrument {instrument!r}")

        require_utc_datetime(row["source_timestamp"], "bars.source_timestamp")
        ts_event = require_utc_datetime(row["ts_event"], "bars.ts_event")
        ts_init = require_utc_datetime(row["ts_init"], "bars.ts_init")
        if ts_event > ts_init:
            raise BacktestContractError(f"bars.ts_event must be <= ts_init for {instrument} at {ts_init.isoformat()}")

        open_price = to_decimal(row["open"], "bars.open")
        high = to_decimal(row["high"], "bars.high")
        low = to_decimal(row["low"], "bars.low")
        close = to_decimal(row["close"], "bars.close")
        volume = to_decimal(row["volume"], "bars.volume")
        for name, value in (
            ("open", open_price),
            ("high", high),
            ("low", low),
            ("close", close),
        ):
            if value <= 0:
                raise BacktestContractError(f"bars.{name} must be positive, got {value}")
        if volume < 0:
            raise BacktestContractError(f"bars.volume must be non-negative, got {volume}")
        if high < max(open_price, close, low):
            raise BacktestContractError(
                f"bars.high must be >= max(open, close, low) for {instrument} at {ts_init.isoformat()}"
            )
        if low > min(open_price, close, high):
            raise BacktestContractError(
                f"bars.low must be <= min(open, close, high) for {instrument} at {ts_init.isoformat()}"
            )
        close_index[(instrument, ts_init)] = close

    normalized = frame.with_columns(
        pl.col(column).cast(pl.Datetime("ns", "UTC"), strict=True)
        for column in ("source_timestamp", "ts_event", "ts_init")
    )
    return normalized.sort(["instrument", "ts_init"]), close_index


# --------------------------------------------------------------------------- #
# Reference prices
# --------------------------------------------------------------------------- #


def validate_reference_prices(
    reference_prices: pl.DataFrame,
    *,
    expected_decisions: Sequence[datetime],
    known_wires: set[str],
    wire_to_key: Mapping[str, InstrumentKey],
    bar_closes: Mapping[tuple[str, datetime], Decimal],
) -> dict[datetime, tuple[ReferencePrice, ...]]:
    """Validate one exact completed-close vector per StrategyWeights decision."""
    if not isinstance(reference_prices, pl.DataFrame):
        raise BacktestContractError("reference_prices must be a polars DataFrame")
    missing = [column for column in REFERENCE_REQUIRED_COLUMNS if column not in reference_prices.columns]
    if missing:
        raise BacktestContractError(f"reference_prices missing required columns: {', '.join(missing)}")
    frame = reference_prices.select(list(REFERENCE_REQUIRED_COLUMNS))
    if frame.is_empty():
        raise BacktestContractError("reference_prices must be non-empty")
    if frame.null_count().sum_horizontal().item() > 0:
        raise BacktestContractError("reference_prices must not contain nulls")

    grouped: dict[datetime, list[tuple[str, datetime, Decimal]]] = {}
    for row in frame.iter_rows(named=True):
        decision_at = require_utc_datetime(row["decision_at"], "reference_prices.decision_at")
        instrument = row["instrument"]
        if not isinstance(instrument, str) or not instrument:
            raise BacktestContractError("reference_prices.instrument must be a non-empty string")
        if instrument not in known_wires:
            raise BacktestContractError(f"reference_prices contain unknown instrument {instrument!r}")
        observed_at = require_utc_datetime(row["observed_at"], "reference_prices.observed_at")
        price = to_decimal(row["price"], "reference_prices.price")
        if price <= 0:
            raise BacktestContractError(f"reference_prices.price must be positive, got {price}")
        grouped.setdefault(decision_at, []).append((instrument, observed_at, price))

    expected = set(expected_decisions)
    actual = set(grouped)
    if missing_decisions := expected - actual:
        formatted = ", ".join(timestamp.isoformat() for timestamp in sorted(missing_decisions))
        raise BacktestContractError(f"reference_prices missing decision vectors: {formatted}")
    if extra_decisions := actual - expected:
        formatted = ", ".join(timestamp.isoformat() for timestamp in sorted(extra_decisions))
        raise BacktestContractError(f"reference_prices contain extra decision vectors: {formatted}")

    indexed: dict[datetime, tuple[ReferencePrice, ...]] = {}
    for decision_at in expected_decisions:
        rows = grouped[decision_at]
        instruments = [instrument for instrument, _, _ in rows]
        if len(set(instruments)) != len(instruments):
            raise BacktestContractError(
                f"duplicate reference_prices instruments for decision_at={decision_at.isoformat()}"
            )
        if set(instruments) != known_wires:
            missing_instruments = known_wires - set(instruments)
            extra_instruments = set(instruments) - known_wires
            details = sorted(missing_instruments or extra_instruments)
            label = "missing" if missing_instruments else "extra"
            raise BacktestContractError(
                f"reference_prices {label} instruments for decision_at={decision_at.isoformat()}: {', '.join(details)}"
            )

        observed_times = {observed_at for _, observed_at, _ in rows}
        if len(observed_times) != 1:
            raise BacktestContractError(
                f"reference_prices for decision_at={decision_at.isoformat()} must share one observed_at"
            )
        observed_at = next(iter(observed_times))
        if observed_at > decision_at:
            raise BacktestContractError(
                "reference_prices observed_at must be <= decision_at "
                f"({observed_at.isoformat()} > {decision_at.isoformat()})"
            )

        values: list[ReferencePrice] = []
        for instrument, _, price in rows:
            completed_close = bar_closes.get((instrument, observed_at))
            if completed_close is None:
                raise BacktestContractError(
                    f"reference price for {instrument} at {observed_at.isoformat()} "
                    "does not identify a completed normalized bar close"
                )
            if price != completed_close:
                raise BacktestContractError(
                    f"reference price for {instrument} at {observed_at.isoformat()} "
                    f"must equal completed bar close {completed_close}, got {price}"
                )
            values.append(
                ReferencePrice(
                    instrument=wire_to_key[instrument],
                    price=price,
                    observed_at=observed_at,
                )
            )
        indexed[decision_at] = tuple(sorted(values, key=lambda item: item.instrument.sort_key()))
    return indexed


# --------------------------------------------------------------------------- #
# Funding settlements
# --------------------------------------------------------------------------- #


def validate_funding_settlements(
    funding_settlements: pl.DataFrame | None,
    *,
    known_wires: set[str],
    wire_to_key: Mapping[str, InstrumentKey],
) -> tuple[FundingSettlement, ...]:
    """Validate explicit settlement rows without observation-time inference."""
    if funding_settlements is None:
        return ()
    if not isinstance(funding_settlements, pl.DataFrame):
        raise BacktestContractError("funding_settlements must be a polars DataFrame")
    missing = [column for column in FUNDING_REQUIRED_COLUMNS if column not in funding_settlements.columns]
    if missing:
        raise BacktestContractError(f"funding_settlements missing required columns: {', '.join(missing)}")
    frame = funding_settlements.select(list(FUNDING_REQUIRED_COLUMNS))
    if frame.null_count().sum_horizontal().item() > 0:
        raise BacktestContractError("funding_settlements must not contain nulls")

    settlements: list[FundingSettlement] = []
    settlement_ids: set[str] = set()
    instrument_times: set[tuple[str, datetime]] = set()
    for row in frame.iter_rows(named=True):
        settlement_id = row["settlement_id"]
        if not isinstance(settlement_id, str) or not settlement_id.strip():
            raise BacktestContractError("funding_settlements.settlement_id must be non-empty")
        if settlement_id in settlement_ids:
            raise BacktestContractError(f"duplicate funding settlement_id: {settlement_id!r}")
        settlement_ids.add(settlement_id)

        instrument = row["instrument"]
        if not isinstance(instrument, str) or instrument not in known_wires:
            raise BacktestContractError(f"funding_settlements unknown instrument: {instrument!r}")
        settled_at = require_utc_datetime(row["settled_at"], "funding_settlements.settled_at")
        pair = (instrument, settled_at)
        if pair in instrument_times:
            raise BacktestContractError(
                f"duplicate funding (instrument, settled_at): {instrument} @ {settled_at.isoformat()}"
            )
        instrument_times.add(pair)

        rate = to_decimal(row["rate"], "funding_settlements.rate")
        mark_price = to_decimal(row["mark_price"], "funding_settlements.mark_price")
        if mark_price <= 0:
            raise BacktestContractError(f"funding_settlements.mark_price must be positive, got {mark_price}")
        settlements.append(
            FundingSettlement(
                settlement_id=settlement_id,
                instrument=wire_to_key[instrument],
                settled_at=settled_at,
                rate=rate,
                mark_price=mark_price,
            )
        )

    settlements.sort(key=lambda item: (item.settled_at, item.instrument.sort_key(), item.settlement_id))
    return tuple(settlements)
