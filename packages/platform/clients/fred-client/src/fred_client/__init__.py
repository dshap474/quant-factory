"""Public API for fred-client."""

from .adapter import (
    FREDClientAdapter,
)
from .api import FredClient

__all__ = ["FREDClientAdapter", "FredClient"]
