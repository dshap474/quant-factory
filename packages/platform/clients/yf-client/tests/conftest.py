"""
Shared test fixtures and configuration for yf-client tests.
"""

import pytest
from unittest.mock import MagicMock, patch

from yf_client.api import AsyncYFinanceClient, YFinanceClient
from yf_client.models import HistoricalData, MultipleQuotes, OHLCV, Quote, StockInfo


@pytest.fixture
def sample_quote():
    """Sample quote data for testing."""
    return Quote(
        symbol="AAPL", price=150.25, currency="USD", timestamp="2023-12-01T10:30:00"
    )


@pytest.fixture
def sample_ohlcv_data():
    """Sample OHLCV data for testing."""
    return [
        OHLCV(
            date="2023-12-01",
            open=148.50,
            high=152.00,
            low=147.80,
            close=150.25,
            volume=50000000,
        ),
        OHLCV(
            date="2023-12-02",
            open=150.25,
            high=155.00,
            low=149.50,
            close=153.75,
            volume=55000000,
        ),
    ]


@pytest.fixture
def sample_historical_data(sample_ohlcv_data):
    """Sample historical data for testing."""
    return HistoricalData(
        symbol="AAPL", data=sample_ohlcv_data, period="1mo", interval="1d"
    )


@pytest.fixture
def sample_stock_info():
    """Sample stock info for testing."""
    return StockInfo(
        symbol="AAPL",
        company_name="Apple Inc.",
        sector="Technology",
        industry="Consumer Electronics",
        market_cap=3000000000000,
        pe_ratio=28.5,
        pb_ratio=8.2,
        dividend_yield=0.005,
        beta=1.2,
        fifty_two_week_high=200.0,
        fifty_two_week_low=120.0,
        average_volume=50000000,
        currency="USD",
        exchange="NASDAQ",
        country="United States",
    )


@pytest.fixture
def sample_multiple_quotes(sample_quote):
    """Sample multiple quotes for testing."""
    quotes = [
        sample_quote,
        Quote(
            symbol="GOOGL",
            price=2800.50,
            currency="USD",
            timestamp="2023-12-01T10:30:00",
        ),
    ]
    return MultipleQuotes(quotes=quotes)


@pytest.fixture
def mock_yfinance_ticker():
    """Mock yfinance Ticker object."""
    with patch("yfinance.Ticker") as mock_ticker_class:
        mock_ticker = MagicMock()
        mock_ticker_class.return_value = mock_ticker

        # Mock info data
        mock_ticker.info = {
            "symbol": "AAPL",
            "currentPrice": 150.25,
            "currency": "USD",
            "longName": "Apple Inc.",
            "sector": "Technology",
            "industry": "Consumer Electronics",
            "marketCap": 3000000000000,
            "trailingPE": 28.5,
            "priceToBook": 8.2,
            "dividendYield": 0.005,
            "beta": 1.2,
            "fiftyTwoWeekHigh": 200.0,
            "fiftyTwoWeekLow": 120.0,
            "averageVolume": 50000000,
            "exchange": "NASDAQ",
            "country": "United States",
        }

        # Mock history data
        import pandas as pd

        dates = pd.date_range("2023-12-01", periods=2, freq="D")
        mock_ticker.history.return_value = pd.DataFrame(
            {
                "Open": [148.50, 150.25],
                "High": [152.00, 155.00],
                "Low": [147.80, 149.50],
                "Close": [150.25, 153.75],
                "Volume": [50000000, 55000000],
            },
            index=dates,
        )

        yield mock_ticker


@pytest.fixture
def yfinance_client(mock_yfinance_ticker):
    """YFinanceClient instance with mocked yfinance."""
    return YFinanceClient()


@pytest.fixture
def async_yfinance_client(mock_yfinance_ticker):
    """AsyncYFinanceClient instance with mocked yfinance."""
    return AsyncYFinanceClient()


@pytest.fixture
def temp_output_dir(tmp_path):
    """Temporary directory for testing file exports."""
    output_dir = tmp_path / "exports"
    output_dir.mkdir()
    return output_dir
