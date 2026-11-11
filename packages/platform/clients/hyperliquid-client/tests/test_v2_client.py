"""Hermetic HIP-3 REST and order-contract tests.

Purpose: prove DEX scoping, SDK-derived asset identity, typed ALO/IOC wires,
reconciliation, and exact risk-control gates.
USAGE: python -m pytest tests/test_v2_client.py -q
"""

from __future__ import annotations

import pytest
from eth_account import Account
from hyperliquid.utils.types import Cloid
from hyperliquid_client import (
    HyperliquidClient,
    HyperliquidClientConfig,
    HyperliquidConfigurationError,
    HyperliquidReadClient,
    HyperliquidTradingDisabledError,
    LimitOrderRequest,
)

# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #

ACCOUNT = "0x1111111111111111111111111111111111111111"
KEY = "0x" + "22" * 32
AGENT = Account.from_key(KEY).address.lower()
CLOID = "0x" + "b" * 32


class Info:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []
        self.assets = {"dexa:TOKN": 110000, "dexb:TOKN": 120000}

    def name_to_asset(self, coin: str) -> int:
        return self.assets[coin]

    def perp_dexs(self) -> list[dict[str, str]]:
        return [{"name": "dexa"}, {"name": "dexb"}]

    def meta(self, dex: str) -> dict[str, str]:
        self.calls.append(("meta", dex))
        return {"dex": dex}

    def post(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        self.calls.append(("post", path, payload))
        return payload

    def user_state(self, address: str, dex: str) -> dict[str, str]:
        self.calls.append(("user_state", address, dex))
        return {"dex": dex}

    def frontend_open_orders(self, address: str, dex: str) -> list[object]:
        self.calls.append(("orders", address, dex))
        return []

    def query_order_by_oid(self, address: str, oid: int) -> dict[str, int]:
        self.calls.append(("oid", address, oid))
        return {"oid": oid}

    def query_order_by_cloid(self, address: str, cloid: Cloid) -> dict[str, str]:
        self.calls.append(("cloid", address, cloid.to_raw()))
        return {"cloid": cloid.to_raw()}

    def historical_orders(self, address: str) -> list[object]:
        self.calls.append(("history", address))
        return []

    def user_fees(self, address: str) -> dict[str, str]:
        self.calls.append(("fees", address))
        return {"maker": "-0.0001"}


class Exchange:
    def __init__(self) -> None:
        self.orders: list[tuple[tuple[object, ...], dict[str, object]]] = []
        self.cancels: list[tuple[object, ...]] = []
        self.schedules: list[int | None] = []

    def order(self, *args: object, **kwargs: object) -> dict[str, str]:
        self.orders.append((args, kwargs))
        return {"status": "ok"}

    def cancel(self, coin: str, oid: int) -> dict[str, str]:
        self.cancels.append((coin, oid))
        return {"status": "ok"}

    def cancel_by_cloid(self, coin: str, cloid: Cloid) -> dict[str, str]:
        self.cancels.append((coin, cloid.to_raw()))
        return {"status": "ok"}

    def schedule_cancel(self, at_ms: int | None) -> dict[str, str]:
        self.schedules.append(at_ms)
        return {"status": "ok"}


def client(*, info: Info | None = None, exchange: Exchange | None = None) -> HyperliquidClient:
    return HyperliquidClient(
        HyperliquidClientConfig(
            network="testnet",
            account_address=ACCOUNT,
            expected_agent_address=AGENT,
            perp_dexs=("dexa", "dexb"),
        ),
        agent_private_key=KEY,
        _info=info,
        _exchange=exchange,
    )


# --------------------------------------------------------------------------- #
# Contracts
# --------------------------------------------------------------------------- #


def test_dex_reads_and_asset_identity_are_explicit() -> None:
    info = Info()
    boundary = client(info=info, exchange=Exchange())
    assert boundary.meta("dexa") == {"dex": "dexa"}
    boundary.meta_and_asset_contexts("dexb")
    boundary.clearinghouse_state(ACCOUNT, "dexa")
    boundary.frontend_open_orders(ACCOUNT, "dexb")
    assert boundary.asset_id("dexa:TOKN") == 110000
    assert info.calls == [
        ("meta", "dexa"),
        ("post", "/info", {"type": "metaAndAssetCtxs", "dex": "dexb"}),
        ("user_state", ACCOUNT, "dexa"),
        ("orders", ACCOUNT, "dexb"),
    ]


def test_read_client_exposes_no_mutation_methods() -> None:
    boundary = HyperliquidReadClient(
        HyperliquidClientConfig(
            network="testnet",
            account_address=ACCOUNT,
            perp_dexs=("dexa", "dexb"),
        ),
        _info=Info(),
    )
    assert boundary.asset_id("dexa:TOKN") == 110000
    for name in (
        "place_limit",
        "place_limit_ioc",
        "cancel_by_oid",
        "cancel_by_cloid",
        "schedule_cancel",
        "clear_scheduled_cancel",
    ):
        assert not hasattr(boundary, name)


@pytest.mark.parametrize("coin", ["TOKN", "bad:TOKN", "dexa:", "dexa:TO KN"])
def test_unqualified_or_unconfigured_hip3_symbols_fail(coin: str) -> None:
    with pytest.raises(ValueError):
        client(info=Info(), exchange=Exchange()).asset_id(coin)


def test_typed_alo_wire_supports_optional_cloid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HYPERLIQUID_TRADING_ENABLED", "1")
    exchange = Exchange()
    boundary = client(info=Info(), exchange=exchange)
    boundary.place_limit(
        LimitOrderRequest(
            coin="dexa:TOKN",
            is_buy=False,
            size="10.5",
            limit_price="0.25",
            time_in_force="Alo",
            reduce_only=False,
        )
    )
    args, kwargs = exchange.orders[0]
    assert args == ("dexa:TOKN", False, 10.5, 0.25, {"limit": {"tif": "Alo"}})
    assert kwargs == {"reduce_only": False, "cloid": None}


@pytest.mark.parametrize("tif", ["Gtc", "Market", ""])
def test_order_type_allowlist_rejects_every_other_tif(tif: str) -> None:
    with pytest.raises(ValueError):
        LimitOrderRequest(
            coin="dexa:TOKN",
            is_buy=True,
            size="1",
            limit_price="1",
            time_in_force=tif,  # type: ignore[arg-type]
            reduce_only=False,
        )


def test_oid_cancel_is_ungated_but_schedule_is_gated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HYPERLIQUID_TRADING_ENABLED", raising=False)
    exchange = Exchange()
    boundary = client(info=Info(), exchange=exchange)
    boundary.cancel_by_oid(coin="dexb:TOKN", oid=42)
    assert exchange.cancels == [("dexb:TOKN", 42)]
    with pytest.raises(HyperliquidTradingDisabledError):
        boundary.schedule_cancel(1000)
    monkeypatch.setenv("HYPERLIQUID_TRADING_ENABLED", "1")
    boundary.schedule_cancel(1000)
    boundary.clear_scheduled_cancel()
    assert exchange.schedules == [1000, None]


@pytest.mark.parametrize("timeout", [0, -1, True, float("inf"), float("nan"), "1"])
def test_read_timeout_rejects_invalid_values(timeout) -> None:
    with pytest.raises(HyperliquidConfigurationError, match="timeout"):
        HyperliquidReadClient(
            HyperliquidClientConfig(network="testnet", account_address=ACCOUNT), request_timeout_s=timeout, _info=Info()
        )


def test_unsigned_timeout_is_forwarded_to_official_sdk(monkeypatch) -> None:
    seen = {}

    def fake_info(*args, **kwargs):
        seen.update(kwargs)
        return Info()

    monkeypatch.setattr("hyperliquid_client.client.Info", fake_info)
    boundary = HyperliquidReadClient(
        HyperliquidClientConfig(network="testnet", account_address=ACCOUNT), request_timeout_s=0.25
    )
    boundary.meta()
    assert seen["timeout"] == 0.25
    assert seen["skip_ws"] is True
