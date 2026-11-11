"""Token Unlocks reads using the provider's distinct query conventions.

USAGE: client.unlocks.assets(assetIDs=[asset_id]); client.unlocks.events(asset_id)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..models import BlockworksResponse

if TYPE_CHECKING:
    from ..client import BlockworksClient


# --------------------------------------------------------------------------- #
# Token Unlocks operations
# --------------------------------------------------------------------------- #


class UnlocksResource:
    def __init__(self, client: BlockworksClient):
        self._client = client

    def allocations(self, asset_id: str) -> BlockworksResponse:
        """Read allocations for ``asset_id``."""
        return self._client._call("/token-unlocks/v1/allocations", params={"assetId": asset_id})

    def assets(
        self,
        *,
        assetIDs: list[str] | str | None = None,
        category: str | None = None,
        sector: str | None = None,
        tags: list[str] | str | None = None,
        page: int | None = None,
        limit: int | None = None,
    ) -> BlockworksResponse:
        """Read covered assets; ``page`` and ``limit`` are passed through as given."""
        return self._client._call(
            "/token-unlocks/v1/assets",
            params={
                "assetIDs": assetIDs,
                "category": category,
                "sector": sector,
                "tags": tags,
                "page": page,
                "limit": limit,
            },
        )

    def events(
        self, asset_id: str, *, startTime: Any = None, endTime: Any = None, unlockType: str | None = None
    ) -> BlockworksResponse:
        return self._client._call(
            "/token-unlocks/v1/assets/{assetId}/events",
            path_params={"assetId": asset_id},
            params={"startTime": startTime, "endTime": endTime, "unlockType": unlockType},
        )

    def unlocks(
        self, asset_id: str, interval: str, *, startTime: Any = None, endTime: Any = None
    ) -> BlockworksResponse:
        return self._client._call(
            "/token-unlocks/v1/assets/{assetId}/unlocks",
            path_params={"assetId": asset_id},
            params={"interval": interval, "startTime": startTime, "endTime": endTime},
        )

    def vesting_schedule(self, asset_id: str, *, startTime: Any = None, endTime: Any = None) -> BlockworksResponse:
        return self._client._call(
            "/token-unlocks/v1/assets/{assetId}/vesting-schedule",
            path_params={"assetId": asset_id},
            params={"startTime": startTime, "endTime": endTime},
        )
