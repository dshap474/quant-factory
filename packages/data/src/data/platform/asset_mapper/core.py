"""Canonical asset-identity paths, validation, fingerprints, and locking.

USAGE:
    from data.platform.asset_mapper.core import asset_mapper_assets_path
"""

from __future__ import annotations

import fcntl
import hashlib
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import polars as pl
import yaml

from data.extensions import EXTENSIONS_ROOT
from data.platform.errors import DatasetContractError

# --------------------------------------------------------------------------- #
# Contract
# --------------------------------------------------------------------------- #

ASSET_MAPPER_CATEGORY = "reference/asset-identity"
ASSET_MAPPER_RESOLUTION = "derived"

ASSET_COLUMNS = ("asset_id", "asset_class", "name")
IDENTIFIER_COLUMNS = (
    "asset_id",
    "identifier_type",
    "identifier_value",
    "venue",
    "valid_from",
    "valid_to",
)
# Identifier types of the provider clients that ship with this repository, plus FIGI. Every other
# provider declares its types in its data extension (``identifier_types.yaml``).
_CORE_IDENTIFIER_TYPES = frozenset({"yfinance_symbol", "composite_figi", "share_class_figi"})
_IDENTIFIER_CASES = frozenset({"lower", "upper", "integer"})


def _extension_identifier_types() -> dict[str, str]:
    """Provider identifier types declared by data extensions, as ``{type: "lower" | "upper" | "integer"}``.

    Each ``extensions/datasets/<family>/identifier_types.yaml`` maps a type to the form its values
    are stored in (lowercase, uppercase, or a canonical integer string), so any other provider's
    identifiers live with that provider's extension.
    """
    declared: dict[str, str] = {}
    for path in sorted(EXTENSIONS_ROOT.glob("datasets/*/identifier_types.yaml")):
        for name, case in (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).items():
            if case not in _IDENTIFIER_CASES:
                raise DatasetContractError(
                    "Identifier type case must be lower, upper or integer", identifier_type=name, path=str(path)
                )
            declared[str(name)] = case
    return declared


_EXTENSION_IDENTIFIER_TYPES = _extension_identifier_types()
IDENTIFIER_TYPES = frozenset(_CORE_IDENTIFIER_TYPES | _EXTENSION_IDENTIFIER_TYPES.keys())
LOWERCASE_IDENTIFIER_TYPES = frozenset(
    name for name, case in _EXTENSION_IDENTIFIER_TYPES.items() if case == "lower"
)
INTEGER_IDENTIFIER_TYPES = frozenset(
    name for name, case in _EXTENSION_IDENTIFIER_TYPES.items() if case == "integer"
)
# Every other identifier type stores and looks up uppercase.
UPPERCASE_IDENTIFIER_TYPES = frozenset(IDENTIFIER_TYPES - INTEGER_IDENTIFIER_TYPES - LOWERCASE_IDENTIFIER_TYPES)

PACK_LOCK_NAME = ".asset-identity.pack.lock"


# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #


def asset_mapper_root(db_root: Path) -> Path:
    """Return the canonical derived asset-identity directory."""
    return db_root / "data" / "derived" / Path(ASSET_MAPPER_CATEGORY)


def asset_mapper_assets_path(db_root: Path) -> Path:
    """Return the canonical assets parquet path."""
    return asset_mapper_root(db_root) / "assets.parquet"


def asset_mapper_identifiers_path(db_root: Path) -> Path:
    """Return the canonical identifiers parquet path."""
    return asset_mapper_root(db_root) / "identifiers.parquet"


def asset_mapper_meta_path(db_root: Path) -> Path:
    """Return the canonical metadata path."""
    return asset_mapper_root(db_root) / "meta.yaml"


def asset_mapper_pack_lock_path(db_root: Path) -> Path:
    """Return the pack coordination lock path."""
    return asset_mapper_root(db_root) / PACK_LOCK_NAME


# --------------------------------------------------------------------------- #
# Fingerprints and pack locking
# --------------------------------------------------------------------------- #


def file_sha256(path: Path) -> str:
    """Return the hex SHA-256 digest of a file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def compute_artifact_fingerprints(db_root: Path) -> dict[str, str]:
    """Fingerprint the three canonical pack artifacts."""
    assets_path = asset_mapper_assets_path(db_root)
    identifiers_path = asset_mapper_identifiers_path(db_root)
    meta_path = asset_mapper_meta_path(db_root)
    missing = [str(path) for path in (assets_path, identifiers_path, meta_path) if not path.exists()]
    if missing:
        raise DatasetContractError("Canonical asset identity pack is incomplete", missing=missing)
    return {
        "assets_sha256": file_sha256(assets_path),
        "identifiers_sha256": file_sha256(identifiers_path),
        "meta_sha256": file_sha256(meta_path),
    }


@contextmanager
def asset_identity_pack_lock(db_root: Path, *, shared: bool = False) -> Iterator[None]:
    """Coordinate readers/writers over the three-artifact identity pack."""
    root = asset_mapper_root(db_root)
    root.mkdir(parents=True, exist_ok=True)
    lock_path = asset_mapper_pack_lock_path(db_root)
    flags = fcntl.LOCK_SH if shared else fcntl.LOCK_EX
    with lock_path.open("a", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), flags)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def validate_pack_generation(
    db_root: Path,
    *,
    expected_seed_fingerprint: str | None = None,
) -> dict[str, Any]:
    """Fail when the canonical pack is incomplete, inconsistent, or unexpectedly seeded."""
    assets_path = asset_mapper_assets_path(db_root)
    identifiers_path = asset_mapper_identifiers_path(db_root)
    meta_path = asset_mapper_meta_path(db_root)
    present = (assets_path.exists(), identifiers_path.exists(), meta_path.exists())
    if not all(present):
        raise DatasetContractError(
            "Canonical asset identity is incomplete",
            assets_exists=present[0],
            identifiers_exists=present[1],
            meta_exists=present[2],
        )
    meta = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
    fingerprints = meta.get("fingerprints") or {}
    seed_fp = fingerprints.get("seed_sha256")
    assets_fp = fingerprints.get("assets_sha256")
    identifiers_fp = fingerprints.get("identifiers_sha256")
    if not seed_fp or not assets_fp or not identifiers_fp:
        raise DatasetContractError(
            "Canonical asset identity generation lacks content fingerprints",
            fingerprints=fingerprints,
        )
    if file_sha256(assets_path) != assets_fp:
        raise DatasetContractError("Canonical assets artifact does not match generation fingerprint")
    if file_sha256(identifiers_path) != identifiers_fp:
        raise DatasetContractError(
            "Canonical identifiers artifact does not match generation fingerprint"
        )
    if expected_seed_fingerprint is not None and seed_fp != expected_seed_fingerprint:
        raise DatasetContractError(
            "Canonical asset identity generation is stale relative to checked-in seeds",
            canonical_seed_sha256=seed_fp,
            current_seed_sha256=expected_seed_fingerprint,
        )
    return meta


# --------------------------------------------------------------------------- #
# Normalization and validation
# --------------------------------------------------------------------------- #


def normalize_assets(frame: pl.DataFrame) -> pl.DataFrame:
    """Normalize an asset table into its canonical schema."""
    _require_columns(frame, ASSET_COLUMNS, table="assets")
    normalized = frame.select(
        pl.col("asset_id").cast(pl.String).str.strip_chars(),
        pl.col("asset_class").cast(pl.String).str.strip_chars().str.to_lowercase(),
        pl.col("name").cast(pl.String).str.strip_chars(),
    ).sort("asset_id")
    validate_assets(normalized)
    return normalized


def normalize_identifiers(frame: pl.DataFrame) -> pl.DataFrame:
    """Normalize an effective-dated identifier table into its canonical schema."""
    _require_columns(frame, IDENTIFIER_COLUMNS, table="identifiers")
    normalized = frame.select(
        pl.col("asset_id").cast(pl.String).str.strip_chars(),
        pl.col("identifier_type").cast(pl.String).str.strip_chars().str.to_lowercase(),
        pl.col("identifier_value").cast(pl.String).str.strip_chars(),
        pl.col("venue").cast(pl.String).str.strip_chars().str.to_uppercase(),
        pl.col("valid_from").cast(pl.Date),
        pl.col("valid_to").cast(pl.Date),
    ).with_columns(
        pl.when(pl.col("venue") == "").then(None).otherwise(pl.col("venue")).alias("venue")
    )
    normalized = _normalize_identifier_values(normalized).sort(
        "identifier_type", "identifier_value", "venue", "valid_from"
    )
    validate_identifiers(normalized)
    return normalized


def validate_assets(frame: pl.DataFrame) -> None:
    """Fail when canonical asset rows violate identity invariants."""
    _require_columns(frame, ASSET_COLUMNS, table="assets")
    for column in ASSET_COLUMNS:
        if frame.filter(pl.col(column).is_null() | (pl.col(column) == "")).height:
            raise DatasetContractError("Asset identity contains empty required values", column=column)
    duplicates = frame.group_by("asset_id").len().filter(pl.col("len") > 1)
    if duplicates.height:
        raise DatasetContractError(
            "Asset identity contains duplicate asset_id values",
            asset_ids=duplicates.get_column("asset_id").to_list(),
        )
    bad_prefixes = frame.filter(~pl.col("asset_id").str.starts_with(pl.col("asset_class") + ":"))
    if bad_prefixes.height:
        raise DatasetContractError(
            "asset_id must start with its asset_class prefix",
            asset_ids=bad_prefixes.get_column("asset_id").to_list()[:20],
        )


def validate_identifiers(frame: pl.DataFrame, assets: pl.DataFrame | None = None) -> None:
    """Fail when identifier rows are invalid, unknown, duplicate, or overlapping."""
    _require_columns(frame, IDENTIFIER_COLUMNS, table="identifiers")
    for column in ("asset_id", "identifier_type", "identifier_value", "valid_from"):
        if frame.filter(pl.col(column).is_null() | (pl.col(column).cast(pl.String) == "")).height:
            raise DatasetContractError("Asset identifiers contain empty required values", column=column)

    unknown_types = sorted(set(frame.get_column("identifier_type").to_list()) - IDENTIFIER_TYPES)
    if unknown_types:
        raise DatasetContractError("Asset identifiers contain unsupported types", identifier_types=unknown_types)

    invalid_intervals = frame.filter(
        pl.col("valid_to").is_not_null() & (pl.col("valid_to") <= pl.col("valid_from"))
    )
    if invalid_intervals.height:
        raise DatasetContractError("Asset identifier valid_to must be after valid_from")

    if assets is not None:
        unknown_assets = frame.join(assets.select("asset_id"), on="asset_id", how="anti")
        if unknown_assets.height:
            raise DatasetContractError(
                "Asset identifiers reference unknown assets",
                asset_ids=unknown_assets.get_column("asset_id").unique().sort().to_list()[:20],
            )

    previous_by_key: dict[tuple[str, str | None, str], tuple[object, str]] = {}
    for row in frame.sort("identifier_type", "venue", "identifier_value", "valid_from").iter_rows(named=True):
        key = (row["identifier_type"], row["venue"], row["identifier_value"])
        previous = previous_by_key.get(key)
        if previous is not None:
            previous_end, previous_asset = previous
            if previous_end is None or row["valid_from"] < previous_end:
                raise DatasetContractError(
                    "Asset identifier validity intervals overlap",
                    identifier_type=key[0],
                    venue=key[1],
                    identifier_value=key[2],
                    asset_ids=[previous_asset, row["asset_id"]],
                )
        previous_by_key[key] = (row["valid_to"], row["asset_id"])


def _require_columns(frame: pl.DataFrame, required: tuple[str, ...], *, table: str) -> None:
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise DatasetContractError(f"Asset identity {table} table is missing columns", missing_columns=missing)


def identifier_value_expression(identifier_type: str, column: str) -> pl.Expr:
    """Shared Polars normalization for stored and lookup identifier values."""
    expression = pl.col(column).cast(pl.String).str.strip_chars()
    if identifier_type in INTEGER_IDENTIFIER_TYPES:
        return expression.cast(pl.Int64, strict=False).cast(pl.String)
    if identifier_type in UPPERCASE_IDENTIFIER_TYPES:
        return expression.str.to_uppercase()
    if identifier_type in LOWERCASE_IDENTIFIER_TYPES:
        return expression.str.to_lowercase()
    raise DatasetContractError("Unsupported asset identifier type", identifier_type=identifier_type)


def normalize_identifier_value(identifier_type: str, value: object) -> str:
    """Normalize one identifier value; same rules as storage and resolution lookup."""
    if identifier_type not in IDENTIFIER_TYPES:
        raise DatasetContractError("Unsupported asset identifier type", identifier_type=identifier_type)
    text = str(value).strip()
    if identifier_type in INTEGER_IDENTIFIER_TYPES:
        try:
            return str(int(text))
        except ValueError as exc:
            raise DatasetContractError(
                f"{identifier_type} must be a numeric string",
                identifier_value=text,
            ) from exc
    if identifier_type in LOWERCASE_IDENTIFIER_TYPES:
        return text.lower()
    return text.upper()


def _normalize_identifier_values(frame: pl.DataFrame) -> pl.DataFrame:
    if frame.is_empty():
        return frame
    parts: list[pl.DataFrame] = []
    for identifier_type in sorted(set(frame.get_column("identifier_type").to_list())):
        subset = frame.filter(pl.col("identifier_type") == identifier_type)
        parts.append(
            subset.with_columns(
                identifier_value_expression(str(identifier_type), "identifier_value").alias(
                    "identifier_value"
                )
            )
        )
    return pl.concat(parts, how="vertical_relaxed")


# --------------------------------------------------------------------------- #
# Metadata
# --------------------------------------------------------------------------- #


def build_meta(
    assets: pl.DataFrame,
    identifiers: pl.DataFrame,
    *,
    source: str,
    seed_sha256: str | None = None,
    assets_sha256: str | None = None,
    identifiers_sha256: str | None = None,
) -> dict[str, Any]:
    """Build compact materialization metadata."""
    type_counts = Counter(identifiers.get_column("identifier_type").to_list())
    meta: dict[str, Any] = {
        "category": ASSET_MAPPER_CATEGORY,
        "resolution": ASSET_MAPPER_RESOLUTION,
        "source": source,
        "stats": {
            "asset_count": assets.height,
            "identifier_count": identifiers.height,
            "asset_class_counts": dict(Counter(assets.get_column("asset_class").to_list())),
            "identifier_type_counts": dict(type_counts),
            "earliest_valid_from": str(identifiers.get_column("valid_from").min()),
            "latest_valid_from": str(identifiers.get_column("valid_from").max()),
        },
        "fingerprints": {"seed_sha256": seed_sha256},
    }
    if assets_sha256 is not None:
        meta["fingerprints"]["assets_sha256"] = assets_sha256
    if identifiers_sha256 is not None:
        meta["fingerprints"]["identifiers_sha256"] = identifiers_sha256
    return meta


__all__ = [
    "ASSET_MAPPER_CATEGORY",
    "ASSET_MAPPER_RESOLUTION",
    "IDENTIFIER_TYPES",
    "asset_identity_pack_lock",
    "asset_mapper_assets_path",
    "asset_mapper_identifiers_path",
    "asset_mapper_meta_path",
    "asset_mapper_pack_lock_path",
    "asset_mapper_root",
    "build_meta",
    "compute_artifact_fingerprints",
    "file_sha256",
    "identifier_value_expression",
    "normalize_assets",
    "normalize_identifier_value",
    "normalize_identifiers",
    "validate_assets",
    "validate_identifiers",
    "validate_pack_generation",
]
