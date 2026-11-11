"""Credential-free example dataset: daily Yahoo Finance prices for BTC and four ETFs.

USAGE: call ``data.api.sync_dataset`` with family ``example`` (see README.md).
"""

from .client import DEFAULT_SYMBOLS, build_raw_prices, derive_prices

# --------------------------------------------------------------------------- #
# Public surface
# --------------------------------------------------------------------------- #

__all__ = ["DEFAULT_SYMBOLS", "build_raw_prices", "derive_prices"]
