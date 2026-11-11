"""Shared ownership marker for venue order identifiers.

USAGE: ``is_owned_client_order_id(order.client_order_id)`` distinguishes
quant-factory orders from foreign account activity.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

OWNERSHIP_PREFIX = "qf."

# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def is_owned_client_order_id(value: str | None) -> bool:
    """True when the client_order_id is in our ownership namespace."""
    return bool(value) and str(value).startswith(OWNERSHIP_PREFIX)
