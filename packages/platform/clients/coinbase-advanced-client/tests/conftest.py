"""Test configuration for the Coinbase Advanced client."""

import sys
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SRC = PACKAGE_ROOT / "src"
if SRC.exists():
    sys.path.insert(0, str(SRC))


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "live: hits the real Coinbase Advanced Trade API (requires config keys; gated by COINBASE_ADVANCED_LIVE=1)",
    )
