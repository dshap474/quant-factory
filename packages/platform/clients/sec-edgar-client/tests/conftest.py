"""Test configuration for the SEC EDGAR client: registers the ``live`` marker.

USAGE:
    uv run pytest packages/platform/clients/sec-edgar-client -q
    SEC_LIVE=1 SEC_USER_AGENT="name email@example.com" uv run pytest packages/platform/clients/sec-edgar-client -m live -q
"""

import pytest


# --------------------------------------------------------------------------- #
# Markers
# --------------------------------------------------------------------------- #
def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "live: hits the real SEC site (gated by SEC_LIVE=1)")
