"""Unit tests for the SECEdgarClientAdapter.

USAGE:
    uv run pytest packages/platform/clients/sec-edgar-client/tests -q
"""

from __future__ import annotations

import io
import json
from pathlib import Path

from sec_edgar_client import SECEdgarClientAdapter

# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


FIXTURE_ROOT = Path(__file__).parent / "fixtures"


def _load_json(name: str):
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


def test_sec_submissions_and_bulk_metadata_to_frame():
    adapter = SECEdgarClientAdapter()
    recent = adapter.submissions_recent_to_frame(_load_json("sec_submissions.json"))
    bulk = adapter.bulk_metadata_frame()
    assert recent.shape == (1, 5)
    assert recent["form"].to_list() == ["10-Q"]
    assert recent["cik"].to_list() == ["0000320193"]
    assert set(bulk["kind"].to_list()) == {"submissions", "companyfacts"}


def test_sec_identity_and_submission_file_frames():
    adapter = SECEdgarClientAdapter()

    tickers = adapter.company_tickers_to_frame(_load_json("sec_company_tickers.json"))
    exchanges = adapter.company_tickers_exchange_to_frame(_load_json("sec_company_tickers_exchange.json"))
    submission = _load_json("sec_submissions_full.json")

    entity = adapter.submissions_entity_to_frame(submission, source_submission_file="CIK0000320193.json")
    former = adapter.submissions_former_names_to_frame(submission, source_submission_file="CIK0000320193.json")
    recent = adapter.submissions_recent_to_frame(
        submission,
        source_submission_file="CIK0000320193.json",
    )
    files = adapter.submissions_files_to_frame(
        submission,
        source_submission_file="CIK0000320193.json",
    )
    additional = adapter.submissions_recent_to_frame(
        {
            "accessionNumber": ["0000320193-15-000001"],
            "filingDate": ["2015-01-28"],
            "form": ["8-K"],
        },
        source_submission_file="CIK0000320193-submissions-001.json",
    )

    assert tickers.shape == (2, 4)
    assert exchanges.shape == (2, 4)
    assert entity["cik"].to_list() == ["0000320193"]
    assert former["name"].to_list() == ["APPLE COMPUTER INC"]
    assert recent["cik"].to_list() == ["0000320193"]
    assert files["name"].to_list() == ["CIK0000320193-submissions-001.json"]
    assert additional["cik"].to_list() == ["0000320193"]


def test_sec_submissions_recent_to_frame_handles_mixed_scalar_types():
    adapter = SECEdgarClientAdapter()
    frame = adapter.submissions_recent_to_frame(
        _load_json("sec_submissions_recent_mixed.json"),
        cik="0000000000",
        source_submission_file="CIK0000000000.json",
    )

    assert frame.shape == (2, 6)
    assert frame["size"].to_list() == ["", "0"]
    assert frame["isXBRL"].to_list() == ["0", "1"]
    assert frame["cik"].to_list() == ["0000000000", "0000000000"]


def test_sec_mixed_records_to_frame_stringifies_nested_payloads():
    adapter = SECEdgarClientAdapter()
    frame = adapter.mixed_records_to_frame([{"cik": 320193, "meta": {"source": "sec"}, "tickers": ["AAPL", "APPL34"]}])

    assert frame["cik"].to_list() == ["320193"]
    assert frame["meta"].to_list() == ['{"source": "sec"}']
    assert frame["tickers"].to_list() == ['["AAPL", "APPL34"]']


def test_sec_companyfacts_frames():
    adapter = SECEdgarClientAdapter()
    payload = _load_json("sec_companyfacts.json")

    entity = adapter.company_facts_entity_to_frame(
        payload,
        source_companyfacts_file="CIK0000320193.json",
    )
    facts = adapter.company_facts_facts_to_frame(
        payload,
        source_companyfacts_file="CIK0000320193.json",
    )

    assert entity["cik"].to_list() == ["0000320193"]
    assert entity["entityName"].to_list() == ["Apple Inc."]
    assert set(facts["unit"].to_list()) == {"USD", "shares", "string"}
    assert "CY2024Q1I" in facts["frame"].drop_nulls().to_list()
    assert "0000320193-24-000069" in facts["accn"].drop_nulls().to_list()
    assert "Apple Inc." in facts["val"].to_list()
    assert any(value not in {None, "Apple Inc."} for value in facts["val"].to_list())


def test_sec_delimited_text_to_frame():
    adapter = SECEdgarClientAdapter()
    frame = adapter.delimited_text_to_frame("ADSH\tCIK\tNAME\n000032019324000069\t320193\tApple Inc.\n")
    assert frame.shape == (1, 3)
    assert frame.columns == ["adsh", "cik", "name"]
    assert frame["name"].to_list() == ["Apple Inc."]


def test_sec_iter_delimited_rows_allows_large_text_fields():
    adapter = SECEdgarClientAdapter()
    long_text = "x" * 200000
    rows = list(adapter.iter_delimited_rows(io.BytesIO(f"adsh\ttxt\n1\t{long_text}\n".encode("utf-8"))))
    assert rows == [{"adsh": "1", "txt": long_text}]
