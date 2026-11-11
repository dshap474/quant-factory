"""
Tests for utility functions.
"""

import pytest
from datetime import datetime
from pathlib import Path

from yf_client.utils import (
    validate_symbol,
    validate_symbols,
    validate_period,
    validate_interval,
    generate_filename,
    create_output_path,
    format_number,
    format_percentage,
    chunk_list,
    calculate_returns,
)
from yf_client.exceptions import (
    ValidationError,
    InvalidPeriodError,
    InvalidIntervalError,
)


class TestSymbolValidation:
    """Test symbol validation functions."""

    def test_validate_symbol_valid(self):
        """Test validating valid symbols."""
        assert validate_symbol("AAPL") == "AAPL"
        assert validate_symbol("aapl") == "AAPL"  # Should uppercase
        assert validate_symbol("MSFT.O") == "MSFT.O"  # Should allow dots
        assert validate_symbol("BRK-A") == "BRK-A"  # Should allow hyphens

    def test_validate_symbol_invalid(self):
        """Test validating invalid symbols."""
        with pytest.raises(ValidationError):
            validate_symbol("")

        with pytest.raises(ValidationError):
            validate_symbol("INVALID@SYMBOL")

        with pytest.raises(ValidationError):
            validate_symbol("TOOLONGSYMBOLNAME" * 10)

    def test_validate_symbols_valid(self):
        """Test validating multiple valid symbols."""
        symbols = ["AAPL", "GOOGL", "msft"]
        result = validate_symbols(symbols)
        assert result == ["AAPL", "GOOGL", "MSFT"]

    def test_validate_symbols_invalid(self):
        """Test validating multiple symbols with invalid ones."""
        with pytest.raises(ValidationError):
            validate_symbols(["AAPL", ""])

        with pytest.raises(ValidationError):
            validate_symbols(["AAPL", "AAPL"])  # Duplicates

    def test_validate_symbols_empty_list(self):
        """Test validating empty symbols list."""
        with pytest.raises(ValidationError):
            validate_symbols([])


class TestPeriodIntervalValidation:
    """Test period and interval validation."""

    def test_validate_period_valid(self):
        """Test validating valid periods."""
        valid_periods = [
            "1d",
            "5d",
            "1mo",
            "3mo",
            "6mo",
            "1y",
            "2y",
            "5y",
            "10y",
            "ytd",
            "max",
        ]
        for period in valid_periods:
            assert validate_period(period) == period

    def test_validate_period_invalid(self):
        """Test validating invalid period."""
        with pytest.raises(InvalidPeriodError):
            validate_period("invalid")

    def test_validate_interval_valid(self):
        """Test validating valid intervals."""
        valid_intervals = [
            "1m",
            "2m",
            "5m",
            "15m",
            "30m",
            "60m",
            "90m",
            "1h",
            "1d",
            "5d",
            "1wk",
            "1mo",
            "3mo",
        ]
        for interval in valid_intervals:
            assert validate_interval(interval) == interval

    def test_validate_interval_invalid(self):
        """Test validating invalid interval."""
        with pytest.raises(InvalidIntervalError):
            validate_interval("invalid")


class TestFilenameGeneration:
    """Test filename generation functions."""

    def test_generate_filename_basic(self):
        """Test basic filename generation."""
        filename = generate_filename("test", "csv")
        assert filename.startswith("test_")
        assert filename.endswith(".csv")
        assert len(filename) > len("test.csv")

    def test_generate_filename_with_timestamp(self):
        """Test filename generation with custom timestamp."""
        timestamp = datetime(2023, 12, 1, 10, 30, 0)
        filename = generate_filename("data", "json", timestamp)
        assert "20231201_103000" in filename
        assert filename == "data_20231201_103000.json"

    def test_generate_filename_with_suffix(self):
        """Test filename generation with suffix."""
        filename = generate_filename("quotes", "xlsx", suffix="processed")
        assert "processed" in filename
        assert filename.startswith("quotes_")
        assert filename.endswith("_processed.xlsx")


class TestOutputPathCreation:
    """Test output path creation."""

    def test_create_output_path_with_directory(self, tmp_path):
        """Test creating output path with directory."""
        output_dir = tmp_path / "exports"
        filepath = create_output_path("test.csv", output_dir)

        assert filepath == output_dir / "test.csv"
        assert output_dir.exists()

    def test_create_output_path_creates_directory(self, tmp_path):
        """Test that output directory is created if it doesn't exist."""
        output_dir = tmp_path / "new" / "exports"
        assert not output_dir.exists()

        filepath = create_output_path("test.csv", output_dir)

        assert output_dir.exists()
        assert filepath == output_dir / "test.csv"


class TestFormattingFunctions:
    """Test formatting utility functions."""

    def test_format_number(self):
        """Test number formatting."""
        assert format_number(1234.56) == "1,234.56"
        assert format_number(1234.56, 0) == "1,235"  # Rounded
        assert format_number(1000000) == "1,000,000.00"

    def test_format_percentage(self):
        """Test percentage formatting."""
        assert format_percentage(0.15) == "15.00%"
        assert format_percentage(0.157, 1) == "15.7%"
        assert format_percentage(None) == "N/A"

    def test_format_number_edge_cases(self):
        """Test number formatting edge cases."""
        assert format_number(0) == "0.00"
        assert format_number(-123.45) == "-123.45"


class TestListOperations:
    """Test list operation utilities."""

    def test_chunk_list(self):
        """Test list chunking."""
        items = [1, 2, 3, 4, 5, 6, 7]
        chunks = chunk_list(items, 3)

        assert len(chunks) == 3
        assert chunks[0] == [1, 2, 3]
        assert chunks[1] == [4, 5, 6]
        assert chunks[2] == [7]

    def test_chunk_list_exact_division(self):
        """Test list chunking with exact division."""
        items = [1, 2, 3, 4, 5, 6]
        chunks = chunk_list(items, 2)

        assert len(chunks) == 3
        assert chunks[0] == [1, 2]
        assert chunks[1] == [3, 4]
        assert chunks[2] == [5, 6]

    def test_chunk_list_empty(self):
        """Test chunking empty list."""
        chunks = chunk_list([], 3)
        assert chunks == []

    def test_chunk_list_chunk_size_larger_than_list(self):
        """Test chunking when chunk size is larger than list."""
        items = [1, 2]
        chunks = chunk_list(items, 5)
        assert chunks == [[1, 2]]


class TestReturnCalculations:
    """Test return calculation functions."""

    def test_calculate_returns(self):
        """Test return calculation."""
        prices = [100.0, 110.0, 120.0, 115.0]
        returns = calculate_returns(prices)

        assert returns[0] is None  # First price has no previous
        assert returns[1] == 0.1  # (110-100)/100 = 0.1
        assert returns[2] == 0.09090909090909091  # (120-110)/110 ≈ 0.0909
        assert returns[3] == -0.041666666666666664  # (115-120)/120 ≈ -0.0417

    def test_calculate_returns_single_price(self):
        """Test return calculation with single price."""
        returns = calculate_returns([100.0])
        assert returns == [None]

    def test_calculate_returns_empty_list(self):
        """Test return calculation with empty list."""
        returns = calculate_returns([])
        assert returns == []

    def test_calculate_returns_zero_price(self):
        """Test return calculation with zero price."""
        prices = [0.0, 100.0]
        returns = calculate_returns(prices)

        assert returns[0] is None
        assert returns[1] is None  # Division by zero case
