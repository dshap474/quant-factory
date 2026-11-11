"""Thin facade over the official ``coinbase-advanced-py`` REST client.

Purpose: resolve API credentials from the environment-injected environment variables, own
one :class:`coinbase.rest.RESTClient`, and expose read / preview / gated
placement passthroughs. Intent→payload shaping lives in ``venues``;
this package does not edit orders, move funds, or transfer.

USAGE:
    from coinbase_advanced_client import CoinbaseAdvanced

    client = CoinbaseAdvanced()  # keys from the environment-injected environment variables
    accounts = client.get_accounts()
    product = client.get_product("BTC-USDC", get_tradability_status=True)
    preview = client.preview_order(
        product_id="BTC-USDC",
        side="BUY",
        order_configuration={"market_market_ioc": {"base_size": "0.0001"}},
    )
    # create_order requires COINBASE_ADVANCED_TRADING_ENABLED == "1"
"""

from __future__ import annotations

import json
import os
from typing import Any

from coinbase.rest import RESTClient
from coinbase.rest.types.accounts_types import ListAccountsResponse
from coinbase.rest.types.data_api_types import GetAPIKeyPermissionsResponse
from coinbase.rest.types.fees_types import GetTransactionSummaryResponse
from coinbase.rest.types.orders_types import (
    CancelOrdersResponse,
    CreateOrderResponse,
    GetOrderResponse,
    ListFillsResponse,
    ListOrdersResponse,
    PreviewOrderResponse,
)
from coinbase.rest.types.portfolios_types import ListPortfoliosResponse
from coinbase.rest.types.product_types import GetBestBidAskResponse, GetProductResponse, ListProductsResponse
from config import (
    COINBASE_ADVANCED_PORTFOLIO_UUID,
    COINBASE_ADVANCED_TRADING_ENABLED,
)

from .exceptions import (
    CoinbaseAdvancedConfigurationError,
    CoinbaseAdvancedTradingDisabledError,
)

# --------------------------------------------------------------------------- #
# Constants / helpers
# --------------------------------------------------------------------------- #

_ALLOWED_QUOTE = "USDC"


def _product_quote_currency(product_id: str) -> str:
    """Return the quote leg of a Coinbase product id (``BASE-QUOTE``)."""
    if not product_id or "-" not in product_id:
        raise ValueError(f"invalid product_id (expected BASE-QUOTE): {product_id!r}")
    quote = product_id.rsplit("-", 1)[-1]
    if not quote:
        raise ValueError(f"invalid product_id (empty quote leg): {product_id!r}")
    return quote.upper()


def _require_usdc_quote(product_id: str) -> None:
    quote = _product_quote_currency(product_id)
    if quote != _ALLOWED_QUOTE:
        raise ValueError(
            f"product_id {product_id!r} quote leg is {quote!r}; only {_ALLOWED_QUOTE}-quoted products are allowed"
        )


def _normalize_private_key(value: str) -> str:
    """Decode a JSON-quoted PEM while leaving ordinary PEM text unchanged."""
    if not value.startswith('"'):
        return value
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError as exc:
        raise CoinbaseAdvancedConfigurationError("COINBASE_ADVANCED_PRIVATE_KEY is invalid JSON-quoted text") from exc
    if not isinstance(decoded, str) or not decoded:
        raise CoinbaseAdvancedConfigurationError("COINBASE_ADVANCED_PRIVATE_KEY must decode to non-empty text")
    return decoded


# --------------------------------------------------------------------------- #
# Facade
# --------------------------------------------------------------------------- #


class CoinbaseAdvanced:
    """Config-resolving facade over :class:`coinbase.rest.RESTClient`."""

    def __init__(
        self,
        api_key_name: str | None = None,
        private_key: str | None = None,
        *,
        timeout: int = 30,
    ) -> None:
        if (api_key_name is None) != (private_key is None):
            raise CoinbaseAdvancedConfigurationError(
                "incomplete Coinbase Advanced credentials: pass both api_key_name and private_key"
            )
        if api_key_name is None:
            resolved_key = os.environ.get("COINBASE_ADVANCED_API_KEY_NAME")
            resolved_secret = os.environ.get("COINBASE_ADVANCED_PRIVATE_KEY")
            if not resolved_key or not resolved_secret:
                raise CoinbaseAdvancedConfigurationError(
                    "COINBASE_ADVANCED_API_KEY_NAME and COINBASE_ADVANCED_PRIVATE_KEY are required; "
                    "set them in the environment."
                )
        elif not api_key_name or not private_key:
            raise CoinbaseAdvancedConfigurationError("Coinbase Advanced credentials must not be empty")
        else:
            resolved_key = api_key_name
            resolved_secret = private_key
        self._rest = RESTClient(
            api_key=resolved_key,
            api_secret=_normalize_private_key(resolved_secret),
            timeout=timeout,
            rate_limit_headers=True,
        )

    @property
    def configured_portfolio_uuid(self) -> str:
        """Return the non-secret expected portfolio UUID resolved by config."""
        return COINBASE_ADVANCED_PORTFOLIO_UUID

    @property
    def trading_gate_enabled(self) -> bool:
        """Return whether this process resolved the exact placement gate."""
        return COINBASE_ADVANCED_TRADING_ENABLED == "1"

    # ----------------------------------------------------------------------- #
    # Read-only / preview passthroughs
    # ----------------------------------------------------------------------- #

    def get_accounts(
        self,
        limit: int | None = None,
        cursor: str | None = None,
        retail_portfolio_id: str | None = None,
    ) -> ListAccountsResponse:
        """Return the SDK accounts response (cursor-complete snapshots at call site)."""
        return self._rest.get_accounts(
            limit=limit,
            cursor=cursor,
            retail_portfolio_id=retail_portfolio_id,
        )

    def get_product(
        self,
        product_id: str,
        get_tradability_status: bool = False,
    ) -> GetProductResponse:
        """Return the SDK product response for ``product_id``.

        Pass ``get_tradability_status=True`` so spot ``view_only`` (and related
        tradability fields) are populated.
        """
        return self._rest.get_product(
            product_id,
            get_tradability_status=get_tradability_status,
        )

    def get_products(
        self,
        *,
        limit: int | None = None,
        cursor: str | None = None,
        product_type: str | None = None,
        contract_expiry_type: str | None = None,
        expiring_contract_status: str | None = None,
        get_tradability_status: bool = False,
    ) -> ListProductsResponse:
        """Return one authenticated product-catalog page.

        Cursor traversal remains explicit at the caller. Use
        :class:`CoinbaseAdvancedPublic` for a credential-free, cursor-complete
        catalog snapshot.
        """
        return self._rest.get_products(
            limit=limit,
            cursor=cursor,
            product_type=product_type,
            contract_expiry_type=contract_expiry_type,
            expiring_contract_status=expiring_contract_status,
            get_tradability_status=get_tradability_status,
            products_sort_order="PRODUCTS_SORT_ORDER_LIST_TIME_DESCENDING",
        )

    def get_best_bid_ask(
        self,
        product_ids: list[str] | None = None,
    ) -> GetBestBidAskResponse:
        """Return best bid/ask for one or more product ids."""
        return self._rest.get_best_bid_ask(product_ids=product_ids)

    def get_transaction_summary(self) -> GetTransactionSummaryResponse:
        """Return the fee / transaction summary for the authenticated principal."""
        return self._rest.get_transaction_summary()

    def get_order(self, order_id: str) -> GetOrderResponse:
        """Return a single order by venue ``order_id``."""
        return self._rest.get_order(order_id)

    def list_orders(
        self,
        *,
        order_ids: list[str] | None = None,
        product_ids: list[str] | None = None,
        order_status: list[str] | None = None,
        limit: int | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        order_types: str | None = None,
        order_side: str | None = None,
        cursor: str | None = None,
        product_type: str | None = None,
        order_placement_source: str | None = None,
        contract_expiry_type: str | None = None,
        asset_filters: list[str] | None = None,
        retail_portfolio_id: str | None = None,
        time_in_forces: str | None = None,
        sort_by: str | None = None,
    ) -> ListOrdersResponse:
        """List orders; cursor pagination is a pure passthrough."""
        return self._rest.list_orders(
            order_ids=order_ids,
            product_ids=product_ids,
            order_status=order_status,
            limit=limit,
            start_date=start_date,
            end_date=end_date,
            order_types=order_types,
            order_side=order_side,
            cursor=cursor,
            product_type=product_type,
            order_placement_source=order_placement_source,
            contract_expiry_type=contract_expiry_type,
            asset_filters=asset_filters,
            retail_portfolio_id=retail_portfolio_id,
            time_in_forces=time_in_forces,
            sort_by=sort_by,
        )

    def get_fills(
        self,
        *,
        order_ids: list[str] | None = None,
        trade_ids: list[str] | None = None,
        product_ids: list[str] | None = None,
        start_sequence_timestamp: str | None = None,
        end_sequence_timestamp: str | None = None,
        retail_portfolio_id: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        sort_by: str | None = None,
    ) -> ListFillsResponse:
        """List fills; cursor pagination is a pure passthrough."""
        return self._rest.get_fills(
            order_ids=order_ids,
            trade_ids=trade_ids,
            product_ids=product_ids,
            start_sequence_timestamp=start_sequence_timestamp,
            end_sequence_timestamp=end_sequence_timestamp,
            retail_portfolio_id=retail_portfolio_id,
            limit=limit,
            cursor=cursor,
            sort_by=sort_by,
        )

    def get_portfolios(
        self,
        portfolio_type: str | None = None,
    ) -> ListPortfoliosResponse:
        """Return portfolios for the authenticated principal."""
        return self._rest.get_portfolios(portfolio_type=portfolio_type)

    def get_api_key_permissions(self) -> GetAPIKeyPermissionsResponse:
        """Return API key permissions (can_view / can_trade / portfolio_uuid)."""
        return self._rest.get_api_key_permissions()

    def preview_order(
        self,
        product_id: str,
        side: str,
        order_configuration: dict[str, dict[str, Any]],
    ) -> PreviewOrderResponse:
        """Preview an order without placing it.

        ``order_configuration`` is the SDK payload shape (e.g.
        ``{"sor_limit_ioc": {"base_size": ..., "limit_price": ...}}``).
        """
        if not order_configuration:
            raise ValueError("order_configuration is required")
        return self._rest.preview_order(
            product_id=product_id,
            side=side,
            order_configuration=order_configuration,
        )

    # ----------------------------------------------------------------------- #
    # Mutating passthroughs (cancel ungated; create hard-gated)
    # ----------------------------------------------------------------------- #

    def cancel_orders(self, order_ids: list[str]) -> CancelOrdersResponse:
        """Cancel orders by venue id. Always allowed (risk-reducing; no trading gate)."""
        if not order_ids:
            raise ValueError("order_ids is required")
        return self._rest.cancel_orders(order_ids=order_ids)

    def create_order(
        self,
        client_order_id: str,
        product_id: str,
        side: str,
        order_configuration: dict[str, dict[str, Any]],
        *,
        retail_portfolio_id: str | None = None,
    ) -> CreateOrderResponse:
        """Place an order. Hard-gated; USDC-quote only; client_order_id required.

        The trading gate is checked first. Placement is refused unless
        ``config.COINBASE_ADVANCED_TRADING_ENABLED == "1"``. Empty / falsey
        ``client_order_id`` is rejected locally so the SDK's uuid4 fallback
        cannot silently remove the duplicate-order safeguard.
        """
        if COINBASE_ADVANCED_TRADING_ENABLED != "1":
            raise CoinbaseAdvancedTradingDisabledError(
                "create_order refused: COINBASE_ADVANCED_TRADING_ENABLED is not '1' "
                f"(current={COINBASE_ADVANCED_TRADING_ENABLED!r}). "
                "Cancel remains available; placement requires an explicit gate."
            )
        if not client_order_id:
            raise ValueError(
                "client_order_id is required (SDK uuid4 fallback is not allowed; "
                "it would drop the duplicate-order safeguard)"
            )
        _require_usdc_quote(product_id)
        if not order_configuration:
            raise ValueError("order_configuration is required")
        return self._rest.create_order(
            client_order_id=client_order_id,
            product_id=product_id,
            side=side,
            order_configuration=order_configuration,
            retail_portfolio_id=retail_portfolio_id,
        )
