"""Schema/contract index helpers.

This module reads ``packages/platform/config/SCHEMA_INDEX.yaml`` and exposes
domain-level pointers used by tooling.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import yaml  # type: ignore[import-untyped]

SCHEMA_INDEX_PATH = Path(__file__).resolve().parents[2] / "SCHEMA_INDEX.yaml"


def resolve_schema_index_path(path: str | Path | None = None) -> Path:
    """Resolve schema index path (defaults to package SCHEMA_INDEX.yaml)."""
    if path is None:
        return SCHEMA_INDEX_PATH
    return Path(path)


def load_schema_index(path: str | Path | None = None) -> dict[str, Any]:
    """Load schema index YAML into a dict."""
    resolved = resolve_schema_index_path(path)
    if not resolved.exists():
        return {"version": 1, "domains": {}}

    with open(resolved, encoding="utf-8") as f:
        loaded = cast(dict[str, Any], yaml.safe_load(f) or {})
    if "domains" not in loaded:
        loaded["domains"] = {}
    return loaded


def get_domain_index(domain: str, path: str | Path | None = None) -> dict[str, Any] | None:
    """Get a single domain entry from the schema index."""
    index = load_schema_index(path)
    domains = cast(dict[str, dict[str, Any]], index.get("domains", {}))
    return domains.get(domain)
