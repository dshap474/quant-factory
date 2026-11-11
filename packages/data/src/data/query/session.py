"""Explicit DuckDB session lifecycle for repeated read-only lake queries."""

from __future__ import annotations

import re
from pathlib import Path
from types import TracebackType
from typing import Any

import duckdb

from ._sql import quote_literal
from .errors import QueryValidationError
from .models import QueryEngineSettings

_SAFE_SETTING = re.compile(r"^[A-Za-z0-9_./ -]+$")
_READ_PREFIXES = ("select ", "explain ")


class DuckDBQuerySession:
    """Reusable in-memory DuckDB connection with validated runtime settings."""

    def __init__(self, settings: QueryEngineSettings | None = None) -> None:
        self.settings = settings or QueryEngineSettings()
        self._connection: duckdb.DuckDBPyConnection | None = None

    def __enter__(self) -> DuckDBQuerySession:
        _ = self._get_connection()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def current_settings(self) -> dict[str, object]:
        """Return the applied DuckDB settings exposed for diagnostics."""
        row = self._get_connection().execute(
            "SELECT "
            "current_setting('threads'), "
            "current_setting('memory_limit'), "
            "current_setting('temp_directory'), "
            "current_setting('preserve_insertion_order')"
        ).fetchone()
        if row is None:
            raise QueryValidationError("DuckDB settings query returned no rows")
        return {
            "threads": row[0],
            "memory_limit": row[1],
            "temp_directory": row[2],
            "preserve_insertion_order": row[3],
        }

    def _execute_generated(
        self,
        sql: str,
        params: list[Any] | tuple[Any, ...] | None = None,
    ) -> duckdb.DuckDBPyConnection:
        """Execute generated read-only query SQL."""
        _validate_generated_read_sql(sql)
        return self._get_connection().execute(sql, params or [])

    def _get_connection(self) -> duckdb.DuckDBPyConnection:
        if self._connection is None:
            self._connection = duckdb.connect(":memory:")
            self._apply_settings(self._connection)
        return self._connection

    def close(self) -> None:
        """Close the underlying DuckDB connection if it is open."""
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def _apply_settings(self, connection: duckdb.DuckDBPyConnection) -> None:
        settings = self.settings
        if settings.threads is not None:
            if settings.threads < 1:
                raise QueryValidationError("threads must be >= 1")
            connection.execute(f"SET threads = {int(settings.threads)}")

        if settings.memory_limit is not None:
            connection.execute(f"SET memory_limit = {quote_literal(_safe_setting(settings.memory_limit))}")

        if settings.temp_directory is not None:
            temp_directory = Path(settings.temp_directory)
            temp_directory.mkdir(parents=True, exist_ok=True)
            connection.execute(f"SET temp_directory = {quote_literal(_safe_setting(str(temp_directory)))}")

        if settings.preserve_insertion_order is not None:
            value = "true" if settings.preserve_insertion_order else "false"
            connection.execute(f"SET preserve_insertion_order = {value}")


def _safe_setting(value: str) -> str:
    if not _SAFE_SETTING.fullmatch(value):
        raise QueryValidationError("DuckDB setting contains unsupported characters")
    return value


def _validate_generated_read_sql(sql: str) -> None:
    normalized = sql.strip().lower()
    if ";" in normalized:
        raise QueryValidationError("Generated query SQL must be a single statement")
    if not normalized.startswith(_READ_PREFIXES):
        raise QueryValidationError("Generated query SQL must be read-only SELECT or EXPLAIN")
