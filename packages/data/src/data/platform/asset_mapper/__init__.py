"""Reusable canonical asset-identity mechanics.

USAGE:
    from data.platform.asset_mapper import resolve_asset_ids
"""

from .core import (
    ASSET_MAPPER_CATEGORY,
    ASSET_MAPPER_RESOLUTION,
    IDENTIFIER_TYPES,
    asset_identity_pack_lock,
    asset_mapper_assets_path,
    asset_mapper_identifiers_path,
    asset_mapper_meta_path,
    asset_mapper_root,
    normalize_assets,
    normalize_identifiers,
    validate_assets,
    validate_identifiers,
    validate_pack_generation,
)
from .resolution import load_asset_identity, resolve_asset_ids

__all__ = [
    "ASSET_MAPPER_CATEGORY",
    "ASSET_MAPPER_RESOLUTION",
    "IDENTIFIER_TYPES",
    "asset_identity_pack_lock",
    "asset_mapper_assets_path",
    "asset_mapper_identifiers_path",
    "asset_mapper_meta_path",
    "asset_mapper_root",
    "load_asset_identity",
    "normalize_assets",
    "normalize_identifiers",
    "resolve_asset_ids",
    "validate_assets",
    "validate_identifiers",
    "validate_pack_generation",
]
