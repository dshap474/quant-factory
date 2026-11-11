"""Safe public exceptions for Blockworks API failures.

USAGE: from blockworks_client import BlockworksAPIError
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Public failure categories
# --------------------------------------------------------------------------- #


class BlockworksError(Exception):
    """Base class for client failures."""


class BlockworksConfigError(BlockworksError, ValueError):
    """Invalid local configuration or unsupported request arguments."""


class BlockworksTransportError(BlockworksError):
    """A network operation failed before an API response was received."""


class BlockworksAPIError(BlockworksError):
    """The provider returned an unsuccessful HTTP status."""

    def __init__(
        self, status: int, request_id: str | None = None, detail: str | None = None, *, retry_after: str | None = None
    ):
        self.status = status
        self.request_id = request_id
        self.detail = detail
        self.retry_after = retry_after
        suffix = f"; request_id={request_id}" if request_id else ""
        explanation = f": {detail}" if detail else ""
        super().__init__(f"Blockworks API returned HTTP {status}{explanation}{suffix}")


class BlockworksDecodeError(BlockworksError):
    """The provider returned malformed or structurally inconsistent content."""


class BlockworksPaginationError(BlockworksError):
    """A page iterator could not make safe forward progress."""
