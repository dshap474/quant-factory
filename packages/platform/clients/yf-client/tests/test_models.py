"""
Tests for Pydantic models.
"""

import pytest
from datetime import date, datetime
from pydantic import ValidationError

from yf_client.models import HistoricalData, MultipleQuotes, OHLCV, Quote, StockInfo


class TestQuote:
    """Test Quote model."""

    def test_valid_quote(self, sample_quote):
        """Test creating a valid quote."""
        assert sample_quote.symbol == "AAPL"
        assert sample_quote.price == 150.25
        assert sample_quote.currency == "USD"
        assert isinstance(sample_quote.timestamp, datetime)

    def test_quote_symbol_validation(self):
        """Test quote symbol validation."""
        with pytest.raises(ValidationError):
            Quote(symbol="", price=100.0, currency="USD", timestamp=datetime.now())

        # Symbol format (e.g. '@') is checked by utils.validate_symbol, not the model

    def test_quote_price_validation(self):
        """Test quote price validation."""
        with pytest.raises(ValidationError):
            Quote(symbol="AAPL", price=-10.0, currency="USD", timestamp=datetime.now())

    def test_quote_currency_validation(self):
        """Test quote currency validation."""
        quote = Quote(
            symbol="AAPL", price=100.0, currency="usd", timestamp=datetime.now()
        )
        assert quote.currency == "USD"  # Should be uppercased

    def test_quote_json_serialization(self, sample_quote):
        """Test quote JSON serialization."""
        data = sample_quote.model_dump(mode="json")
        assert "timestamp" in data
        assert data["timestamp"] == "2023-12-01T10:30:00"  # ISO format


class TestOHLCV:
    """Test OHLCV model."""

    def test_valid_ohlcv(self, sample_ohlcv_data):
        """Test creating valid OHLCV data."""
        ohlcv = sample_ohlcv_data[0]
        assert not hasattr(ohlcv, "symbol")  # OHLCV carries no symbol
        assert ohlcv.date == date(2023, 12, 1)
        assert ohlcv.open == 148.50
        assert ohlcv.high == 152.00
        assert ohlcv.low == 147.80
        assert ohlcv.close == 150.25
        assert ohlcv.volume == 50000000

    def test_ohlcv_high_low_validation(self):
        """Test OHLCV high/low validation."""
        with pytest.raises(ValidationError):
            OHLCV(
                date=date.today(),
                open=100.0,
                high=90.0,  # High < Open
                low=95.0,
                close=98.0,
                volume=1000000,
            )

        with pytest.raises(ValidationError):
            OHLCV(
                date=date.today(),
                open=100.0,
                high=110.0,
                low=105.0,  # Low > Open
                close=108.0,
                volume=1000000,
            )

    def test_ohlcv_json_serialization(self, sample_ohlcv_data):
        """Test OHLCV JSON serialization."""
        ohlcv = sample_ohlcv_data[0]
        data = ohlcv.model_dump(mode="json", by_alias=True)
        assert data["date"] == "2023-12-01"  # ISO format, aliased key


class TestStockInfo:
    """Test StockInfo model."""

    def test_valid_stock_info(self, sample_stock_info):
        """Test creating valid stock info."""
        assert sample_stock_info.symbol == "AAPL"
        assert sample_stock_info.company_name == "Apple Inc."
        assert sample_stock_info.sector == "Technology"
        assert sample_stock_info.market_cap == 3000000000000
        assert sample_stock_info.pe_ratio == 28.5

    def test_stock_info_symbol_validation(self):
        """Test stock info symbol validation."""
        with pytest.raises(ValidationError):
            StockInfo(symbol="")

    def test_stock_info_currency_normalization(self):
        """Test stock info currency normalization."""
        info = StockInfo(symbol="AAPL", currency="usd")
        assert info.currency == "USD"


class TestHistoricalData:
    """Test HistoricalData model."""

    def test_valid_historical_data(self, sample_historical_data):
        """Test creating valid historical data."""
        assert sample_historical_data.symbol == "AAPL"
        assert len(sample_historical_data.data) == 2
        assert sample_historical_data.period == "1mo"
        assert sample_historical_data.interval == "1d"

    def test_historical_data_symbol_validation(self):
        """Test historical data symbol validation."""
        with pytest.raises(ValidationError):
            HistoricalData(symbol="", data=[], period="1mo", interval="1d")

    def test_historical_data_length(self, sample_historical_data):
        """Test historical data length methods."""
        assert len(sample_historical_data) == 2
        assert not sample_historical_data.is_empty()

        empty_data = HistoricalData(symbol="AAPL", data=[], period="1mo", interval="1d")
        assert len(empty_data) == 0
        assert empty_data.is_empty()


class TestMultipleQuotes:
    """Test MultipleQuotes model."""

    def test_valid_multiple_quotes(self, sample_multiple_quotes):
        """Test creating valid multiple quotes."""
        assert len(sample_multiple_quotes.quotes) == 2
        assert sample_multiple_quotes.quotes[0].symbol == "AAPL"
        assert sample_multiple_quotes.quotes[1].symbol == "GOOGL"

    def test_multiple_quotes_length(self, sample_multiple_quotes):
        """Test multiple quotes length methods."""
        assert len(sample_multiple_quotes) == 2
        assert not sample_multiple_quotes.is_empty()

        empty_quotes = MultipleQuotes(quotes=[])
        assert len(empty_quotes) == 0
        assert empty_quotes.is_empty()

    def test_get_quote_by_symbol(self, sample_multiple_quotes):
        """Test getting quote by symbol."""
        aapl_quote = sample_multiple_quotes.get_quote("AAPL")
        assert aapl_quote is not None
        assert aapl_quote.symbol == "AAPL"

        nonexistent_quote = sample_multiple_quotes.get_quote("INVALID")
        assert nonexistent_quote is None

    def test_multiple_quotes_json_serialization(self, sample_multiple_quotes):
        """Test multiple quotes JSON serialization."""
        data = sample_multiple_quotes.model_dump(mode="json")
        assert len(data["quotes"]) == len(sample_multiple_quotes.quotes)
        assert isinstance(data["timestamp"], str)  # ISO format
