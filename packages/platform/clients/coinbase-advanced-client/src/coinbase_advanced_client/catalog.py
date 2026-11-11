"""Read the public Coinbase Advanced product catalog without credentials.

Purpose: provide cursor-complete, deduplicated product discovery for runtime
universe inspection without exposing authenticated or order-mutating methods.

USAGE:
    from coinbase_advanced_client import CoinbaseAdvancedPublic

    client = CoinbaseAdvancedPublic()
    spot = client.list_products(product_type="SPOT")
    futures = client.list_futures()
"""

from __future__ import annotations

from typing import Any

from coinbase.rest import RESTClient

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

_PRODUCTS_SORT_ORDER = "PRODUCTS_SORT_ORDER_LIST_TIME_DESCENDING"
_SUPPORTED_PRODUCT_TYPES = frozenset({"SPOT", "FUTURE", "EQUITY", "OPTION_GROUP", "FUTURE_GROUP"})


# --------------------------------------------------------------------------- #
# Response helpers
# --------------------------------------------------------------------------- #


def _as_dict(value: Any) -> dict[str, Any]:
    """Return an SDK response model or mapping as a plain dictionary."""
    if isinstance(value, dict):
        return dict(value)
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        result = to_dict()
        if isinstance(result, dict):
            return result
    raise TypeError(f"Coinbase response item is not mapping-like: {type(value).__name__}")


def _pagination(response: Any) -> dict[str, Any]:
    """Return the SDK's currently untyped pagination payload."""
    value = getattr(response, "pagination", None)
    if value is None and isinstance(response, dict):
        value = response.get("pagination")
    return _as_dict(value) if value is not None else {}


def _products(response: Any) -> list[Any]:
    """Return product rows from an SDK model or mapping response."""
    value = getattr(response, "products", None)
    if value is None and isinstance(response, dict):
        value = response.get("products")
    return list(value or [])


def _candles(response: Any) -> list[Any]:
    """Return candle rows from an SDK model or mapping response."""
    value = getattr(response, "candles", None)
    if value is None and isinstance(response, dict):
        value = response.get("candles")
    return list(value or [])


# --------------------------------------------------------------------------- #
# Public catalog client
# --------------------------------------------------------------------------- #


class CoinbaseAdvancedPublic:
    """Credential-free, read-only Coinbase Advanced product catalog client."""

    def __init__(self, *, timeout: int = 30) -> None:
        self._rest = RESTClient(timeout=timeout, rate_limit_headers=True)

    def list_products(
        self,
        *,
        product_type: str,
        page_size: int = 250,
        contract_expiry_type: str | None = None,
        expiring_contract_status: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return every public product for one explicit type/filter set.

        Coinbase pages may repeat products. Results are therefore deduplicated
        by canonical ``product_id`` while preserving the first returned row.
        """
        normalized_type = product_type.upper()
        if normalized_type not in _SUPPORTED_PRODUCT_TYPES:
            raise ValueError(f"unsupported Coinbase product_type: {product_type!r}")
        if page_size <= 0:
            raise ValueError("page_size must be positive")

        by_id: dict[str, dict[str, Any]] = {}
        cursor: str | None = None
        used_cursors: set[str] = set()

        while True:
            request: dict[str, Any] = {
                "limit": page_size,
                "product_type": normalized_type,
                "contract_expiry_type": contract_expiry_type,
                "expiring_contract_status": expiring_contract_status,
                "products_sort_order": _PRODUCTS_SORT_ORDER,
            }
            if cursor is not None:
                request["cursor"] = cursor

            response = self._rest.get_public_products(**request)
            for item in _products(response):
                product = _as_dict(item)
                product_id = product.get("product_id")
                if not isinstance(product_id, str) or not product_id:
                    raise ValueError("Coinbase product is missing canonical product_id")
                by_id.setdefault(product_id, product)

            pagination = _pagination(response)
            if not pagination.get("has_next", False):
                break
            next_cursor = pagination.get("next_cursor")
            if not isinstance(next_cursor, str) or not next_cursor:
                raise RuntimeError("Coinbase pagination has_next=true without next_cursor")
            if next_cursor in used_cursors:
                raise RuntimeError("Coinbase pagination repeated a cursor")
            used_cursors.add(next_cursor)
            cursor = next_cursor

        return list(by_id.values())

    def list_futures(self, *, include_expired: bool = False, page_size: int = 250) -> list[dict[str, Any]]:
        """Return the union of expiring and perpetual public futures."""
        expiring_status = "STATUS_ALL" if include_expired else "STATUS_UNEXPIRED"
        expiring = self.list_products(
            product_type="FUTURE",
            page_size=page_size,
            contract_expiry_type="EXPIRING",
            expiring_contract_status=expiring_status,
        )
        perpetual = self.list_products(
            product_type="FUTURE",
            page_size=page_size,
            contract_expiry_type="PERPETUAL",
        )
        return list({row["product_id"]: row for row in [*expiring, *perpetual]}.values())

    def get_candles(
        self,
        *,
        product_id: str,
        start: int,
        end: int,
        granularity: str = "ONE_DAY",
        limit: int = 350,
    ) -> list[dict[str, Any]]:
        """Return one public candle window for an exact canonical product."""
        if not product_id or "-" not in product_id:
            raise ValueError("product_id must be a canonical Coinbase pair")
        if start >= end:
            raise ValueError("candle start must precede end")
        if limit <= 0 or limit > 350:
            raise ValueError("candle limit must be between 1 and 350")
        response = self._rest.get_public_candles(
            product_id=product_id,
            start=str(start),
            end=str(end),
            granularity=granularity,
            limit=limit,
        )
        return [_as_dict(item) for item in _candles(response)]
