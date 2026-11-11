"""Catalog API router for browsing db/data.

USAGE: mount this router at /api/catalog to browse logical dataset families.
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

import yaml
from fastapi import APIRouter, Query, Request
from features.api import PUBLISHABLE_FAMILIES

from ..catalog_labels import RawFamilyRule, catalog_path_labels, human_label, raw_family_rules
from ..config import settings
from ..dataset_browser import (
    compute_scope_overview,
    compute_scope_stats,
    list_directory,
    preview_markdown,
)
from ..dataset_charts import (
    ChartBundleRequest,
    get_chart_values,
    preview_chart,
    preview_chart_bundle,
)
from ..dataset_index import get_parquet_index, refresh_parquet_indexes
from ..dataset_profiles import profile_parquet_feature_detail, profile_parquet_features
from ..orderbook_charts import orderbook_depth, orderbook_heatmap, orderbook_historical_scale
from ..responses import polars_json_response, polars_nested_json_response, ttl_cache

router = APIRouter()


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    return loaded if isinstance(loaded, dict) else {}


def _domain_from_category(category: str) -> str | None:
    parts = category.strip("/").split("/")
    if not parts or not parts[0]:
        return None
    if parts[0] == "index" and len(parts) > 1:
        return parts[1]
    if parts[0] == "cross_sectional" and len(parts) > 1:
        return parts[1]
    return parts[0]


def _scope_path(data_path: str) -> tuple[str, str] | None:
    normalized = data_path.strip("/")
    if normalized.startswith("data/"):
        return "data", normalized.removeprefix("data/")
    if normalized.startswith("features/"):
        return "features", normalized.removeprefix("features/")
    return None


def _logical_item(
    *,
    kind: str,
    layer: str,
    category: str,
    category_meta: dict[str, Any],
    options: list[dict[str, Any]],
) -> dict[str, Any]:
    resolutions = sorted(
        options,
        key=lambda option: (option["resolution"], option.get("version") or "latest"),
    )
    default = resolutions[0]["resolution"] if resolutions else None
    description = category_meta.get("description")
    label = category_meta.get("label")
    return {
        "id": f"{kind}:{category}",
        "kind": kind,
        "layer": layer,
        "label": label if isinstance(label, str) else human_label(category),
        "category_path": category,
        "description": description if isinstance(description, str) else None,
        "domain": _domain_from_category(category),
        "status": category_meta.get("status", "active"),
        "asset_column": bool(category_meta.get("asset_column", False)),
        "default_resolution": default,
        "resolutions": resolutions,
    }


def _feature_package_root(package_dir: Path) -> str:
    """Registry category a feature package owns, as its registered runner declares it.

    A family ships its runner module at `<package>/src/<module>`; the package's root
    is the shortest category whose runner it ships, and its other categories become
    options below it. Reading the registry keeps this router free of a hardcoded
    directory-name table. The slug conversion stays as the fallback for a package
    with no registered runner.
    """
    owned = [
        family.category
        for family in PUBLISHABLE_FAMILIES.values()
        if (package_dir / "src" / family.runner_module.split(".")[0]).is_dir()
    ]
    if owned:
        return min(owned, key=lambda category: (category.count("/"), category))
    return package_dir.name.replace("-", "_")


def _feature_option_version(category: str, package_root: str) -> str | None:
    """Option label a registry category carries inside the family that owns it.

    A family publishes its canonical panel at its own category and every other
    output — engine versions (`v001`), presets (`variant-a`), intraday panels
    (`intraday`) — one segment below it. The label is the sub-path itself,
    so a family's alternative panels are selectable beside the canonical one
    instead of being dropped for not looking like a version.
    """
    if category == package_root:
        return "latest"
    prefix = f"{package_root}/"
    if category.startswith(prefix):
        return category.removeprefix(prefix) or "latest"
    return None


def _logical_feature_registry_items(db_root: Path) -> list[dict[str, Any]]:
    registry = _load_yaml(db_root / "features" / "REGISTRY.yaml")
    categories = registry.get("categories", {})
    features = registry.get("features", {})
    if not isinstance(categories, dict) or not isinstance(features, dict):
        return []

    by_category: dict[str, list[dict[str, Any]]] = {}
    for key, entry in features.items():
        if not isinstance(key, str) or "/" not in key or not isinstance(entry, dict):
            continue
        resolution, category = key.split("/", 1)
        scoped = _scope_path(str(entry.get("data_path", "")))
        if scoped is None or scoped[0] != "features":
            continue
        path = db_root / entry["data_path"]
        by_category.setdefault(category, []).append(
            {
                "resolution": resolution,
                "scope": scoped[0],
                "path": scoped[1],
                "version": "latest",
                "updated_at": entry.get("updated_at"),
                "description": entry.get("description") if isinstance(entry.get("description"), str) else None,
                "exists": path.exists(),
            }
        )

    return [
        _logical_item(
            kind="feature_set",
            layer="features",
            category=category,
            category_meta=categories.get(category, {}),
            options=options,
        )
        for category, options in sorted(by_category.items())
    ]


def _logical_feature_items(db_root: Path) -> list[dict[str, Any]]:
    packages_root = Path(settings.repo_root) / "packages" / "features" / "extensions" / "lib"
    if not packages_root.exists():
        return _logical_feature_registry_items(db_root)

    registry = _load_yaml(db_root / "features" / "REGISTRY.yaml")
    categories = registry.get("categories", {})
    features = registry.get("features", {})
    if not isinstance(categories, dict) or not isinstance(features, dict):
        return []

    package_roots = {
        _feature_package_root(package_dir): package_dir.name
        for package_dir in sorted(packages_root.iterdir())
        if package_dir.is_dir() and not package_dir.name.startswith((".", "_"))
    }
    if not package_roots:
        return _logical_feature_registry_items(db_root)

    by_package: dict[str, list[dict[str, Any]]] = {package_root: [] for package_root in package_roots}
    for key, entry in features.items():
        if not isinstance(key, str) or "/" not in key or not isinstance(entry, dict):
            continue
        resolution, category = key.split("/", 1)
        package_root = next(
            (root for root in package_roots if _feature_option_version(category, root) is not None),
            None,
        )
        if package_root is None:
            continue
        scoped = _scope_path(str(entry.get("data_path", "")))
        if scoped is None or scoped[0] != "features":
            continue
        path = db_root / entry["data_path"]
        by_package[package_root].append(
            {
                "resolution": resolution,
                "scope": scoped[0],
                "path": scoped[1],
                "version": _feature_option_version(category, package_root) or "latest",
                "updated_at": entry.get("updated_at"),
                "description": entry.get("description") if isinstance(entry.get("description"), str) else None,
                "exists": path.exists(),
            }
        )

    return [
        _logical_item(
            kind="feature_set",
            layer="features",
            category=package_root,
            category_meta={**categories.get(package_root, {}), "label": human_label(package_roots[package_root])},
            options=options,
        )
        for package_root, options in sorted(by_package.items())
    ]


def _logical_derived_items(db_root: Path) -> list[dict[str, Any]]:
    registry = _load_yaml(db_root / "data" / "derived" / "REGISTRY.yaml")
    categories = registry.get("categories", {})
    if not isinstance(categories, dict):
        categories = {}

    registered: dict[str, Any] = {}
    for section in ("datasets", "features"):
        section_entries = registry.get(section, {})
        if isinstance(section_entries, dict):
            registered.update(section_entries)

    by_category: dict[str, list[dict[str, Any]]] = {}
    for key, entry in registered.items():
        if not isinstance(key, str) or "/" not in key or not isinstance(entry, dict):
            continue
        resolution, category = key.split("/", 1)
        scoped = _scope_path(str(entry.get("data_path", "")))
        if scoped is None or scoped[0] != "data":
            continue
        path = db_root / entry["data_path"]
        by_category.setdefault(category, []).append(
            {
                "resolution": resolution,
                "scope": scoped[0],
                "path": scoped[1],
                "version": "latest",
                "updated_at": entry.get("updated_at"),
                "exists": path.exists(),
            }
        )

    derived_root = db_root / "data" / "derived"
    if derived_root.exists():
        for entry in get_parquet_index(db_root, "data"):
            if not entry.relative_path.parts or entry.relative_path.parts[0] != "derived":
                continue
            parquet_file = entry.path
            category = _category_from_partitioned_file(derived_root, parquet_file)
            if category is None:
                continue
            resolution, category_path = category
            path = str(parquet_file.relative_to(db_root / "data"))
            if any(option["path"] == path for option in by_category.get(category_path, [])):
                continue
            by_category.setdefault(category_path, []).append(
                {
                    "resolution": resolution,
                    "scope": "data",
                    "path": path,
                    "version": "latest",
                    "updated_at": None,
                    "exists": True,
                }
            )

    return [
        _logical_item(
            kind="dataset",
            layer="derived",
            category=category,
            category_meta=categories.get(category, {}),
            options=options,
        )
        for category, options in sorted(by_category.items())
    ]


def _category_from_partitioned_file(root: Path, parquet_file: Path) -> tuple[str, str] | None:
    relative = parquet_file.relative_to(root)
    if len(relative.parts) < 3:
        return None
    resolution = relative.parts[0]
    if not (resolution[:1].isdigit() or resolution == "tick"):
        return None
    category_parts = list(relative.parts[1:-1])
    if not category_parts or any(part.startswith("_") for part in category_parts):
        return None
    if parquet_file.name != "data.parquet":
        category_parts.append(parquet_file.stem)
    return resolution, "/".join(category_parts)


def _raw_category_from_file(raw_root: Path, parquet_file: Path) -> tuple[str, str] | None:
    partitioned = _category_from_partitioned_file(raw_root, parquet_file)
    if partitioned is not None:
        return partitioned

    relative = parquet_file.relative_to(raw_root)
    if len(relative.parts) != 2:
        return None
    contract = _load_yaml(parquet_file.parent / "CONTRACT.yaml")
    datasets = contract.get("datasets")
    if not isinstance(datasets, dict):
        return None
    expected_root = Path("data") / "raw" / relative.parent
    matches: list[tuple[str, str]] = []
    for entry in datasets.values():
        if not isinstance(entry, dict) or entry.get("target") != "canonical_data_raw":
            continue
        resolution = entry.get("resolution")
        canonical_root = Path(str(entry.get("canonical_root", "")))
        if (
            isinstance(resolution, str)
            and resolution[:1].isdigit()
            and entry.get("canonical_artifact") == parquet_file.name
            and canonical_root.parts[-len(expected_root.parts) :] == expected_root.parts
        ):
            matches.append((resolution, relative.parent.as_posix()))
    return matches[0] if len(matches) == 1 else None


RAW_LIKE_LAYERS = ("raw", "corrected")


def _raw_like_id(layer: str, category: str) -> str:
    """A corrected mirror shares its raw dataset's category path, so its id names the layer."""
    return f"dataset:{category}" if layer == "raw" else f"dataset:{layer}/{category}"


def _logical_raw_items(db_root: Path, layer: str = "raw") -> list[dict[str, Any]]:
    """Raw datasets, or with ``layer="corrected"`` their corrected mirrors (same paths under data/corrected)."""
    layer_root = db_root / "data" / layer
    if not layer_root.exists():
        return []

    by_category: dict[str, list[dict[str, Any]]] = {}
    for entry in get_parquet_index(db_root, "data"):
        if not entry.relative_path.parts or entry.relative_path.parts[0] != layer:
            continue
        parquet_file = entry.path
        category = _raw_category_from_file(layer_root, parquet_file)
        if category is None:
            continue
        resolution, category_path = category
        by_category.setdefault(category_path, []).append(
            {
                "resolution": resolution,
                "scope": "data",
                "path": str(parquet_file.relative_to(db_root / "data")),
                "version": "latest",
                "updated_at": None,
                "exists": True,
            }
        )

    return [
        {
            **_logical_item(
                kind="dataset",
                layer=layer,
                category=category,
                category_meta={
                    "description": f"{layer.capitalize()} {category.replace('/', ' ')} dataset",
                    "status": "active",
                    "asset_column": False,
                },
                options=options,
            ),
            "id": _raw_like_id(layer, category),
        }
        for category, options in sorted(by_category.items())
    ]


def _raw_family(category: str, rules: tuple[RawFamilyRule, ...] = ()) -> str:
    """Collapse physical raw paths into stable dataset-family paths; registered rules win."""
    parts = category.strip("/").split("/")
    for rule in rules:
        if (family := rule.family(parts)) is not None:
            return family

    family_parts: list[str] = []
    for part in parts:
        if part == "_runs" or part.startswith("dt="):
            break
        if part.isdigit() and (
            len(part) == 4 or (len(part) == 2 and any(value.isdigit() and len(value) == 4 for value in parts))
        ):
            continue
        if part == "data" or part.startswith(("chunk-", "seed-", "quarter=")):
            continue
        family_parts.append(part)
    return "/".join(family_parts)


def _raw_family_label(family: str, labels: dict[str, str]) -> str:
    if family in labels:
        return labels[family]
    parts = family.split("/")
    if len(parts) > 1:
        parts = parts[1:]
    return " / ".join(labels.get(part, human_label(part)) for part in parts)


def _logical_raw_summary_items(
    items: list[dict[str, Any]], labels: dict[str, str], rules: tuple[RawFamilyRule, ...] = ()
) -> list[dict[str, Any]]:
    by_family: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        family = _raw_family(str(item["category_path"]), rules)
        by_family.setdefault(family, []).append(item)

    summaries: list[dict[str, Any]] = []
    for family, members in by_family.items():
        by_resolution: dict[str, dict[str, Any]] = {}
        for member in members:
            for option in cast(list[dict[str, Any]], member["resolutions"]):
                by_resolution.setdefault(str(option["resolution"]), option)
        resolutions = sorted(by_resolution)
        representative_options = [by_resolution[resolution] for resolution in resolutions]
        label = _raw_family_label(family, labels)
        layer = str(members[0]["layer"])
        summaries.append(
            {
                "id": _raw_like_id(layer, family),
                "kind": "dataset",
                "layer": layer,
                "label": label,
                "category_path": family,
                "description": f"{layer.capitalize()} {label} dataset",
                "domain": _domain_from_category(family),
                "status": "active",
                "asset_column": any(bool(member["asset_column"]) for member in members),
                "default_resolution": resolutions[0] if len(resolutions) == 1 else None,
                "resolutions": representative_options,
            }
        )
    return sorted(summaries, key=lambda item: (str(item["domain"] or ""), str(item["label"])))


@ttl_cache(seconds=300, maxsize=4)
def _cached_logical_catalog(db_root: Path | None = None) -> dict[str, object]:
    root = db_root or settings.db_root
    items = [
        *_logical_raw_items(root),
        *_logical_raw_items(root, "corrected"),
        *_logical_derived_items(root),
        *_logical_feature_items(root),
    ]
    items.sort(key=lambda item: (str(item["kind"]), str(item["domain"] or ""), str(item["label"])))
    return {"items": items}


def _raw_group(item: dict[str, Any]) -> str | None:
    if item.get("layer") not in RAW_LIKE_LAYERS:
        return None
    parts = str(item.get("category_path", "")).split("/")
    return parts[1] if len(parts) > 1 else None


@router.get("/labels")
def get_catalog_labels(request: Request) -> dict[str, str]:
    """Return presentation metadata without scanning the lake."""
    return request.app.state.catalog_labels


@router.get("/logical")
def get_logical_catalog(
    request: Request,
    kind: Literal["dataset", "feature_set"] | None = None,
    layer: Literal["raw", "corrected", "derived", "features"] | None = None,
    domain: str | None = None,
    group: str | None = None,
    family: str | None = None,
    summary: bool = False,
    q: str = Query("", description="Case-insensitive catalog search"),
    offset: int = Query(0, ge=0),
    limit: int | None = Query(None, ge=1, le=1000),
) -> dict[str, object]:
    """Return logical datasets and feature sets backed by canonical parquet paths."""
    # Feature navigation needs registry-backed families, not a walk of every
    # raw/derived dataset. Read this small registry directly, outside the shared
    # whole-catalog cache lock, preserving the same ordering and facets.
    if kind == "feature_set":
        all_items = sorted(
            _logical_feature_items(settings.db_root),
            key=lambda item: (str(item["domain"] or ""), str(item["label"])),
        )
    else:
        all_items = list(_cached_logical_catalog(settings.db_root)["items"])
    kind_items = [item for item in all_items if kind is None or item["kind"] == kind]
    layers = sorted({str(item["layer"]) for item in kind_items})
    layer_items = [item for item in kind_items if layer is None or item["layer"] == layer]
    if summary and layer in RAW_LIKE_LAYERS:
        layer_items = _logical_raw_summary_items(
            layer_items, request.app.state.catalog_labels, raw_family_rules(request.app)
        )
    labels = request.app.state.catalog_labels
    # Copy cached records before decorating: labels belong to this application instance.
    layer_items = [{**item} for item in layer_items]
    for item in layer_items:
        category = str(item["category_path"])
        parts = category.split("/")
        raw = item["layer"] in RAW_LIKE_LAYERS
        item["category_labels"] = catalog_path_labels(f"raw/{category}" if raw else category, labels)[1 if raw else 0 :]
        if category in labels:
            item["label"] = labels[category]
        elif parts[-1] in labels and item["label"] == human_label(parts[-1]):
            item["label"] = labels[parts[-1]]
    layer_items.sort(key=lambda item: (str(item["domain"] or ""), str(item["label"])))
    domains = sorted({str(item["domain"]) for item in layer_items if item.get("domain")})
    domain_items = [item for item in layer_items if domain is None or item.get("domain") == domain]
    groups = sorted({value for item in domain_items if (value := _raw_group(item))})
    filtered = [item for item in domain_items if group is None or _raw_group(item) == group]
    if family is not None:
        rules = raw_family_rules(request.app)
        filtered = [item for item in filtered if _raw_family(str(item["category_path"]), rules) == family]
    normalized_query = q.strip().casefold()
    if normalized_query:
        filtered = [
            item
            for item in filtered
            if normalized_query
            in (
                " ".join(str(item.get(field) or "") for field in ("label", "category_path", "description", "domain"))
                + " "
                + " ".join(item["category_labels"])
            ).casefold()
        ]
    total = len(filtered)
    page_items = filtered[offset:] if limit is None else filtered[offset : offset + limit]
    return {
        "items": page_items,
        "total": total,
        "offset": offset,
        "limit": limit,
        "facets": {"layers": layers, "domains": domains, "groups": groups},
    }


@router.post("/refresh")
def refresh_catalog() -> dict[str, object]:
    """Rebuild read-only in-memory indexes and invalidate discovery caches."""
    from .features import clear_feature_browser_cache

    _cached_logical_catalog.cache_clear()
    _cached_catalog_stats.cache_clear()
    _cached_catalog_overview.cache_clear()
    clear_feature_browser_cache()
    scopes = refresh_parquet_indexes(settings.db_root)
    _cached_logical_catalog(settings.db_root)
    return {
        "status": "refreshed",
        "refreshed_at": datetime.now(UTC).isoformat(),
        "scopes": scopes,
    }


@ttl_cache(seconds=30)
def _cached_profile_data_parquet_features(
    db_root: Path,
    path: str,
    query: str,
    family: str,
    sort: str,
    page: int,
    page_size: int,
    entity_column: str | None,
    entity_value: str | None,
    max_spark_points: int,
) -> dict[str, object]:
    return profile_parquet_features(
        db_root,
        "data",
        path,
        query=query,
        family=family,
        sort=cast(
            Literal["schema", "family", "coverage_desc", "missing_desc", "std_desc", "name"],
            sort,
        ),
        page=page,
        page_size=page_size,
        entity_column=entity_column,
        entity_value=entity_value,
        max_spark_points=max_spark_points,
    )


@ttl_cache(seconds=30)
def _cached_profile_data_parquet_feature_detail(
    db_root: Path,
    path: str,
    column: str,
    entity_column: str | None,
    entity_value: str | None,
    max_spark_points: int,
) -> dict[str, object]:
    return profile_parquet_feature_detail(
        db_root,
        "data",
        path,
        column=column,
        entity_column=entity_column,
        entity_value=entity_value,
        max_spark_points=max_spark_points,
    )


def _label_listing(listing: dict[str, Any], labels: dict[str, str]) -> dict[str, Any]:
    path = listing["path"]
    return {
        **listing,
        "path_labels": catalog_path_labels(path, labels),
        "items": [
            {
                **item,
                "label": catalog_path_labels(f"{path}/{item['name']}", labels)[-1] if item["is_dir"] else item["name"],
            }
            for item in listing["items"]
        ],
    }


@router.get("")
def list_root(request: Request) -> dict[str, object]:
    """List contents of db/data root directory."""
    return _label_listing(list_directory(settings.db_root, "data"), request.app.state.catalog_labels)


@router.get("/browse/{path:path}")
def browse_directory(path: str, request: Request) -> dict[str, object]:
    """Browse a directory in db/data."""
    return _label_listing(list_directory(settings.db_root, "data", path), request.app.state.catalog_labels)


@router.get("/markdown/{path:path}")
def preview_data_markdown(path: str) -> dict[str, object]:
    """Preview a markdown file in db/data."""
    return preview_markdown(settings.db_root, "data", path)


@router.get("/chart/{path:path}")
def preview_data_chart(
    path: str,
    metric: str | None = Query(None, description="Numeric metric to plot"),
    entity_column: str | None = Query(None, description="Entity column for tall tables"),
    entity_value: str | None = Query(None, description="Entity value to filter before plotting"),
    max_points: int = Query(2000, ge=50, le=5000, description="Max chart points to return"),
):
    """Build a time-series chart preview for a parquet file in db/data."""
    payload, series = preview_chart(
        settings.db_root,
        "data",
        path,
        metric=metric,
        entity_column=entity_column,
        entity_value=entity_value,
        max_points=max_points,
    )
    payload["series"] = series
    return polars_json_response(payload, df_key="series")


@router.post("/chart-bundle/{path:path}")
def preview_data_chart_bundle(path: str, request: ChartBundleRequest):
    """Build a multi-chart bundle preview for a parquet file in db/data."""
    payload = preview_chart_bundle(
        settings.db_root,
        "data",
        path,
        request=request,
    )
    return polars_nested_json_response(payload)


@router.get("/chart-values/{path:path}")
def preview_data_chart_values(
    path: str,
    entity_column: str = Query(..., description="Entity column to fetch distinct values for"),
    query: str = Query("", description="Case-insensitive substring filter"),
    limit: int = Query(100, ge=1, le=50_000, description="Max values to return"),
    offset: int = Query(0, ge=0, description="Distinct value offset"),
) -> dict[str, object]:
    """Get distinct entity values for a parquet chart selector in db/data."""
    return get_chart_values(
        settings.db_root,
        "data",
        path,
        entity_column=entity_column,
        query=query,
        limit=limit,
        offset=offset,
    )


@router.get("/profile/{path:path}")
def profile_data_parquet_features(
    path: str,
    query: str = Query("", description="Case-insensitive feature-name filter"),
    family: str = Query("all", description="Inferred feature family id"),
    sort: str = Query("schema", description="Feature sort order"),
    page: int = Query(1, ge=1, description="1-based feature page number"),
    page_size: int = Query(100, ge=1, le=250, description="Feature rows per page"),
    entity_column: str | None = Query(None, description="Optional entity column"),
    entity_value: str | None = Query(None, description="Optional entity value"),
    max_spark_points: int = Query(36, ge=1, le=80, description="Max sparkline points"),
) -> dict[str, object]:
    """Profile numeric feature columns for a parquet file in db/data."""
    return _cached_profile_data_parquet_features(
        settings.db_root,
        path,
        query,
        family,
        sort,
        page,
        page_size,
        entity_column,
        entity_value,
        max_spark_points,
    )


@router.get("/profile-detail/{path:path}")
def profile_data_parquet_feature_detail(
    path: str,
    column: str = Query(..., description="Numeric feature column to inspect"),
    entity_column: str | None = Query(None, description="Optional entity column"),
    entity_value: str | None = Query(None, description="Optional entity value"),
    max_spark_points: int = Query(120, ge=20, le=500, description="Max detail sparkline points"),
) -> dict[str, object]:
    """Profile one numeric feature column for a parquet file in db/data."""
    return _cached_profile_data_parquet_feature_detail(
        settings.db_root,
        path,
        column,
        entity_column,
        entity_value,
        max_spark_points,
    )


@ttl_cache(seconds=300, maxsize=4)
def _cached_catalog_stats():
    return compute_scope_stats(settings.db_root, "data")


@ttl_cache(seconds=300, maxsize=4)
def _cached_catalog_overview():
    return compute_scope_overview(settings.db_root, "data")


@router.get("/stats")
def get_catalog_stats() -> dict[str, object]:
    """Get overall statistics about db/data."""
    return _cached_catalog_stats()


@router.get("/overview")
def get_catalog_overview(request: Request) -> dict[str, object]:
    """Get a root-level overview of db/data."""
    labels = request.app.state.catalog_labels

    def decorate(node: dict[str, Any]) -> dict[str, Any]:
        names = catalog_path_labels(node["path"], labels)
        return {
            **node,
            "label": names[-1] if names else node["name"],
            "children": [decorate(child) for child in node.get("children", [])],
        }

    overview = _cached_catalog_overview()
    return {
        **overview,
        "branches": [decorate(node) for node in overview["branches"]],
        "tree": [decorate(node) for node in overview["tree"]],
        "featured_surfaces": [decorate(node) for node in overview["featured_surfaces"]],
    }


# --------------------------------------------------------------------------- #
# Orderbook charts
# --------------------------------------------------------------------------- #


@router.get("/orderbook/heatmap/{path:path}")
def preview_orderbook_heatmap(
    path: str,
    start: int | None = Query(None, ge=0),
    band_percent: float = Query(2, ge=0, le=100),
    hours: int = Query(6, ge=1, le=24),
) -> dict:
    """Sample intact books in a bounded window; bin price levels without averaging time."""
    return orderbook_heatmap(settings.db_root, path, start=start, band_percent=band_percent, hours=hours)


@router.get("/orderbook/depth/{path:path}")
def preview_orderbook_depth(
    path: str,
    timestamp: int = Query(..., ge=0),
    midprice: float = Query(..., gt=0, allow_inf_nan=False),
) -> dict:
    """Return every level of one timestamp/midpoint book, without heatmap binning."""
    return orderbook_depth(settings.db_root, path, timestamp=timestamp, midprice=midprice)


@router.get("/orderbook/historical-scale/{path:path}")
def preview_orderbook_historical_scale(path: str) -> dict:
    """Calibrate fixed-bin percentiles across the same stored order book family."""
    return orderbook_historical_scale(settings.db_root, path)
