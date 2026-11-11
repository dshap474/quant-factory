"""FRED and ALFRED adapter used by data-package callers.

USAGE: with the API key in the environment, call ``FREDClientAdapter()``.
"""

from __future__ import annotations

from typing import Any

import polars as pl
from client_common import records_to_frame

from .api import FredClient

# --------------------------------------------------------------------------- #
# Client adapter
# --------------------------------------------------------------------------- #


class FREDClientAdapter:
    """Adapter over `fred-client` with frame helpers."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        timeout: float = 10.0,
        client=None,
    ) -> None:
        self.client = FredClient(api_key=api_key, timeout=timeout, client=client)

    def close(self) -> None:
        self.client.close()

    def fetch_series_observations(self, series_id: str, **params: Any) -> dict[str, Any]:
        return self.client.get_series_observations(series_id, **params)

    def fetch_series_observations_public(self, series_id: str, **params: Any) -> dict[str, Any]:
        """Keyless observations from FRED's public graph CSV (no realtime or series metadata)."""
        return self.client.get_series_observations_public(series_id, **params)

    def fetch_series_vintages(self, series_id: str) -> dict[str, Any]:
        return self.client.get_series_vintages(series_id)

    def fetch_series(self, series_id: str) -> dict[str, Any]:
        return self.client.get_series(series_id)

    def observations_to_frame(self, payload: dict[str, Any]) -> pl.DataFrame:
        return records_to_frame(list(payload.get("observations", [])))

    def vintages_to_frame(self, payload: dict[str, Any]) -> pl.DataFrame:
        dates = payload.get("vintage_dates", [])
        return records_to_frame([{"vintage_date": value} for value in dates])

    def series_to_frame(self, payload: dict[str, Any]) -> pl.DataFrame:
        return records_to_frame(list(payload.get("seriess", [])))
