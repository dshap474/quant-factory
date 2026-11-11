"""Test opt-in streaming and retry policy without changing existing consumers.

USAGE: uv run pytest packages/platform/clients/client-common/tests -q
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import format_datetime

import httpx
import pytest
from client_common import HTTPClient, RetryConfig

# --------------------------------------------------------------------------- #
# Streaming lifecycle and retry boundaries
# --------------------------------------------------------------------------- #


class _Chunks(httpx.SyncByteStream):
    def __init__(self, fail=False):
        self.closed = False
        self.fail = fail
        self.yields = 0

    def __iter__(self):
        self.yields += 1
        yield b"first"
        if self.fail:
            raise httpx.ReadError("synthetic interrupted read")
        self.yields += 1
        yield b"second"

    def close(self):
        self.closed = True


def test_stream_closes_on_early_exit_without_materializing():
    chunks = _Chunks()
    session = httpx.Client(
        base_url="https://example.test",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=chunks)),
    )
    transport = HTTPClient(client=session)
    with transport.stream_get("/data") as response:
        iterator = response.iter_bytes()
        assert next(iterator) == b"first"
        assert chunks.yields == 1
    assert chunks.closed and response.is_closed and chunks.yields == 1
    session.close()


def test_stream_retries_connect_failure_before_yield():
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ConnectError("synthetic connect failure", request=request)
        return httpx.Response(200, stream=_Chunks())

    with httpx.Client(base_url="https://example.test", transport=httpx.MockTransport(handler)) as session:
        transport = HTTPClient(client=session, retry_config=RetryConfig(max_attempts=2, backoff_factor=0))
        with transport.stream_get("/data") as response:
            assert b"".join(response.iter_bytes()) == b"firstsecond"
    assert len(calls) == 2


def test_stream_never_retries_after_bytes_are_yielded():
    calls = []
    chunks = _Chunks(fail=True)

    def handler(request):
        calls.append(request)
        return httpx.Response(200, stream=chunks)

    with httpx.Client(base_url="https://example.test", transport=httpx.MockTransport(handler)) as session:
        transport = HTTPClient(client=session, retry_config=RetryConfig(max_attempts=3, backoff_factor=0))
        with pytest.raises(httpx.ReadError):
            with transport.stream_get("/data") as response:
                list(response.iter_bytes())
    assert len(calls) == 1 and chunks.closed


# --------------------------------------------------------------------------- #
# Backward compatibility and opt-in limits
# --------------------------------------------------------------------------- #


def test_default_injected_redirect_setting_is_preserved():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(302, headers={"Location": "/other"})

    with httpx.Client(
        base_url="https://example.test", follow_redirects=False, transport=httpx.MockTransport(handler)
    ) as session:
        with pytest.raises(httpx.HTTPStatusError):
            HTTPClient(client=session).get("/data")
    assert len(calls) == 1


def test_extended_retry_after_is_opt_in():
    with httpx.Client(base_url="https://example.test") as session:
        legacy = HTTPClient(client=session, retry_config=RetryConfig(backoff_factor=0.5))
        extended = HTTPClient(client=session, retry_config=RetryConfig(backoff_factor=0.5, extended_retry_after=True))
        assert legacy._retry_delay(1, "0.25") == 0.5
        assert extended._retry_delay(1, "0.25") == 0.25
        future = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=30), usegmt=True)
        assert legacy._retry_delay(1, future) == 0.5
        assert 28 <= extended._retry_delay(1, future) <= 30


def test_retry_budget_does_not_sleep_past_retry_after(monkeypatch):
    calls = []
    sleeps = []
    monkeypatch.setattr("client_common.http.time.sleep", sleeps.append)

    def handler(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "60"})

    with httpx.Client(base_url="https://example.test", transport=httpx.MockTransport(handler)) as session:
        client = HTTPClient(client=session, retry_config=RetryConfig(max_attempts=3, max_elapsed=1))
        with pytest.raises(httpx.HTTPStatusError):
            client.get("/data")
    assert len(calls) == 1 and sleeps == []


def test_request_timeout_override_does_not_mutate_injected_session():
    timeouts = []

    def handler(request):
        timeouts.append(request.extensions["timeout"])
        return httpx.Response(200, json={})

    with httpx.Client(base_url="https://example.test", timeout=None, transport=httpx.MockTransport(handler)) as session:
        HTTPClient(client=session).get("/legacy")
        HTTPClient(client=session, request_timeout=2).get("/opt-in")
        with HTTPClient(client=session, request_timeout=3).stream_get("/stream") as response:
            response.read()
        assert session.timeout.connect is None
    assert set(timeouts[0].values()) == {None}
    assert set(timeouts[1].values()) == {2}
    assert set(timeouts[2].values()) == {3}


@pytest.mark.parametrize("value", ["NaN", "inf", "-1"])
def test_malformed_extended_retry_after_uses_backoff(value):
    with httpx.Client() as session:
        transport = HTTPClient(client=session, retry_config=RetryConfig(extended_retry_after=True, backoff_factor=0.5))
        assert transport._retry_delay(1, value) == 0.5
