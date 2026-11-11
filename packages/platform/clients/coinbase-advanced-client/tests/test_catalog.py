"""Hermetic tests for cursor-complete public Coinbase product discovery.

USAGE:
    uv run --project packages/platform/clients/coinbase-advanced-client \
      pytest packages/platform/clients/coinbase-advanced-client/tests/test_catalog.py -q
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from coinbase_advanced_client.catalog import CoinbaseAdvancedPublic

# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


class _StubRest:
    def __init__(self, pages: list[SimpleNamespace]) -> None:
        self.pages = list(pages)
        self.calls: list[dict[str, Any]] = []

    def get_public_products(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        return self.pages.pop(0)

    def get_public_candles(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        return self.pages.pop(0)


def _page(ids: list[str], *, has_next: bool, next_cursor: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        products=[{"product_id": product_id} for product_id in ids],
        pagination={"has_next": has_next, "next_cursor": next_cursor},
    )


def _client(stub: _StubRest) -> CoinbaseAdvancedPublic:
    client = CoinbaseAdvancedPublic.__new__(CoinbaseAdvancedPublic)
    client._rest = stub
    return client


# --------------------------------------------------------------------------- #
# Catalog behavior
# --------------------------------------------------------------------------- #


def test_list_products_traverses_cursor_and_deduplicates() -> None:
    stub = _StubRest(
        [
            _page(["BTC-USD", "ETH-USD"], has_next=True, next_cursor="next"),
            _page(["ETH-USD", "SOL-USD"], has_next=False),
        ]
    )
    products = _client(stub).list_products(product_type="spot", page_size=2)

    assert [row["product_id"] for row in products] == ["BTC-USD", "ETH-USD", "SOL-USD"]
    assert "cursor" not in stub.calls[0]
    assert stub.calls[1]["cursor"] == "next"
    assert stub.calls[0]["product_type"] == "SPOT"


def test_list_products_rejects_missing_next_cursor() -> None:
    stub = _StubRest([_page(["BTC-USD"], has_next=True)])
    with pytest.raises(RuntimeError, match="without next_cursor"):
        _client(stub).list_products(product_type="SPOT")


def test_list_products_rejects_repeated_cursor() -> None:
    stub = _StubRest(
        [
            _page(["BTC-USD"], has_next=True, next_cursor="same"),
            _page(["ETH-USD"], has_next=True, next_cursor="same"),
        ]
    )
    with pytest.raises(RuntimeError, match="repeated a cursor"):
        _client(stub).list_products(product_type="SPOT")


def test_list_futures_unions_expiring_and_perpetual() -> None:
    stub = _StubRest(
        [
            _page(["BIT-27"], has_next=False),
            _page(["BTC-PERP-INTX"], has_next=False),
        ]
    )
    products = _client(stub).list_futures()

    assert {row["product_id"] for row in products} == {"BIT-27", "BTC-PERP-INTX"}
    assert stub.calls[0]["contract_expiry_type"] == "EXPIRING"
    assert stub.calls[0]["expiring_contract_status"] == "STATUS_UNEXPIRED"
    assert stub.calls[1]["contract_expiry_type"] == "PERPETUAL"


def test_get_candles_forwards_exact_public_window() -> None:
    stub = _StubRest([SimpleNamespace(candles=[{"start": "1", "open": "100"}])])

    candles = _client(stub).get_candles(product_id="BTC-USDC", start=1, end=2)

    assert candles == [{"start": "1", "open": "100"}]
    assert stub.calls == [
        {
            "product_id": "BTC-USDC",
            "start": "1",
            "end": "2",
            "granularity": "ONE_DAY",
            "limit": 350,
        }
    ]


def test_get_candles_rejects_invalid_window() -> None:
    with pytest.raises(ValueError, match="start must precede"):
        _client(_StubRest([])).get_candles(product_id="BTC-USDC", start=2, end=2)
