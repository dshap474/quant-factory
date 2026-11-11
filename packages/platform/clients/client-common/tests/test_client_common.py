"""Unit tests for client-common transport and frame helpers.

USAGE: uv run pytest packages/platform/clients/client-common/tests -q
"""

import httpx
from client_common import HTTPClient, RetryConfig, key_value_frame, records_to_frame

# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


def test_http_client_retries_then_returns_json():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503)
        return httpx.Response(200, json={"ok": True})

    client = HTTPClient(
        client=httpx.Client(base_url="https://example.test", transport=httpx.MockTransport(handler)),
        retry_config=RetryConfig(max_attempts=2, backoff_factor=0.0),
    )
    assert client.get_json("/x") == {"ok": True}
    assert calls["n"] == 2


def test_http_client_get_returns_not_modified_response():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["If-Modified-Since"] == "stamp"
        return httpx.Response(304, headers={"Last-Modified": "stamp"})

    client = HTTPClient(client=httpx.Client(base_url="https://example.test", transport=httpx.MockTransport(handler)))
    response = client.get("/x", headers={"If-Modified-Since": "stamp"})
    assert response.status_code == 304 and response.headers["Last-Modified"] == "stamp"


def test_frames():
    assert records_to_frame([]).is_empty()
    assert records_to_frame([{"a": 1}]).to_dicts() == [{"a": 1}]
    assert key_value_frame({"k": 1}).to_dicts() == [{"key": "k", "value": 1}]
