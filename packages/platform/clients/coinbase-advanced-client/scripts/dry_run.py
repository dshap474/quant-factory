"""Coinbase Advanced Trade dry-run: config + read-only + preview only.

Purpose: verify credentials, list non-zero balances (no key material / no
account UUIDs), fetch BTC-USDC, size a ~$0.01 market buy, and call ``preview_order``. Never places or
cancels orders — this script contains no call to ``create_order``.

Success is strict: every step passes, the preview response carries an
explicit empty ``errs`` list, and ``order_total`` / ``commission_total`` are
present. Anything else exits non-zero.

USAGE (from monorepo root; root venv resolves workspace members):

    uv run python packages/platform/clients/coinbase-advanced-client/scripts/dry_run.py
"""

from __future__ import annotations

import sys
from decimal import Decimal

from coinbase_advanced_client import CoinbaseAdvanced

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

NOTIONAL_USD = Decimal("0.01")
PRODUCT_ID = "BTC-USDC"


def _step(ok: bool, label: str, detail: str = "") -> None:
    if ok:
        print(f"PASS {label}" + (f" — {detail}" if detail else ""))
    else:
        print(f"FAIL {label}" + (f" — {detail}" if detail else ""))
        raise SystemExit(1)


def _required(obj: object, name: str) -> object:
    """Return a typed-SDK response attribute, failing closed when absent/empty."""
    value = getattr(obj, name, None)
    if value is None or value == "":
        raise ValueError(f"response field {name!r} missing")
    return value


def _nonzero_balances(accounts: list[object]) -> list[tuple[str, str]]:
    """Return (currency, available) for accounts with non-zero available balance."""
    rows: list[tuple[str, str]] = []
    for acct in accounts:
        currency = getattr(acct, "currency", "?")
        available = getattr(acct, "available_balance", None)
        value = getattr(available, "value", None) if available is not None else None
        if value is None and isinstance(available, dict):
            value = available.get("value")
        if value is None:
            continue
        if Decimal(str(value)) != 0:
            rows.append((str(currency), str(value)))
    return rows


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #


def main() -> int:
    # 1. Construct client from config
    try:
        client = CoinbaseAdvanced()
    except Exception as exc:
        _step(False, "construct CoinbaseAdvanced()", str(exc))
    _step(True, "construct CoinbaseAdvanced()")

    # 2. Accounts (no UUIDs / keys)
    try:
        response = client.get_accounts()
        raw_accounts = _required(response, "accounts")
        if not isinstance(raw_accounts, list):
            raise TypeError(f"accounts must be a list, got {type(raw_accounts)!r}")
        accounts = [item for item in raw_accounts]
        currencies = ", ".join(f"{c}={v}" for c, v in _nonzero_balances(accounts)) or "(none)"
        _step(True, "get_accounts()", f"{len(accounts)} accounts; non-zero available: {currencies}")
    except Exception as exc:
        _step(False, "get_accounts()", str(exc))

    # 3. Product BTC-USDC
    try:
        product = client.get_product(PRODUCT_ID)
        price = Decimal(str(_required(product, "price")))
        base_increment = Decimal(str(_required(product, "base_increment")))
        _step(True, "get_product(BTC-USDC)", f"price={price} base_increment={base_increment}")
    except Exception as exc:
        _step(False, "get_product(BTC-USDC)", str(exc))

    # 4. Size a ~$0.01 BTC market buy, rounded down to the base increment
    qty = (NOTIONAL_USD / price // base_increment) * base_increment
    if qty <= 0:
        _step(False, "size ~$0.01 BTC buy", f"rounded quantity is {qty}")
    order_configuration = {"market_market_ioc": {"base_size": f"{qty:f}"}}
    _step(True, "size ~$0.01 BTC buy", f"side=BUY base_size={qty:f}")

    # 5. Preview only — never create_order. Fail closed: errs must be an
    # explicit empty list and both total fields must be present.
    try:
        preview = client.preview_order(
            product_id=PRODUCT_ID,
            side="BUY",
            order_configuration=order_configuration,
        )
        errs = getattr(preview, "errs", None)
        if errs is None:
            _step(False, "preview_order", "response has no 'errs' field (cannot prove clean preview)")
        if errs:
            _step(False, "preview_order", f"errs={errs!r}")
        order_total = _required(preview, "order_total")
        commission_total = _required(preview, "commission_total")
        _step(
            True,
            "preview_order",
            f"errs empty; order_total={order_total} commission_total={commission_total}",
        )
    except SystemExit:
        raise
    except Exception as exc:
        _step(False, "preview_order", str(exc))

    print("DRY RUN PASS — no orders were placed (create_order is never called by this script)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
