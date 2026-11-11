"""Exception hierarchy for the Coinbase Advanced Trade client facade.

Purpose: surface configuration and trading-gate failures from this thin
wrapper; SDK HTTP errors propagate as-is (not re-wrapped).

USAGE:
    from coinbase_advanced_client import (
        CoinbaseAdvanced,
        CoinbaseAdvancedConfigurationError,
        CoinbaseAdvancedTradingDisabledError,
    )
    try:
        client = CoinbaseAdvanced()
        client.create_order(...)
    except CoinbaseAdvancedConfigurationError as exc:
        print(exc)
    except CoinbaseAdvancedTradingDisabledError as exc:
        print(exc)
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Exception hierarchy
# --------------------------------------------------------------------------- #


class CoinbaseAdvancedError(Exception):
    """Base exception for coinbase-advanced-client facade errors."""


class CoinbaseAdvancedConfigurationError(CoinbaseAdvancedError):
    """Raised when required credentials are missing from args or config."""


class CoinbaseAdvancedTradingDisabledError(CoinbaseAdvancedError):
    """Raised when create_order is called while the trading gate is off.

    The gate is ``config.COINBASE_ADVANCED_TRADING_ENABLED``; placement is
    allowed only when that constant equals ``"1"``. Cancel remains ungated
    (risk-reducing).
    """
