"""Boundary exceptions for the internal Hyperliquid SDK facade.

Purpose: expose stable, secret-safe errors without leaking upstream objects.

USAGE:
    from hyperliquid_client import HyperliquidTradingDisabledError
"""

# --------------------------------------------------------------------------- #
# Exceptions
# --------------------------------------------------------------------------- #


class HyperliquidClientError(RuntimeError):
    """Base error raised at the internal Hyperliquid client boundary."""


class HyperliquidConfigurationError(HyperliquidClientError):
    """Raised when account, network, or API-wallet configuration is invalid."""


class HyperliquidTradingDisabledError(HyperliquidClientError):
    """Raised before order placement when the exact trading gate is disabled."""


class HyperliquidStreamError(HyperliquidClientError):
    """Raised when the bounded public stream cannot safely continue."""


class HyperliquidStreamTimeoutError(HyperliquidStreamError):
    """Raised when one bounded receive interval contains no message."""


__all__ = [
    "HyperliquidClientError",
    "HyperliquidConfigurationError",
    "HyperliquidStreamError",
    "HyperliquidStreamTimeoutError",
    "HyperliquidTradingDisabledError",
]
