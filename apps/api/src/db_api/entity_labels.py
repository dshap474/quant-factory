"""Human labels for opaque entity identifiers (e.g. UUID asset keys) shown in dataset views.

An installation declares rules in its extension root's ``entity-labels.json``; the core
names no vendor. Each rule says: datasets under ``path_prefix`` (in ``scope``) carry an
identifier column ``column`` whose values are the ``key`` column of the lookup parquet
``source``; the label is that row's ``label`` column, followed by ``detail`` when it adds
something. Identifiers with no lookup row keep their raw value.

USAGE:
    configure_entity_labels(load_entity_label_rules(extension_root / "entity-labels.json"))
    entity_labels(db_root, "data", "raw/1d/provider/prices.parquet", "asset_key", ["a1b2…"])
    # -> {"a1b2…": "BTC · Bitcoin"}
    page_labels(db_root, "data", "raw/1d/provider/prices.parquet", frame)
    # -> {"asset_key": {"title": "symbol · name", "values": {"a1b2…": "BTC · Bitcoin"}}}

    entity-labels.json:
    [{"scope": "data", "path_prefix": "raw/1d/provider/", "column": "asset_key",
      "source": "raw/1d/provider/reference/assets.parquet", "key": "asset_key",
      "label": "symbol", "detail": "name"}]
"""

# --------------------------------------------------------------------------- #
# Imports
# --------------------------------------------------------------------------- #

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import polars as pl

from .parquet import fingerprint, read_parquet_frame

# --------------------------------------------------------------------------- #
# Rules
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class EntityLabelRule:
    scope: str
    path_prefix: str
    column: str
    source: str
    key: str
    label: str
    detail: str | None = None


_RULES: tuple[EntityLabelRule, ...] = ()


def load_entity_label_rules(path: Path) -> tuple[EntityLabelRule, ...]:
    """Parse the instance's rule list; a missing file means none."""
    if not path.exists():
        return ()
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"Entity label rules must be a list: {path}")
    return tuple(EntityLabelRule(**item) for item in raw)


def configure_entity_labels(rules: Iterable[EntityLabelRule]) -> None:
    """Install the active rules (called once at app construction)."""
    global _RULES
    _RULES = tuple(rules)
    _cached_lookup.cache_clear()


def _rule_for(scope: str, path: str, column: str) -> EntityLabelRule | None:
    normalized = path.strip("/")
    return next(
        (
            rule
            for rule in _RULES
            if rule.scope == scope and rule.column == column and normalized.startswith(rule.path_prefix)
        ),
        None,
    )


# --------------------------------------------------------------------------- #
# Lookup
# --------------------------------------------------------------------------- #


def entity_labels(
    db_root: Path,
    scope: str,
    path: str,
    column: str | None,
    values: Iterable[str | None],
) -> dict[str, str]:
    """Labels for the given identifier values; empty when no rule covers the column."""
    rule = _rule_for(scope, path, column) if column else None
    if rule is None:
        return {}
    source = db_root / rule.scope / rule.source
    if not source.exists():
        return {}
    lookup = _cached_lookup(rule, str(db_root), fingerprint(source))
    return {value: lookup[value] for value in values if value is not None and value in lookup}


def page_labels(db_root: Path, scope: str, path: str, frame: pl.DataFrame) -> dict[str, dict[str, object]]:
    """Label maps for every labelled column of a page of rows, for a table's label columns.

    The lookup file itself is skipped: its label columns are already in the row.
    """
    normalized = path.strip("/")
    result: dict[str, dict[str, object]] = {}
    for column in frame.columns:
        rule = _rule_for(scope, normalized, column)
        if rule is None or rule.source == normalized:
            continue
        values = frame.get_column(column).cast(pl.String).drop_nulls().unique().to_list()
        labels = entity_labels(db_root, scope, normalized, column, values)
        if labels:
            title = " · ".join(part for part in (rule.label, rule.detail) if part)
            result[column] = {"title": title, "values": labels}
    return result


def entity_label(db_root: Path, scope: str, path: str, column: str | None, value: str | None) -> str | None:
    """One value's label, or None."""
    if value is None:
        return None
    return entity_labels(db_root, scope, path, column, [value]).get(value)


@lru_cache(maxsize=8)
def _cached_lookup(rule: EntityLabelRule, db_root: str, signature: object) -> dict[str, str]:
    del signature  # cache key only: a rewritten lookup file gets a fresh map
    source = Path(db_root) / rule.scope / rule.source
    columns = [rule.key, rule.label, *([rule.detail] if rule.detail else [])]
    frame = read_parquet_frame(source, columns=columns, db_root=Path(db_root)).select(
        pl.col(rule.key).cast(pl.String).alias("key"),
        pl.col(rule.label).cast(pl.String).alias("label"),
        (pl.col(rule.detail).cast(pl.String) if rule.detail else pl.lit(None, pl.String)).alias("detail"),
    )
    lookup: dict[str, str] = {}
    for key, label, detail in frame.drop_nulls("key").iter_rows():
        if key in lookup:
            continue
        parts = [part for part in (label, detail) if part and part.strip()]
        if len(parts) == 2 and parts[0].casefold() == parts[1].casefold():
            parts = parts[:1]
        if parts:
            lookup[key] = " · ".join(parts)
    return lookup
