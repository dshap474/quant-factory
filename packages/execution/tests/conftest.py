"""Pytest fixtures for packages/execution tests.

Purpose: expose hermetic instrument, target, and account fixtures.
USAGE: uv run --project packages/execution pytest packages/execution/tests -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from execution import AccountSnapshot, InstrumentKey, InstrumentSpec, PortfolioTarget

# Make sibling helpers importable under pytest --import-mode=importlib.
_TESTS_DIR = Path(__file__).resolve().parent
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))

from helpers import make_account, make_key, make_spec, make_target  # noqa: E402


@pytest.fixture
def btc() -> InstrumentKey:
    return make_key("BTCUSDT")


@pytest.fixture
def eth() -> InstrumentKey:
    return make_key("ETHUSDT")


@pytest.fixture
def btc_spec() -> InstrumentSpec:
    return make_spec("BTCUSDT")


@pytest.fixture
def eth_spec() -> InstrumentSpec:
    return make_spec("ETHUSDT")


@pytest.fixture
def two_asset_target() -> PortfolioTarget:
    return make_target()


@pytest.fixture
def flat_account() -> AccountSnapshot:
    return make_account()
