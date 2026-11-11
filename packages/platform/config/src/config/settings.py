"""Environment-backed process settings (paths and trading gates) for standalone quant-factory.

USAGE::

    from config import QUANT_DB_ROOT

Settings come only from the existing process environment. This module never
reads a repository ``.env`` file or resolves provider credentials.
"""

from __future__ import annotations

import os
from pathlib import Path

# --------------------------------------------------------------------------- #
# Repository discovery
# --------------------------------------------------------------------------- #


def get_repo_root() -> Path:
    """Return the repository root path."""
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "pyproject.toml").exists() and (parent / "packages").exists():
            return parent
    for parent in current.parents:
        if (parent / "pyproject.toml").exists() and (parent / "src").exists():
            return parent
    # Fallback for unexpected layouts.
    return current.parents[6]


# --------------------------------------------------------------------------- #
# Environment helpers
# --------------------------------------------------------------------------- #


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def _path_from_env(name: str, default: Path) -> Path:
    raw = os.getenv(name)
    if not raw:
        return default
    return Path(raw).expanduser().resolve()


# --------------------------------------------------------------------------- #
# Runtime settings
# --------------------------------------------------------------------------- #

ROOT_QUANT_FACTORY = get_repo_root()

QUANT_DB_ROOT = _path_from_env("QUANT_DB_ROOT", ROOT_QUANT_FACTORY / "db")
QUANT_SIGNALS_DIR = _path_from_env("QUANT_SIGNALS_DIR", QUANT_DB_ROOT / "signals")

# Trading placement gate: must be exactly "1" for create_order; default off.
COINBASE_ADVANCED_TRADING_ENABLED = _env("COINBASE_ADVANCED_TRADING_ENABLED")
# Optional expected portfolio UUID checked before live arming; empty = unset.
COINBASE_ADVANCED_PORTFOLIO_UUID = _env("COINBASE_ADVANCED_PORTFOLIO_UUID")
