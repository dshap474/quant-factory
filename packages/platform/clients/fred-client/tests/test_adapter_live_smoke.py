"""Opt-in live smoke test for the FREDClientAdapter (gated by RUN_FRED_LIVE).

USAGE:
    RUN_FRED_LIVE=1 uv run pytest packages/platform/clients/fred-client/tests/test_adapter_live_smoke.py -q
"""

from __future__ import annotations

import os

import pytest
from fred_client import FREDClientAdapter

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _present_env(name: str) -> bool:
    value = os.getenv(name)
    return bool(value and value.strip())


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


@pytest.mark.skipif(not _present_env("RUN_FRED_LIVE"), reason="RUN_FRED_LIVE not set")
def test_live_fred_smoke():
    adapter = FREDClientAdapter()
    payload = adapter.fetch_series_observations("FEDFUNDS", limit=1)
    assert payload["observations"]
