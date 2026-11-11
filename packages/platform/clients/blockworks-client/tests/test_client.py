"""Deterministic client behavior against synthetic provider responses.

USAGE: uv run pytest packages/platform/clients/blockworks-client/tests/test_client.py -q
"""

from __future__ import annotations

import io
from datetime import datetime

import httpx
import pytest
from blockworks_client import (
    BlockworksAPIError,
    BlockworksClient,
    BlockworksConfigError,
    BlockworksDecodeError,
    BlockworksPaginationError,
)

# --------------------------------------------------------------------------- #
# Synthetic transport and response shapes
# --------------------------------------------------------------------------- #


def _client(handler):
    session = httpx.Client(base_url="https://api.blockworks.com", transport=httpx.MockTransport(handler))
    return BlockworksClient("synthetic-test-key", http_client=session, max_attempts=1)


def _series_body(single=False):
    schema = [{"field": "time", "type": "time"}, {"field": "close", "type": "float64"}]
    series = {"key": "opaque", "entity": {"name": "Synthetic"}, "points": [[1, None]], "future": 7}
    return {"data": {"point_schema": schema, **series} if single else {"point_schema": schema, "series": [series]}}


# --------------------------------------------------------------------------- #
# Request and response tests
# --------------------------------------------------------------------------- #


def test_credentials_at_construction_and_injected_session_ownership(monkeypatch):
    monkeypatch.delenv("BLOCKWORKS_API_KEY", raising=False)
    with pytest.raises(BlockworksConfigError):
        BlockworksClient()
    monkeypatch.setenv("BLOCKWORKS_API_KEY", "environment-key")
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"data": []})

    session = httpx.Client(base_url="https://api.blockworks.com", transport=httpx.MockTransport(handler))
    with BlockworksClient(http_client=session, max_attempts=1) as client:
        client.watchlists.list()
    assert requests[0].headers["x-blockworks-api-key"] == "environment-key"
    assert not session.is_closed
    session.close()


@pytest.mark.parametrize(
    "base",
    [
        "https://api.blockworks.com:8443",
        "https://api.blockworks.com/other",
        "http://api.blockworks.com",
        "https://example.test",
    ],
)
def test_injected_origin_must_be_exact(base):
    with httpx.Client(base_url=base, transport=httpx.MockTransport(lambda request: httpx.Response(200))) as session:
        with pytest.raises(BlockworksConfigError):
            BlockworksClient("synthetic-test-key", http_client=session)


@pytest.mark.parametrize(
    "path", ["https://example.test/a", "//example.test/a", "/a/../b", "/a?x=1", "/%2fexample.test"]
)
def test_raw_get_rejects_unsafe_paths(path):
    with _client(lambda request: httpx.Response(200, json={"data": []})) as client:
        with pytest.raises(BlockworksConfigError):
            client.get_raw(path)


def test_redirect_does_not_forward_credentials():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(302, headers={"Location": "https://example.test/steal"})

    with _client(handler) as client:
        with pytest.raises(BlockworksAPIError) as failure:
            client.watchlists.list()
    assert failure.value.status == 302
    assert len(calls) == 1


def test_tabular_filters_and_opaque_row_identifier():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"data": [], "metadata": {"totalPages": 0}, "error": None})

    with _client(handler) as client:
        body = client.tabular.list(
            "assets",
            filters={"isStablecoinEq": False, "assetIDIsOneOf": ["a", "b"]},
            page_size=1,
            selections=["name", "symbol"],
        ).body
    assert body["error"] is None
    assert requests[0].url.params["isStablecoinEq"] == "false"
    assert requests[0].url.params["assetIDIsOneOf"] == "a,b"
    assert requests[0].url.params["selections"] == "name,symbol"


def test_timeseries_path_window_and_nullable_tuple():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=_series_body(single=True))

    with _client(handler) as client:
        result = client.timeseries.single("asset-price", "1d", "opaque/identifier", timeframe="7d", bounds=False)
        assert result.body["data"]["points"] == [[1, None]]
        with pytest.raises(BlockworksConfigError):
            client.timeseries.single("asset-price", "1d", "x", timeframe="7d", start="2026-01-01")
        with pytest.raises(BlockworksConfigError):
            client.timeseries.single("asset-price", "1d", "x", start=datetime(2026, 1, 1))
        with pytest.raises(BlockworksConfigError):
            client.timeseries.batch("asset-price", "1d", series=[str(i) for i in range(11)])
    assert requests[0].url.path.endswith("/opaque/identifier") or "%2F" in str(requests[0].url)
    assert requests[0].url.params["bounds"] == "false"


def test_bad_json_and_tuple_width_rejected():
    with _client(lambda request: httpx.Response(200, text="<html>bad</html>")) as client:
        with pytest.raises(BlockworksDecodeError):
            client.tabular.list("assets")
    with _client(
        lambda request: httpx.Response(
            200,
            json={
                "data": {
                    "point_schema": [{"field": "time"}, {"field": "close"}],
                    "key": "a",
                    "entity": {},
                    "points": [[1]],
                }
            },
        )
    ) as client:
        with pytest.raises(BlockworksDecodeError):
            client.timeseries.single("asset-price", "1d", "a")


def test_api_error_is_bounded_and_redacted():
    def handler(request):
        return httpx.Response(
            403,
            headers={"x-request-id": "synthetic-test-key"},
            json={"error": "synthetic provider message"},
        )

    with _client(handler) as client:
        with pytest.raises(BlockworksAPIError) as failure:
            client.tabular.list("assets")
    assert failure.value.status == 403
    assert "access forbidden" in str(failure.value)
    assert "synthetic-test-key" not in str(failure.value)


def test_explicit_pagination_detects_repeat_and_budget():
    pages = []

    def handler(request):
        page = int(request.url.params["page"])
        pages.append(page)
        return httpx.Response(200, json={"data": [{"assetID": "same"}], "metadata": {"totalPages": 3}})

    with _client(handler) as client:
        iterator = client.tabular.iter_pages("assets", max_pages=3)
        next(iterator)
        with pytest.raises(BlockworksPaginationError):
            next(iterator)
    assert pages == [1, 2]

    def progress(request):
        page = int(request.url.params["page"])
        return httpx.Response(200, json={"data": [{"assetID": str(page)}], "metadata": {"totalPages": 3}})

    with _client(progress) as client:
        iterator = client.tabular.iter_pages("assets", max_pages=2)
        assert len(next(iterator).body["data"]) == 1
        assert len(next(iterator).body["data"]) == 1
        with pytest.raises(BlockworksPaginationError):
            next(iterator)


def test_explicit_series_chunking_and_string_rejection():
    calls = []

    def handler(request):
        calls.append(request.url.params["series"])
        return httpx.Response(200, json=_series_body())

    with _client(handler) as client:
        assert len(list(client.timeseries.iter_batches("asset-price", "1d", ["a", "b", "c"], batch_size=2))) == 2
        with pytest.raises(BlockworksConfigError):
            list(client.timeseries.iter_batches("asset-price", "1d", "abc"))
        with pytest.raises(BlockworksConfigError):
            list(client.timeseries.iter_batches("asset-price", "1d", ["a", "a"]))
    assert calls == ["a,b", "c"]


def test_native_export_writes_streamed_bytes():
    payload = b"assetID,time,close\na,1,2\n"

    def handler(request):
        assert request.url.params["acceptFormat"] == "csv"
        return httpx.Response(200, content=payload, headers={"content-type": "text/csv"})

    output = io.BytesIO()
    with _client(handler) as client:
        count = client.timeseries.export_batch("asset-price", "1d", output, format="csv", series=["a"])
    assert count == len(payload) and output.getvalue() == payload
