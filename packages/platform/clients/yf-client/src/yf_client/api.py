"""
API
---
packages/platform/clients/yf-client/src/yf_client/api.py
---
Core API wrapper classes for yfinance integration.
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Dict, List, Optional, Union, AsyncIterator

import pandas as pd
import json
from urllib import parse, request
import yfinance as yf

from .config import settings
from .exceptions import (
    DataFetchError,
    NetworkError,
    RateLimitError,
    SymbolNotFoundError,
    ValidationError,
    YFinanceClientError,
)
from .models import (
    HistoricalData,
    MultipleQuotes,
    OHLCV,
    OptionContract,
    Quote,
    StockInfo,
)
from .utils import (
    pandas_to_ohlcv,
    pandas_to_quotes,
    validate_interval,
    validate_period,
    validate_symbol,
    validate_symbols,
    df_to_option_contracts,
)

logger = logging.getLogger(__name__)


class YFinanceClient:
    """
    Synchronous wrapper around yfinance with typed returns.

    This class provides a clean, typed interface to yfinance operations
    with proper error handling and data validation.
    """

    def __init__(self, user_agent: Optional[str] = None):
        """
        Initialize the YFinance client.

        Args:
            user_agent: Custom user agent string
        """
        self.user_agent = user_agent or settings.user_agent
        self._ticker_cache = {}

    def get_quote(self, symbol: str) -> Quote:
        """
        Get current quote for a stock symbol.

        Args:
            symbol: Stock ticker symbol

        Returns:
            Quote object with current price data

        Raises:
            SymbolNotFoundError: If symbol is invalid
            DataFetchError: If data fetch fails
        """
        symbol = validate_symbol(symbol)
        logger.info(f"Fetching quote for symbol: {symbol}")

        try:
            ticker = self._get_ticker(symbol)
            info = ticker.info

            if not info or "currentPrice" not in info:
                raise SymbolNotFoundError(symbol)

            quote = Quote(
                symbol=symbol,
                price=info["currentPrice"],
                currency=info.get("currency", "USD"),
                timestamp=datetime.now(),
            )

            logger.info(f"Successfully fetched quote for {symbol}: ${quote.price}")
            return quote

        except SymbolNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Failed to fetch quote for {symbol}: {str(e)}")
            raise DataFetchError(symbol, original_error=e)

    def get_multiple_quotes(self, symbols: List[str]) -> MultipleQuotes:
        """
        Get quotes for multiple stock symbols.

        Args:
            symbols: List of stock ticker symbols

        Returns:
            MultipleQuotes object with all quote data

        Raises:
            ValidationError: If symbols list is invalid
            DataFetchError: If data fetch fails
        """
        symbols = validate_symbols(symbols)
        logger.info(f"Fetching quotes for {len(symbols)} symbols: {symbols}")

        quotes = []
        for symbol in symbols:
            try:
                quote = self.get_quote(symbol)
                quotes.append(quote)
            except (SymbolNotFoundError, DataFetchError) as e:
                logger.warning(f"Failed to fetch quote for {symbol}: {str(e)}")
                # Continue with other symbols instead of failing completely

        if not quotes:
            raise DataFetchError(
                f"Failed to fetch quotes for any of the symbols: {symbols}"
            )

        multiple_quotes = MultipleQuotes(quotes=quotes)
        logger.info(f"Successfully fetched {len(quotes)} quotes")
        return multiple_quotes

    # ┌────────────────────────────────────────────────────────────────────────────────────┐
    # │ Market Data - Bulk download                                                        
    # └────────────────────────────────────────────────────────────────────────────────────┘
    def download(
        self,
        tickers: Union[str, List[str]],
        period: Optional[str] = None,
        interval: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        actions: bool = False,
        auto_adjust: bool = True,
        back_adjust: bool = False,
        prepost: bool = False,
        group_by: str = "column",
        threads: Optional[Union[bool, int]] = None,
        repair: bool = False,
        keepna: bool = False,
        rounding: bool = False,
        timeout: Optional[int] = None,
    ) -> Dict[str, List[OHLCV]]:
        """
        Bulk historical price data for one or more tickers.

        Returns a mapping of ticker -> list of OHLCV records.
        """
        # Normalize and validate tickers
        if isinstance(tickers, str):
            symbols = [validate_symbol(tickers)]
            yf_tickers: Union[str, List[str]] = symbols[0]
        else:
            symbols = validate_symbols(list(tickers))
            yf_tickers = symbols

        # Validate period/interval and mutual exclusivity with start/end
        if period is None and (start is None or end is None):
            period = settings.default_period
        if interval is None:
            interval = settings.default_interval

        if period is not None and (start is not None or end is not None):
            raise ValidationError("Use either 'period' or 'start'/'end', not both")

        validate_period(period)
        validate_interval(interval)

        logger.info(
            "Downloading market data for %s (period=%s, interval=%s)",
            symbols,
            period,
            interval,
        )

        try:
            # Only pass kwargs known to be supported by yfinance.download to avoid errors
            kwargs: Dict[str, Any] = {
                "tickers": yf_tickers,
                "period": period,
                "interval": interval,
                "start": start,
                "end": end,
                "actions": actions,
                "auto_adjust": auto_adjust,
                "prepost": prepost,
                "group_by": group_by,
                "threads": threads,
                "keepna": keepna,
                "rounding": rounding,
                # ignore unknowns: back_adjust, repair, timeout
            }

            df = yf.download(**{k: v for k, v in kwargs.items() if v is not None})

            if df is None or (isinstance(df, pd.DataFrame) and df.empty):
                raise DataFetchError(message="No data returned from Yahoo Finance")

            result: Dict[str, List[OHLCV]] = {}

            if isinstance(df.columns, pd.MultiIndex):
                # Determine layout: either (field, symbol) or (symbol, field)
                level0 = list(df.columns.get_level_values(0))
                has_fields_in_level0 = any(
                    lbl in {"Open", "High", "Low", "Close", "Volume"} for lbl in set(level0)
                )
                if has_fields_in_level0:
                    # level 0 = field, level 1 = symbol
                    for sym in symbols:
                        try:
                            sub = pd.DataFrame(
                                {
                                    "Open": df[("Open", sym)],
                                    "High": df[("High", sym)],
                                    "Low": df[("Low", sym)],
                                    "Close": df[("Close", sym)],
                                    "Volume": df[("Volume", sym)],
                                }
                            )
                            result[sym] = pandas_to_ohlcv(sub)
                        except Exception:
                            continue
                else:
                    # level 0 = symbol, level 1 = field
                    for sym in symbols:
                        if sym in df.columns.get_level_values(0):
                            sub = df[sym]
                            cols = [
                                c
                                for c in ["Open", "High", "Low", "Close", "Volume"]
                                if c in sub.columns
                            ]
                            if cols:
                                result[sym] = pandas_to_ohlcv(sub[cols])
            else:
                # Single symbol DataFrame
                sym = symbols[0]
                cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
                if not cols:
                    raise DataFetchError(sym, message="Unexpected DataFrame structure for download")
                result[sym] = pandas_to_ohlcv(df[cols])

            if not result:
                raise DataFetchError(message="No usable data parsed from download result")

            logger.info("Successfully downloaded data for %d symbols", len(result))
            return result

        except YFinanceClientError:
            raise
        except Exception as e:
            logger.error("download() failed for %s: %s", symbols, str(e))
            raise DataFetchError(message="Failed to download data", original_error=e)

    # ┌────────────────────────────────────────────────────────────────────────────────────┐
    # │ Ticker - Fast Info                                                                
    # └────────────────────────────────────────────────────────────────────────────────────┘
    def get_fast_info(self, symbol: str) -> Dict[str, Any]:
        """Get lightweight real-time fields via yfinance fast_info (dict-like)."""
        symbol = validate_symbol(symbol)
        logger.info("Fetching fast_info for symbol: %s", symbol)
        try:
            ticker = self._get_ticker(symbol)
            fast_info = getattr(ticker, "fast_info", None)
            if fast_info is None:
                raise DataFetchError(symbol, message="fast_info not available")
            # Ensure plain dict
            if not isinstance(fast_info, dict):
                try:
                    fast_info = dict(fast_info)
                except Exception:
                    fast_info = {k: getattr(fast_info, k) for k in dir(fast_info) if not k.startswith("_")}
            return fast_info
        except YFinanceClientError:
            raise
        except Exception as e:
            logger.error("Failed to fetch fast_info for %s: %s", symbol, str(e))
            raise DataFetchError(symbol, original_error=e)

    # ┌────────────────────────────────────────────────────────────────────────────────────┐
    # │ Options                                                                            
    # └────────────────────────────────────────────────────────────────────────────────────┘
    def get_options(self, symbol: str) -> List[str]:
        """List available option expiration dates for a symbol (YYYY-MM-DD)."""
        symbol = validate_symbol(symbol)
        logger.info("Fetching options expirations for %s", symbol)
        try:
            ticker = self._get_ticker(symbol)
            expirations = getattr(ticker, "options", None) or []
            # Normalize to list[str]
            expirations = [str(x) for x in expirations]
            return expirations
        except Exception as e:
            logger.error("Failed to fetch options for %s: %s", symbol, str(e))
            raise DataFetchError(symbol, original_error=e)

    def get_option_chain(self, symbol: str, date: str) -> Dict[str, List[OptionContract]]:
        """Get full option chain for a given expiration date."""
        symbol = validate_symbol(symbol)
        if not date:
            raise ValidationError("Expiration date is required", field="date")
        logger.info("Fetching option chain for %s @ %s", symbol, date)
        try:
            ticker = self._get_ticker(symbol)
            expirations = getattr(ticker, "options", None) or []
            if str(date) not in [str(x) for x in expirations]:
                raise ValidationError(
                    f"Expiration '{date}' not available for {symbol}", field="date"
                )

            chain = ticker.option_chain(str(date))
            calls_df = getattr(chain, "calls", None)
            puts_df = getattr(chain, "puts", None)
            calls = df_to_option_contracts(calls_df)
            puts = df_to_option_contracts(puts_df)
            return {"calls": calls, "puts": puts}
        except ValidationError:
            raise
        except Exception as e:
            logger.error("Failed to fetch option chain for %s @ %s: %s", symbol, date, str(e))
            raise DataFetchError(symbol, original_error=e)

    def get_history(
        self,
        symbol: str,
        period: str = None,
        interval: str = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> HistoricalData:
        """
        Get historical price data for a stock symbol.

        Args:
            symbol: Stock ticker symbol
            period: Time period (e.g., "1mo", "1y")
            interval: Data interval (e.g., "1d", "1h")
            start: Start date (YYYY-MM-DD)
            end: End date (YYYY-MM-DD)

        Returns:
            HistoricalData object with OHLCV data

        Raises:
            SymbolNotFoundError: If symbol is invalid
            DataFetchError: If data fetch fails
            ValidationError: If parameters are invalid
        """
        symbol = validate_symbol(symbol)
        period = period or settings.default_period
        interval = interval or settings.default_interval

        validate_period(period)
        validate_interval(interval)

        logger.info(
            f"Fetching historical data for {symbol} (period: {period}, interval: {interval})"
        )

        try:
            ticker = self._get_ticker(symbol)

            # Fetch historical data
            hist = ticker.history(
                period=period,
                interval=interval,
                start=start,
                end=end,
                prepost=True,
                actions=True,
            )

            if hist.empty:
                raise SymbolNotFoundError(symbol, "No historical data available")

            # Convert to OHLCV objects
            ohlcv_data = pandas_to_ohlcv(hist)

            historical_data = HistoricalData(
                symbol=symbol, data=ohlcv_data, period=period, interval=interval
            )

            logger.info(
                f"Successfully fetched {len(ohlcv_data)} data points for {symbol}"
            )
            return historical_data

        except SymbolNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Failed to fetch historical data for {symbol}: {str(e)}")
            raise DataFetchError(symbol, original_error=e)

    def get_info(self, symbol: str) -> StockInfo:
        """
        Get comprehensive information about a stock.

        Args:
            symbol: Stock ticker symbol

        Returns:
            StockInfo object with company details

        Raises:
            SymbolNotFoundError: If symbol is invalid
            DataFetchError: If data fetch fails
        """
        symbol = validate_symbol(symbol)
        logger.info(f"Fetching info for symbol: {symbol}")

        try:
            ticker = self._get_ticker(symbol)
            info = ticker.info

            if not info or "symbol" not in info:
                raise SymbolNotFoundError(symbol)

            stock_info = StockInfo(
                symbol=symbol,
                company_name=info.get("longName") or info.get("shortName"),
                sector=info.get("sector"),
                industry=info.get("industry"),
                market_cap=info.get("marketCap"),
                pe_ratio=info.get("trailingPE"),
                pb_ratio=info.get("priceToBook"),
                dividend_yield=info.get("dividendYield"),
                beta=info.get("beta"),
                fifty_two_week_high=info.get("fiftyTwoWeekHigh"),
                fifty_two_week_low=info.get("fiftyTwoWeekLow"),
                average_volume=info.get("averageVolume"),
                currency=info.get("currency"),
                exchange=info.get("exchange"),
                country=info.get("country"),
            )

            logger.info(f"Successfully fetched info for {symbol}")
            return stock_info

        except SymbolNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Failed to fetch info for {symbol}: {str(e)}")
            raise DataFetchError(symbol, original_error=e)

    # ┌────────────────────────────────────────────────────────────────────────────────────┐
    # │ Corporate actions                                                                  
    # └────────────────────────────────────────────────────────────────────────────────────┘
    def get_actions(self, symbol: str) -> List[Dict[str, Any]]:
        """Get corporate actions (dividends, splits) as list of events dicts."""
        symbol = validate_symbol(symbol)
        logger.info("Fetching actions for %s", symbol)
        try:
            ticker = self._get_ticker(symbol)
            df = getattr(ticker, "actions", None)
            if df is None or (hasattr(df, "empty") and df.empty):
                return []
            # yfinance actions is a DataFrame with columns: Dividends, Stock Splits
            df = df.copy()
            df.index = pd.to_datetime(df.index).date
            records = []
            for idx, row in df.iterrows():
                if "Dividends" in row and pd.notna(row["Dividends"]) and row["Dividends"] != 0:
                    records.append({"date": idx, "type": "dividend", "value": float(row["Dividends"])})
                if "Stock Splits" in row and pd.notna(row["Stock Splits"]) and row["Stock Splits"] != 0:
                    records.append({"date": idx, "type": "split", "value": float(row["Stock Splits"])})
            return records
        except Exception as e:
            logger.error("Failed to fetch actions for %s: %s", symbol, str(e))
            raise DataFetchError(symbol, original_error=e)

    def get_dividends(self, symbol: str) -> List[Dict[str, Any]]:
        """Get dividends series as list of {date, amount}."""
        symbol = validate_symbol(symbol)
        logger.info("Fetching dividends for %s", symbol)
        try:
            ticker = self._get_ticker(symbol)
            series = getattr(ticker, "dividends", None)
            if series is None or (hasattr(series, "empty") and series.empty):
                return []
            series = series.copy()
            series.index = pd.to_datetime(series.index).date
            return [{"date": idx, "amount": float(val)} for idx, val in series.items()]
        except Exception as e:
            logger.error("Failed to fetch dividends for %s: %s", symbol, str(e))
            raise DataFetchError(symbol, original_error=e)

    def get_splits(self, symbol: str) -> List[Dict[str, Any]]:
        """Get stock split series as list of {date, ratio}."""
        symbol = validate_symbol(symbol)
        logger.info("Fetching splits for %s", symbol)
        try:
            ticker = self._get_ticker(symbol)
            series = getattr(ticker, "splits", None)
            if series is None or (hasattr(series, "empty") and series.empty):
                return []
            series = series.copy()
            series.index = pd.to_datetime(series.index).date
            return [{"date": idx, "ratio": float(val)} for idx, val in series.items()]
        except Exception as e:
            logger.error("Failed to fetch splits for %s: %s", symbol, str(e))
            raise DataFetchError(symbol, original_error=e)

    # ┌────────────────────────────────────────────────────────────────────────────────────┐
    # │ Fundamentals                                                                       
    # └────────────────────────────────────────────────────────────────────────────────────┘
    def get_financials(self, symbol: str) -> Dict[str, Any]:
        """Get annual financial statements as a dict (shape varies by source)."""
        symbol = validate_symbol(symbol)
        logger.info("Fetching financials for %s", symbol)
        try:
            ticker = self._get_ticker(symbol)
            df = getattr(ticker, "financials", None)
            return self._df_to_dict(df)
        except Exception as e:
            logger.error("Failed to fetch financials for %s: %s", symbol, str(e))
            raise DataFetchError(symbol, original_error=e)

    def get_financials_quarterly(self, symbol: str) -> Dict[str, Any]:
        """Get quarterly financial statements as a dict."""
        symbol = validate_symbol(symbol)
        logger.info("Fetching quarterly financials for %s", symbol)
        try:
            ticker = self._get_ticker(symbol)
            df = getattr(ticker, "quarterly_financials", None)
            return self._df_to_dict(df)
        except Exception as e:
            logger.error("Failed to fetch quarterly financials for %s: %s", symbol, str(e))
            raise DataFetchError(symbol, original_error=e)

    def get_financials_ttm(self, symbol: str) -> Dict[str, Any]:
        """Get trailing-twelve-month financials as a dict if derivable."""
        symbol = validate_symbol(symbol)
        logger.info("Fetching TTM financials for %s", symbol)
        try:
            ticker = self._get_ticker(symbol)
            q_df = getattr(ticker, "quarterly_financials", None)
            if q_df is None or q_df.empty:
                raise DataFetchError(symbol, message="TTM financials unavailable (no quarterly data)")

            # Sum last 4 quarters for numeric rows as an approximation
            try:
                last4 = q_df.iloc[:, :4]
            except Exception:
                last4 = q_df
            ttm = {}
            for idx, row in last4.iterrows():
                try:
                    # Sum across columns, ignore non-numeric
                    numeric = pd.to_numeric(row, errors="coerce")
                    if numeric.notna().any():
                        ttm[str(idx)] = float(numeric.sum(skipna=True))
                except Exception:
                    continue
            if not ttm:
                raise DataFetchError(symbol, message="TTM derivation failed")
            return ttm
        except YFinanceClientError:
            raise
        except Exception as e:
            logger.error("Failed to compute TTM for %s: %s", symbol, str(e))
            raise DataFetchError(symbol, original_error=e)

    def get_balance_sheet(self, symbol: str, quarterly: bool = False) -> Dict[str, Any]:
        """Get balance sheet (annual or quarterly) as a dict."""
        symbol = validate_symbol(symbol)
        logger.info("Fetching %s balance sheet for %s", "quarterly" if quarterly else "annual", symbol)
        try:
            ticker = self._get_ticker(symbol)
            df = getattr(ticker, "quarterly_balance_sheet" if quarterly else "balance_sheet", None)
            return self._df_to_dict(df)
        except Exception as e:
            logger.error("Failed to fetch balance sheet for %s: %s", symbol, str(e))
            raise DataFetchError(symbol, original_error=e)

    def get_cashflow(self, symbol: str, quarterly: bool = False) -> Dict[str, Any]:
        """Get cashflow (annual or quarterly) as a dict."""
        symbol = validate_symbol(symbol)
        logger.info("Fetching %s cashflow for %s", "quarterly" if quarterly else "annual", symbol)
        try:
            ticker = self._get_ticker(symbol)
            df = getattr(ticker, "quarterly_cashflow" if quarterly else "cashflow", None)
            return self._df_to_dict(df)
        except Exception as e:
            logger.error("Failed to fetch cashflow for %s: %s", symbol, str(e))
            raise DataFetchError(symbol, original_error=e)

    # ┌────────────────────────────────────────────────────────────────────────────────────┐
    # │ Ownership & Analysts                                                               
    # └────────────────────────────────────────────────────────────────────────────────────┘
    def get_holders(self, symbol: str) -> Dict[str, List[Dict[str, Any]]]:
        """Get holders data composed of major/institutional/mutualfund holders."""
        symbol = validate_symbol(symbol)
        logger.info("Fetching holders for %s", symbol)
        try:
            ticker = self._get_ticker(symbol)
            major_df = getattr(ticker, "major_holders", None)
            institutional_df = getattr(ticker, "institutional_holders", None)
            mutual_df = getattr(ticker, "mutualfund_holders", None)

            def to_records(df: Any) -> List[Dict[str, Any]]:
                if df is None or (hasattr(df, "empty") and df.empty):
                    return []
                try:
                    return df.reset_index().to_dict("records")
                except Exception:
                    return []

            return {
                "major_holders": to_records(major_df),
                "institutional_holders": to_records(institutional_df),
                "mutualfund_holders": to_records(mutual_df),
            }
        except Exception as e:
            logger.error("Failed to fetch holders for %s: %s", symbol, str(e))
            raise DataFetchError(symbol, original_error=e)

    def get_analyst(self, symbol: str) -> Dict[str, Any]:
        """
        Get analyst-related datasets: recommendations, summary/trend, upgrades/downgrades,
        price targets, and estimates where available.
        """
        symbol = validate_symbol(symbol)
        logger.info("Fetching analyst data for %s", symbol)
        try:
            ticker = self._get_ticker(symbol)

            def df_records(obj: Any) -> List[Dict[str, Any]]:
                df = obj
                if df is None or (hasattr(df, "empty") and df.empty):
                    return []
                try:
                    return df.reset_index().to_dict("records")
                except Exception:
                    return []

            out: Dict[str, Any] = {
                "recommendations": df_records(getattr(ticker, "recommendations", None)),
                "recommendations_summary": getattr(ticker, "recommendation_trend", None).to_dict()
                if getattr(ticker, "recommendation_trend", None) is not None
                else {},
                "upgrades_downgrades": df_records(getattr(ticker, "upgrades_downgrades", None)),
                "analyst_price_targets": df_records(getattr(ticker, "analyst_price_target", None)),
                "earnings_estimate": df_records(getattr(ticker, "earnings_estimate", None)),
                "revenue_estimate": df_records(getattr(ticker, "revenue_estimate", None)),
                "earnings_history": df_records(getattr(ticker, "earnings_history", None)),
                "eps_trend": df_records(getattr(ticker, "eps_trend", None)),
                "eps_revisions": df_records(getattr(ticker, "eps_revisions", None)),
                "growth_estimates": df_records(getattr(ticker, "growth_estimates", None)),
            }
            return out
        except Exception as e:
            logger.error("Failed to fetch analyst data for %s: %s", symbol, str(e))
            raise DataFetchError(symbol, original_error=e)

    # ┌────────────────────────────────────────────────────────────────────────────────────┐
    # │ News                                                                               
    # └────────────────────────────────────────────────────────────────────────────────────┘
    def get_news(self, symbol: str) -> List[Dict[str, Any]]:
        """Get recent news items for a symbol."""
        symbol = validate_symbol(symbol)
        logger.info("Fetching news for %s", symbol)
        try:
            ticker = self._get_ticker(symbol)
            news = getattr(ticker, "news", None) or []
            # Ensure each item is a dict and only keep relevant fields
            cleaned: List[Dict[str, Any]] = []
            for item in news:
                if not isinstance(item, dict):
                    continue
                cleaned.append({
                    "title": item.get("title"),
                    "publisher": item.get("publisher"),
                    "link": item.get("link") or item.get("url"),
                    "published": pd.to_datetime(
                        item.get("providerPublishTime") or item.get("published")).isoformat()
                    if item.get("providerPublishTime") or item.get("published") else None,
                    "summary": item.get("summary"),
                })
            return cleaned
        except Exception as e:
            logger.error("Failed to fetch news for %s: %s", symbol, str(e))
            raise DataFetchError(symbol, original_error=e)

    # ┌────────────────────────────────────────────────────────────────────────────────────┐
    # │ Streaming (symbolic; optional dependency)                                          
    # └────────────────────────────────────────────────────────────────────────────────────┘
    async def stream_quotes(
        self,
        symbols: List[str],
        url: str = "wss://streamer.finance.yahoo.com/?version=2",
        verbose: bool = False,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Stream trade/quote updates via Yahoo's websocket. Requires 'websockets' package.

        Yields dicts with quote update payloads. This function connects and starts
        streaming immediately; caller should iterate and cancel/close when done.
        """
        if not symbols:
            raise ValidationError("symbols list cannot be empty", field="symbols")
        try:
            import websockets  # type: ignore
        except Exception:
            raise DataFetchError(message="Streaming requires 'websockets' package. Install via extras.")

        payload = {
            "subscribe": [s.upper() for s in symbols],
        }

        async def _run():
            async with websockets.connect(url) as ws:  # pragma: no cover - network
                await ws.send(json.dumps(payload))
                if verbose:
                    logger.info("Subscribed to %s", symbols)
                while True:
                    msg = await ws.recv()
                    try:
                        data = json.loads(msg)
                        yield data
                    except Exception:
                        if verbose:
                            logger.debug("Non-JSON message: %s", msg)
                        yield {"raw": msg}

        # Delegate to inner async generator to keep type hints clean
        async for item in _run():
            yield item

    # ┌────────────────────────────────────────────────────────────────────────────────────┐
    # │ Discovery / Screener (sync HTTP)                                                   
    # └────────────────────────────────────────────────────────────────────────────────────┘
    def search(self, query: str, max_results: int = 10, news_count: int = 10) -> Dict[str, Any]:
        if not query:
            raise ValidationError("query is required", field="query")
        base = "https://query2.finance.yahoo.com/v1/finance/search"
        params = {"q": query, "quotesCount": max_results, "newsCount": news_count}
        url = f"{base}?{parse.urlencode(params)}"
        logger.info("Search request: %s", url)
        try:
            with request.urlopen(url, timeout=settings.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return {
                "quotes": data.get("quotes", []),
                "news": data.get("news", []),
            }
        except Exception as e:
            logger.error("Search failed for '%s': %s", query, str(e))
            raise DataFetchError(message=f"Search failed for '{query}'", original_error=e)

    def lookup(self, query: str) -> List[Dict[str, Any]]:
        if not query:
            raise ValidationError("query is required", field="query")
        base = "https://autoc.finance.yahoo.com/autoc"
        params = {"query": query, "region": 1, "lang": "en"}
        url = f"{base}?{parse.urlencode(params)}"
        logger.info("Lookup request: %s", url)
        try:
            with request.urlopen(url, timeout=settings.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return (data.get("ResultSet", {}) or {}).get("Result", [])
        except Exception as e:
            logger.error("Lookup failed for '%s': %s", query, str(e))
            raise DataFetchError(message=f"Lookup failed for '{query}'", original_error=e)

    def run_screener(self, predefined: Optional[str] = None, query: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not predefined and not query:
            raise ValidationError("Either 'predefined' or 'query' must be provided")
        try:
            if predefined:
                base = "https://query2.finance.yahoo.com/v1/finance/screener/predefined/saved"
                url = f"{base}?{parse.urlencode({'scrIds': predefined})}"
                logger.info("Screener predefined request: %s", url)
                with request.urlopen(url, timeout=settings.timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                return data
            else:
                base = "https://query2.finance.yahoo.com/v1/finance/screener"
                payload = json.dumps({"query": query}).encode("utf-8")
                req = request.Request(base, data=payload, headers={"Content-Type": "application/json"})
                logger.info("Screener custom POST request: %s", base)
                with request.urlopen(req, timeout=settings.timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                return data
        except Exception as e:
            logger.error("Screener request failed: %s", str(e))
            raise DataFetchError(message="Screener request failed", original_error=e)

    # ┌────────────────────────────────────────────────────────────────────────────────────┐
    # │ Helper: DataFrame → dict                                                            
    # └────────────────────────────────────────────────────────────────────────────────────┘
    def _df_to_dict(self, df: Any) -> Dict[str, Any]:
        """Convert a yfinance DataFrame into a nested dict with string keys."""
        if df is None:
            return {}
        try:
            if hasattr(df, "to_dict"):
                # orient=columns produces mapping row->col:value after transpose
                # yfinance financial frames are transposed; normalize to dict[str, dict]
                if isinstance(df, pd.DataFrame):
                    return df.astype(object).where(df.notna(), None).to_dict()
                return dict(df)
        except Exception:
            pass
        return {}

    def _get_ticker(self, symbol: str) -> yf.Ticker:
        """
        Get or create cached yfinance Ticker object.

        Args:
            symbol: Stock ticker symbol

        Returns:
            yfinance Ticker object
        """
        if symbol not in self._ticker_cache:
            self._ticker_cache[symbol] = yf.Ticker(symbol)
        return self._ticker_cache[symbol]

    def clear_cache(self) -> None:
        """Clear the ticker cache."""
        self._ticker_cache.clear()
        logger.info("Ticker cache cleared")


class AsyncYFinanceClient:
    """
    Asynchronous wrapper around yfinance using thread pools.

    This class provides async versions of all YFinanceClient methods
    using asyncio.to_thread() for non-blocking operations.
    """

    def __init__(self, user_agent: Optional[str] = None, max_workers: int = 4):
        """
        Initialize the AsyncYFinance client.

        Args:
            user_agent: Custom user agent string
            max_workers: Maximum number of thread pool workers
        """
        self.user_agent = user_agent or settings.user_agent
        self.max_workers = max_workers
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="yf-client"
        )
        self._sync_client = YFinanceClient(user_agent=user_agent)

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    async def close(self) -> None:
        """Close the async client and cleanup resources."""
        self._executor.shutdown(wait=True)
        logger.info("AsyncYFinanceClient closed")

    async def get_quote(self, symbol: str) -> Quote:
        """
        Asynchronously get current quote for a stock symbol.

        Args:
            symbol: Stock ticker symbol

        Returns:
            Quote object with current price data
        """
        return await asyncio.to_thread(self._sync_client.get_quote, symbol)

    async def get_multiple_quotes(self, symbols: List[str]) -> MultipleQuotes:
        """
        Asynchronously get quotes for multiple stock symbols.

        Args:
            symbols: List of stock ticker symbols

        Returns:
            MultipleQuotes object with all quote data
        """
        return await asyncio.to_thread(self._sync_client.get_multiple_quotes, symbols)

    # ┌────────────────────────────────────────────────────────────────────────────────────┐
    # │ Market Data / Options (async wrappers)                                             
    # └────────────────────────────────────────────────────────────────────────────────────┘
    async def download(
        self,
        tickers: Union[str, List[str]],
        period: Optional[str] = None,
        interval: Optional[str] = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
        actions: bool = False,
        auto_adjust: bool = True,
        back_adjust: bool = False,
        prepost: bool = False,
        group_by: str = "column",
        threads: Optional[Union[bool, int]] = None,
        repair: bool = False,
        keepna: bool = False,
        rounding: bool = False,
        timeout: Optional[int] = None,
    ) -> Dict[str, List[OHLCV]]:
        return await asyncio.to_thread(
            self._sync_client.download,
            tickers,
            period,
            interval,
            start,
            end,
            actions,
            auto_adjust,
            back_adjust,
            prepost,
            group_by,
            threads,
            repair,
            keepna,
            rounding,
            timeout,
        )

    async def get_fast_info(self, symbol: str) -> Dict[str, Any]:
        return await asyncio.to_thread(self._sync_client.get_fast_info, symbol)

    async def get_options(self, symbol: str) -> List[str]:
        return await asyncio.to_thread(self._sync_client.get_options, symbol)

    async def get_option_chain(self, symbol: str, date: str) -> Dict[str, List[OptionContract]]:
        return await asyncio.to_thread(self._sync_client.get_option_chain, symbol, date)

    async def get_history(
        self,
        symbol: str,
        period: str = None,
        interval: str = None,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> HistoricalData:
        """
        Asynchronously get historical price data for a stock symbol.

        Args:
            symbol: Stock ticker symbol
            period: Time period (e.g., "1mo", "1y")
            interval: Data interval (e.g., "1d", "1h")
            start: Start date (YYYY-MM-DD)
            end: End date (YYYY-MM-DD)

        Returns:
            HistoricalData object with OHLCV data
        """
        return await asyncio.to_thread(
            self._sync_client.get_history, symbol, period, interval, start, end
        )

    async def get_info(self, symbol: str) -> StockInfo:
        """
        Asynchronously get comprehensive information about a stock.

        Args:
            symbol: Stock ticker symbol

        Returns:
            StockInfo object with company details
        """
        return await asyncio.to_thread(self._sync_client.get_info, symbol)

    # ┌────────────────────────────────────────────────────────────────────────────────────┐
    # │ Corporate actions / Fundamentals / Ownership / News / Discovery (async wrappers)   
    # └────────────────────────────────────────────────────────────────────────────────────┘
    async def get_actions(self, symbol: str) -> List[Dict[str, Any]]:
        return await asyncio.to_thread(self._sync_client.get_actions, symbol)

    async def get_dividends(self, symbol: str) -> List[Dict[str, Any]]:
        return await asyncio.to_thread(self._sync_client.get_dividends, symbol)

    async def get_splits(self, symbol: str) -> List[Dict[str, Any]]:
        return await asyncio.to_thread(self._sync_client.get_splits, symbol)

    async def get_financials(self, symbol: str) -> Dict[str, Any]:
        return await asyncio.to_thread(self._sync_client.get_financials, symbol)

    async def get_financials_quarterly(self, symbol: str) -> Dict[str, Any]:
        return await asyncio.to_thread(self._sync_client.get_financials_quarterly, symbol)

    async def get_financials_ttm(self, symbol: str) -> Dict[str, Any]:
        return await asyncio.to_thread(self._sync_client.get_financials_ttm, symbol)

    async def get_balance_sheet(self, symbol: str, quarterly: bool = False) -> Dict[str, Any]:
        return await asyncio.to_thread(self._sync_client.get_balance_sheet, symbol, quarterly)

    async def get_cashflow(self, symbol: str, quarterly: bool = False) -> Dict[str, Any]:
        return await asyncio.to_thread(self._sync_client.get_cashflow, symbol, quarterly)

    async def get_holders(self, symbol: str) -> Dict[str, List[Dict[str, Any]]]:
        return await asyncio.to_thread(self._sync_client.get_holders, symbol)

    async def get_analyst(self, symbol: str) -> Dict[str, Any]:
        return await asyncio.to_thread(self._sync_client.get_analyst, symbol)

    async def get_news(self, symbol: str) -> List[Dict[str, Any]]:
        return await asyncio.to_thread(self._sync_client.get_news, symbol)

    async def search(self, query: str, max_results: int = 10, news_count: int = 10) -> Dict[str, Any]:
        return await asyncio.to_thread(self._sync_client.search, query, max_results, news_count)

    async def lookup(self, query: str) -> List[Dict[str, Any]]:
        return await asyncio.to_thread(self._sync_client.lookup, query)

    async def run_screener(self, predefined: Optional[str] = None, query: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return await asyncio.to_thread(self._sync_client.run_screener, predefined, query)

    async def batch_get_quotes(
        self, symbols: List[str], batch_size: int = 10
    ) -> MultipleQuotes:
        """
        Asynchronously get quotes for multiple symbols in batches.

        This method processes symbols in batches to avoid overwhelming the API
        and provides better error handling for large symbol lists.

        Args:
            symbols: List of stock ticker symbols
            batch_size: Number of symbols to process per batch

        Returns:
            MultipleQuotes object with all quote data
        """
        symbols = validate_symbols(symbols)
        logger.info(
            f"Batch fetching quotes for {len(symbols)} symbols in batches of {batch_size}"
        )

        all_quotes = []

        # Process in batches
        for i in range(0, len(symbols), batch_size):
            batch = symbols[i : i + batch_size]
            logger.debug(f"Processing batch {i//batch_size + 1}: {batch}")

            try:
                batch_quotes = await self.get_multiple_quotes(batch)
                all_quotes.extend(batch_quotes.quotes)
            except Exception as e:
                logger.warning(f"Failed to fetch batch {i//batch_size + 1}: {str(e)}")
                # Continue with next batch

        if not all_quotes:
            raise DataFetchError(
                f"Failed to fetch quotes for any symbols in batch: {symbols}"
            )

        multiple_quotes = MultipleQuotes(quotes=all_quotes)
        logger.info(f"Successfully fetched {len(all_quotes)} quotes in batches")
        return multiple_quotes
