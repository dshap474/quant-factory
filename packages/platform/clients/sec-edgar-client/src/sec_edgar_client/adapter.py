"""SEC EDGAR adapter used by data-package callers."""

from __future__ import annotations

import csv
import io
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterator

import polars as pl
from client_common import records_to_frame

from .api import SECEdgarClient


class SECEdgarClientAdapter:
    """Adapter over `sec-edgar-client` with frame helpers."""

    def __init__(
        self, *, timeout: float = 10.0, client=None, user_agent: str = "quant-factory/0.1 contact@example.com"
    ) -> None:
        self.client = SECEdgarClient(timeout=timeout, client=client, user_agent=user_agent)

    def close(self) -> None:
        self.client.close()

    def fetch_submissions(self, cik: str | int) -> dict[str, Any]:
        return self.client.get_submissions(cik)

    def fetch_company_tickers(self) -> dict[str, Any]:
        return self.client.get_company_tickers()

    def fetch_company_tickers_exchange(self) -> dict[str, Any]:
        return self.client.get_company_tickers_exchange()

    def fetch_company_facts(self, cik: str | int) -> dict[str, Any]:
        return self.client.get_company_facts(cik)

    def fetch_company_concept(self, cik: str | int, taxonomy: str, tag: str) -> dict[str, Any]:
        return self.client.get_company_concept(cik, taxonomy, tag)

    def fetch_frames(self, taxonomy: str, tag: str, unit: str, frame: str) -> dict[str, Any]:
        return self.client.get_frames(taxonomy, tag, unit, frame)

    def download_bulk_submissions_zip(self, *, last_modified: str | None = None) -> tuple[bytes | None, str | None]:
        return self.client.download_bulk_submissions_zip(last_modified=last_modified)

    def download_bulk_companyfacts_zip(self, *, last_modified: str | None = None) -> tuple[bytes | None, str | None]:
        return self.client.download_bulk_companyfacts_zip(last_modified=last_modified)

    def download_latest_financial_statement_data_set_zip(self) -> bytes:
        return self.client.download_latest_financial_statement_data_set_zip()

    def list_financial_statement_data_set_urls(self) -> list[str]:
        return self.client.list_financial_statement_data_set_urls()

    def list_form_nport_data_set_urls(self) -> list[str]:
        return self.client.list_form_nport_data_set_urls()

    def download_archive_if_modified(
        self, url: str, *, last_modified: str | None = None
    ) -> tuple[bytes | None, str | None]:
        return self.client.download_archive_if_modified(url, last_modified=last_modified)

    def download_latest_financial_statement_notes_data_set_zip(self) -> bytes:
        return self.client.download_latest_financial_statement_notes_data_set_zip()

    def list_insider_transactions_data_set_urls(self) -> list[str]:
        return self.client.list_insider_transactions_data_set_urls()

    def download_latest_form_13f_data_set_zip(self) -> bytes:
        return self.client.download_latest_form_13f_data_set_zip()

    def list_fails_to_deliver_urls(self) -> list[str]:
        return self.client.list_fails_to_deliver_urls()

    def download_fails_to_deliver_zip(self, url: str) -> bytes:
        return self.client.download_fails_to_deliver_zip(url)

    def bulk_metadata_frame(self) -> pl.DataFrame:
        return records_to_frame(
            [
                {"kind": "submissions", "url": self.client.bulk_submissions_url()},
                {"kind": "companyfacts", "url": self.client.bulk_companyfacts_url()},
            ]
        )

    def company_tickers_to_frame(self, payload: dict[str, Any]) -> pl.DataFrame:
        rows = []
        for row_key, row in payload.items():
            if not isinstance(row, dict):
                continue
            rows.append(
                {
                    "source_row_key": str(row_key),
                    "cik_str": row.get("cik_str"),
                    "ticker": row.get("ticker"),
                    "title": row.get("title"),
                }
            )
        return records_to_frame(rows)

    def company_tickers_exchange_to_frame(self, payload: dict[str, Any]) -> pl.DataFrame:
        fields = payload.get("fields", [])
        rows = []
        for record in payload.get("data", []):
            if not isinstance(record, list):
                continue
            rows.append({str(field): record[idx] if idx < len(record) else None for idx, field in enumerate(fields)})
        return records_to_frame(rows)

    def company_facts_entity_to_frame(
        self,
        payload: dict[str, Any],
        *,
        source_companyfacts_file: str | None = None,
    ) -> pl.DataFrame:
        if not isinstance(payload.get("facts"), dict):
            return pl.DataFrame()
        return self.mixed_records_to_frame(
            [
                {
                    "cik": payload.get("cik"),
                    "entityName": payload.get("entityName"),
                    "source_companyfacts_file": source_companyfacts_file,
                }
            ]
        )

    def company_facts_facts_to_frame(
        self,
        payload: dict[str, Any],
        *,
        source_companyfacts_file: str | None = None,
    ) -> pl.DataFrame:
        facts = payload.get("facts", {})
        if not isinstance(facts, dict):
            return pl.DataFrame()

        rows = []
        for taxonomy, concepts in facts.items():
            if not isinstance(concepts, dict):
                continue
            for tag, concept in concepts.items():
                if not isinstance(concept, dict):
                    continue
                units = concept.get("units", {})
                if not isinstance(units, dict):
                    continue
                for unit, observations in units.items():
                    if not isinstance(observations, list):
                        continue
                    for observation in observations:
                        if not isinstance(observation, dict):
                            continue
                        rows.append(
                            {
                                "cik": payload.get("cik"),
                                "entityName": payload.get("entityName"),
                                "taxonomy": taxonomy,
                                "tag": tag,
                                "label": concept.get("label"),
                                "description": concept.get("description"),
                                "unit": unit,
                                "start": observation.get("start"),
                                "end": observation.get("end"),
                                "val": observation.get("val"),
                                "accn": observation.get("accn"),
                                "fy": observation.get("fy"),
                                "fp": observation.get("fp"),
                                "form": observation.get("form"),
                                "filed": observation.get("filed"),
                                "frame": observation.get("frame"),
                                "source_companyfacts_file": source_companyfacts_file,
                            }
                        )
        return self.mixed_records_to_frame(rows)

    def submissions_entity_to_frame(
        self,
        payload: dict[str, Any],
        *,
        source_submission_file: str | None = None,
    ) -> pl.DataFrame:
        if "filings" not in payload:
            return pl.DataFrame()

        address = payload.get("addresses", {}).get("business", {}) if isinstance(payload.get("addresses"), dict) else {}
        return self.mixed_records_to_frame(
            [
                {
                    "cik": payload.get("cik"),
                    "entityType": payload.get("entityType"),
                    "sic": payload.get("sic"),
                    "sicDescription": payload.get("sicDescription"),
                    "ownerOrg": payload.get("ownerOrg"),
                    "insiderTransactionForOwnerExists": payload.get("insiderTransactionForOwnerExists"),
                    "insiderTransactionForIssuerExists": payload.get("insiderTransactionForIssuerExists"),
                    "name": payload.get("name"),
                    "tickers_json": payload.get("tickers"),
                    "exchanges_json": payload.get("exchanges"),
                    "ein": payload.get("ein"),
                    "description": payload.get("description"),
                    "website": payload.get("website"),
                    "investorWebsite": payload.get("investorWebsite"),
                    "category": payload.get("category"),
                    "fiscalYearEnd": payload.get("fiscalYearEnd"),
                    "stateOfIncorporation": payload.get("stateOfIncorporation"),
                    "stateOfIncorporationDescription": payload.get("stateOfIncorporationDescription"),
                    "phone": address.get("phone"),
                    "source_submission_file": source_submission_file,
                }
            ]
        )

    def submissions_former_names_to_frame(
        self,
        payload: dict[str, Any],
        *,
        source_submission_file: str | None = None,
    ) -> pl.DataFrame:
        if "filings" not in payload:
            return pl.DataFrame()
        rows = []
        for entry in payload.get("formerNames", []) or []:
            if not isinstance(entry, dict):
                continue
            rows.append(
                {
                    "cik": payload.get("cik"),
                    "name": entry.get("name"),
                    "from_date": entry.get("from"),
                    "to_date": entry.get("to"),
                    "source_submission_file": source_submission_file,
                }
            )
        return self.mixed_records_to_frame(rows)

    def submissions_recent_to_frame(
        self,
        payload: dict[str, Any],
        *,
        cik: str | None = None,
        source_submission_file: str | None = None,
    ) -> pl.DataFrame:
        filings = payload.get("filings", {}).get("recent", {}) if "filings" in payload else payload
        if not filings:
            return pl.DataFrame()
        rows = self._rows_from_parallel_arrays(filings)
        derived_cik = cik or payload.get("cik") or self._extract_cik_from_filename(source_submission_file)
        for row in rows:
            row["cik"] = derived_cik
            row["source_submission_file"] = source_submission_file
        return self.mixed_records_to_frame(rows)

    def submissions_files_to_frame(
        self,
        payload: dict[str, Any],
        *,
        cik: str | None = None,
        source_submission_file: str | None = None,
    ) -> pl.DataFrame:
        if "filings" not in payload:
            return pl.DataFrame()
        rows = []
        derived_cik = cik or payload.get("cik") or self._extract_cik_from_filename(source_submission_file)
        for entry in payload.get("filings", {}).get("files", []) or []:
            if not isinstance(entry, dict):
                continue
            rows.append(
                {
                    "cik": derived_cik,
                    "name": entry.get("name"),
                    "filingCount": entry.get("filingCount"),
                    "filingFrom": entry.get("filingFrom"),
                    "filingTo": entry.get("filingTo"),
                    "source_submission_file": source_submission_file,
                }
            )
        return self.mixed_records_to_frame(rows)

    def mixed_records_to_frame(self, records: list[dict[str, Any]]) -> pl.DataFrame:
        return _mixed_payload_records_to_frame(records)

    def company_concept_to_frame(self, payload: dict[str, Any]) -> pl.DataFrame:
        units = payload.get("units", {})
        rows: list[dict[str, Any]] = []
        for unit, observations in units.items():
            for observation in observations:
                row = dict(observation)
                row["unit"] = unit
                rows.append(row)
        return records_to_frame(rows)

    def delimited_text_to_frame(self, text: str, *, separator: str = "\t") -> pl.DataFrame:
        _ensure_csv_field_limit()
        rows = list(csv.DictReader(io.StringIO(text), delimiter=separator))
        if not rows:
            return pl.DataFrame()
        normalized = [
            {str(key).strip().lower(): value for key, value in row.items() if key is not None} for row in rows
        ]
        return records_to_frame(normalized)

    def iter_delimited_rows(self, handle, *, separator: str = "\t") -> Iterator[dict[str, Any]]:
        _ensure_csv_field_limit()
        text_handle = io.TextIOWrapper(handle, encoding="utf-8-sig", newline="")
        reader = csv.DictReader(text_handle, delimiter=separator)
        try:
            for row in reader:
                yield {str(key).strip().lower(): value for key, value in row.items() if key is not None}
        finally:
            text_handle.detach()

    def save_bulk_zip(self, destination: Path, *, kind: str) -> Path:
        data, _ = self.download_bulk_companyfacts_zip() if kind == "companyfacts" else self.download_bulk_submissions_zip()
        destination.write_bytes(data)
        return destination

    @staticmethod
    def _rows_from_parallel_arrays(mapping: dict[str, Any]) -> list[dict[str, Any]]:
        keys = list(mapping.keys())
        if not keys:
            return []
        rows = []
        row_count = max(len(mapping.get(key, [])) for key in keys)
        for idx in range(row_count):
            row = {}
            for key in keys:
                values = mapping.get(key, [])
                row[key] = values[idx] if idx < len(values) else None
            rows.append(row)
        return rows

    @staticmethod
    def _extract_cik_from_filename(source_submission_file: str | None) -> str | None:
        if not source_submission_file:
            return None
        match = re.search(r"CIK(\d{10})", source_submission_file)
        if not match:
            return None
        return match.group(1)


def _stringify_record(record: dict[str, Any]) -> dict[str, str | None]:
    return {key: _stringify_scalar(value) for key, value in record.items()}


def _stringify_scalar(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True)
    return str(value)


def _mixed_payload_records_to_frame(records: list[dict[str, Any]]) -> pl.DataFrame:
    if not records:
        return pl.DataFrame()
    rows = [_stringify_record(record) for record in records]
    columns = sorted({key for row in rows for key in row})
    schema = {column: pl.String for column in columns}
    return pl.from_dicts(rows, schema=schema)


def _ensure_csv_field_limit() -> None:
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit //= 10
