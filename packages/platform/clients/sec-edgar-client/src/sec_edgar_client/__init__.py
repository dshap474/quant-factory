"""Public API for sec-edgar-client."""

from .adapter import (
    SECEdgarClientAdapter,
)
from .api import SECEdgarClient

__all__ = ["SECEdgarClientAdapter", "SECEdgarClient"]
