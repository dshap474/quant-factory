"""Shared HTTP requests, retries and optional response accounting for platform clients.

USAGE: from client_common import HTTPClient; HTTPClient(base_url="https://example.com").get_json("/data")
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from random import uniform
from typing import Any

import httpx

# --------------------------------------------------------------------------- #
# Transport configuration
# --------------------------------------------------------------------------- #

DEFAULT_USER_AGENT = "quant-factory/0.1"


@dataclass(slots=True)
class RetryConfig:
    max_attempts: int = 3
    backoff_factor: float = 0.5
    retry_on_status: tuple[int, ...] = (408, 425, 429, 500, 502, 503, 504)
    jitter: float = 0.0
    max_elapsed: float | None = None
    extended_retry_after: bool = False


# --------------------------------------------------------------------------- #
# Shared request and response handling
# --------------------------------------------------------------------------- #


class HTTPClient:
    """Small sync-only HTTP helper with retry support."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout: float = 10.0,
        headers: dict[str, str] | None = None,
        client: httpx.Client | None = None,
        retry_config: RetryConfig | None = None,
        response_hook: Callable[[httpx.Response], None] | None = None,
        follow_redirects: bool | None = None,
        request_timeout: float | httpx.Timeout | None = None,
    ) -> None:
        self._owns_client = client is None
        merged_headers = {"User-Agent": DEFAULT_USER_AGENT}
        if headers:
            merged_headers.update(headers)
        self._client = client or httpx.Client(
            base_url=base_url or "",
            timeout=timeout,
            headers=merged_headers,
            follow_redirects=True if follow_redirects is None else follow_redirects,
        )
        self._retry = retry_config or RetryConfig()
        self._response_hook = response_hook
        self._follow_redirects = follow_redirects
        self._request_timeout = request_timeout

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _retry_delay(self, attempt: int, retry_after: str | None) -> float:
        if retry_after and retry_after.isdigit():
            return float(retry_after)
        if retry_after and self._retry.extended_retry_after:
            try:
                delay = float(retry_after)
                if math.isfinite(delay) and delay >= 0:
                    return delay
            except ValueError:
                try:
                    date = parsedate_to_datetime(retry_after)
                    if date.tzinfo is None:
                        date = date.replace(tzinfo=timezone.utc)
                    return max(0.0, (date - datetime.now(timezone.utc)).total_seconds())
                except (TypeError, ValueError, OverflowError):
                    pass
        base = self._retry.backoff_factor * (2 ** (attempt - 1))
        return base + uniform(0.0, self._retry.jitter * base) if self._retry.jitter else base

    def _can_retry(self, attempt: int, started: float, delay: float) -> bool:
        return attempt < self._retry.max_attempts and (
            self._retry.max_elapsed is None or time.monotonic() - started + delay < self._retry.max_elapsed
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
        ok_status: frozenset[int] = frozenset(),
    ) -> httpx.Response:
        attempt = 1
        started = time.monotonic()
        while True:
            try:
                request_options: dict[str, Any] = (
                    {} if self._follow_redirects is None else {"follow_redirects": self._follow_redirects}
                )
                if self._request_timeout is not None:
                    request_options["timeout"] = self._request_timeout
                response = self._client.request(
                    method,
                    path,
                    params=params,
                    headers=headers,
                    json=json,
                    **request_options,
                )
                if self._response_hook is not None:
                    self._response_hook(response)
                if response.status_code in self._retry.retry_on_status:
                    delay = self._retry_delay(attempt, response.headers.get("Retry-After"))
                    if self._can_retry(attempt, started, delay):
                        response.close()
                        time.sleep(delay)
                        attempt += 1
                        continue
                if response.status_code not in ok_status:
                    response.raise_for_status()
                return response
            except httpx.RequestError:
                delay = self._retry_delay(attempt, None)
                if not self._can_retry(attempt, started, delay):
                    raise
                time.sleep(delay)
                attempt += 1

    @contextmanager
    def stream_get(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ):
        """Stream one GET with retries only before yielding response bytes."""
        attempt = 1
        started = time.monotonic()
        while True:
            yielded = False
            request_options: dict[str, Any] = (
                {} if self._follow_redirects is None else {"follow_redirects": self._follow_redirects}
            )
            if self._request_timeout is not None:
                request_options["timeout"] = self._request_timeout
            try:
                with self._client.stream("GET", path, params=params, headers=headers, **request_options) as response:
                    if self._response_hook is not None:
                        self._response_hook(response)
                    if response.status_code in self._retry.retry_on_status:
                        delay = self._retry_delay(attempt, response.headers.get("Retry-After"))
                        if self._can_retry(attempt, started, delay):
                            response.close()
                            time.sleep(delay)
                            attempt += 1
                            continue
                    response.raise_for_status()
                    yielded = True
                    yield response
                    return
            except httpx.RequestError:
                delay = self._retry_delay(attempt, None)
                if yielded or not self._can_retry(attempt, started, delay):
                    raise
                time.sleep(delay)
                attempt += 1

    def get(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """The raw response, for callers that need status or headers; a 304 (conditional GET) is returned, not raised."""
        return self._request("GET", path, params=params, headers=headers, ok_status=frozenset({304}))

    def get_json(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any] | list[Any]:
        return self._request("GET", path, params=params, headers=headers).json()

    def get_text(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> str:
        return self._request("GET", path, params=params, headers=headers).text

    def get_bytes(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> bytes:
        return self._request("GET", path, params=params, headers=headers).content

    def post_json(
        self,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any] | list[Any]:
        return self._request("POST", path, json=payload, headers=headers).json()

    def post(
        self,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """The raw response, for callers that need status or headers; a 204 (no content) is returned, not raised."""
        return self._request("POST", path, json=payload, headers=headers, ok_status=frozenset({204}))
