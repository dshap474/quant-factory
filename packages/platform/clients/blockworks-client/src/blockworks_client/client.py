"""Authenticated synchronous Blockworks API client and shared request lifecycle.

USAGE: with BlockworksClient() as client: print(client.tabular.list("assets", page_size=1).body)
"""

from __future__ import annotations

import math
import os
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from email.utils import format_datetime, parsedate_to_datetime
from pathlib import Path
from typing import BinaryIO

import httpx
from client_common import HTTPClient, RetryConfig

from ._generated import ROUTES
from ._wire import decode_json, encode_query, path_value, safe_relative_path, validate_timeseries
from .exceptions import BlockworksAPIError, BlockworksConfigError, BlockworksDecodeError, BlockworksTransportError
from .models import BlockworksResponse

# --------------------------------------------------------------------------- #
# Client configuration and lifecycle
# --------------------------------------------------------------------------- #

_BASE_URL = "https://api.blockworks.com"
_USER_AGENT = "blockworks-client/0.1.0"


class BlockworksClient:
    """Read-only Blockworks client; credentials are loaded at construction."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        timeout: float = 20.0,
        max_attempts: int = 3,
        max_elapsed: float = 60.0,
        http_client: httpx.Client | None = None,
    ) -> None:
        key = api_key if api_key is not None else os.environ.get("BLOCKWORKS_API_KEY")
        if not isinstance(key, str) or not key or key.isspace():
            raise BlockworksConfigError("BLOCKWORKS_API_KEY is required")
        if any(ord(c) < 32 for c in key):
            raise BlockworksConfigError("API key contains an invalid character")
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout)
            or timeout <= 0
            or timeout > 300
            or isinstance(max_attempts, bool)
            or not isinstance(max_attempts, int)
            or not 1 <= max_attempts <= 10
            or isinstance(max_elapsed, bool)
            or not isinstance(max_elapsed, (int, float))
            or not math.isfinite(max_elapsed)
            or not 0 < max_elapsed <= 300
        ):
            raise BlockworksConfigError("timeout, retry attempts, and elapsed budget must be finite and bounded")
        if http_client is not None:
            if not isinstance(http_client, httpx.Client):
                raise BlockworksConfigError("http_client must be an httpx.Client")
            url = http_client.base_url
            if (
                url.scheme != "https"
                or url.host != "api.blockworks.com"
                or url.port not in (None, 443)
                or url.username
                or url.password
                or url.path not in ("", "/")
                or url.query
                or url.fragment
            ):
                raise BlockworksConfigError("injected HTTP client must use https://api.blockworks.com")
        self._injected_client = http_client
        self._check_injected_defaults()
        self._key = key
        self._http = HTTPClient(
            base_url=_BASE_URL,
            timeout=timeout,
            client=http_client,
            follow_redirects=False,
            request_timeout=timeout,
            retry_config=RetryConfig(
                max_attempts=max_attempts,
                backoff_factor=0.5,
                jitter=0.25,
                max_elapsed=max_elapsed,
                extended_retry_after=True,
            ),
        )
        from .resources.charts import ChartsResource
        from .resources.monitoring import MonitoringResource
        from .resources.tabular import TabularResource
        from .resources.timeseries import TimeseriesResource
        from .resources.unlocks import UnlocksResource
        from .resources.watchlists import WatchlistsResource

        self.tabular = TabularResource(self)
        self.timeseries = TimeseriesResource(self)
        self.charts = ChartsResource(self)
        self.unlocks = UnlocksResource(self)
        self.monitoring = MonitoringResource(self)
        self.watchlists = WatchlistsResource(self)

    def _check_injected_defaults(self) -> None:
        client = self._injected_client
        if client is not None and (
            client.params
            or client.auth is not None
            or client.cookies
            or "Authorization" in client.headers
            or "X-Blockworks-API-Key" in client.headers
        ):
            raise BlockworksConfigError(
                "injected HTTP client must not have query, auth, cookie, or credential defaults"
            )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> BlockworksClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _headers(self) -> dict[str, str]:
        return {"X-Blockworks-API-Key": self._key, "User-Agent": _USER_AGENT}

    def _api_error(self, response: httpx.Response) -> BlockworksAPIError:
        request_id = response.headers.get("x-request-id") or response.headers.get("x-correlation-id")
        if request_id:
            request_id = "".join(
                c for c in request_id.replace(self._key, "[redacted]")[:80] if c.isalnum() or c in "-_ .[]"
            )
        detail = None
        if response.status_code == 403:
            detail = "access forbidden"
        elif response.status_code == 401:
            detail = "authentication rejected"
        elif response.status_code == 429:
            detail = "rate limit exceeded"
        elif response.status_code >= 500:
            detail = "provider unavailable"
        retry_after = response.headers.get("retry-after")
        if retry_after is not None:
            raw_retry_after = retry_after
            if len(retry_after) > 128 or any(ord(c) < 32 for c in retry_after):
                retry_after = None
            else:
                try:
                    delay = float(retry_after)
                    if not math.isfinite(delay) or delay < 0:
                        retry_after = None
                    else:
                        retry_after = str(int(delay)) if delay.is_integer() else str(delay)
                except ValueError:
                    try:
                        retry_after = format_datetime(parsedate_to_datetime(raw_retry_after))
                    except (ValueError, TypeError, OverflowError):
                        retry_after = None
        return BlockworksAPIError(response.status_code, request_id or None, detail, retry_after=retry_after)

    # --------------------------------------------------------------------------- #
    # Raw and decoded GET requests
    # --------------------------------------------------------------------------- #

    def get_raw(self, relative_path: str, *, params: Mapping[str, object] | None = None) -> httpx.Response:
        """Return one complete raw GET response, including bytes and headers."""
        self._check_injected_defaults()
        path = _BASE_URL + safe_relative_path(relative_path)
        try:
            return self._http.get(path, params=encode_query(params), headers=self._headers())
        except httpx.HTTPStatusError as exc:
            raise self._api_error(exc.response) from None
        except httpx.RequestError:
            raise BlockworksTransportError("Blockworks request failed before a response") from None

    @contextmanager
    def stream(self, relative_path: str, *, params: Mapping[str, object] | None = None) -> Iterator[httpx.Response]:
        """Yield a live streaming GET response; close it on normal or early exit."""
        self._check_injected_defaults()
        path = _BASE_URL + safe_relative_path(relative_path)
        try:
            with self._http.stream_get(path, params=encode_query(params), headers=self._headers()) as response:
                yield response
        except httpx.HTTPStatusError as exc:
            raise self._api_error(exc.response) from None
        except httpx.RequestError:
            raise BlockworksTransportError("Blockworks stream failed") from None

    def export_to(
        self,
        relative_path: str,
        destination: BinaryIO | str | Path,
        *,
        format: str,
        params: Mapping[str, object] | None = None,
    ) -> int:
        """Stream a native CSV/JSONL export to a caller-provided file or binary handle."""
        if format not in ("csv", "jsonl"):
            raise BlockworksConfigError("export format must be csv or jsonl")
        merged = dict(params or {})
        merged["acceptFormat"] = format
        with self.stream(relative_path, params=merged) as response:

            def write_to(handle: BinaryIO) -> int:
                count = 0
                for chunk in response.iter_bytes():
                    offset = 0
                    while offset < len(chunk):
                        written = handle.write(chunk[offset:])
                        if (
                            isinstance(written, bool)
                            or not isinstance(written, int)
                            or not 0 < written <= len(chunk) - offset
                        ):
                            raise OSError("export destination made no valid write progress")
                        offset += written
                        count += written
                return count

            if isinstance(destination, (str, Path)):
                with open(destination, "wb") as handle:
                    return write_to(handle)
            return write_to(destination)

    def _call(
        self,
        template: str,
        *,
        path_params: Mapping[str, object] | None = None,
        params: Mapping[str, object] | None = None,
    ) -> BlockworksResponse:
        if (params or {}).get("acceptFormat") is not None:
            raise BlockworksConfigError("decoded methods require JSON; use export_to or resource export methods")
        path, supplied = self._prepare(template, path_params=path_params, params=params)
        route = ROUTES[template]
        response = self.get_raw(path, params=supplied)
        family = route["family"]
        body = decode_json(response.content, family)
        if template.startswith("/query/timeseries/") and not template.endswith("/catalog"):
            validate_timeseries(body, single=template.count("{") == 2)
        if template.startswith("/query/tabular/") and not template.endswith("/catalog"):
            data = body.get("data")
            if not isinstance(data, dict if "{" in template else list):
                raise BlockworksDecodeError("unexpected tabular data envelope")
        request_id = response.headers.get("x-request-id") or response.headers.get("x-correlation-id")
        return BlockworksResponse(body, response.status_code, dict(response.headers), request_id)

    @staticmethod
    def _prepare(
        template: str,
        *,
        path_params: Mapping[str, object] | None = None,
        params: Mapping[str, object] | None = None,
    ) -> tuple[str, dict[str, object]]:
        route = ROUTES.get(template)
        if route is None:
            raise BlockworksConfigError("unknown documented GET route")
        names = set(route["query"])
        supplied = {k: v for k, v in (params or {}).items() if v is not None}
        if set(supplied) - names:
            raise BlockworksConfigError(f"unsupported query parameter: {sorted(set(supplied) - names)[0]}")
        missing = set(route["required"]) - set(supplied)
        if missing:
            raise BlockworksConfigError(f"required query parameter missing: {sorted(missing)[0]}")
        values = dict(path_params or {})
        if set(values) != set(route["path"]):
            raise BlockworksConfigError("path identifiers do not match route template")
        for name, options in route["enums"].items():
            value = values.get(name, supplied.get(name))
            if value is not None and options and value not in options and not isinstance(value, (list, tuple)):
                raise BlockworksConfigError(f"unsupported {name} value")
        path = template.format(**{name: path_value(value) for name, value in values.items()})
        return path, supplied
