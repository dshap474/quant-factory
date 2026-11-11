"""
yf-client - A typed wrapper around yfinance with async support, CLI tool, and data export capabilities.
"""

from .api import AsyncYFinanceClient, YFinanceClient
from .config import settings
from .exceptions import (
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
from .exporters import export_to_csv, export_to_json, export_to_xlsx
from .models import (
    ActionEvent,
    Dividend,
    HistoricalData,
    MultipleQuotes,
    NewsItem,
    OHLCV,
    OptionContract,
    Quote,
    Split,
    StockInfo,
)

__version__ = "0.2.0"

__all__ = [
    # Main API classes
    "YFinanceClient",
    "AsyncYFinanceClient",
    # Models
    "Quote",
    "OHLCV",
    "StockInfo",
    "HistoricalData",
    "MultipleQuotes",
    "ActionEvent",
    "Dividend",
    "Split",
    "OptionContract",
    "NewsItem",
    # Exceptions
    "YFinanceClientError",
    "SymbolNotFoundError",
    "DataFetchError",
    "ExportError",
    "ValidationError",
    "ConfigurationError",
    "RateLimitError",
    "NetworkError",
    "InvalidPeriodError",
    "InvalidIntervalError",
    # Exporters
    "export_to_csv",
    "export_to_json",
    "export_to_xlsx",
    # Configuration
    "settings",
    # Metadata
    "__version__",
]
