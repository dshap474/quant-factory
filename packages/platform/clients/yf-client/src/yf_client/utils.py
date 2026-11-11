"""
Utilities
---
packages/platform/clients/yf-client/src/yf_client/utils.py
---
Utility functions for yf-client.
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import pandas as pd

from .config import settings
from .exceptions import InvalidIntervalError, InvalidPeriodError, ValidationError
from .models import (
    ActionEvent,
    Dividend,
    HistoricalData,
    NewsItem,
    OHLCV,
    OptionContract,
    Quote,
    Split,
)


def validate_symbol(symbol: str) -> str:
    """
    Validate and normalize a stock symbol.

    Args:
        symbol: Stock ticker symbol to validate

    Returns:
        Normalized uppercase symbol

    Raises:
        ValidationError: If symbol is invalid
    """
    if not symbol or not isinstance(symbol, str):
        raise ValidationError("Symbol must be a non-empty string")

    # Remove whitespace and convert to uppercase
    symbol = symbol.strip().upper()

    # Basic validation - alphanumeric, dots, hyphens (common in ticker symbols)
    if not re.match(r"^[A-Z0-9.\-^=]+$", symbol):
        raise ValidationError(
            f"Invalid symbol format '{symbol}'. "
            "Symbols should contain only letters, numbers, dots, and hyphens"
        )

    # Check length constraints
    if len(symbol) > 20:
        raise ValidationError(f"Symbol '{symbol}' is too long (max 20 characters)")

    return symbol


def validate_symbols(symbols: List[str]) -> List[str]:
    """
    Validate and normalize multiple stock symbols.

    Args:
        symbols: List of stock ticker symbols to validate

    Returns:
        List of normalized uppercase symbols

    Raises:
        ValidationError: If any symbol is invalid
    """
    if not symbols:
        raise ValidationError("Symbols list cannot be empty")

    validated_symbols = []
    for symbol in symbols:
        try:
            validated_symbols.append(validate_symbol(symbol))
        except ValidationError as e:
            raise ValidationError(f"Invalid symbol in list: {e.message}")

    # Check for duplicates
    if len(validated_symbols) != len(set(validated_symbols)):
        duplicates = [s for s in validated_symbols if validated_symbols.count(s) > 1]
        raise ValidationError(f"Duplicate symbols found: {list(set(duplicates))}")

    return validated_symbols


def validate_period(period: str) -> str:
    """
    Validate time period parameter.

    Args:
        period: Time period string to validate

    Returns:
        Validated period string

    Raises:
        InvalidPeriodError: If period is invalid
    """
    if period not in settings.valid_periods:
        raise InvalidPeriodError(period, settings.valid_periods)
    return period


def validate_interval(interval: str) -> str:
    """
    Validate data interval parameter.

    Args:
        interval: Data interval string to validate

    Returns:
        Validated interval string

    Raises:
        InvalidIntervalError: If interval is invalid
    """
    if interval not in settings.valid_intervals:
        raise InvalidIntervalError(interval, settings.valid_intervals)
    return interval


def generate_filename(
    base_name: str,
    extension: str,
    timestamp: Optional[datetime] = None,
    suffix: Optional[str] = None,
) -> str:
    """
    Generate a filename with timestamp.

    Args:
        base_name: Base filename without extension
        extension: File extension (without dot)
        timestamp: Timestamp to include (defaults to current time)
        suffix: Optional suffix to add

    Returns:
        Generated filename
    """
    if timestamp is None:
        timestamp = datetime.now()

    timestamp_str = timestamp.strftime("%Y%m%d_%H%M%S")

    parts = [base_name, timestamp_str]
    if suffix:
        parts.append(suffix)

    return f"{'_'.join(parts)}.{extension}"


def create_output_path(
    filename: str, output_dir: Optional[Union[str, Path]] = None
) -> Path:
    """
    Create and return the full output path for a file.

    Args:
        filename: Filename to create path for
        output_dir: Output directory (defaults to settings.output_dir)

    Returns:
        Full path to output file

    Raises:
        ValidationError: If path cannot be created
    """
    if output_dir is None:
        output_dir = settings.output_dir
    elif isinstance(output_dir, str):
        output_dir = Path(output_dir)

    # Ensure output directory exists
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        raise ValidationError(
            f"Cannot create output directory '{output_dir}': {str(e)}"
        )

    return output_dir / filename


def pandas_to_quotes(df: pd.DataFrame, symbol: str) -> List[Quote]:
    """
    Convert pandas DataFrame to list of Quote objects.

    Args:
        df: DataFrame with quote data
        symbol: Stock symbol

    Returns:
        List of Quote objects
    """
    quotes = []
    for _, row in df.iterrows():
        try:
            quote = Quote(
                symbol=symbol,
                price=float(row.get("Close", row.get("price", 0))),
                currency=row.get("Currency", "USD"),
                timestamp=pd.to_datetime(
                    row.name if hasattr(row, "name") else datetime.now()
                ),
            )
            quotes.append(quote)
        except (ValueError, KeyError, TypeError):
            continue
    return quotes


def pandas_to_ohlcv(df: pd.DataFrame) -> List[OHLCV]:
    """
    Convert pandas DataFrame to list of OHLCV objects.

    Args:
        df: DataFrame with OHLCV data

    Returns:
        List of OHLCV objects
    """
    ohlcv_list = []
    for date, row in df.iterrows():
        try:
            ohlcv = OHLCV(
                date=pd.to_datetime(date).date(),
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                volume=int(row["Volume"]),
            )
            ohlcv_list.append(ohlcv)
        except (ValueError, KeyError, TypeError):
            continue
    return ohlcv_list


# ┌────────────────────────────────────────────────────────────────────────────────────┐
# │ Converters: Corporate Actions / News / Options                                     
# └────────────────────────────────────────────────────────────────────────────────────┘
def pandas_to_action_events(df: pd.DataFrame) -> List[ActionEvent]:
    """Convert yfinance actions DataFrame to list of ActionEvent."""
    events: List[ActionEvent] = []
    if df is None or df.empty:
        return events

    # yfinance actions may split into dividends/splits; normalize to unified events
    for idx, row in df.iterrows():
        # dividends
        if "Dividends" in row and pd.notna(row["Dividends"]) and row["Dividends"] != 0:
            try:
                events.append(
                    ActionEvent(date=pd.to_datetime(idx).date(), type="dividend", value=float(row["Dividends"]))
                )
            except Exception:
                pass
        # splits
        if "Stock Splits" in row and pd.notna(row["Stock Splits"]) and row["Stock Splits"] != 0:
            try:
                events.append(
                    ActionEvent(date=pd.to_datetime(idx).date(), type="split", value=float(row["Stock Splits"]))
                )
            except Exception:
                pass
    return events


def pandas_to_dividends(df: pd.DataFrame) -> List[Dividend]:
    """Convert yfinance dividends Series/DataFrame to list of Dividend."""
    dividends: List[Dividend] = []
    if df is None or df.empty:
        return dividends

    # yfinance returns Series with index as date for dividends; also supports DataFrame
    if isinstance(df, pd.Series):
        series = df
        for idx, value in series.items():
            try:
                dividends.append(Dividend(date=pd.to_datetime(idx).date(), amount=float(value)))
            except Exception:
                continue
        return dividends

    for idx, row in df.iterrows():
        try:
            # try common column names
            amount_val = row.get("Dividends", row.get("amount", row.get("value", None)))
            if amount_val is None:
                continue
            dividends.append(Dividend(date=pd.to_datetime(idx).date(), amount=float(amount_val)))
        except Exception:
            continue
    return dividends


def pandas_to_splits(df: pd.DataFrame) -> List[Split]:
    """Convert yfinance splits Series/DataFrame to list of Split."""
    splits: List[Split] = []
    if df is None or df.empty:
        return splits

    if isinstance(df, pd.Series):
        series = df
        for idx, value in series.items():
            try:
                splits.append(Split(date=pd.to_datetime(idx).date(), ratio=float(value)))
            except Exception:
                continue
        return splits

    for idx, row in df.iterrows():
        try:
            ratio_val = row.get("Stock Splits", row.get("ratio", row.get("value", None)))
            if ratio_val is None:
                continue
            splits.append(Split(date=pd.to_datetime(idx).date(), ratio=float(ratio_val)))
        except Exception:
            continue
    return splits


def dicts_to_news_items(items: List[Dict[str, Any]]) -> List[NewsItem]:
    """Convert list of news dicts from yfinance to NewsItem models."""
    news: List[NewsItem] = []
    for item in items or []:
        try:
            news.append(
                NewsItem(
                    title=str(item.get("title", "")),
                    publisher=str(item.get("publisher", "")),
                    link=str(item.get("link", item.get("url", ""))),
                    published=pd.to_datetime(item.get("providerPublishTime") or item.get("published_at") or item.get("published")).to_pydatetime(),
                    summary=item.get("summary"),
                )
            )
        except Exception:
            continue
    return news


def df_to_option_contracts(df: pd.DataFrame) -> List[OptionContract]:
    """Convert option chain DataFrame (calls/puts) to OptionContract list."""
    contracts: List[OptionContract] = []
    if df is None or df.empty:
        return contracts

    # Common columns seen in yfinance option chain
    for _, row in df.iterrows():
        try:
            expiration_value = row.get("expiration") or row.get("lastTradeDate") or None
            expiration_date = None
            if expiration_value is not None:
                try:
                    expiration_date = pd.to_datetime(expiration_value).date()
                except Exception:
                    expiration_date = None

            contracts.append(
                OptionContract(
                    contractSymbol=row.get("contractSymbol"),
                    strike=_safe_float(row.get("strike")),
                    lastPrice=_safe_float(row.get("lastPrice")),
                    bid=_safe_float(row.get("bid")),
                    ask=_safe_float(row.get("ask")),
                    change=_safe_float(row.get("change")),
                    percentChange=_safe_float(row.get("percentChange")),
                    volume=_safe_float(row.get("volume")),
                    openInterest=_safe_float(row.get("openInterest")),
                    impliedVolatility=_safe_float(row.get("impliedVolatility")),
                    inTheMoney=_safe_bool(row.get("inTheMoney")),
                    expiration=expiration_date,
                    contractSize=row.get("contractSize"),
                    currency=row.get("currency"),
                )
            )
        except Exception:
            continue
    return contracts


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        return float(value)
    except Exception:
        return None


def _safe_bool(value: Any) -> Optional[bool]:
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            return value.lower() in {"true", "1", "yes", "y"}
        return None
    except Exception:
        return None


def historical_data_to_dataframe(historical_data: HistoricalData) -> pd.DataFrame:
    """
    Convert HistoricalData to pandas DataFrame.

    Args:
        historical_data: HistoricalData object

    Returns:
        pandas DataFrame
    """
    data = []
    for ohlcv in historical_data.data:
        data.append(
            {
                "Date": ohlcv.date,
                "Open": ohlcv.open,
                "High": ohlcv.high,
                "Low": ohlcv.low,
                "Close": ohlcv.close,
                "Volume": ohlcv.volume,
            }
        )

    df = pd.DataFrame(data)
    if not df.empty:
        df["Date"] = pd.to_datetime(df["Date"])
        df.set_index("Date", inplace=True)

    return df


def format_number(value: Union[int, float], decimals: int = 2) -> str:
    """
    Format a number with specified decimal places.

    Args:
        value: Number to format
        decimals: Number of decimal places

    Returns:
        Formatted string
    """
    if isinstance(value, (int, float)):
        return f"{value:,.{decimals}f}"
    return str(value)


def format_percentage(value: Optional[float], decimals: int = 2) -> str:
    """
    Format a percentage value.

    Args:
        value: Percentage value (e.g., 0.15 for 15%)
        decimals: Number of decimal places

    Returns:
        Formatted percentage string
    """
    if value is None:
        return "N/A"
    return f"{value * 100:.{decimals}f}%"


def safe_get_nested_value(
    data: Dict[str, Any], keys: List[str], default: Any = None
) -> Any:
    """
    Safely get nested value from dictionary.

    Args:
        data: Dictionary to extract from
        keys: List of keys to navigate
        default: Default value if key not found

    Returns:
        Value from nested dictionary or default
    """
    current = data
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default
    return current


def chunk_list(items: List[Any], chunk_size: int) -> List[List[Any]]:
    """
    Split a list into chunks of specified size.

    Args:
        items: List to split
        chunk_size: Size of each chunk

    Returns:
        List of chunks
    """
    return [items[i : i + chunk_size] for i in range(0, len(items), chunk_size)]


def calculate_returns(prices: List[float]) -> List[Optional[float]]:
    """
    Calculate period-over-period returns from a list of prices.

    Args:
        prices: List of prices in chronological order

    Returns:
        List of returns (percentage change)
    """
    if len(prices) < 2:
        return [None] * len(prices)

    returns = [None]  # First price has no previous price
    for i in range(1, len(prices)):
        if prices[i - 1] != 0:
            ret = (prices[i] - prices[i - 1]) / prices[i - 1]
            returns.append(ret)
        else:
            returns.append(None)

    return returns
