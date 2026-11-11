"""Hermetic unit tests for the CoinbaseAdvanced facade (no network)."""

from __future__ import annotations

from typing import Any

import coinbase_advanced_client
import pytest
from coinbase_advanced_client import (
    CoinbaseAdvanced,
    CoinbaseAdvancedConfigurationError,
    CoinbaseAdvancedTradingDisabledError,
)

# --------------------------------------------------------------------------- #
# Construction / config
# --------------------------------------------------------------------------- #


def test_omitted_credentials_read_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class StubRESTClient:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

    monkeypatch.setenv("COINBASE_ADVANCED_API_KEY_NAME", "fake-key-name")
    monkeypatch.setenv("COINBASE_ADVANCED_PRIVATE_KEY", "fake-private-key")
    monkeypatch.setattr("coinbase_advanced_client.api.RESTClient", StubRESTClient)
    CoinbaseAdvanced()

    assert captured["api_key"] == "fake-key-name"
    assert captured["api_secret"] == "fake-private-key"


def test_json_quoted_environment_private_key_is_normalized(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class StubRESTClient:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

    monkeypatch.setenv("COINBASE_ADVANCED_API_KEY_NAME", "fake-key-name")
    monkeypatch.setenv("COINBASE_ADVANCED_PRIVATE_KEY", '"-----BEGIN KEY-----\\nTEST\\n-----END KEY-----\\n"')
    monkeypatch.setattr("coinbase_advanced_client.api.RESTClient", StubRESTClient)
    CoinbaseAdvanced()

    assert captured["api_secret"] == "-----BEGIN KEY-----\nTEST\n-----END KEY-----\n"


def test_partial_explicit_pair_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COINBASE_ADVANCED_API_KEY_NAME", raising=False)
    monkeypatch.delenv("COINBASE_ADVANCED_PRIVATE_KEY", raising=False)
    with pytest.raises(CoinbaseAdvancedConfigurationError, match="incomplete"):
        CoinbaseAdvanced(api_key_name="org/key")


def test_missing_environment_pair_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COINBASE_ADVANCED_API_KEY_NAME", raising=False)
    monkeypatch.delenv("COINBASE_ADVANCED_PRIVATE_KEY", raising=False)

    with pytest.raises(CoinbaseAdvancedConfigurationError, match="set them in the environment"):
        CoinbaseAdvanced()


def test_explicit_creds_construct_rest_client(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class StubRESTClient:
        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

    monkeypatch.setattr("coinbase_advanced_client.api.RESTClient", StubRESTClient)
    client = CoinbaseAdvanced(
        api_key_name="organizations/org/apiKeys/key",
        private_key="-----BEGIN EC PRIVATE KEY-----\nTEST\n-----END EC PRIVATE KEY-----\n",  # gitleaks:allow (fake key)
        timeout=12,
    )
    assert captured["api_key"] == "organizations/org/apiKeys/key"
    assert captured["api_secret"].startswith("-----BEGIN EC PRIVATE KEY-----")
    assert captured["timeout"] == 12
    assert captured["rate_limit_headers"] is True
    assert not hasattr(client, "rest")  # no public escape hatch to the raw SDK


def test_non_secret_runtime_settings_are_exposed(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _stub = _client_with_stub(monkeypatch)
    monkeypatch.setattr("coinbase_advanced_client.api.COINBASE_ADVANCED_PORTFOLIO_UUID", "portfolio-uuid")
    monkeypatch.setattr("coinbase_advanced_client.api.COINBASE_ADVANCED_TRADING_ENABLED", "1")

    assert client.configured_portfolio_uuid == "portfolio-uuid"
    assert client.trading_gate_enabled is True


# --------------------------------------------------------------------------- #
# Stub rest helpers
# --------------------------------------------------------------------------- #


class _StubRest:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def preview_order(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("preview_order", kwargs))
        return {"order_total": "10", "errs": []}

    def create_order(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("create_order", kwargs))
        return {"success": True, "order_id": "ord-1"}

    def cancel_orders(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("cancel_orders", kwargs))
        return {"results": [{"success": True, "order_id": kwargs["order_ids"][0]}]}

    def get_product(self, product_id: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("get_product", {"product_id": product_id, **kwargs}))
        return {"product_id": product_id}

    def get_products(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("get_products", kwargs))
        return {"products": [], "pagination": {"has_next": False}}

    def get_best_bid_ask(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("get_best_bid_ask", kwargs))
        return {"pricebooks": []}

    def get_transaction_summary(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("get_transaction_summary", kwargs))
        return {"fee_tier": {"pricing_tier": "Advanced 1"}}

    def get_order(self, order_id: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("get_order", {"order_id": order_id, **kwargs}))
        return {"order": {"order_id": order_id}}

    def list_orders(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("list_orders", kwargs))
        return {"orders": [], "cursor": kwargs.get("cursor")}

    def get_fills(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("get_fills", kwargs))
        return {"fills": [], "cursor": kwargs.get("cursor")}

    def get_portfolios(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("get_portfolios", kwargs))
        return {"portfolios": []}

    def get_accounts(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("get_accounts", kwargs))
        return {"accounts": []}

    def get_api_key_permissions(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("get_api_key_permissions", kwargs))
        return {"can_view": True, "can_trade": True, "portfolio_uuid": "p-1"}


def _client_with_stub(monkeypatch: pytest.MonkeyPatch) -> tuple[CoinbaseAdvanced, _StubRest]:
    stub = _StubRest()

    class StubRESTClient:
        def __init__(self, **kwargs: Any) -> None:
            pass

    monkeypatch.setattr("coinbase_advanced_client.api.RESTClient", StubRESTClient)
    client = CoinbaseAdvanced(api_key_name="k", private_key="s")
    client._rest = stub  # type: ignore[method-assign]
    return client, stub


# --------------------------------------------------------------------------- #
# preview_order passthrough
# --------------------------------------------------------------------------- #


def test_preview_order_forwards_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    client, stub = _client_with_stub(monkeypatch)
    cfg = {"market_market_ioc": {"base_size": "0.0001"}}
    result = client.preview_order(product_id="BTC-USD", side="BUY", order_configuration=cfg)
    assert result["errs"] == []
    assert stub.calls[0][0] == "preview_order"
    call = stub.calls[0][1]
    assert call["product_id"] == "BTC-USD"
    assert call["side"] == "BUY"
    assert call["order_configuration"] == cfg


def test_preview_order_rejects_empty_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _stub = _client_with_stub(monkeypatch)
    with pytest.raises(ValueError, match="order_configuration"):
        client.preview_order(product_id="BTC-USD", side="BUY", order_configuration={})


# --------------------------------------------------------------------------- #
# create_order gate / client_order_id / USDC
# --------------------------------------------------------------------------- #


def test_create_order_refuses_when_gate_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    client, stub = _client_with_stub(monkeypatch)
    monkeypatch.setattr("coinbase_advanced_client.api.COINBASE_ADVANCED_TRADING_ENABLED", "")
    with pytest.raises(CoinbaseAdvancedTradingDisabledError):
        client.create_order(
            client_order_id="qf.run.t.s.a0",
            product_id="BTC-USDC",
            side="BUY",
            order_configuration={"market_market_ioc": {"base_size": "0.001"}},
        )
    assert stub.calls == []


def test_create_order_refuses_when_gate_not_one(monkeypatch: pytest.MonkeyPatch) -> None:
    client, stub = _client_with_stub(monkeypatch)
    monkeypatch.setattr("coinbase_advanced_client.api.COINBASE_ADVANCED_TRADING_ENABLED", "true")
    with pytest.raises(CoinbaseAdvancedTradingDisabledError):
        client.create_order(
            client_order_id="qf.run.t.s.a0",
            product_id="BTC-USDC",
            side="BUY",
            order_configuration={"market_market_ioc": {"base_size": "0.001"}},
        )
    assert stub.calls == []


def test_create_order_passthrough_when_gate_open(monkeypatch: pytest.MonkeyPatch) -> None:
    client, stub = _client_with_stub(monkeypatch)
    monkeypatch.setattr("coinbase_advanced_client.api.COINBASE_ADVANCED_TRADING_ENABLED", "1")
    cfg = {"sor_limit_ioc": {"base_size": "0.001", "limit_price": "100"}}
    result = client.create_order(
        client_order_id="qf.run.t.s.a0",
        product_id="BTC-USDC",
        side="BUY",
        order_configuration=cfg,
        retail_portfolio_id="portfolio-uuid",
    )
    assert result["success"] is True
    assert len(stub.calls) == 1
    name, kwargs = stub.calls[0]
    assert name == "create_order"
    assert kwargs["client_order_id"] == "qf.run.t.s.a0"
    assert kwargs["product_id"] == "BTC-USDC"
    assert kwargs["side"] == "BUY"
    assert kwargs["order_configuration"] == cfg
    assert kwargs["retail_portfolio_id"] == "portfolio-uuid"


def test_create_order_rejects_empty_client_order_id(monkeypatch: pytest.MonkeyPatch) -> None:
    client, stub = _client_with_stub(monkeypatch)
    monkeypatch.setattr("coinbase_advanced_client.api.COINBASE_ADVANCED_TRADING_ENABLED", "1")
    with pytest.raises(ValueError, match="client_order_id"):
        client.create_order(
            client_order_id="",
            product_id="BTC-USDC",
            side="BUY",
            order_configuration={"market_market_ioc": {"base_size": "0.001"}},
        )
    assert stub.calls == []


def test_create_order_rejects_non_usdc_product(monkeypatch: pytest.MonkeyPatch) -> None:
    client, stub = _client_with_stub(monkeypatch)
    monkeypatch.setattr("coinbase_advanced_client.api.COINBASE_ADVANCED_TRADING_ENABLED", "1")
    with pytest.raises(ValueError, match="USDC"):
        client.create_order(
            client_order_id="qf.run.t.s.a0",
            product_id="BTC-USD",
            side="BUY",
            order_configuration={"market_market_ioc": {"base_size": "0.001"}},
        )
    assert stub.calls == []


def test_create_order_gate_checked_before_client_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Gate is the first statement — empty client id never reaches validation when gated off."""
    client, stub = _client_with_stub(monkeypatch)
    monkeypatch.setattr("coinbase_advanced_client.api.COINBASE_ADVANCED_TRADING_ENABLED", "")
    with pytest.raises(CoinbaseAdvancedTradingDisabledError):
        client.create_order(
            client_order_id="",
            product_id="BTC-USD",
            side="BUY",
            order_configuration={},
        )
    assert stub.calls == []


# --------------------------------------------------------------------------- #
# cancel_orders ungated
# --------------------------------------------------------------------------- #


def test_cancel_orders_passthrough_when_gate_off(monkeypatch: pytest.MonkeyPatch) -> None:
    client, stub = _client_with_stub(monkeypatch)
    monkeypatch.setattr("coinbase_advanced_client.api.COINBASE_ADVANCED_TRADING_ENABLED", "")
    result = client.cancel_orders(order_ids=["ord-1", "ord-2"])
    assert result["results"][0]["success"] is True
    assert stub.calls[0][0] == "cancel_orders"
    assert stub.calls[0][1]["order_ids"] == ["ord-1", "ord-2"]


def test_cancel_orders_rejects_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _stub = _client_with_stub(monkeypatch)
    with pytest.raises(ValueError, match="order_ids"):
        client.cancel_orders(order_ids=[])


# --------------------------------------------------------------------------- #
# Read passthroughs
# --------------------------------------------------------------------------- #


def test_get_product_forwards_tradability_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    client, stub = _client_with_stub(monkeypatch)
    client.get_product("BTC-USDC", get_tradability_status=True)
    name, kwargs = stub.calls[0]
    assert name == "get_product"
    assert kwargs["product_id"] == "BTC-USDC"
    assert kwargs["get_tradability_status"] is True


def test_get_products_forwards_catalog_filters(monkeypatch: pytest.MonkeyPatch) -> None:
    client, stub = _client_with_stub(monkeypatch)
    client.get_products(
        limit=100,
        cursor="page-2",
        product_type="SPOT",
        get_tradability_status=True,
    )
    name, kwargs = stub.calls[0]
    assert name == "get_products"
    assert kwargs["limit"] == 100
    assert kwargs["cursor"] == "page-2"
    assert kwargs["product_type"] == "SPOT"
    assert kwargs["get_tradability_status"] is True


def test_get_best_bid_ask_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    client, stub = _client_with_stub(monkeypatch)
    client.get_best_bid_ask(product_ids=["BTC-USDC", "ETH-USDC"])
    assert stub.calls[0][0] == "get_best_bid_ask"
    assert stub.calls[0][1]["product_ids"] == ["BTC-USDC", "ETH-USDC"]


def test_get_transaction_summary_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    client, stub = _client_with_stub(monkeypatch)
    client.get_transaction_summary()
    assert stub.calls[0][0] == "get_transaction_summary"


def test_list_orders_cursor_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    client, stub = _client_with_stub(monkeypatch)
    client.list_orders(cursor="page-2", limit=50, product_ids=["BTC-USDC"])
    name, kwargs = stub.calls[0]
    assert name == "list_orders"
    assert kwargs["cursor"] == "page-2"
    assert kwargs["limit"] == 50
    assert kwargs["product_ids"] == ["BTC-USDC"]


def test_get_fills_cursor_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    client, stub = _client_with_stub(monkeypatch)
    client.get_fills(order_ids=["ord-1"], cursor="c1")
    name, kwargs = stub.calls[0]
    assert name == "get_fills"
    assert kwargs["order_ids"] == ["ord-1"]
    assert kwargs["cursor"] == "c1"


def test_get_accounts_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    client, stub = _client_with_stub(monkeypatch)
    client.get_accounts(limit=100, cursor="c", retail_portfolio_id="pf")
    name, kwargs = stub.calls[0]
    assert name == "get_accounts"
    assert kwargs == {"limit": 100, "cursor": "c", "retail_portfolio_id": "pf"}


def test_get_api_key_permissions_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    client, stub = _client_with_stub(monkeypatch)
    result = client.get_api_key_permissions()
    assert result["can_trade"] is True
    assert stub.calls[0][0] == "get_api_key_permissions"


def test_get_portfolios_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    client, stub = _client_with_stub(monkeypatch)
    client.get_portfolios()
    assert stub.calls[0][0] == "get_portfolios"


def test_public_exports() -> None:
    for name in (
        "CoinbaseAdvanced",
        "CoinbaseAdvancedPublic",
        "CoinbaseAdvancedError",
        "CoinbaseAdvancedConfigurationError",
        "CoinbaseAdvancedTradingDisabledError",
        "MarketDataStream",
        "UserStream",
    ):
        assert hasattr(coinbase_advanced_client, name)
    assert coinbase_advanced_client.__version__ == "0.1.0"
