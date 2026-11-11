"""Timeseries catalog, batch/single access, and explicit series chunking.

USAGE: client.timeseries.single("asset-price", "1d", asset_id, timeframe="7d")
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, BinaryIO

from .._generated import ROUTES
from ..exceptions import BlockworksConfigError
from ..models import BlockworksResponse

if TYPE_CHECKING:
    from ..client import BlockworksClient


# --------------------------------------------------------------------------- #
# Timeseries operations
# --------------------------------------------------------------------------- #


MAX_SERIES = 10


class TimeseriesResource:
    def __init__(self, client: BlockworksClient):
        self._client = client

    @staticmethod
    def _template(model: str, single: bool = False) -> str:
        if not isinstance(model, str) or not model or "/" in model or model == "catalog":
            raise BlockworksConfigError("unknown timeseries model")
        prefix = f"/query/timeseries/{model}/{{granularity}}"
        if not single:
            if prefix not in ROUTES or ROUTES[prefix]["method"] != "timeseries.batch":
                raise BlockworksConfigError("unknown timeseries model")
            return prefix
        matches = [
            path for path in ROUTES if path.startswith(prefix + "/{") and ROUTES[path]["method"] == "timeseries.single"
        ]
        if len(matches) != 1:
            raise BlockworksConfigError("timeseries model has no single route")
        return matches[0]

    @staticmethod
    def _window(
        start: str | int | date | datetime | None, end: str | int | date | datetime | None, timeframe: str | None
    ) -> None:
        if timeframe is not None and (start is not None or end is not None):
            raise BlockworksConfigError("timeframe cannot be combined with start or end")

    @staticmethod
    def _series(series: Sequence[str] | str | None) -> str | None:
        if series is None:
            return None
        values = [series] if isinstance(series, str) else list(series)
        if not 1 <= len(values) <= MAX_SERIES or any(not isinstance(value, str) or not value for value in values):
            raise BlockworksConfigError("series must contain 1..10 nonempty identifiers")
        if any("," in value for value in values):
            raise BlockworksConfigError("series identifiers cannot contain commas")
        return ",".join(values)

    def catalog(self, *, public_only: bool | None = True, accessible: bool | None = None) -> BlockworksResponse:
        return self._client._call(
            "/query/timeseries/catalog", params={"publicOnly": public_only, "accessible": accessible}
        )

    def batch(
        self,
        model: str,
        granularity: str,
        series: Sequence[str] | str | None = None,
        *,
        start: str | int | date | datetime | None = None,
        end: str | int | date | datetime | None = None,
        timeframe: str | None = None,
        selections: Sequence[str] | None = None,
        bounds: bool | None = None,
    ) -> BlockworksResponse:
        self._window(start, end, timeframe)
        template = self._template(model)
        return self._client._call(
            template,
            path_params={"granularity": granularity},
            params={
                "series": self._series(series),
                "start": start,
                "end": end,
                "timeframe": timeframe,
                "selections": selections,
                "bounds": bounds,
            },
        )

    def single(
        self,
        model: str,
        granularity: str,
        identifier: str,
        *,
        start: str | int | date | datetime | None = None,
        end: str | int | date | datetime | None = None,
        timeframe: str | None = None,
        selections: Sequence[str] | None = None,
        bounds: bool | None = None,
    ) -> BlockworksResponse:
        self._window(start, end, timeframe)
        template = self._template(model, single=True)
        name = ROUTES[template]["path"][1]
        return self._client._call(
            template,
            path_params={"granularity": granularity, name: identifier},
            params={"start": start, "end": end, "timeframe": timeframe, "selections": selections, "bounds": bounds},
        )

    def iter_batches(
        self,
        model: str,
        granularity: str,
        series: Sequence[str],
        *,
        batch_size: int = MAX_SERIES,
        start: str | int | date | datetime | None = None,
        end: str | int | date | datetime | None = None,
        timeframe: str | None = None,
        selections: Sequence[str] | None = None,
        bounds: bool | None = None,
    ) -> Iterator[BlockworksResponse]:
        if (
            isinstance(batch_size, bool)
            or not isinstance(batch_size, int)
            or not 1 <= batch_size <= MAX_SERIES
            or isinstance(series, (str, bytes))
            or not series
        ):
            raise BlockworksConfigError("batch_size must be 1..10 and series cannot be empty")
        series = tuple(series)
        if any(not isinstance(item, str) or not item or "," in item for item in series):
            raise BlockworksConfigError("series identifiers must be nonempty strings without commas")
        if len(set(series)) != len(series):
            raise BlockworksConfigError("duplicate series identifiers are not accepted")
        for offset in range(0, len(series), batch_size):
            yield self.batch(
                model,
                granularity,
                series[offset : offset + batch_size],
                start=start,
                end=end,
                timeframe=timeframe,
                selections=selections,
                bounds=bounds,
            )

    def export_batch(
        self,
        model: str,
        granularity: str,
        destination: BinaryIO | str | Path,
        *,
        format: str,
        series: Sequence[str] | str | None = None,
        start: str | int | date | datetime | None = None,
        end: str | int | date | datetime | None = None,
        timeframe: str | None = None,
        selections: Sequence[str] | None = None,
        bounds: bool | None = None,
    ) -> int:
        self._window(start, end, timeframe)
        template = self._template(model)
        params = {
            "series": self._series(series),
            "start": start,
            "end": end,
            "timeframe": timeframe,
            "selections": selections,
            "bounds": bounds,
        }
        path, params = self._client._prepare(template, path_params={"granularity": granularity}, params=params)
        return self._client.export_to(path, destination, format=format, params=params)

    def export_single(
        self,
        model: str,
        granularity: str,
        identifier: str,
        destination: BinaryIO | str | Path,
        *,
        format: str,
        start: str | int | date | datetime | None = None,
        end: str | int | date | datetime | None = None,
        timeframe: str | None = None,
        selections: Sequence[str] | None = None,
        bounds: bool | None = None,
    ) -> int:
        self._window(start, end, timeframe)
        template = self._template(model, single=True)
        name = ROUTES[template]["path"][1]
        path, params = self._client._prepare(
            template,
            path_params={"granularity": granularity, name: identifier},
            params={"start": start, "end": end, "timeframe": timeframe, "selections": selections, "bounds": bounds},
        )
        return self._client.export_to(path, destination, format=format, params=params)
