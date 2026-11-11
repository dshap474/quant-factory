"""Minimal stable response types while retaining dynamic provider fields.

USAGE: response = client.tabular.list("assets"); rows = response.body["data"]
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypedDict

# --------------------------------------------------------------------------- #
# Wire envelopes
# --------------------------------------------------------------------------- #


class TabularMetadata(TypedDict, total=False):
    totalRows: int
    totalPages: int
    page: int
    pageSize: int
    matchedField: str


class TabularListBody(TypedDict, total=False):
    data: list[dict[str, Any]]
    metadata: TabularMetadata
    error: str | None


class TimeseriesData(TypedDict, total=False):
    point_schema: list[dict[str, Any]]
    series: list[dict[str, Any]]
    key: str
    entity: dict[str, Any]
    points: list[list[Any]]


class TimeseriesBody(TypedDict, total=False):
    data: TimeseriesData
    error: str | None


# --------------------------------------------------------------------------- #
# Public response wrapper
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class BlockworksResponse:
    body: dict[str, Any]
    status: int
    headers: dict[str, str]
    request_id: str | None
