"""Read-only strategy version records for the version page's Details tab.

USAGE::

    GET /api/strategy-versions/{family}
    GET /api/strategy-versions/{family}/{version}/records

The first returns one lineage row per version (parent, question, finding, status, headline)
for the family's evolution view; the second returns the version's ``VERSION.toml`` and its
record documents (SPEC, HYPOTHESIS_OUTCOME, REVIEW, CHANGELOG) exactly as the folder holds them.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports
# --------------------------------------------------------------------------- #
import re
import tomllib
from typing import Any

from fastapi import APIRouter, HTTPException
from strategies.records import family_versions, load_version_records

# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #

router = APIRouter()
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


@router.get("/{family}")
def get_family_versions(family: str) -> list[dict[str, Any]]:
    if not _NAME.match(family) or ".." in family:
        raise HTTPException(status_code=400, detail="invalid family")
    try:
        rows = family_versions(family)
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise HTTPException(status_code=409, detail=f"Unreadable records for '{family}'") from exc
    if not rows:
        raise HTTPException(status_code=404, detail=f"No versions for '{family}'")
    return rows


@router.get("/{family}/{version}/records")
def get_version_records(family: str, version: str) -> dict[str, Any]:
    if not all(_NAME.match(name) and ".." not in name for name in (family, version)):
        raise HTTPException(status_code=400, detail="invalid version path")
    try:
        records = load_version_records(family, version)
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise HTTPException(status_code=409, detail=f"Unreadable records for '{family}/{version}'") from exc
    if records is None:
        raise HTTPException(status_code=404, detail=f"No VERSION.toml for '{family}/{version}'")
    return records
