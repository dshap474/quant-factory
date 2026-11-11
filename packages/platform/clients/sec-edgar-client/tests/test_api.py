"""Tests for the thin SEC EDGAR workspace client."""

from __future__ import annotations

import httpx
import pytest
from sec_edgar_client import SECEdgarClient


def test_get_company_tickers_uses_official_sec_files_endpoint():
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    sec_client = SECEdgarClient(client=client)

    payload = sec_client.get_company_tickers()

    assert seen["url"] == "https://www.sec.gov/files/company_tickers.json"
    assert payload["0"]["ticker"] == "AAPL"


def test_get_company_tickers_exchange_uses_official_sec_files_endpoint():
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(
            200,
            json={"fields": ["cik", "name", "ticker", "exchange"], "data": [[320193, "Apple Inc.", "AAPL", "Nasdaq"]]},
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    sec_client = SECEdgarClient(client=client)

    payload = sec_client.get_company_tickers_exchange()

    assert seen["url"] == "https://www.sec.gov/files/company_tickers_exchange.json"
    assert payload["data"][0][2] == "AAPL"


def test_existing_submissions_endpoint_shape_is_unchanged():
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"cik": "0000320193", "name": "Apple Inc."})

    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="https://data.sec.gov",
        headers={"User-Agent": "quant-factory/0.1 contact@example.com"},
    )
    sec_client = SECEdgarClient(client=client)

    payload = sec_client.get_submissions("320193")

    assert seen["url"] == "https://data.sec.gov/submissions/CIK0000320193.json"
    assert payload["cik"] == "0000320193"


def test_latest_financial_statement_notes_zip_comes_from_first_page_link():
    seen: dict[str, list[str]] = {"urls": []}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["urls"].append(str(request.url))
        if str(request.url).endswith("/financial-statement-notes-data-sets"):
            return httpx.Response(
                200,
                text="""
                <html><body>
                <a href="/files/dera/data/financial-statement-notes-data-sets/2026_03_notes.zip">latest</a>
                <a href="/files/dera/data/financial-statement-notes-data-sets/2025q4_notes.zip">older</a>
                </body></html>
                """,
            )
        return httpx.Response(200, content=b"notes-bytes")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    sec_client = SECEdgarClient(client=client)

    payload = sec_client.download_latest_financial_statement_notes_data_set_zip()

    assert seen["urls"][0] == "https://www.sec.gov/data-research/sec-markets-data/financial-statement-notes-data-sets"
    assert (
        seen["urls"][1] == "https://www.sec.gov/files/dera/data/financial-statement-notes-data-sets/2026_03_notes.zip"
    )
    assert payload == b"notes-bytes"


def test_latest_form_13f_zip_comes_from_first_page_link():
    seen: dict[str, list[str]] = {"urls": []}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["urls"].append(str(request.url))
        if str(request.url).endswith("/form-13f-data-sets"):
            return httpx.Response(
                200,
                text="""
                <html><body>
                <a href="/files/structureddata/data/form-13f-data-sets/01dec2025-28feb2026_form13f.zip">latest</a>
                <a href="/files/structureddata/data/form-13f-data-sets/2023q4_form13f.zip">older</a>
                </body></html>
                """,
            )
        return httpx.Response(200, content=b"13f-bytes")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    sec_client = SECEdgarClient(client=client)

    payload = sec_client.download_latest_form_13f_data_set_zip()

    assert seen["urls"][0] == "https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets"
    assert (
        seen["urls"][1]
        == "https://www.sec.gov/files/structureddata/data/form-13f-data-sets/01dec2025-28feb2026_form13f.zip"
    )
    assert payload == b"13f-bytes"


def test_fails_to_deliver_urls_and_download_use_official_page():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if str(request.url).endswith("/fails-deliver-data"):
            return httpx.Response(
                200,
                text='<a href="/files/data/fails-deliver-data/cnsfails202607b.zip">archive</a>',
            )
        return httpx.Response(200, content=b"ftd-bytes")

    sec_client = SECEdgarClient(client=httpx.Client(transport=httpx.MockTransport(handler)))

    urls = sec_client.list_fails_to_deliver_urls()
    payload = sec_client.download_fails_to_deliver_zip(urls[0])

    assert urls == ["https://www.sec.gov/files/data/fails-deliver-data/cnsfails202607b.zip"]
    assert payload == b"ftd-bytes"
    assert seen == [
        "https://www.sec.gov/data-research/sec-markets-data/fails-deliver-data",
        urls[0],
    ]


def test_fails_to_deliver_rejects_foreign_archive_hosts_without_requesting_them():
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(200, content=b"unexpected")

    sec_client = SECEdgarClient(client=httpx.Client(transport=httpx.MockTransport(handler)))

    with pytest.raises(ValueError, match="configured SEC HTTPS host"):
        sec_client.download_fails_to_deliver_zip("https://evil.example/cnsfails202607b.zip")

    assert requested == []


def test_download_archive_if_modified_returns_none_on_304():
    seen: list[str | None] = []
    stamp = "Fri, 27 Dec 2024 19:31:58 GMT"

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("If-Modified-Since"))
        if request.headers.get("If-Modified-Since") == stamp:
            return httpx.Response(304)
        return httpx.Response(200, content=b"zip-bytes", headers={"Last-Modified": stamp})

    sec_client = SECEdgarClient(client=httpx.Client(transport=httpx.MockTransport(handler)))
    url = "https://www.sec.gov/files/dera/data/financial-statement-data-sets/2016q1.zip"

    assert sec_client.download_archive_if_modified(url) == (b"zip-bytes", stamp)
    assert sec_client.download_archive_if_modified(url, last_modified=stamp) == (None, stamp)
    assert seen == [None, stamp]


@pytest.mark.parametrize(
    ("kind", "page", "first", "second"),
    [
        (
            "nport",
            "form-n-port-data-sets",
            "/files/dera/data/form-n-port-data-sets/2026q2_nport.zip",
            "/files/dera/data/form-n-port-data-sets/2026q1_nport.zip",
        ),
        (
            "nmfp",
            "dera-form-n-mfp-data-sets",
            "/files/dera/data/form-n-mfp-data-sets/20260810-20260908_nmfp.zip",
            "/files/dera/data/form-n-mfp-data-sets/20260709-20260807_nmfp.zip",
        ),
        (
            "ncen",
            "form-n-cen-data-sets",
            "/files/dera/data/form-n-cen-data-sets/2026q2_ncen.zip",
            "/files/dera/data/form-n-cen-data-sets/2026q1_ncen.zip",
        ),
    ],
)
def test_fund_data_set_urls_latest_and_download(kind, page, first, second):
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if str(request.url).endswith(f"/{page}"):
            html = f'<a href="{first}">a</a><a href="{second}">b</a><a href="{first}">dup</a>'
            return httpx.Response(200, text=html)
        return httpx.Response(200, content=b"zip")

    sec_client = SECEdgarClient(client=httpx.Client(transport=httpx.MockTransport(handler)))
    page_url = f"https://www.sec.gov/data-research/sec-markets-data/{page}"
    assert getattr(sec_client, f"form_{kind}_data_sets_page_url")() == page_url
    urls = getattr(sec_client, f"list_form_{kind}_data_set_urls")()
    assert urls == [f"https://www.sec.gov{first}", f"https://www.sec.gov{second}"]
    assert getattr(sec_client, f"latest_form_{kind}_data_set_url")() == urls[0]
    assert getattr(sec_client, f"download_form_{kind}_data_set_zip")(urls[1]) == b"zip"
    assert seen[-1] == urls[1]
    with pytest.raises(ValueError):
        getattr(sec_client, f"download_form_{kind}_data_set_zip")("https://evil.example/x.zip")
    assert seen.count(page_url) == 2
