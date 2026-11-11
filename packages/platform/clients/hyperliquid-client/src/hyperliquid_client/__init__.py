"""Public API for the internal official-SDK Hyperliquid facade.

Purpose: expose only validated contracts, the narrow client and stream, and
stable boundary exceptions; no raw SDK object is public.

USAGE:
    from hyperliquid_client import HyperliquidClient, HyperliquidClientConfig
"""

from hyperliquid_client.client import (
    HyperliquidClient,
    HyperliquidClientConfig,
    HyperliquidReadClient,
)
from hyperliquid_client.contracts import LimitOrderRequest, StreamEnvelope, StreamSubscription
from hyperliquid_client.exceptions import (
    HyperliquidClientError,
    HyperliquidConfigurationError,
    HyperliquidStreamError,
    HyperliquidStreamTimeoutError,
    HyperliquidTradingDisabledError,
)
from hyperliquid_client.stream import HyperliquidStream

__version__ = "0.2.0"

__all__ = [
    "HyperliquidClient",
    "HyperliquidClientConfig",
    "HyperliquidClientError",
    "HyperliquidConfigurationError",
    "HyperliquidReadClient",
    "HyperliquidStream",
    "HyperliquidStreamError",
    "HyperliquidStreamTimeoutError",
    "HyperliquidTradingDisabledError",
    "LimitOrderRequest",
    "StreamEnvelope",
    "StreamSubscription",
]
