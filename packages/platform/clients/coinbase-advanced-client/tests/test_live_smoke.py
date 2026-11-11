"""Live smoke tests against Coinbase Advanced Trade (read-only).

Opt-in: skipped unless ``COINBASE_ADVANCED_LIVE=1`` is set. Credentials then
resolve from the paired environment names.

    COINBASE_ADVANCED_LIVE=1 \\
        uv run --project packages/platform/clients/coinbase-advanced-client \\
            pytest packages/platform/clients/coinbase-advanced-client/tests -m live -q

Never places orders. ``create_order`` is only exercised to prove the trading
gate refuses placement when unset.
"""

from __future__ import annotations

import os
from typing import Any

import pytest
from coinbase_advanced_client import (
    CoinbaseAdvanced,
    CoinbaseAdvancedTradingDisabledError,
)

pytestmark = pytest.mark.live

_RUN_LIVE = os.getenv("COINBASE_ADVANCED_LIVE") == "1"
skip_unless_live = pytest.mark.skipif(
    not _RUN_LIVE,
    reason="set COINBASE_ADVANCED_LIVE=1 to run live Coinbase smoke tests",
)


def _field(obj: Any, name: str) -> Any:
    """Read a response field from a typed SDK object or plain mapping."""
    value = getattr(obj, name, None)
    if value is not None:
        return value
    if isinstance(obj, dict):
        return obj.get(name)
    return None


@skip_unless_live
def test_get_accounts() -> None:
    client = CoinbaseAdvanced()
    response = client.get_accounts()
    accounts = _field(response, "accounts")
    assert accounts is not None
    assert isinstance(accounts, list)


@skip_unless_live
def test_get_product_btc_usdc() -> None:
    client = CoinbaseAdvanced()
    product = client.get_product("BTC-USDC", get_tradability_status=True)
    assert _field(product, "product_id") == "BTC-USDC"
    assert _field(product, "price") is not None


@skip_unless_live
def test_get_best_bid_ask() -> None:
    client = CoinbaseAdvanced()
    response = client.get_best_bid_ask(product_ids=["BTC-USDC"])
    pricebooks = _field(response, "pricebooks")
    assert pricebooks is not None
    assert len(pricebooks) >= 1


@skip_unless_live
def test_get_transaction_summary() -> None:
    client = CoinbaseAdvanced()
    response = client.get_transaction_summary()
    # Fee tier / summary fields must be present on a live authenticated response.
    assert _field(response, "fee_tier") is not None


@skip_unless_live
def test_create_order_raises_when_trading_gate_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prove placement is blocked with the gate off — ZERO orders placed."""
    monkeypatch.setattr(
        "coinbase_advanced_client.api.COINBASE_ADVANCED_TRADING_ENABLED",
        "",
    )
    client = CoinbaseAdvanced()
    with pytest.raises(CoinbaseAdvancedTradingDisabledError):
        client.create_order(
            client_order_id="qf.live-smoke.gate.a0",
            product_id="BTC-USDC",
            side="BUY",
            order_configuration={"market_market_ioc": {"base_size": "0.0001"}},
        )
