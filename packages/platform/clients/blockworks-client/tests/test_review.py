"""Independent regression checks for documented provider response shapes.

USAGE: uv run pytest packages/platform/clients/blockworks-client/tests/test_review.py -q
"""

from datetime import datetime, timezone

import pytest
from blockworks_client._wire import encode_query, safe_relative_path, validate_timeseries
from blockworks_client.exceptions import BlockworksConfigError, BlockworksDecodeError

# --------------------------------------------------------------------------- #
# Independently specified provider shapes and encoding
# --------------------------------------------------------------------------- #


def test_point_schema_shape_and_additive_metadata():
    schema = [
        {"field": "time", "name": "Time", "type": "time", "time": True},
        {"field": "close", "name": "Close", "type": "float64", "time": False, "future": "value"},
    ]
    entry = {"key": "opaque-key", "entity": {"slug": "example"}, "points": [[1790208000, None]]}
    validate_timeseries({"data": {"point_schema": schema, "series": [entry]}}, single=False)
    validate_timeseries({"data": {"point_schema": schema, **entry}}, single=True)
    with pytest.raises(BlockworksDecodeError):
        validate_timeseries({"data": {"point_schema": schema, **entry, "points": [[1790208000]]}}, single=True)


def test_query_false_zero_and_metric_order_are_preserved():
    values = encode_query({"verified": False, "page": 0, "selections": ["volume", "close"], "unused": None})
    assert values == {"verified": "false", "page": "0", "selections": "volume,close"}
    assert encode_query({"start": datetime(2026, 9, 1, tzinfo=timezone.utc)})["start"].startswith("2026-09-01T")
    with pytest.raises(BlockworksConfigError):
        encode_query({"start": datetime(2026, 9, 1)})


@pytest.mark.parametrize(
    "path",
    [
        "https://example.org/path",
        "//example.org/path",
        "/%2fexample.org",
        "/a/../b",
        "/a/%2e%2e/b",
        "/a?key=x",
        "/a#fragment",
        "/a\\b",
    ],
)
def test_authenticated_raw_paths_reject_origin_and_traversal(path):
    with pytest.raises(BlockworksConfigError):
        safe_relative_path(path)


# --------------------------------------------------------------------------- #
# Public client regression checks
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "options",
    [
        {"timeout": float("nan")},
        {"timeout": float("inf")},
        {"max_elapsed": float("nan")},
        {"max_attempts": True},
        {"max_attempts": 1.5},
    ],
)
def test_nonfinite_or_noninteger_budgets_are_rejected(options):
    from blockworks_client.client import BlockworksClient

    with pytest.raises(BlockworksConfigError):
        BlockworksClient(api_key="synthetic", **options)


def test_composite_identifier_is_encoded_once_and_injected_client_is_not_closed():
    import httpx
    from blockworks_client.client import BlockworksClient

    calls = []

    def handler(request):
        calls.append(request)
        assert request.url.raw_path == b"/query/tabular/token-transparency-filing-questions/example%3Aq1"
        return httpx.Response(200, json={"data": {"id": "example:q1"}, "metadata": {}, "error": None})

    with httpx.Client(base_url="https://api.blockworks.com", transport=httpx.MockTransport(handler)) as transport:
        with BlockworksClient(api_key="synthetic", http_client=transport) as client:
            assert (
                client.tabular.get("token-transparency-filing-questions", "example:q1").body["data"]["id"]
                == "example:q1"
            )
        assert not transport.is_closed
    assert len(calls) == 1


def test_stream_never_restarts_after_partial_output():
    import httpx
    from blockworks_client.client import BlockworksClient
    from blockworks_client.exceptions import BlockworksTransportError

    class FailingStream(httpx.SyncByteStream):
        closed = False

        def __iter__(self):
            yield b"first-row\n"
            raise httpx.ReadError("synthetic stream interruption")

        def close(self):
            self.closed = True

    body = FailingStream()
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, stream=body)

    with httpx.Client(base_url="https://api.blockworks.com", transport=httpx.MockTransport(handler)) as transport:
        with BlockworksClient(api_key="synthetic", http_client=transport) as client:
            with pytest.raises(BlockworksTransportError):
                with client.stream("/query/tabular/assets", params={"acceptFormat": "csv"}) as response:
                    iterator = response.iter_bytes()
                    assert next(iterator) == b"first-row\n"
                    next(iterator)
    assert len(calls) == 1
    assert body.closed


def test_page_budget_does_not_silently_claim_complete_dataset():
    import httpx
    from blockworks_client.client import BlockworksClient
    from blockworks_client.exceptions import BlockworksPaginationError

    def handler(request):
        return httpx.Response(200, json={"data": [{"id": "first"}], "metadata": {"totalPages": 2}, "error": None})

    with httpx.Client(base_url="https://api.blockworks.com", transport=httpx.MockTransport(handler)) as transport:
        with BlockworksClient(api_key="synthetic", http_client=transport) as client:
            iterator = client.tabular.iter_pages("assets", max_pages=1)
            assert next(iterator).body["data"] == [{"id": "first"}]
            with pytest.raises(BlockworksPaginationError):
                next(iterator)


def test_explicit_timeout_applies_to_injected_transport_without_mutation():
    import httpx
    from blockworks_client.client import BlockworksClient

    seen = []

    def handler(request):
        seen.append(request.extensions["timeout"])
        return httpx.Response(200, json={"data": []})

    with httpx.Client(
        base_url="https://api.blockworks.com", timeout=None, transport=httpx.MockTransport(handler)
    ) as transport:
        with BlockworksClient(api_key="synthetic", http_client=transport, timeout=2) as client:
            client.get_raw("/query/tabular/assets")
            with client.stream("/query/tabular/assets") as response:
                response.read()
        assert transport.timeout.read is None
    assert len(seen) == 2
    assert all(settings == {"connect": 2, "read": 2, "write": 2, "pool": 2} for settings in seen)


def test_export_handles_partial_sink_writes_without_data_loss():
    import httpx
    from blockworks_client.client import BlockworksClient

    class PartialSink:
        def __init__(self):
            self.contents = bytearray()

        def write(self, value):
            length = min(3, len(value))
            self.contents.extend(value[:length])
            return length

    source = b"asset,value\nexample,12345\n"
    sink = PartialSink()

    def handler(request):
        return httpx.Response(200, content=source)

    with httpx.Client(base_url="https://api.blockworks.com", transport=httpx.MockTransport(handler)) as transport:
        with BlockworksClient(api_key="synthetic", http_client=transport) as client:
            count = client.export_to("/query/tabular/assets", sink, format="csv")
    assert bytes(sink.contents) == source
    assert count == len(source)
