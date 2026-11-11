"""Fetch daily Yahoo Finance bars and derive the canonical example price panel.

USAGE: ``build_raw_prices(["BTC-USD", "SPY"])`` returns completed provider bars;
``derive_prices(raw)`` returns ``[timestamp, asset, close]`` keyed by canonical asset ids.
"""

from __future__ import annotations

from datetime import UTC, datetime

import polars as pl
from yf_client import YFinanceClient

# --------------------------------------------------------------------------- #
# Source contract
# --------------------------------------------------------------------------- #

DEFAULT_SYMBOLS = ("BTC-USD", "SPY", "QQQ", "GLD", "TLT")
RAW_SCHEMA = {
    "timestamp": pl.Datetime("us", time_zone="UTC"),
    "symbol": pl.String,
    "open": pl.Float64,
    "high": pl.Float64,
    "low": pl.Float64,
    "close": pl.Float64,
    "volume": pl.Int64,
}
CRYPTO_SUFFIX = "-USD"


def asset_id(symbol: str) -> str:
    """``BTC-USD`` -> ``crypto:BTC``; an exchange ticker -> ``us:<ticker>``."""
    if symbol.endswith(CRYPTO_SUFFIX):
        return f"crypto:{symbol.removesuffix(CRYPTO_SUFFIX)}"
    return f"us:{symbol}"


# --------------------------------------------------------------------------- #
# Raw fetch
# --------------------------------------------------------------------------- #


def build_raw_prices(symbols: list[str] | tuple[str, ...], *, client: YFinanceClient | None = None) -> pl.DataFrame:
    """Full daily history, auto-adjusted (splits and dividends) as Yahoo publishes it.

    The current UTC day is dropped: its bar is still forming, and row ``T`` must be the
    value known at ``T``'s close.
    """
    history = (client or YFinanceClient()).download(list(symbols), period="max", interval="1d")
    today = datetime.now(UTC).date()
    rows = [
        {
            "timestamp": datetime(bar.trading_date.year, bar.trading_date.month, bar.trading_date.day, tzinfo=UTC),
            "symbol": symbol,
            "open": bar.open_price,
            "high": bar.high,
            "low": bar.low,
            "close": bar.close,
            "volume": bar.volume,
        }
        for symbol, bars in history.items()
        for bar in bars
        if bar.trading_date < today
    ]
    return pl.DataFrame(rows, schema=RAW_SCHEMA).sort("symbol", "timestamp")


# --------------------------------------------------------------------------- #
# Derived panel
# --------------------------------------------------------------------------- #


def derive_prices(raw: pl.DataFrame) -> pl.DataFrame:
    """``[timestamp, asset, close]``: canonical asset ids, positive closes only."""
    return (
        raw.filter(pl.col("close") > 0)
        .select(
            "timestamp",
            pl.col("symbol").map_elements(asset_id, return_dtype=pl.String).alias("asset"),
            "close",
        )
        .sort("asset", "timestamp")
    )
