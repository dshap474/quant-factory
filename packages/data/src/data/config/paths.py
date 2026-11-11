"""Path helpers for the data package."""

from __future__ import annotations

from pathlib import Path

from config import QUANT_DB_ROOT as REPO_QUANT_DB_ROOT

QUANT_DB_ROOT = REPO_QUANT_DB_ROOT


def resolve_db_root(db_root: str | Path | None) -> Path:
    """Resolve an optional db_root override into a Path."""
    if db_root is None:
        return QUANT_DB_ROOT
    return Path(db_root)
