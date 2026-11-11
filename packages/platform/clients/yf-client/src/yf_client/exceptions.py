"""
Custom exceptions for yf-client package.
"""

from typing import Optional


class YFinanceClientError(Exception):
    """Base exception for all yf-client errors."""

    def __init__(self, message: str, symbol: Optional[str] = None) -> None:
        self.symbol = symbol
        self.message = message
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        """Format error message with symbol if available."""
        if self.symbol:
            return f"[{self.symbol}] {self.message}"
        return self.message


class SymbolNotFoundError(YFinanceClientError):
    """Raised when a stock symbol is not found or invalid."""

    def __init__(self, symbol: str, message: Optional[str] = None) -> None:
        default_message = f"Symbol '{symbol}' not found or invalid"
        super().__init__(message or default_message, symbol)


class DataFetchError(YFinanceClientError):
    """Raised when data fetching from yfinance fails."""

    def __init__(
        self,
        symbol: Optional[str] = None,
        message: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ) -> None:
        self.original_error = original_error
        default_message = "Failed to fetch data from Yahoo Finance"
        if original_error:
            default_message += f": {str(original_error)}"
        super().__init__(message or default_message, symbol)


class ExportError(YFinanceClientError):
    """Raised when data export operations fail."""

    def __init__(
        self,
        message: str,
        filepath: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ) -> None:
        self.filepath = filepath
        self.original_error = original_error
        if filepath:
            message = f"Export failed for '{filepath}': {message}"
        if original_error:
            message += f" (original error: {str(original_error)})"
        super().__init__(message)


class ValidationError(YFinanceClientError):
    """Raised when input validation fails."""

    def __init__(self, message: str, field: Optional[str] = None) -> None:
        self.field = field
        if field:
            message = f"Validation failed for field '{field}': {message}"
        super().__init__(message)


class ConfigurationError(YFinanceClientError):
    """Raised when configuration is invalid or missing."""

    def __init__(self, message: str, config_key: Optional[str] = None) -> None:
        self.config_key = config_key
        if config_key:
            message = f"Configuration error for '{config_key}': {message}"
        super().__init__(message)


class RateLimitError(YFinanceClientError):
    """Raised when Yahoo Finance rate limits are exceeded."""

    def __init__(
        self,
        symbol: Optional[str] = None,
        message: Optional[str] = None,
        retry_after: Optional[int] = None,
    ) -> None:
        self.retry_after = retry_after
        default_message = "Rate limit exceeded"
        if retry_after:
            default_message += f". Retry after {retry_after} seconds"
        super().__init__(message or default_message, symbol)


class NetworkError(YFinanceClientError):
    """Raised when network-related errors occur."""

    def __init__(
        self,
        message: str,
        symbol: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ) -> None:
        self.original_error = original_error
        if original_error:
            message += f" (original error: {str(original_error)})"
        super().__init__(message, symbol)


class InvalidPeriodError(YFinanceClientError):
    """Raised when an invalid period is specified."""

    def __init__(self, period: str, valid_periods: Optional[list] = None) -> None:
        self.period = period
        self.valid_periods = valid_periods or []
        message = f"Invalid period '{period}'"
        if self.valid_periods:
            message += f". Valid periods: {', '.join(self.valid_periods)}"
        super().__init__(message)


class InvalidIntervalError(YFinanceClientError):
    """Raised when an invalid interval is specified."""

    def __init__(self, interval: str, valid_intervals: Optional[list] = None) -> None:
        self.interval = interval
        self.valid_intervals = valid_intervals or []
        message = f"Invalid interval '{interval}'"
        if self.valid_intervals:
            message += f". Valid intervals: {', '.join(self.valid_intervals)}"
        super().__init__(message)
