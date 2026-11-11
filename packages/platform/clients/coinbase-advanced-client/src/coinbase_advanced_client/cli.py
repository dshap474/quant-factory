"""Print public Coinbase Advanced products from a cursor-complete snapshot.

USAGE:
    qf-coinbase-products --product-type SPOT --head 10 --descending
    qf-coinbase-products --product-type FUTURE --head 10 --descending
"""

from __future__ import annotations

import argparse

from .catalog import CoinbaseAdvancedPublic

# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="List public Coinbase Advanced products.")
    parser.add_argument(
        "--product-type",
        choices=("SPOT", "FUTURE", "EQUITY", "OPTION_GROUP", "FUTURE_GROUP"),
        required=True,
    )
    parser.add_argument("--head", type=int, default=None, help="Print only the first N sorted products.")
    parser.add_argument("--descending", action="store_true", help="Sort product IDs in descending alphabetical order.")
    parser.add_argument(
        "--include-expired-futures",
        action="store_true",
        help="Include expired expiring contracts when product type is FUTURE.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the public product-list command."""
    args = _parser().parse_args(argv)
    if args.head is not None and args.head <= 0:
        raise SystemExit("--head must be positive")

    client = CoinbaseAdvancedPublic()
    if args.product_type == "FUTURE":
        products = client.list_futures(include_expired=args.include_expired_futures)
    else:
        products = client.list_products(product_type=args.product_type)

    product_ids = sorted(
        (str(product["product_id"]) for product in products),
        reverse=args.descending,
    )
    selected = product_ids[: args.head] if args.head is not None else product_ids
    print(f"{args.product_type} products: {len(product_ids)}")
    for product_id in selected:
        print(product_id)
    return 0


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


if __name__ == "__main__":
    raise SystemExit(main())
