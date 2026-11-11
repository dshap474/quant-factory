"""Charts list and visualization data reads.

USAGE: client.charts.list(limit=5); client.charts.data("chart-id", limit=5)
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from ..models import BlockworksResponse

if TYPE_CHECKING:
    from ..client import BlockworksClient


# --------------------------------------------------------------------------- #
# Chart operations
# --------------------------------------------------------------------------- #


class ChartsResource:
    def __init__(self, client: BlockworksClient):
        self._client = client

    def list(
        self, *, page: int | None = None, limit: int | None = None, search: str | None = None
    ) -> BlockworksResponse:
        return self._client._call("/v1/charts", params={"page": page, "limit": limit, "search": search})

    def data(
        self,
        visualization_id: str | int,
        *,
        page: int | None = None,
        limit: int | None = None,
        search: str | None = None,
        select: str | Sequence[str] | None = None,
        order_by: str | None = None,
        order_dir: str | None = None,
    ) -> BlockworksResponse:
        return self._client._call(
            "/v1/charts/{visualizationId}/data",
            path_params={"visualizationId": visualization_id},
            params={
                "page": page,
                "limit": limit,
                "search": search,
                "select": select,
                "order_by": order_by,
                "order_dir": order_dir,
            },
        )
