"""Thin FRED + ALFRED client with public and authenticated read paths.

USAGE: call ``get_series_observations_public`` for keyless chart data, or set
``FRED_API_KEY`` in the environment for authenticated API methods.
"""

from __future__ import annotations

import csv
import os
from io import StringIO
from typing import Any

import httpx

# --------------------------------------------------------------------------- #
# Client
# --------------------------------------------------------------------------- #


class FredClient:
    """Thin client for FRED API v2 and ALFRED vintages."""

    _PUBLIC_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = "https://api.stlouisfed.org",
        timeout: float = 10.0,
        client: httpx.Client | None = None,
        user_agent: str = "quant-factory/0.1",
    ) -> None:
        self._api_key = api_key
        # The public CSV feed has been observed to stall requests whose User-Agent omits the
        # HTTP library token, so the public reader appends it.
        self._public_user_agent = f"{user_agent} python-httpx/{httpx.__version__}"
        self._owns_client = client is None
        self._client = client or httpx.Client(
            base_url=base_url,
            timeout=timeout,
            headers={"User-Agent": user_agent},
        )

    @property
    def api_key(self) -> str:
        """Resolve ``FRED_API_KEY`` only when a request needs it."""
        if self._api_key is None:
            self._api_key = os.environ.get("FRED_API_KEY")
            if not self._api_key:
                raise ValueError("FRED_API_KEY is required; set it in the environment.")
        return self._api_key

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "FredClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        self.close()

    def _get(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        request_params = {"file_type": "json"}
        if self.api_key:
            request_params["api_key"] = self.api_key
        if params:
            request_params.update({key: value for key, value in params.items() if value is not None})
        try:
            response = self._client.get(path, params=request_params)
            response.raise_for_status()
        except httpx.HTTPError:
            raise RuntimeError(f"FRED request failed for '{path}'") from None
        return response.json()

    def get_series(self, series_id: str) -> dict[str, Any]:
        return self._get("/fred/series", params={"series_id": series_id})

    def get_series_observations(
        self,
        series_id: str,
        *,
        realtime_start: str | None = None,
        realtime_end: str | None = None,
        observation_start: str | None = None,
        observation_end: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
        sort_order: str | None = None,
        units: str | None = None,
        frequency: str | None = None,
        output_type: int | None = None,
    ) -> dict[str, Any]:
        """Observations; ``output_type=4`` with an all-time realtime window returns ALFRED first releases."""
        params = {
            "series_id": series_id,
            "realtime_start": realtime_start,
            "realtime_end": realtime_end,
            "observation_start": observation_start,
            "observation_end": observation_end,
            "limit": limit,
            "offset": offset,
            "sort_order": sort_order,
            "units": units,
            "frequency": frequency,
            "output_type": output_type,
        }
        return self._get("/fred/series/observations", params=params)

    def get_series_observations_public(
        self,
        series_id: str,
        *,
        observation_start: str | None = None,
        observation_end: str | None = None,
    ) -> dict[str, Any]:
        """Read one series from FRED's public graph CSV endpoint without a key."""
        params = {
            "id": series_id,
            "cosd": observation_start,
            "coed": observation_end,
        }
        try:
            response = self._client.get(
                self._PUBLIC_CSV_URL,
                params={key: value for key, value in params.items() if value is not None},
                headers={"User-Agent": self._public_user_agent},
            )
            response.raise_for_status()
        except httpx.HTTPError:
            raise RuntimeError(f"FRED public CSV request failed for '{series_id}'") from None

        observations = []
        for row in csv.DictReader(StringIO(response.text)):
            observation_date = row.get("observation_date")
            value = row.get(series_id)
            if observation_date and value:
                observations.append({"date": observation_date, "value": value})
        return {"observations": observations}

    def get_series_vintages(self, series_id: str) -> dict[str, Any]:
        return self._get("/fred/series/vintagedates", params={"series_id": series_id})

    def get_release_dates(
        self,
        release_id: int,
        *,
        realtime_start: str | None = None,
        realtime_end: str | None = None,
        include_release_dates_with_no_data: bool = False,
        limit: int | None = None,
        offset: int | None = None,
        sort_order: str | None = None,
    ) -> dict[str, Any]:
        """Dates a release was (or, with ``include_release_dates_with_no_data``, is scheduled to be) published."""
        params = {
            "release_id": release_id,
            "realtime_start": realtime_start,
            "realtime_end": realtime_end,
            "include_release_dates_with_no_data": "true" if include_release_dates_with_no_data else None,
            "limit": limit,
            "offset": offset,
            "sort_order": sort_order,
        }
        return self._get("/fred/release/dates", params=params)
