"""Hermetic contract tests for the official-SDK Hyperliquid facade.

Purpose: prove lazy read-only use, activation-bound signer identity, narrow
method exposure, exact placement gating, and SDK fixed-point wire conversion.

USAGE: uv run --project packages/platform/clients/hyperliquid-client pytest tests -q
"""

from __future__ import annotations

from importlib.metadata import version
from pathlib import Path

import pytest
from eth_account import Account
from hyperliquid.utils.signing import order_request_to_order_wire
from hyperliquid.utils.types import Cloid
from hyperliquid_client import (
    HyperliquidClient,
    HyperliquidClientConfig,
    HyperliquidConfigurationError,
    HyperliquidTradingDisabledError,
)

# --------------------------------------------------------------------------- #
# Constants and fakes
# --------------------------------------------------------------------------- #

ACCOUNT = "0x1111111111111111111111111111111111111111"
SUBACCOUNT = "0x2222222222222222222222222222222222222222"
TEST_PRIVATE_KEY = "0x" + "11" * 32
AGENT = Account.from_key(TEST_PRIVATE_KEY).address.lower()
CLOID_TEXT = "0x" + "a" * 32


class FakeInfo:
    """Record explicit read-only calls without making a provider request."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    def _call(self, name: str, *args: object, **kwargs: object) -> dict[str, object]:
        self.calls.append((name, args, kwargs))
        return {"method": name}

    def meta_and_asset_ctxs(self) -> dict[str, object]:
        return self._call("meta_and_asset_ctxs")

    def user_state(self, address: str) -> dict[str, object]:
        return self._call("user_state", address)

    def frontend_open_orders(self, address: str) -> dict[str, object]:
        return self._call("frontend_open_orders", address)

    def l2_snapshot(self, coin: str) -> dict[str, object]:
        return self._call("l2_snapshot", coin)

    def post(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        return self._call("post", path, payload)

    def query_user_abstraction_state(self, address: str) -> dict[str, object]:
        return self._call("query_user_abstraction_state", address)

    def user_role(self, address: str) -> dict[str, object]:
        return self._call("user_role", address)

    def query_order_by_cloid(self, address: str, cloid: Cloid) -> dict[str, object]:
        return self._call("query_order_by_cloid", address, cloid.to_raw())

    def user_fills_by_time(self, *args: object, **kwargs: object) -> dict[str, object]:
        return self._call("user_fills_by_time", *args, **kwargs)

    def user_funding_history(self, *args: object) -> dict[str, object]:
        return self._call("user_funding_history", *args)


class FakeExchange:
    """Capture the final official-SDK method boundary only."""

    def __init__(self) -> None:
        self.orders: list[tuple[tuple[object, ...], dict[str, object]]] = []
        self.cancels: list[tuple[str, str]] = []

    def order(self, *args: object, **kwargs: object) -> dict[str, object]:
        self.orders.append((args, kwargs))
        return {"status": "ok"}

    def cancel_by_cloid(self, coin: str, cloid: Cloid) -> dict[str, object]:
        self.cancels.append((coin, cloid.to_raw()))
        return {"status": "ok"}


def _live_client(*, exchange: FakeExchange | None = None) -> HyperliquidClient:
    return HyperliquidClient(
        HyperliquidClientConfig(
            network="testnet",
            account_address=ACCOUNT,
            subaccount_address=SUBACCOUNT,
            expected_agent_address=AGENT,
        ),
        agent_private_key=TEST_PRIVATE_KEY,
        _exchange=exchange,
    )


# --------------------------------------------------------------------------- #
# Configuration and read boundary
# --------------------------------------------------------------------------- #


def test_exact_official_sdk_version_is_pinned() -> None:
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    assert '"hyperliquid-python-sdk==0.24.0"' in pyproject.read_text(encoding="utf-8")
    assert version("hyperliquid-python-sdk") == "0.24.0"


def test_read_only_construction_needs_no_private_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HYPERLIQUID_AGENT_PRIVATE_KEY", raising=False)
    info = FakeInfo()
    client = HyperliquidClient(
        HyperliquidClientConfig(network="testnet", account_address=ACCOUNT),
        _info=info,
    )
    assert client.agent_address is None
    assert client.clearinghouse_state(ACCOUNT) == {"method": "user_state"}
    assert info.calls == [("user_state", (ACCOUNT,), {})]


def test_all_read_methods_route_to_explicit_sdk_info_calls() -> None:
    info = FakeInfo()
    client = HyperliquidClient(
        HyperliquidClientConfig(network="mainnet", account_address=ACCOUNT),
        _info=info,
    )
    client.meta_and_asset_contexts()
    client.frontend_open_orders(ACCOUNT)
    client.l2_book("BTC")
    client.active_asset_data(ACCOUNT, "BTC")
    client.user_abstraction(ACCOUNT)
    client.user_role(AGENT)
    client.order_status(ACCOUNT, CLOID_TEXT)
    client.user_fills_by_time(ACCOUNT, 1, 2)
    client.user_funding(ACCOUNT, 1, 2)
    assert [name for name, _, _ in info.calls] == [
        "meta_and_asset_ctxs",
        "frontend_open_orders",
        "l2_snapshot",
        "post",
        "query_user_abstraction_state",
        "user_role",
        "query_order_by_cloid",
        "user_fills_by_time",
        "user_funding_history",
    ]
    assert info.calls[3][1] == (
        "/info",
        {"type": "activeAssetData", "user": ACCOUNT, "coin": "BTC"},
    )


def test_private_key_resolves_only_for_expected_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HYPERLIQUID_AGENT_PRIVATE_KEY", TEST_PRIVATE_KEY)
    client = HyperliquidClient(
        HyperliquidClientConfig(
            network="testnet",
            account_address=ACCOUNT,
            expected_agent_address=AGENT,
        )
    )
    assert client.agent_address == AGENT
    with pytest.raises(HyperliquidConfigurationError, match="does not match"):
        HyperliquidClient(
            HyperliquidClientConfig(
                network="testnet",
                account_address=ACCOUNT,
                expected_agent_address=ACCOUNT,
            )
        )


def test_private_key_never_appears_in_repr_or_error() -> None:
    client = _live_client(exchange=FakeExchange())
    assert TEST_PRIVATE_KEY not in repr(client)
    with pytest.raises(HyperliquidConfigurationError) as captured:
        HyperliquidClient(
            HyperliquidClientConfig(
                network="testnet",
                account_address=ACCOUNT,
                expected_agent_address=AGENT,
            ),
            agent_private_key="not-a-key",
        )
    assert TEST_PRIVATE_KEY not in str(captured.value)
    assert "not-a-key" not in str(captured.value)
    assert captured.value.__cause__ is None


# --------------------------------------------------------------------------- #
# Mutation boundary and official wire
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("gate", [None, "", "true", "0"])
def test_placement_requires_exact_gate(monkeypatch: pytest.MonkeyPatch, gate: str | None) -> None:
    exchange = FakeExchange()
    client = _live_client(exchange=exchange)
    if gate is None:
        monkeypatch.delenv("HYPERLIQUID_TRADING_ENABLED", raising=False)
    else:
        monkeypatch.setenv("HYPERLIQUID_TRADING_ENABLED", gate)
    with pytest.raises(HyperliquidTradingDisabledError):
        client.place_limit_ioc(
            coin="BTC",
            is_buy=True,
            size="0.00123",
            limit_price="123456",
            reduce_only=False,
            cloid=CLOID_TEXT,
        )
    assert exchange.orders == []


def test_placement_uses_only_explicit_ioc(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HYPERLIQUID_TRADING_ENABLED", "1")
    exchange = FakeExchange()
    client = _live_client(exchange=exchange)
    assert client.place_limit_ioc(
        coin="BTC",
        is_buy=True,
        size="0.00123",
        limit_price="123456",
        reduce_only=False,
        cloid=CLOID_TEXT,
    ) == {"status": "ok"}
    args, kwargs = exchange.orders[0]
    assert args[:5] == ("BTC", True, 0.00123, 123456.0, {"limit": {"tif": "Ioc"}})
    assert kwargs["reduce_only"] is False
    assert isinstance(kwargs["cloid"], Cloid)


def test_official_sdk_wire_preserves_fixed_point_fixture() -> None:
    """Differential oracle through the reviewed SDK's production wire converter."""
    wire = order_request_to_order_wire(
        {
            "coin": "BTC",
            "is_buy": True,
            "sz": 0.00123,
            "limit_px": 123456.0,
            "order_type": {"limit": {"tif": "Ioc"}},
            "reduce_only": False,
            "cloid": Cloid.from_str(CLOID_TEXT),
        },
        0,
    )
    assert wire == {
        "a": 0,
        "b": True,
        "p": "123456",
        "s": "0.00123",
        "r": False,
        "t": {"limit": {"tif": "Ioc"}},
        "c": CLOID_TEXT,
    }


def test_cancel_is_risk_reducing_and_not_placement_gated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HYPERLIQUID_TRADING_ENABLED", raising=False)
    exchange = FakeExchange()
    client = _live_client(exchange=exchange)
    assert client.cancel_by_cloid(coin="BTC", cloid=CLOID_TEXT) == {"status": "ok"}
    assert exchange.cancels == [("BTC", CLOID_TEXT)]


def test_dangerous_sdk_capabilities_are_not_public() -> None:
    client = _live_client(exchange=FakeExchange())
    for name in (
        "exchange",
        "transfer",
        "withdraw",
        "approve_agent",
        "update_leverage",
        "update_isolated_margin",
        "create_sub_account",
        "market_open",
        "market_close",
        "post",
    ):
        assert not hasattr(client, name)
