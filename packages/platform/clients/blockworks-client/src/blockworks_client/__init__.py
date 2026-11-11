"""Read-only synchronous Python client for the Blockworks API.

USAGE: from blockworks_client import BlockworksClient
"""

from .client import BlockworksClient
from .exceptions import (
    BlockworksAPIError,
    BlockworksConfigError,
    BlockworksDecodeError,
    BlockworksError,
    BlockworksPaginationError,
    BlockworksTransportError,
)
from .models import BlockworksResponse, TabularListBody, TabularMetadata, TimeseriesBody, TimeseriesData

# --------------------------------------------------------------------------- #
# Public exports
# --------------------------------------------------------------------------- #

__all__ = [
    "BlockworksClient",
    "BlockworksResponse",
    "BlockworksError",
    "BlockworksAPIError",
    "BlockworksConfigError",
    "BlockworksDecodeError",
    "BlockworksPaginationError",
    "BlockworksTransportError",
    "TabularListBody",
    "TabularMetadata",
    "TimeseriesBody",
    "TimeseriesData",
]
