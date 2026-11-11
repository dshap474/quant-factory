"""Opt-in live smoke test for the SECEdgarClientAdapter (gated by RUN_SEC_EDGAR_LIVE).

USAGE:
    RUN_SEC_EDGAR_LIVE=1 uv run pytest packages/platform/clients/sec-edgar-client/tests/test_adapter_live_smoke.py -q
"""

from __future__ import annotations

import os

import pytest
from sec_edgar_client import SECEdgarClientAdapter

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _present_env(name: str) -> bool:
    value = os.getenv(name)
    return bool(value and value.strip())


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


@pytest.mark.skipif(not _present_env("RUN_SEC_EDGAR_LIVE"), reason="RUN_SEC_EDGAR_LIVE not set")
def test_live_sec_smoke():
    adapter = SECEdgarClientAdapter()
    payload = adapter.fetch_submissions("320193")
    assert payload["cik"]
