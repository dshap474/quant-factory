"""Read-only Watchlists API access; mutations are outside this package.

USAGE: client.watchlists.list(); client.watchlists.get("watchlist-id")
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..models import BlockworksResponse

if TYPE_CHECKING:
    from ..client import BlockworksClient


# --------------------------------------------------------------------------- #
# Watchlist operations
# --------------------------------------------------------------------------- #


class WatchlistsResource:
    def __init__(self, client: BlockworksClient):
        self._client = client

    def list(self) -> BlockworksResponse:
        return self._client._call("/user-management/v1/watchlists")

    def get(self, watchlist_id: str) -> BlockworksResponse:
        return self._client._call("/user-management/v1/watchlists/{id}", path_params={"id": watchlist_id})
