"""qf-config: shared config/logging utilities for quant-factory."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .schema_index import (
    SCHEMA_INDEX_PATH,
    get_domain_index,
    load_schema_index,
    resolve_schema_index_path,
)
from .settings import (
    COINBASE_ADVANCED_PORTFOLIO_UUID,
    COINBASE_ADVANCED_TRADING_ENABLED,
    QUANT_DB_ROOT,
    QUANT_SIGNALS_DIR,
    ROOT_QUANT_FACTORY,
    get_repo_root,
)

__version__ = "0.1.0"


def get_logger(name: str) -> logging.Logger:
    """Return a standard library logger for package-local logging."""
    return logging.getLogger(name)


__all__ = [
    "COINBASE_ADVANCED_PORTFOLIO_UUID",
    "COINBASE_ADVANCED_TRADING_ENABLED",
    "QUANT_DB_ROOT",
    "QUANT_SIGNALS_DIR",
    "ROOT_QUANT_FACTORY",
    "SCHEMA_INDEX_PATH",
    "get_domain_index",
    "get_logger",
    "get_repo_root",
    "load_schema_index",
    "resolve_schema_index_path",
]
