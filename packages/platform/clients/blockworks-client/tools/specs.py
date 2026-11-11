"""Validate pinned Blockworks specs and regenerate the compact GET route registry.

USAGE: python tools/specs.py [--check]
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import io
import json
from datetime import date
from pathlib import Path

# --------------------------------------------------------------------------- #
# Source inventory and validation
# --------------------------------------------------------------------------- #

ROOT = Path(__file__).resolve().parents[1]
SPEC_NAMES = ("data-api", "charts", "token-unlocks", "monitoring", "monitoring-watchlists")
SPEC_URLS = {
    "data-api": "https://docs.blockworks.com/api-reference/data-api/openapi.json",
    "charts": "https://docs.blockworks.com/api-reference/charts/openapi.json",
    "token-unlocks": "https://docs.blockworks.com/api-reference/token-unlocks/openapi.json",
    "monitoring": "https://docs.blockworks.com/api-reference/monitoring/openapi.json",
    "monitoring-watchlists": "https://docs.blockworks.com/api-reference/monitoring/watchlists-openapi.json",
}


def _validate_refs(document: dict[str, object], name: str) -> None:
    def walk(value: object) -> None:
        if isinstance(value, dict):
            ref = value.get("$ref")
            if ref is not None:
                if not isinstance(ref, str) or not ref.startswith("#/"):
                    raise ValueError(f"{name}: external or invalid reference: {ref!r}")
                target: object = document
                for token in ref[2:].split("/"):
                    token = token.replace("~1", "/").replace("~0", "~")
                    if not isinstance(target, dict) or token not in target:
                        raise ValueError(f"{name}: unresolved reference: {ref}")
                    target = target[token]
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(document)


def apply_overrides(documents: dict[str, dict]) -> dict[str, dict]:
    """Apply only reviewed nullability additions to copies of the public specs."""
    effective = copy.deepcopy(documents)
    config = json.loads((ROOT / "specs" / "overrides.json").read_text())
    if config.get("version") != 1:
        raise ValueError("unsupported override version")
    seen: set[tuple[str, str]] = set()
    for change in config["overrides"]:
        name, pointer = change["spec"], change["pointer"]
        if name not in effective or not pointer.startswith("#/") or not change.get("reason"):
            raise ValueError("invalid override scope")
        adjustment = change["change"]
        if (
            adjustment != {"nullable": True}
            and adjustment != {"nullable": True, "inlineAllOf": "#/components/schemas/UnlockEventTranche"}
        ) or (name, pointer) in seen:
            raise ValueError("only unique scoped nullable additions are permitted")
        seen.add((name, pointer))
        target = effective[name]
        try:
            for token in pointer[2:].split("/"):
                target = target[token.replace("~1", "/").replace("~0", "~")]
        except (KeyError, TypeError):
            raise ValueError(f"stale override target: {name} {pointer}") from None
        if adjustment.get("inlineAllOf"):
            reference = adjustment["inlineAllOf"]
            if (
                name != "token-unlocks-openapi.json"
                or pointer != "#/components/schemas/UnlockEvent/properties/dailyLinearRateChange"
                or target.get("allOf") != [{"$ref": reference}]
                or target.get("nullable") is not True
            ):
                raise ValueError("stale scoped nullable reference correction")
            referenced = effective[name]
            for token in reference[2:].split("/"):
                referenced = referenced[token]
            description = target.get("description")
            target.clear()
            target.update(copy.deepcopy(referenced))
            target["nullable"] = True
            if description:
                target["description"] = description
            continue
        if not isinstance(target, dict) or "type" not in target or target.get("nullable"):
            raise ValueError(f"override no longer needed or invalid: {name} {pointer}")
        target.update(change["change"])
    return effective


# --------------------------------------------------------------------------- #
# Deterministic generated artifacts
# --------------------------------------------------------------------------- #


def _method_for(path: str) -> str:
    if path.startswith("/query/tabular/"):
        return "tabular.catalog" if path.endswith("/catalog") else ("tabular.get" if "{" in path else "tabular.list")
    if path.startswith("/query/timeseries/"):
        return (
            "timeseries.catalog"
            if path.endswith("/catalog")
            else ("timeseries.single" if path.count("{") == 2 else "timeseries.batch")
        )
    methods = {
        "/v1/charts": "charts.list",
        "/v1/charts/{visualizationId}/data": "charts.data",
        "/token-unlocks/v1/allocations": "unlocks.allocations",
        "/token-unlocks/v1/assets": "unlocks.assets",
        "/token-unlocks/v1/assets/{assetId}/events": "unlocks.events",
        "/token-unlocks/v1/assets/{assetId}/unlocks": "unlocks.unlocks",
        "/token-unlocks/v1/assets/{assetId}/vesting-schedule": "unlocks.vesting_schedule",
        "/monitoring/v2/categories": "monitoring.categories",
        "/monitoring/v2/developments": "monitoring.developments",
        "/monitoring/v2/developments/{developmentId}": "monitoring.development",
        "/monitoring/v2/events": "monitoring.events",
        "/monitoring/v2/events/{eventId}": "monitoring.event",
        "/monitoring/v2/monitoring-views": "monitoring.views",
        "/monitoring/v2/monitoring-views/{monitoringViewId}": "monitoring.view",
        "/monitoring/v2/monitoring-views/{monitoringViewId}/developments": "monitoring.view_developments",
        "/monitoring/v2/monitoring-views/{monitoringViewId}/events": "monitoring.view_events",
        "/monitoring/v2/monitoring-views/all/developments": "monitoring.all_view_developments",
        "/monitoring/v2/monitoring-views/all/events": "monitoring.all_view_events",
        "/user-management/v1/watchlists": "watchlists.list",
        "/user-management/v1/watchlists/{id}": "watchlists.get",
    }
    return methods[path]


def _artifacts(retrieved_date: str | None = None) -> dict[Path, str]:
    routes: dict[str, dict[str, object]] = {}
    hashes: dict[str, str] = {}
    coverage: list[tuple[str, str, str, str]] = []
    writes = 0
    documents: dict[str, dict] = {}
    for name in SPEC_NAMES:
        path = ROOT / "specs" / "upstream" / f"{name}-openapi.json"
        raw = path.read_bytes()
        hashes[path.name] = hashlib.sha256(raw).hexdigest()
        document = json.loads(raw)
        documents[path.name] = document
        _validate_refs(document, name)
        if document.get("servers", [{}])[0].get("url") != "https://api.blockworks.com":
            raise ValueError(f"{name}: server origin changed")
        for template, item in document["paths"].items():
            writes += len(set(item) & {"post", "put", "patch", "delete"})
            if "get" not in item:
                continue
            if template in routes:
                raise ValueError(f"duplicate GET template: {template}")
            operation = item["get"]
            params = item.get("parameters", []) + operation.get("parameters", [])
            query = [p for p in params if p["in"] == "query"]
            path_params = [p for p in params if p["in"] == "path"]
            route = {
                "family": name,
                "method": _method_for(template),
                "query": tuple(p["name"] for p in query),
                "path": tuple(p["name"] for p in path_params),
                "required": tuple(p["name"] for p in query if p.get("required")),
                "enums": {
                    p["name"]: tuple(p.get("schema", {}).get("enum", []))
                    for p in params
                    if p.get("schema", {}).get("enum")
                },
            }
            routes[template] = route
            coverage.append((name, template, operation.get("operationId", ""), route["method"]))
    if len(routes) != 226 or writes != 4:
        raise ValueError(f"expected 226 GETs and 4 excluded writes; got {len(routes)} and {writes}")
    apply_overrides(documents)
    lines = [
        '"""Pinned GET route metadata generated from public Blockworks OpenAPI snapshots.\n',
        "\nUSAGE: from blockworks_client._generated import ROUTES\n",
        '"""\n\n',
        "from typing import TypedDict\n\n",
        "# --------------------------------------------------------------------------- #\n",
        "# Generated route registry\n",
        "# --------------------------------------------------------------------------- #\n\n\n",
        "# fmt: off\n",
        "class RouteMetadata(TypedDict):\n",
        "    family: str\n    method: str\n    query: tuple[str, ...]\n    path: tuple[str, ...]\n",
        "    required: tuple[str, ...]\n    enums: dict[str, tuple[str, ...]]\n\n\n",
        "ROUTES: dict[str, RouteMetadata] = {\n",
    ]
    for template, route in sorted(routes.items()):
        lines.append(f"    {template!r}: {route!r},\n")
    lines += ["}\n\n", "# fmt: on\n"]
    previous = json.loads((ROOT / "specs" / "manifest.json").read_text())
    if retrieved_date is None:
        if previous["sha256"] != hashes:
            raise ValueError("changed spec snapshots require an explicit --retrieved-date YYYY-MM-DD")
        retrieved_date = previous["retrieved_date"]
    date.fromisoformat(retrieved_date)
    manifest = {
        "retrieved_date": retrieved_date,
        "source_urls": SPEC_URLS,
        "sha256": hashes,
        "get_operations": 226,
        "excluded_write_operations": 4,
    }
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(("family", "route_template", "operation_id", "public_method"))
    writer.writerows(sorted(coverage))
    return {
        ROOT / "src" / "blockworks_client" / "_generated.py": "".join(lines),
        ROOT / "specs" / "manifest.json": json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        ROOT / "docs" / "coverage.csv": buffer.getvalue(),
    }


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail when generated files are stale")
    parser.add_argument("--retrieved-date", help="actual retrieval date for changed snapshots, YYYY-MM-DD")
    args = parser.parse_args()
    artifacts = _artifacts(args.retrieved_date)
    for path, contents in artifacts.items():
        if args.check:
            if not path.exists() or path.read_text() != contents:
                raise SystemExit(f"stale generated artifact: {path.relative_to(ROOT)}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(contents)
    print("Validated five specs, 226 GET routes, and four excluded mutations.")


if __name__ == "__main__":
    main()
