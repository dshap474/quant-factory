"""Tabular discovery, rows, and explicit bounded page iteration.

USAGE: client.tabular.list("assets", filters={"slugEq": "bitcoin"}, page_size=1)
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, BinaryIO

from .._generated import ROUTES
from ..exceptions import BlockworksConfigError, BlockworksPaginationError
from ..models import BlockworksResponse

if TYPE_CHECKING:
    from ..client import BlockworksClient


# --------------------------------------------------------------------------- #
# Tabular operations
# --------------------------------------------------------------------------- #


class TabularResource:
    def __init__(self, client: BlockworksClient):
        self._client = client

    @staticmethod
    def _template(model: str, row: bool = False) -> str:
        prefix = f"/query/tabular/{model}"
        if not isinstance(model, str) or not model or "/" in model or model == "catalog":
            raise BlockworksConfigError("unknown tabular model")
        if not row:
            if prefix not in ROUTES or ROUTES[prefix]["method"] != "tabular.list":
                raise BlockworksConfigError("unknown tabular model")
            return prefix
        matches = [
            path for path in ROUTES if path.startswith(prefix + "/{") and ROUTES[path]["method"] == "tabular.get"
        ]
        if len(matches) != 1:
            raise BlockworksConfigError("tabular model has no row lookup")
        return matches[0]

    def catalog(self, *, public_only: bool | None = True, accessible: bool | None = None) -> BlockworksResponse:
        return self._client._call(
            "/query/tabular/catalog", params={"publicOnly": public_only, "accessible": accessible}
        )

    @staticmethod
    def _params(
        filters: Mapping[str, object] | None,
        page: int | None,
        page_size: int | None,
        selections: Sequence[str] | None,
        sort_by: str | None = None,
        sort_direction: str | None = None,
    ) -> dict[str, object]:
        params: dict[str, object] = dict(filters or {})
        for key, value in {
            "page": page,
            "pageSize": page_size,
            "selections": selections,
            "sortBy": sort_by,
            "sortDirection": sort_direction,
        }.items():
            if value is not None:
                if key in params:
                    raise BlockworksConfigError(f"duplicate {key} parameter")
                params[key] = value
        effective_page = params.get("page")
        effective_size = params.get("pageSize")
        if (
            effective_page is not None
            and (isinstance(effective_page, bool) or not isinstance(effective_page, int) or effective_page < 1)
        ) or (
            effective_size is not None
            and (
                isinstance(effective_size, bool)
                or not isinstance(effective_size, int)
                or not 1 <= effective_size <= 1000
            )
        ):
            raise BlockworksConfigError("page must be at least 1 and page_size must be 1..1000")
        return params

    def list(
        self,
        model: str,
        *,
        filters: Mapping[str, object] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        selections: Sequence[str] | None = None,
        sort_by: str | None = None,
        sort_direction: str | None = None,
    ) -> BlockworksResponse:
        params = self._params(filters, page, page_size, selections, sort_by, sort_direction)
        return self._client._call(self._template(model), params=params)

    def get(self, model: str, identifier: str, *, selections: Sequence[str] | None = None) -> BlockworksResponse:
        template = self._template(model, row=True)
        name = ROUTES[template]["path"][0]
        return self._client._call(template, path_params={name: identifier}, params={"selections": selections})

    def iter_pages(
        self,
        model: str,
        *,
        filters: Mapping[str, object] | None = None,
        page: int = 1,
        page_size: int = 100,
        max_pages: int = 100,
        selections: Sequence[str] | None = None,
        sort_by: str | None = None,
        sort_direction: str | None = None,
    ) -> Iterator[BlockworksResponse]:
        if isinstance(max_pages, bool) or not isinstance(max_pages, int) or not 1 <= max_pages <= 10000:
            raise BlockworksConfigError("max_pages must be 1..10000")
        seen: set[str] = set()
        for _ in range(max_pages):
            result = self.list(
                model,
                filters=filters,
                page=page,
                page_size=page_size,
                selections=selections,
                sort_by=sort_by,
                sort_direction=sort_direction,
            )
            rows = result.body["data"]
            metadata = result.body.get("metadata")
            if (
                not isinstance(metadata, dict)
                or isinstance(metadata.get("totalPages"), bool)
                or not isinstance(metadata.get("totalPages"), int)
                or metadata["totalPages"] < 0
            ):
                raise BlockworksPaginationError("tabular response has no totalPages metadata")
            if rows:
                signature = hashlib.sha256(json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest()
                if signature in seen:
                    raise BlockworksPaginationError("provider repeated a tabular page")
                seen.add(signature)
            total_pages = metadata["totalPages"]
            empty = not rows
            if empty and page < total_pages:
                raise BlockworksPaginationError("empty page before provider totalPages")
            done = empty or page >= total_pages
            yield result
            if done:
                return
            page += 1
        raise BlockworksPaginationError("max_pages reached before provider totalPages")

    def export_list(
        self,
        model: str,
        destination: BinaryIO | str | Path,
        *,
        format: str,
        filters: Mapping[str, object] | None = None,
        page: int | None = None,
        page_size: int | None = None,
        selections: Sequence[str] | None = None,
    ) -> int:
        params = self._params(filters, page, page_size, selections)
        path, params = self._client._prepare(self._template(model), params=params)
        return self._client.export_to(path, destination, format=format, params=params)
