"""Regression coverage for request boundaries, exports, and iterator stability.

USAGE: uv run pytest packages/platform/clients/blockworks-client/tests/test_audit_fixes.py
"""

import io
from contextlib import contextmanager

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
# Synthetic HTTP boundary
# --------------------------------------------------------------------------- #


@contextmanager
def client(handler):
    with httpx.Client(base_url="https://api.blockworks.com", transport=httpx.MockTransport(handler)) as session:
        with BlockworksClient("synthetic-key", http_client=session, max_attempts=1) as sdk:
            yield sdk, session


def test_fixed_origin_for_buffered_and_streamed_requests():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"data": []})

    with client(handler) as (sdk, session):
        session.base_url = "https://untrusted.invalid"
        sdk.get_raw("/query/ping")
        with sdk.stream("/query/ping") as response:
            response.read()
    assert len(seen) == 2
    assert all(
        r.url.host == "api.blockworks.com" and r.headers["x-blockworks-api-key"] == "synthetic-key" for r in seen
    )


@pytest.mark.parametrize("kind", ["params", "auth", "header", "cookie"])
@pytest.mark.parametrize("stream", [False, True])
def test_mutated_injected_defaults_fail_before_sending(kind, stream):
    def handler(request):
        pytest.fail("conflicting defaults must not reach transport")

    with client(handler) as (sdk, session):
        if kind == "params":
            session.params = {"start": "1"}
        elif kind == "auth":
            session.auth = ("user", "password")
        elif kind == "header":
            session.headers["Authorization"] = "Bearer other"
        else:
            session.cookies.set("session", "other")
        with pytest.raises(BlockworksConfigError):
            if stream:
                with sdk.stream("/query/ping"):
                    pass
            else:
                sdk.get_raw("/query/ping")
        with pytest.raises(BlockworksConfigError):
            BlockworksClient("synthetic-key", http_client=session)


@pytest.mark.parametrize(
    "header, expected",
    [
        ("120", "120"),
        ("0.25", "0.25"),
        ("NaN", None),
        ("inf", None),
        ("-1", None),
        ("Bearer other", None),
        ("x" * 129, None),
        ("Wed, 21 Oct 2015 07:28:00 GMT", "Wed, 21 Oct 2015 07:28:00 +0000"),
    ],
)
def test_terminal_retry_metadata(header, expected):
    with client(lambda r: httpx.Response(429, headers={"Retry-After": header})) as (sdk, _):
        with pytest.raises(BlockworksAPIError) as error:
            sdk.get_raw("/query/ping")
    assert error.value.retry_after == expected


@pytest.mark.parametrize(
    "detail", ["Authorization: Bearer OTHER_TOKEN", "Authorization: Basic OTHER_TOKEN", "token: OTHER_TOKEN"]
)
def test_provider_error_text_is_not_exposed(detail):
    with client(lambda r: httpx.Response(400, json={"error": detail})) as (sdk, _):
        with pytest.raises(BlockworksAPIError) as error:
            sdk.get_raw("/query/ping")
    assert error.value.detail is None
    assert "OTHER_TOKEN" not in str(error.value)


# --------------------------------------------------------------------------- #
# Read/export parity and minimal envelopes
# --------------------------------------------------------------------------- #


def test_tabular_export_preserves_native_params_and_matches_read():
    seen = []

    def handler(request):
        seen.append(dict(request.url.params))
        return httpx.Response(200, json={"data": []})

    with client(handler) as (sdk, _):
        filters = {"page": 2, "pageSize": 7, "selections": ["assetID", "symbol"]}
        sdk.tabular.list("assets", filters=filters)
        sdk.tabular.export_list("assets", io.BytesIO(), format="csv", filters=filters)
    assert seen[0] == {"page": "2", "pageSize": "7", "selections": "assetID,symbol"}
    assert seen[1] == {**seen[0], "acceptFormat": "csv"}


@pytest.mark.parametrize(
    "params", [{"filters": {"pageSize": 1001}}, {"filters": {"page": True}}, {"filters": {"page": 2}, "page": 3}]
)
def test_both_tabular_paths_reject_invalid_effective_params(params):
    with client(lambda r: pytest.fail("invalid request sent")) as (sdk, _):
        with pytest.raises(BlockworksConfigError):
            sdk.tabular.list("assets", **params)
        with pytest.raises(BlockworksConfigError):
            sdk.tabular.export_list("assets", io.BytesIO(), format="csv", **params)


def test_decoded_method_rejects_export_format_before_http():
    with client(lambda r: pytest.fail("invalid request sent")) as (sdk, _):
        with pytest.raises(BlockworksConfigError, match="export"):
            sdk.tabular.list("assets", filters={"acceptFormat": "csv"})


@pytest.mark.parametrize("resource", ["charts", "monitoring"])
def test_missing_envelope_rejected(resource):
    with client(lambda r: httpx.Response(200, json={"unexpected": []})) as (sdk, _):
        with pytest.raises(BlockworksDecodeError):
            if resource == "charts":
                sdk.charts.list()
            else:
                sdk.monitoring.categories()


def test_timeseries_exports_share_required_and_enum_checks():
    with client(lambda r: pytest.fail("invalid request sent")) as (sdk, _):
        with pytest.raises(BlockworksConfigError):
            sdk.timeseries.export_batch("asset-price", "1d", io.BytesIO(), format="csv")
        with pytest.raises(BlockworksConfigError):
            sdk.timeseries.export_batch("asset-price", "bad", io.BytesIO(), format="csv", series=["a"])
        with pytest.raises(BlockworksConfigError):
            sdk.timeseries.export_single("asset-price", "bad", "a", io.BytesIO(), format="csv")


# --------------------------------------------------------------------------- #
# Iterator state must survive consumer mutation
# --------------------------------------------------------------------------- #


def test_pagination_uses_pre_yield_state():
    seen = []

    def handler(request):
        page = int(request.url.params["page"])
        seen.append(page)
        return httpx.Response(200, json={"data": [{"id": page}], "metadata": {"totalPages": 2}})

    with client(handler) as (sdk, _):
        pages = sdk.tabular.iter_pages("assets")
        first = next(pages)
        first.body["data"].clear()
        first.body["metadata"]["totalPages"] = 1
        assert len(list(pages)) == 1
    assert seen == [1, 2]


def test_empty_nonterminal_page_is_incomplete():
    with client(lambda r: httpx.Response(200, json={"data": [], "metadata": {"totalPages": 2}})) as (sdk, _):
        with pytest.raises(BlockworksPaginationError, match="empty"):
            list(sdk.tabular.iter_pages("assets"))


def test_batches_snapshot_ids_and_validate_all_before_first_request():
    seen = []

    def handler(request):
        seen.append(request.url.params["series"])
        return httpx.Response(200, json={"data": {"point_schema": [{"field": "time"}], "series": []}})

    with client(handler) as (sdk, _):
        ids = [str(i) for i in range(11)]
        batches = sdk.timeseries.iter_batches("asset-price", "1d", ids)
        next(batches)
        ids[10] = "changed"
        list(batches)
        assert seen == [",".join(str(i) for i in range(10)), "10"]
        with pytest.raises(BlockworksConfigError):
            sdk.timeseries.batch("asset-price", "1d", ids)
        before = len(seen)
        with pytest.raises(BlockworksConfigError):
            list(sdk.timeseries.iter_batches("asset-price", "1d", ["ok", "bad,id"], batch_size=1))
        assert len(seen) == before
