"""Live smoke for SEC DERA fund data set pages (lists URLs only; never downloads zips).

USAGE:
    SEC_LIVE=1 SEC_USER_AGENT="name email@example.com" \
        uv run pytest packages/platform/clients/sec-edgar-client -m live -q
"""

from __future__ import annotations

import os

import pytest
from sec_edgar_client import SECEdgarClient

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(os.environ.get("SEC_LIVE") != "1", reason="set SEC_LIVE=1 to hit sec.gov"),
    pytest.mark.skipif(not os.environ.get("SEC_USER_AGENT"), reason="SEC requires a contact SEC_USER_AGENT"),
]

USER_AGENT = os.environ.get("SEC_USER_AGENT", "")


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(("kind", "suffix"), [("nport", "_nport.zip"), ("nmfp", "_nmfp.zip"), ("ncen", "_ncen.zip")])
def test_fund_data_set_pages_list_zip_urls(kind: str, suffix: str) -> None:
    with SECEdgarClient(user_agent=USER_AGENT, timeout=30.0) as sec_client:
        urls = getattr(sec_client, f"list_form_{kind}_data_set_urls")()
    assert urls, kind
    assert urls[0].startswith("https://www.sec.gov/files/dera/data/")
    assert urls[0].endswith(suffix)
