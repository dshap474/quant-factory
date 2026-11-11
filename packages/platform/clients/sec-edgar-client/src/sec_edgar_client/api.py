"""Thin SEC EDGAR client."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx


class SECEdgarClient:
    """Thin client for the public SEC EDGAR API surface."""

    _ZIP_LINK_RE = re.compile(r'href="([^"]+\.zip)"', re.IGNORECASE)

    def __init__(
        self,
        *,
        base_url: str = "https://data.sec.gov",
        archives_base_url: str = "https://www.sec.gov",
        timeout: float = 10.0,
        client: httpx.Client | None = None,
        user_agent: str = "quant-factory/0.1 contact@example.com",
    ) -> None:
        headers = {
            "User-Agent": user_agent,
            "Accept-Encoding": "gzip, deflate",
            "Accept": "application/json",
        }
        self.archives_base_url = archives_base_url.rstrip("/")
        self._owns_client = client is None
        self._client = client or httpx.Client(base_url=base_url, timeout=timeout, headers=headers)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "SECEdgarClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        self.close()

    @staticmethod
    def normalize_cik(cik: str | int) -> str:
        digits = "".join(ch for ch in str(cik) if ch.isdigit())
        if not digits:
            raise ValueError("CIK must contain digits")
        return digits.zfill(10)

    def _get_json(self, path: str) -> dict[str, Any]:
        response = self._client.get(path)
        response.raise_for_status()
        return response.json()

    def _get_json_url(self, url: str) -> dict[str, Any]:
        response = self._client.get(url)
        response.raise_for_status()
        return response.json()

    def _get_text_url(self, url: str) -> str:
        response = self._client.get(url, headers={"Accept": "text/html,application/xhtml+xml"})
        response.raise_for_status()
        return response.text

    def _get_bytes(self, url: str) -> bytes:
        response = self._client.get(url)
        response.raise_for_status()
        return response.content

    def _zip_urls_from_page(self, url: str) -> list[str]:
        html = self._get_text_url(url)
        seen: list[str] = []
        for match in self._ZIP_LINK_RE.finditer(html):
            absolute = urljoin(self.archives_base_url, match.group(1))
            self._validate_archive_url(absolute)
            if absolute not in seen:
                seen.append(absolute)
        return seen

    def _validate_archive_url(self, url: str) -> None:
        parsed = urlparse(url)
        allowed_host = urlparse(self.archives_base_url).hostname
        if parsed.scheme != "https" or parsed.hostname != allowed_host:
            raise ValueError(f"SEC archive URL must use the configured SEC HTTPS host: {url}")

    def get_submissions(self, cik: str | int) -> dict[str, Any]:
        return self._get_json(f"/submissions/CIK{self.normalize_cik(cik)}.json")

    def get_company_facts(self, cik: str | int) -> dict[str, Any]:
        return self._get_json(f"/api/xbrl/companyfacts/CIK{self.normalize_cik(cik)}.json")

    def get_company_concept(
        self,
        cik: str | int,
        taxonomy: str,
        tag: str,
    ) -> dict[str, Any]:
        return self._get_json(f"/api/xbrl/companyconcept/CIK{self.normalize_cik(cik)}/{taxonomy}/{tag}.json")

    def get_frames(
        self,
        taxonomy: str,
        tag: str,
        unit: str,
        frame: str,
    ) -> dict[str, Any]:
        return self._get_json(f"/api/xbrl/frames/{taxonomy}/{tag}/{unit}/{frame}.json")

    def company_tickers_url(self) -> str:
        return f"{self.archives_base_url}/files/company_tickers.json"

    def company_tickers_exchange_url(self) -> str:
        return f"{self.archives_base_url}/files/company_tickers_exchange.json"

    def get_company_tickers(self) -> dict[str, Any]:
        return self._get_json_url(self.company_tickers_url())

    def get_company_tickers_exchange(self) -> dict[str, Any]:
        return self._get_json_url(self.company_tickers_exchange_url())

    def bulk_submissions_url(self) -> str:
        return f"{self.archives_base_url}/Archives/edgar/daily-index/bulkdata/submissions.zip"

    def bulk_companyfacts_url(self) -> str:
        return f"{self.archives_base_url}/Archives/edgar/daily-index/xbrl/companyfacts.zip"

    def financial_statement_data_sets_page_url(self) -> str:
        return f"{self.archives_base_url}/data-research/sec-markets-data/financial-statement-data-sets"

    def financial_statement_notes_data_sets_page_url(self) -> str:
        return f"{self.archives_base_url}/data-research/sec-markets-data/financial-statement-notes-data-sets"

    def insider_transactions_data_sets_page_url(self) -> str:
        return f"{self.archives_base_url}/data-research/sec-markets-data/insider-transactions-data-sets"

    def form_13f_data_sets_page_url(self) -> str:
        return f"{self.archives_base_url}/data-research/sec-markets-data/form-13f-data-sets"

    def fails_to_deliver_page_url(self) -> str:
        return f"{self.archives_base_url}/data-research/sec-markets-data/fails-deliver-data"

    def list_financial_statement_data_set_urls(self) -> list[str]:
        return self._zip_urls_from_page(self.financial_statement_data_sets_page_url())

    def latest_financial_statement_data_set_url(self) -> str:
        return self.list_financial_statement_data_set_urls()[0]

    def list_financial_statement_notes_data_set_urls(self) -> list[str]:
        return self._zip_urls_from_page(self.financial_statement_notes_data_sets_page_url())

    def latest_financial_statement_notes_data_set_url(self) -> str:
        return self.list_financial_statement_notes_data_set_urls()[0]

    def list_insider_transactions_data_set_urls(self) -> list[str]:
        return self._zip_urls_from_page(self.insider_transactions_data_sets_page_url())

    def latest_insider_transactions_data_set_url(self) -> str:
        return self.list_insider_transactions_data_set_urls()[0]

    def list_form_13f_data_set_urls(self) -> list[str]:
        return self._zip_urls_from_page(self.form_13f_data_sets_page_url())

    def list_fails_to_deliver_urls(self) -> list[str]:
        return self._zip_urls_from_page(self.fails_to_deliver_page_url())

    def latest_form_13f_data_set_url(self) -> str:
        return self.list_form_13f_data_set_urls()[0]

    def download_bulk_submissions_zip(self, *, last_modified: str | None = None) -> tuple[bytes | None, str | None]:
        return self.download_archive_if_modified(self.bulk_submissions_url(), last_modified=last_modified)

    def download_bulk_companyfacts_zip(self, *, last_modified: str | None = None) -> tuple[bytes | None, str | None]:
        return self.download_archive_if_modified(self.bulk_companyfacts_url(), last_modified=last_modified)

    def download_latest_financial_statement_data_set_zip(self) -> bytes:
        return self._get_bytes(self.latest_financial_statement_data_set_url())

    def download_latest_financial_statement_notes_data_set_zip(self) -> bytes:
        return self._get_bytes(self.latest_financial_statement_notes_data_set_url())

    def download_latest_insider_transactions_data_set_zip(self) -> bytes:
        return self._get_bytes(self.latest_insider_transactions_data_set_url())

    def download_latest_form_13f_data_set_zip(self) -> bytes:
        return self._get_bytes(self.latest_form_13f_data_set_url())

    def download_fails_to_deliver_zip(self, url: str) -> bytes:
        self._validate_archive_url(url)
        return self._get_bytes(url)

    def form_nport_data_sets_page_url(self) -> str:
        return f"{self.archives_base_url}/data-research/sec-markets-data/form-n-port-data-sets"

    def list_form_nport_data_set_urls(self) -> list[str]:
        return self._zip_urls_from_page(self.form_nport_data_sets_page_url())

    def latest_form_nport_data_set_url(self) -> str:
        return self.list_form_nport_data_set_urls()[0]

    def download_form_nport_data_set_zip(self, url: str) -> bytes:
        self._validate_archive_url(url)
        return self._get_bytes(url)

    def form_nmfp_data_sets_page_url(self) -> str:
        return f"{self.archives_base_url}/data-research/sec-markets-data/dera-form-n-mfp-data-sets"

    def list_form_nmfp_data_set_urls(self) -> list[str]:
        return self._zip_urls_from_page(self.form_nmfp_data_sets_page_url())

    def latest_form_nmfp_data_set_url(self) -> str:
        return self.list_form_nmfp_data_set_urls()[0]

    def download_form_nmfp_data_set_zip(self, url: str) -> bytes:
        self._validate_archive_url(url)
        return self._get_bytes(url)

    def form_ncen_data_sets_page_url(self) -> str:
        return f"{self.archives_base_url}/data-research/sec-markets-data/form-n-cen-data-sets"

    def list_form_ncen_data_set_urls(self) -> list[str]:
        return self._zip_urls_from_page(self.form_ncen_data_sets_page_url())

    def latest_form_ncen_data_set_url(self) -> str:
        return self.list_form_ncen_data_set_urls()[0]

    def download_form_ncen_data_set_zip(self, url: str) -> bytes:
        self._validate_archive_url(url)
        return self._get_bytes(url)

    def download_archive_if_modified(
        self, url: str, *, last_modified: str | None = None
    ) -> tuple[bytes | None, str | None]:
        """GET an SEC archive; ``(None, last_modified)`` when the server copy is unchanged (HTTP 304)."""
        self._validate_archive_url(url)
        headers = {"If-Modified-Since": last_modified} if last_modified else None
        response = self._client.get(url, headers=headers)
        if response.status_code == 304:
            return None, last_modified
        response.raise_for_status()
        return response.content, response.headers.get("Last-Modified")
