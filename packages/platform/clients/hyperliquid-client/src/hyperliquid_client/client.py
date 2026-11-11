"""Narrow REST and signing facade over the official Hyperliquid Python SDK.

Purpose: expose explicit DEX-aware reads, allowlisted limit orders, and narrow
risk-control mutations without leaking raw SDK objects.
USAGE:
    client = HyperliquidClient(
        HyperliquidClientConfig(
            network="testnet",
            account_address="0x1111111111111111111111111111111111111111",
            perp_dexs=("dexa", "dexb"),
        )
    )
    metadata = client.meta_and_asset_contexts("dexa")
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Any

from eth_account import Account
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils.constants import MAINNET_API_URL, TESTNET_API_URL
from hyperliquid.utils.types import Cloid

from hyperliquid_client.contracts import (
    LimitOrderRequest,
    validated_address,
    validated_cloid,
    validated_coin,
    validated_dex,
    validated_window,
)
from hyperliquid_client.exceptions import (
    HyperliquidConfigurationError,
    HyperliquidTradingDisabledError,
)

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

_NETWORK_URLS = {"mainnet": MAINNET_API_URL, "testnet": TESTNET_API_URL}


@dataclass(frozen=True, slots=True)
class HyperliquidClientConfig:
    """Non-secret provider configuration for one account or subaccount."""

    network: str
    account_address: str
    subaccount_address: str | None = None
    expected_agent_address: str | None = None
    perp_dexs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.network not in _NETWORK_URLS:
            raise HyperliquidConfigurationError("network must be 'testnet' or 'mainnet'")
        try:
            account = validated_address(self.account_address, "account_address")
            subaccount = validated_address(
                self.subaccount_address,
                "subaccount_address",
                optional=True,
            )
            expected_agent = validated_address(
                self.expected_agent_address,
                "expected_agent_address",
                optional=True,
            )
            dexes = tuple(validated_dex(dex) for dex in self.perp_dexs)
        except ValueError as exc:
            raise HyperliquidConfigurationError(str(exc)) from None
        if len(set(dexes)) != len(dexes):
            raise HyperliquidConfigurationError("perp_dexs entries must be unique")
        if subaccount == account:
            raise HyperliquidConfigurationError("subaccount_address must differ from account_address")
        object.__setattr__(self, "account_address", account)
        object.__setattr__(self, "subaccount_address", subaccount)
        object.__setattr__(self, "expected_agent_address", expected_agent)
        object.__setattr__(self, "perp_dexs", dexes)

    @property
    def selected_account_address(self) -> str:
        """Return the address whose positions and orders are authoritative."""
        return self.subaccount_address or self.account_address


# --------------------------------------------------------------------------- #
# Client facade
# --------------------------------------------------------------------------- #


class HyperliquidReadClient:
    """Unsigned facade exposing only the reviewed read contract."""

    def __init__(
        self,
        config: HyperliquidClientConfig,
        *,
        _info: Any | None = None,
        request_timeout_s: float | None = None,
    ) -> None:
        if not isinstance(config, HyperliquidClientConfig):
            raise TypeError("config must be HyperliquidClientConfig")
        if config.expected_agent_address is not None:
            raise HyperliquidConfigurationError("read-only client must not configure an expected agent address")
        if request_timeout_s is not None and (
            isinstance(request_timeout_s, bool)
            or not isinstance(request_timeout_s, (int, float))
            or not math.isfinite(request_timeout_s)
            or request_timeout_s <= 0
        ):
            raise HyperliquidConfigurationError("request_timeout_s must be finite and positive")
        self.request_timeout_s = request_timeout_s
        self.config = config
        self.base_url = _NETWORK_URLS[config.network]
        self.__info = _info

    def __repr__(self) -> str:
        return (
            "HyperliquidReadClient("
            f"network={self.config.network!r}, "
            f"account_address={self.config.account_address!r}, "
            f"subaccount_address={self.config.subaccount_address!r}, "
            f"perp_dexs={self.config.perp_dexs!r})"
        )

    def _info_client(self) -> Any:
        if self.__info is None:
            self.__info = Info(
                self.base_url,
                skip_ws=True,
                perp_dexs=list(self.config.perp_dexs) or None,
                timeout=self.request_timeout_s,
            )
        return self.__info

    def _dex(self, dex: str) -> str:
        if dex == "":
            return dex
        validated_dex(dex)
        if dex not in self.config.perp_dexs:
            raise ValueError("DEX is not explicitly configured")
        return dex

    def _coin(self, coin: str) -> str:
        return validated_coin(coin, self.config.perp_dexs)

    def perp_dexs(self) -> Any:
        return self._info_client().perp_dexs()

    def meta(self, dex: str = "") -> Any:
        return self._info_client().meta(self._dex(dex))

    def meta_and_asset_contexts(self, dex: str = "") -> Any:
        selected = self._dex(dex)
        if not selected:
            return self._info_client().meta_and_asset_ctxs()
        return self._info_client().post("/info", {"type": "metaAndAssetCtxs", "dex": selected})

    def clearinghouse_state(self, account_address: str, dex: str = "") -> Any:
        address = validated_address(account_address, "account_address")
        selected = self._dex(dex)
        if not selected:
            return self._info_client().user_state(address)
        return self._info_client().user_state(address, selected)

    def frontend_open_orders(self, account_address: str, dex: str = "") -> Any:
        address = validated_address(account_address, "account_address")
        selected = self._dex(dex)
        if not selected:
            return self._info_client().frontend_open_orders(address)
        return self._info_client().frontend_open_orders(address, selected)

    def l2_book(self, coin: str) -> Any:
        return self._info_client().l2_snapshot(self._coin(coin))

    def asset_id(self, coin: str) -> int:
        selected = self._coin(coin)
        try:
            asset_id = self._info_client().name_to_asset(selected)
        except KeyError as exc:
            raise ValueError("SDK metadata has no asset ID for coin") from exc
        if isinstance(asset_id, bool) or not isinstance(asset_id, int):
            raise ValueError("SDK metadata has no asset ID for coin")
        return asset_id

    def active_asset_data(self, account_address: str, coin: str) -> Any:
        return self._info_client().post(
            "/info",
            {
                "type": "activeAssetData",
                "user": validated_address(account_address, "account_address"),
                "coin": self._coin(coin),
            },
        )

    def order_status_by_cloid(self, account_address: str, cloid: str) -> Any:
        return self._info_client().query_order_by_cloid(
            validated_address(account_address, "account_address"),
            Cloid.from_str(validated_cloid(cloid)),
        )

    def order_status_by_oid(self, account_address: str, oid: int) -> Any:
        if isinstance(oid, bool) or not isinstance(oid, int) or oid <= 0:
            raise ValueError("oid must be a positive integer")
        return self._info_client().query_order_by_oid(
            validated_address(account_address, "account_address"),
            oid,
        )

    def historical_orders(self, account_address: str) -> Any:
        return self._info_client().historical_orders(validated_address(account_address, "account_address"))

    def user_fills_by_time(
        self,
        account_address: str,
        start_ms: int,
        end_ms: int,
        dex: str = "",
    ) -> Any:
        start, end = validated_window(start_ms, end_ms)
        address = validated_address(account_address, "account_address")
        selected = self._dex(dex)
        if not selected:
            return self._info_client().user_fills_by_time(
                address,
                start,
                end,
                aggregate_by_time=False,
            )
        return self._info_client().post(
            "/info",
            {
                "type": "userFillsByTime",
                "user": address,
                "startTime": start,
                "endTime": end,
                "aggregateByTime": False,
                "dex": selected,
            },
        )

    def user_funding(self, account_address: str, start_ms: int, end_ms: int) -> Any:
        start, end = validated_window(start_ms, end_ms)
        return self._info_client().user_funding_history(
            validated_address(account_address, "account_address"),
            start,
            end,
        )

    def user_fees(self, account_address: str) -> Any:
        return self._info_client().user_fees(validated_address(account_address, "account_address"))


class HyperliquidClient:
    """Lazy, secret-safe facade exposing only the reviewed v2 REST contract."""

    def __init__(
        self,
        config: HyperliquidClientConfig,
        *,
        agent_private_key: str | None = None,
        _info: Any | None = None,
        _exchange: Any | None = None,
    ) -> None:
        if not isinstance(config, HyperliquidClientConfig):
            raise TypeError("config must be HyperliquidClientConfig")
        self.config = config
        self.base_url = _NETWORK_URLS[config.network]
        self.__info = _info
        self.__exchange = _exchange
        self.__wallet: Any | None = None

        if agent_private_key is not None and config.expected_agent_address is None:
            raise HyperliquidConfigurationError("agent_private_key requires expected_agent_address")
        if config.expected_agent_address is not None:
            private_key = agent_private_key or os.environ.get("HYPERLIQUID_AGENT_PRIVATE_KEY")
            if not private_key:
                raise HyperliquidConfigurationError(
                    "HYPERLIQUID_AGENT_PRIVATE_KEY must be injected for mutating construction"
                )
            try:
                wallet = Account.from_key(private_key)
            except Exception:
                raise HyperliquidConfigurationError("API-wallet private key is invalid") from None
            if wallet.address.lower() != config.expected_agent_address:
                raise HyperliquidConfigurationError("API-wallet address does not match activation")
            self.__wallet = wallet

    def __repr__(self) -> str:
        return (
            "HyperliquidClient("
            f"network={self.config.network!r}, "
            f"account_address={self.config.account_address!r}, "
            f"subaccount_address={self.config.subaccount_address!r}, "
            f"perp_dexs={self.config.perp_dexs!r})"
        )

    @property
    def agent_address(self) -> str | None:
        """Return the derived non-secret signer address, if configured."""
        return self.__wallet.address.lower() if self.__wallet is not None else None

    def _info_client(self) -> Any:
        if self.__info is None:
            self.__info = Info(
                self.base_url,
                skip_ws=True,
                perp_dexs=list(self.config.perp_dexs) or None,
            )
        return self.__info

    def _exchange_client(self) -> Any:
        if self.__wallet is None:
            raise HyperliquidConfigurationError("mutating use requires an activation-bound API wallet")
        if self.__exchange is None:
            self.__exchange = Exchange(
                self.__wallet,
                self.base_url,
                account_address=self.config.account_address,
                vault_address=self.config.subaccount_address,
                perp_dexs=list(self.config.perp_dexs) or None,
            )
        return self.__exchange

    def _dex(self, dex: str) -> str:
        if dex == "":
            return dex
        validated_dex(dex)
        if dex not in self.config.perp_dexs:
            raise ValueError("DEX is not explicitly configured")
        return dex

    def _coin(self, coin: str) -> str:
        return validated_coin(coin, self.config.perp_dexs)

    @staticmethod
    def _cloid(value: str) -> Cloid:
        return Cloid.from_str(validated_cloid(value))

    @staticmethod
    def _trading_gate() -> None:
        if os.environ.get("HYPERLIQUID_TRADING_ENABLED") != "1":
            raise HyperliquidTradingDisabledError("HYPERLIQUID_TRADING_ENABLED=1 is required")

    # ----------------------------------------------------------------------- #
    # Read-only /info methods
    # ----------------------------------------------------------------------- #

    def perp_dexs(self) -> Any:
        return self._info_client().perp_dexs()

    def meta(self, dex: str = "") -> Any:
        return self._info_client().meta(self._dex(dex))

    def meta_and_asset_contexts(self, dex: str = "") -> Any:
        selected = self._dex(dex)
        if not selected:
            return self._info_client().meta_and_asset_ctxs()
        return self._info_client().post("/info", {"type": "metaAndAssetCtxs", "dex": selected})

    def clearinghouse_state(self, account_address: str, dex: str = "") -> Any:
        address = validated_address(account_address, "account_address")
        selected = self._dex(dex)
        if not selected:
            return self._info_client().user_state(address)
        return self._info_client().user_state(address, selected)

    def frontend_open_orders(self, account_address: str, dex: str = "") -> Any:
        address = validated_address(account_address, "account_address")
        selected = self._dex(dex)
        if not selected:
            return self._info_client().frontend_open_orders(address)
        return self._info_client().frontend_open_orders(address, selected)

    def l2_book(self, coin: str) -> Any:
        return self._info_client().l2_snapshot(self._coin(coin))

    def asset_id(self, coin: str) -> int:
        """Return the SDK metadata-derived asset ID for one validated coin."""
        selected = self._coin(coin)
        try:
            asset_id = self._info_client().name_to_asset(selected)
        except KeyError as exc:
            raise ValueError("SDK metadata has no asset ID for coin") from exc
        if isinstance(asset_id, bool) or not isinstance(asset_id, int):
            raise ValueError("SDK metadata has no asset ID for coin")
        return asset_id

    def active_asset_data(self, account_address: str, coin: str) -> Any:
        return self._info_client().post(
            "/info",
            {
                "type": "activeAssetData",
                "user": validated_address(account_address, "account_address"),
                "coin": self._coin(coin),
            },
        )

    def user_abstraction(self, account_address: str) -> Any:
        return self._info_client().query_user_abstraction_state(validated_address(account_address, "account_address"))

    def user_role(self, address: str) -> Any:
        return self._info_client().user_role(validated_address(address, "address"))

    def order_status_by_cloid(self, account_address: str, cloid: str) -> Any:
        return self._info_client().query_order_by_cloid(
            validated_address(account_address, "account_address"),
            self._cloid(cloid),
        )

    def order_status(self, account_address: str, cloid: str) -> Any:
        """Compatibility alias for the v1 cloid lookup."""
        return self.order_status_by_cloid(account_address, cloid)

    def order_status_by_oid(self, account_address: str, oid: int) -> Any:
        if isinstance(oid, bool) or not isinstance(oid, int) or oid <= 0:
            raise ValueError("oid must be a positive integer")
        return self._info_client().query_order_by_oid(
            validated_address(account_address, "account_address"),
            oid,
        )

    def historical_orders(self, account_address: str) -> Any:
        return self._info_client().historical_orders(validated_address(account_address, "account_address"))

    def user_fills_by_time(
        self,
        account_address: str,
        start_ms: int,
        end_ms: int,
        dex: str = "",
    ) -> Any:
        start, end = validated_window(start_ms, end_ms)
        address = validated_address(account_address, "account_address")
        selected = self._dex(dex)
        if not selected:
            return self._info_client().user_fills_by_time(
                address,
                start,
                end,
                aggregate_by_time=False,
            )
        return self._info_client().post(
            "/info",
            {
                "type": "userFillsByTime",
                "user": address,
                "startTime": start,
                "endTime": end,
                "aggregateByTime": False,
                "dex": selected,
            },
        )

    def user_funding(self, account_address: str, start_ms: int, end_ms: int) -> Any:
        start, end = validated_window(start_ms, end_ms)
        return self._info_client().user_funding_history(
            validated_address(account_address, "account_address"),
            start,
            end,
        )

    def user_fees(self, account_address: str) -> Any:
        return self._info_client().user_fees(validated_address(account_address, "account_address"))

    # ----------------------------------------------------------------------- #
    # Narrow /exchange methods
    # ----------------------------------------------------------------------- #

    def place_limit(self, request: LimitOrderRequest) -> Any:
        """Place one explicit ALO or IOC after the exact environment gate."""
        if not isinstance(request, LimitOrderRequest):
            raise TypeError("request must be LimitOrderRequest")
        self._trading_gate()
        return self._exchange_client().order(
            self._coin(request.coin),
            request.is_buy,
            float(request.size),
            float(request.limit_price),
            {"limit": {"tif": request.time_in_force}},
            reduce_only=request.reduce_only,
            cloid=self._cloid(request.cloid) if request.cloid is not None else None,
        )

    def place_limit_ioc(
        self,
        *,
        coin: str,
        is_buy: bool,
        size: str,
        limit_price: str,
        reduce_only: bool,
        cloid: str,
    ) -> Any:
        """Place one v1-compatible capped IOC with a mandatory cloid."""
        return self.place_limit(
            LimitOrderRequest(
                coin=coin,
                is_buy=is_buy,
                size=size,
                limit_price=limit_price,
                time_in_force="Ioc",
                reduce_only=reduce_only,
                cloid=cloid,
            )
        )

    def cancel_by_oid(self, *, coin: str, oid: int) -> Any:
        """Cancel one provider order ID without requiring the placement gate."""
        if isinstance(oid, bool) or not isinstance(oid, int) or oid <= 0:
            raise ValueError("oid must be a positive integer")
        return self._exchange_client().cancel(self._coin(coin), oid)

    def cancel_by_cloid(self, *, coin: str, cloid: str) -> Any:
        """Cancel one caller-owned cloid without requiring the placement gate."""
        return self._exchange_client().cancel_by_cloid(self._coin(coin), self._cloid(cloid))

    def schedule_cancel(self, at_ms: int) -> Any:
        """Schedule the provider dead-man action after the trading gate."""
        if isinstance(at_ms, bool) or not isinstance(at_ms, int) or at_ms <= 0:
            raise ValueError("at_ms must be a positive integer")
        self._trading_gate()
        return self._exchange_client().schedule_cancel(at_ms)

    def clear_scheduled_cancel(self) -> Any:
        """Clear the provider dead-man action after the trading gate."""
        self._trading_gate()
        return self._exchange_client().schedule_cancel(None)


__all__ = ["HyperliquidClient", "HyperliquidClientConfig", "HyperliquidReadClient"]
