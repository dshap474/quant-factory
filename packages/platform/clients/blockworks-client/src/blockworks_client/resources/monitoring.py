"""Named Monitoring v2 read operations with exact provider query names.

USAGE: client.monitoring.developments(limit=5); client.monitoring.view(view_id)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..models import BlockworksResponse

if TYPE_CHECKING:
    from ..client import BlockworksClient


# --------------------------------------------------------------------------- #
# Monitoring operations
# --------------------------------------------------------------------------- #


class MonitoringResource:
    def __init__(self, client: BlockworksClient):
        self._client = client

    def categories(self) -> BlockworksResponse:
        return self._client._call("/monitoring/v2/categories")

    def developments(self, **params: Any) -> BlockworksResponse:
        return self._client._call("/monitoring/v2/developments", params=params)

    def development(self, development_id: str) -> BlockworksResponse:
        return self._client._call(
            "/monitoring/v2/developments/{developmentId}", path_params={"developmentId": development_id}
        )

    def events(self, **params: Any) -> BlockworksResponse:
        return self._client._call("/monitoring/v2/events", params=params)

    def event(self, event_id: str) -> BlockworksResponse:
        return self._client._call("/monitoring/v2/events/{eventId}", path_params={"eventId": event_id})

    def views(self, **params: Any) -> BlockworksResponse:
        return self._client._call("/monitoring/v2/monitoring-views", params=params)

    def view(self, view_id: str) -> BlockworksResponse:
        return self._client._call(
            "/monitoring/v2/monitoring-views/{monitoringViewId}", path_params={"monitoringViewId": view_id}
        )

    def view_developments(self, view_id: str, **params: Any) -> BlockworksResponse:
        return self._client._call(
            "/monitoring/v2/monitoring-views/{monitoringViewId}/developments",
            path_params={"monitoringViewId": view_id},
            params=params,
        )

    def view_events(self, view_id: str, **params: Any) -> BlockworksResponse:
        return self._client._call(
            "/monitoring/v2/monitoring-views/{monitoringViewId}/events",
            path_params={"monitoringViewId": view_id},
            params=params,
        )

    def all_view_developments(self, **params: Any) -> BlockworksResponse:
        return self._client._call("/monitoring/v2/monitoring-views/all/developments", params=params)

    def all_view_events(self, **params: Any) -> BlockworksResponse:
        return self._client._call("/monitoring/v2/monitoring-views/all/events", params=params)
