"""
Tests for custom exceptions.
"""

import pytest

from yf_client.exceptions import (
    ConfigurationError,
    DataFetchError,
    ExportError,
    InvalidIntervalError,
    InvalidPeriodError,
    NetworkError,
    RateLimitError,
    SymbolNotFoundError,
    ValidationError,
    YFinanceClientError,
)


class TestYFinanceClientError:
    """Test base YFinanceClientError."""

    def test_base_exception(self):
        """Test base exception without symbol."""
        error = YFinanceClientError("Test error")
        assert str(error) == "Test error"

    def test_base_exception_with_symbol(self):
        """Test base exception with symbol."""
        error = YFinanceClientError("Test error", "AAPL")
        assert str(error) == "[AAPL] Test error"


class TestSymbolNotFoundError:
    """Test SymbolNotFoundError."""

    def test_symbol_not_found(self):
        """Test symbol not found error."""
        error = SymbolNotFoundError("INVALID")
        assert str(error) == "[INVALID] Symbol 'INVALID' not found or invalid"

    def test_symbol_not_found_custom_message(self):
        """Test symbol not found with custom message."""
        error = SymbolNotFoundError("INVALID", "Custom message")
        assert str(error) == "[INVALID] Custom message"


class TestDataFetchError:
    """Test DataFetchError."""

    def test_data_fetch_error(self):
        """Test data fetch error."""
        error = DataFetchError("AAPL")
        assert str(error) == "[AAPL] Failed to fetch data from Yahoo Finance"

    def test_data_fetch_error_with_original(self):
        """Test data fetch error with original exception."""
        original = ValueError("Network timeout")
        error = DataFetchError("AAPL", original_error=original)
        assert "Network timeout" in str(error)


class TestExportError:
    """Test ExportError."""

    def test_export_error(self):
        """Test export error."""
        error = ExportError("Export failed")
        assert str(error) == "Export failed"

    def test_export_error_with_filepath(self):
        """Test export error with filepath."""
        error = ExportError("Export failed", "/path/to/file.csv")
        assert str(error) == "Export failed for '/path/to/file.csv': Export failed"

    def test_export_error_with_original(self):
        """Test export error with original exception."""
        original = PermissionError("Permission denied")
        error = ExportError("Export failed", original_error=original)
        assert "Permission denied" in str(error)


class TestValidationError:
    """Test ValidationError."""

    def test_validation_error(self):
        """Test validation error."""
        error = ValidationError("Invalid input")
        assert str(error) == "Invalid input"

    def test_validation_error_with_field(self):
        """Test validation error with field."""
        error = ValidationError("Invalid input", "symbol")
        assert str(error) == "Validation failed for field 'symbol': Invalid input"


class TestConfigurationError:
    """Test ConfigurationError."""

    def test_configuration_error(self):
        """Test configuration error."""
        error = ConfigurationError("Invalid config")
        assert str(error) == "Invalid config"

    def test_configuration_error_with_key(self):
        """Test configuration error with config key."""
        error = ConfigurationError("Invalid config", "api_key")
        assert str(error) == "Configuration error for 'api_key': Invalid config"


class TestRateLimitError:
    """Test RateLimitError."""

    def test_rate_limit_error(self):
        """Test rate limit error."""
        error = RateLimitError()
        assert str(error) == "Rate limit exceeded"

    def test_rate_limit_error_with_retry(self):
        """Test rate limit error with retry time."""
        error = RateLimitError(retry_after=60)
        assert str(error) == "Rate limit exceeded. Retry after 60 seconds"


class TestNetworkError:
    """Test NetworkError."""

    def test_network_error(self):
        """Test network error."""
        error = NetworkError("Connection failed")
        assert str(error) == "Connection failed"

    def test_network_error_with_symbol(self):
        """Test network error with symbol."""
        error = NetworkError("Connection failed", "AAPL")
        assert str(error) == "[AAPL] Connection failed"

    def test_network_error_with_original(self):
        """Test network error with original exception."""
        original = ConnectionError("Network unreachable")
        error = NetworkError("Connection failed", original_error=original)
        assert "Network unreachable" in str(error)


class TestInvalidPeriodError:
    """Test InvalidPeriodError."""

    def test_invalid_period_error(self):
        """Test invalid period error."""
        error = InvalidPeriodError("invalid")
        assert str(error) == "Invalid period 'invalid'"

    def test_invalid_period_error_with_valid_periods(self):
        """Test invalid period error with valid periods list."""
        valid_periods = ["1d", "5d", "1mo"]
        error = InvalidPeriodError("invalid", valid_periods)
        assert "Valid periods: 1d, 5d, 1mo" in str(error)


class TestInvalidIntervalError:
    """Test InvalidIntervalError."""

    def test_invalid_interval_error(self):
        """Test invalid interval error."""
        error = InvalidIntervalError("invalid")
        assert str(error) == "Invalid interval 'invalid'"

    def test_invalid_interval_error_with_valid_intervals(self):
        """Test invalid interval error with valid intervals list."""
        valid_intervals = ["1m", "5m", "1h", "1d"]
        error = InvalidIntervalError("invalid", valid_intervals)
        assert "Valid intervals: 1m, 5m, 1h, 1d" in str(error)


class TestExceptionHierarchy:
    """Test exception hierarchy."""

    def test_exception_inheritance(self):
        """Test that specific exceptions inherit from base exception."""
        exceptions = [
            SymbolNotFoundError("TEST"),
            DataFetchError("TEST"),
            ExportError("Test"),
            ValidationError("Test"),
            ConfigurationError("Test"),
            RateLimitError(),
            NetworkError("Test"),
            InvalidPeriodError("invalid"),
            InvalidIntervalError("invalid"),
        ]

        for exc in exceptions:
            assert isinstance(exc, YFinanceClientError)

    def test_exception_attributes(self):
        """Test exception attributes are preserved."""
        error = SymbolNotFoundError("TEST")
        assert hasattr(error, "symbol")
        assert error.symbol == "TEST"

        config_error = ConfigurationError("Test", "test_key")
        assert hasattr(config_error, "config_key")
        assert config_error.config_key == "test_key"
