"""
Tests for API classes.
"""

import asyncio
from datetime import datetime

import pytest
from unittest.mock import patch

from yf_client.api import AsyncYFinanceClient, YFinanceClient
from yf_client.exceptions import DataFetchError, SymbolNotFoundError
from yf_client.models import Quote


class TestYFinanceClient:
    """Test YFinanceClient class."""

    def test_client_initialization(self):
        """Test client initialization."""
        client = YFinanceClient()
        assert client.user_agent is not None
        assert client._ticker_cache == {}

    def test_client_initialization_with_user_agent(self):
        """Test client initialization with custom user agent."""
        client = YFinanceClient(user_agent="test-agent")
        assert client.user_agent == "test-agent"

    def test_get_quote_success(self, yfinance_client, sample_quote):
        """Test successful quote retrieval."""
        quote = yfinance_client.get_quote("AAPL")

        assert quote.symbol == "AAPL"
        assert quote.price == 150.25
        assert quote.currency == "USD"

    def test_get_quote_symbol_not_found(self, yfinance_client):
        """Test quote retrieval for invalid symbol."""
        # Mock ticker with empty info
        with patch.object(yfinance_client, "_get_ticker") as mock_get_ticker:
            mock_ticker = mock_get_ticker.return_value
            mock_ticker.info = {}

            with pytest.raises(SymbolNotFoundError):
                yfinance_client.get_quote("INVALID")

    def test_get_multiple_quotes_success(self, yfinance_client, sample_multiple_quotes):
        """Test successful multiple quotes retrieval."""
        quotes = yfinance_client.get_multiple_quotes(["AAPL", "GOOGL"])

        assert len(quotes.quotes) == 2
        assert quotes.quotes[0].symbol == "AAPL"
        assert quotes.quotes[1].symbol == "GOOGL"

    def test_get_multiple_quotes_partial_failure(self, yfinance_client):
        """Test multiple quotes with some failures."""

        # Mock get_quote to fail for one symbol
        def mock_get_quote(symbol):
            if symbol == "INVALID":
                raise SymbolNotFoundError(symbol)
            return Quote(
                symbol=symbol,
                price=100.0,
                currency="USD",
                timestamp=datetime(2023, 12, 1, 10, 30),
            )

        with patch.object(yfinance_client, "get_quote", side_effect=mock_get_quote):
            quotes = yfinance_client.get_multiple_quotes(["AAPL", "INVALID", "GOOGL"])

            # Should return only valid quotes
            assert len(quotes.quotes) == 2
            assert quotes.quotes[0].symbol == "AAPL"
            assert quotes.quotes[1].symbol == "GOOGL"

    def test_get_multiple_quotes_all_failures(self, yfinance_client):
        """Test multiple quotes when all requests fail."""
        with patch.object(
            yfinance_client, "get_quote", side_effect=SymbolNotFoundError("TEST")
        ):
            with pytest.raises(DataFetchError):
                yfinance_client.get_multiple_quotes(["INVALID1", "INVALID2"])

    def test_get_history_success(self, yfinance_client, sample_historical_data):
        """Test successful historical data retrieval."""
        history = yfinance_client.get_history("AAPL")

        assert history.symbol == "AAPL"
        assert len(history.data) == 2
        assert history.period == "1mo"
        assert history.interval == "1d"

    def test_get_history_invalid_period(self, yfinance_client):
        """Test historical data with invalid period."""
        from yf_client.exceptions import InvalidPeriodError

        with pytest.raises(InvalidPeriodError):
            yfinance_client.get_history("AAPL", period="invalid")

    def test_get_history_invalid_interval(self, yfinance_client):
        """Test historical data with invalid interval."""
        from yf_client.exceptions import InvalidIntervalError

        with pytest.raises(InvalidIntervalError):
            yfinance_client.get_history("AAPL", interval="invalid")

    def test_get_info_success(self, yfinance_client, sample_stock_info):
        """Test successful stock info retrieval."""
        info = yfinance_client.get_info("AAPL")

        assert info.symbol == "AAPL"
        assert info.company_name == "Apple Inc."
        assert info.sector == "Technology"
        assert info.market_cap == 3000000000000

    def test_get_info_symbol_not_found(self, yfinance_client):
        """Test stock info retrieval for invalid symbol."""
        with patch.object(yfinance_client, "_get_ticker") as mock_get_ticker:
            mock_ticker = mock_get_ticker.return_value
            mock_ticker.info = {}

            with pytest.raises(SymbolNotFoundError):
                yfinance_client.get_info("INVALID")

    def test_clear_cache(self, yfinance_client):
        """Test cache clearing."""
        # Add something to cache
        yfinance_client._ticker_cache["TEST"] = "mock_ticker"
        assert len(yfinance_client._ticker_cache) == 1

        yfinance_client.clear_cache()
        assert len(yfinance_client._ticker_cache) == 0

    def test_ticker_caching(self, yfinance_client, mock_yfinance_ticker):
        """Test ticker caching functionality."""
        # First call should create ticker
        ticker1 = yfinance_client._get_ticker("AAPL")
        assert len(yfinance_client._ticker_cache) == 1

        # Second call should return cached ticker
        ticker2 = yfinance_client._get_ticker("AAPL")
        assert len(yfinance_client._ticker_cache) == 1
        assert ticker1 is ticker2


class TestAsyncYFinanceClient:
    """Test AsyncYFinanceClient class."""

    @pytest.mark.asyncio
    async def test_async_client_initialization(self):
        """Test async client initialization."""
        client = AsyncYFinanceClient()
        assert client.user_agent is not None
        assert client.max_workers == 4

    @pytest.mark.asyncio
    async def test_async_client_initialization_custom(self):
        """Test async client initialization with custom parameters."""
        client = AsyncYFinanceClient(user_agent="test-agent", max_workers=8)
        assert client.user_agent == "test-agent"
        assert client.max_workers == 8

    @pytest.mark.asyncio
    async def test_async_get_quote(self, async_yfinance_client, sample_quote):
        """Test async quote retrieval."""
        quote = await async_yfinance_client.get_quote("AAPL")

        assert quote.symbol == "AAPL"
        assert quote.price == 150.25

    @pytest.mark.asyncio
    async def test_async_get_multiple_quotes(
        self, async_yfinance_client, sample_multiple_quotes
    ):
        """Test async multiple quotes retrieval."""
        quotes = await async_yfinance_client.get_multiple_quotes(["AAPL", "GOOGL"])

        assert len(quotes.quotes) == 2

    @pytest.mark.asyncio
    async def test_async_get_history(
        self, async_yfinance_client, sample_historical_data
    ):
        """Test async historical data retrieval."""
        history = await async_yfinance_client.get_history("AAPL")

        assert history.symbol == "AAPL"
        assert len(history.data) == 2

    @pytest.mark.asyncio
    async def test_async_get_info(self, async_yfinance_client, sample_stock_info):
        """Test async stock info retrieval."""
        info = await async_yfinance_client.get_info("AAPL")

        assert info.symbol == "AAPL"
        assert info.company_name == "Apple Inc."

    @pytest.mark.asyncio
    async def test_async_batch_get_quotes(self, async_yfinance_client):
        """Test async batch quotes retrieval."""
        quotes = await async_yfinance_client.batch_get_quotes(
            ["AAPL", "GOOGL"], batch_size=1
        )

        assert len(quotes.quotes) >= 1  # At least some should succeed

    @pytest.mark.asyncio
    async def test_async_context_manager(self):
        """Test async client as context manager."""
        async with AsyncYFinanceClient() as client:
            assert client.user_agent is not None

        # After context exit, executor should be shut down
        assert client._executor is None or client._executor._shutdown

    @pytest.mark.asyncio
    async def test_async_close(self):
        """Test async client close method."""
        client = AsyncYFinanceClient()
        await client.close()

        # Executor should be shut down
        assert client._executor._shutdown
