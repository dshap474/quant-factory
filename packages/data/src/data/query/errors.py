"""Public exception types for safe parquet query operations."""

from __future__ import annotations


class QueryError(Exception):
    """Base class for data query failures."""


class QueryPathError(QueryError):
    """Raised when a query path is missing, unsafe, or unsupported."""


class QueryValidationError(QueryError):
    """Raised when query parameters do not match the target dataset."""
