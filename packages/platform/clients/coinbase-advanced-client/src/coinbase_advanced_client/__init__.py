"""Thin auth/config facade over the official coinbase-advanced-py SDK.

Purpose: resolve credentials via ``config``, own one RESTClient, expose read /
preview / gated placement helpers, and own WebSocket supervisors that control
reconnection (SDK auto-retry is disabled).
"""

from .api import CoinbaseAdvanced
from .catalog import CoinbaseAdvancedPublic
from .exceptions import (
    CoinbaseAdvancedConfigurationError,
    CoinbaseAdvancedError,
    CoinbaseAdvancedTradingDisabledError,
)
from .ws import MarketDataStream, UserStream

__all__ = [
    "CoinbaseAdvanced",
    "CoinbaseAdvancedPublic",
    "CoinbaseAdvancedError",
    "CoinbaseAdvancedConfigurationError",
    "CoinbaseAdvancedTradingDisabledError",
    "MarketDataStream",
    "UserStream",
]

__version__ = "0.1.0"

