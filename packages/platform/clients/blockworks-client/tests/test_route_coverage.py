"""Independent public-method route coverage derived directly from pinned upstream specs.

USAGE: uv run --package blockworks-client pytest tests/test_route_coverage.py -q
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import unquote

import httpx
import pytest
from blockworks_client import BlockworksClient

# --------------------------------------------------------------------------- #
# Public dispatch independent of generated runtime route metadata
# --------------------------------------------------------------------------- #


def call(client, record):
    template, path, params = record["template"], record["path"], dict(record["params"])
    names = re.findall(r"\{([^}]+)\}", template)
    match = re.fullmatch(re.sub(r"\{[^}]+\}", r"([^/]+)", template), path)
    ids = dict(zip(names, map(unquote, match.groups())))
    if template.startswith("/query/tabular/"):
        model = template.split("/")[3]
        if model == "catalog":
            return client.tabular.catalog(**{{"publicOnly": "public_only"}.get(k, k): v for k, v in params.items()})
        aliases = {
            "page": "page",
            "pageSize": "page_size",
            "selections": "selections",
            "sortBy": "sort_by",
            "sortDirection": "sort_direction",
        }
        options = {aliases[k]: params.pop(k) for k in list(params) if k in aliases}
        if names:
            assert not params
            return client.tabular.get(model, next(iter(ids.values())), **options)
        return client.tabular.list(model, filters=params, **options)
    if template.startswith("/query/timeseries/"):
        model = template.split("/")[3]
        if model == "catalog":
            return client.timeseries.catalog(**{{"publicOnly": "public_only"}.get(k, k): v for k, v in params.items()})
        if len(names) == 2:
            return client.timeseries.single(model, ids["granularity"], ids[names[1]], **params)
        if isinstance(params.get("series"), str):
            params["series"] = params["series"].split(",")
        return client.timeseries.batch(model, ids["granularity"], **params)
    funcs = {
        "/v1/charts": client.charts.list,
        "/v1/charts/{visualizationId}/data": client.charts.data,
        "/token-unlocks/v1/allocations": client.unlocks.allocations,
        "/token-unlocks/v1/assets": client.unlocks.assets,
        "/token-unlocks/v1/assets/{assetId}/events": client.unlocks.events,
        "/token-unlocks/v1/assets/{assetId}/unlocks": client.unlocks.unlocks,
        "/token-unlocks/v1/assets/{assetId}/vesting-schedule": client.unlocks.vesting_schedule,
        "/monitoring/v2/categories": client.monitoring.categories,
        "/monitoring/v2/developments": client.monitoring.developments,
        "/monitoring/v2/developments/{developmentId}": client.monitoring.development,
        "/monitoring/v2/events": client.monitoring.events,
        "/monitoring/v2/events/{eventId}": client.monitoring.event,
        "/monitoring/v2/monitoring-views": client.monitoring.views,
        "/monitoring/v2/monitoring-views/{monitoringViewId}": client.monitoring.view,
        "/monitoring/v2/monitoring-views/{monitoringViewId}/developments": client.monitoring.view_developments,
        "/monitoring/v2/monitoring-views/{monitoringViewId}/events": client.monitoring.view_events,
        "/monitoring/v2/monitoring-views/all/developments": client.monitoring.all_view_developments,
        "/monitoring/v2/monitoring-views/all/events": client.monitoring.all_view_events,
        "/user-management/v1/watchlists": client.watchlists.list,
        "/user-management/v1/watchlists/{id}": client.watchlists.get,
    }
    if template.endswith("/allocations"):
        params["asset_id"] = params.pop("assetId")
    return funcs[template](*ids.values(), **params)


# --------------------------------------------------------------------------- #
# Synthetic, independent upstream cases and exact wire assertions
# --------------------------------------------------------------------------- #


def cases():
    root = Path(__file__).resolve().parents[1]
    records = []
    for file in sorted((root / "specs/upstream").glob("*.json")):
        doc = json.loads(file.read_text())
        for template, item in doc["paths"].items():
            if "get" not in item:
                continue
            path, params = template, {}
            for parameter in item.get("parameters", []) + item["get"].get("parameters", []):
                name = parameter["name"]
                schema = parameter.get("schema", {})
                value = schema.get("enum", ["synthetic-id"])[0]
                if parameter["in"] == "path":
                    path = path.replace("{" + name + "}", str(value))
                elif parameter.get("required"):
                    params[name] = value
            if template.endswith("/catalog"):
                params["publicOnly"] = True
            if template.startswith("/query/timeseries/") and not template.endswith("/catalog"):
                single = template.count("{") == 2
                schema = [{"field": "time", "type": "time"}, {"field": "value", "type": "float64"}]
                series = {"key": "synthetic-id", "entity": {}, "points": [[1790208000, None]]}
                body = {
                    "data": {"point_schema": schema, **series}
                    if single
                    else {"point_schema": schema, "series": [series]}
                }
            elif template.startswith("/query/tabular/") and "{" in template:
                body = {"data": {"synthetic": True}, "metadata": {}}
            else:
                body = {"data": [], "metadata": {"totalPages": 0}, "error": None}
            records.append({"template": template, "path": path, "params": params, "response": body})
    assert len(records) == 226
    return records


@pytest.mark.parametrize("record", cases(), ids=lambda r: r["template"])
def test_public_method_reaches_exact_documented_route(record):
    requests = []

    def handler(request):
        requests.append(request)
        assert request.method == "GET"
        assert request.url.path == record["path"]
        expected = {k: str(v).lower() if isinstance(v, bool) else str(v) for k, v in record["params"].items()}
        assert dict(request.url.params) == expected
        assert request.headers["x-blockworks-api-key"] == "synthetic-test-key"
        return httpx.Response(200, json=record["response"])

    with httpx.Client(base_url="https://api.blockworks.com", transport=httpx.MockTransport(handler)) as transport:
        with BlockworksClient("synthetic-test-key", http_client=transport, max_attempts=1) as client:
            assert call(client, record).body == record["response"]
    assert len(requests) == 1
