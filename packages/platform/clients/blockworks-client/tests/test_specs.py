"""Check pinned route inventory, drift gates, and scoped schema corrections.

USAGE: uv run --package blockworks-client pytest packages/platform/clients/blockworks-client/tests/test_specs.py -q
"""

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest
from blockworks_client._generated import ROUTES
from openapi_schema_validator import OAS30Validator

# --------------------------------------------------------------------------- #
# Independent upstream inventory
# --------------------------------------------------------------------------- #

ROOT = Path(__file__).resolve().parents[1]


def _tool():
    spec = importlib.util.spec_from_file_location("blockworks_spec_tool", ROOT / "tools" / "specs.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_all_198_get_routes_match_independent_spec_inventory():
    expected = {}
    mutations = 0
    for file in sorted((ROOT / "specs" / "upstream").glob("*.json")):
        document = json.loads(file.read_text())
        for path, item in document["paths"].items():
            mutations += len(set(item) & {"post", "put", "patch", "delete"})
            if "get" not in item:
                continue
            params = item.get("parameters", []) + item["get"].get("parameters", [])
            expected[path] = params
    assert len(expected) == 226 and mutations == 4
    assert set(expected) == set(ROUTES)
    for path, params in expected.items():
        assert ROUTES[path]["query"] == tuple(p["name"] for p in params if p["in"] == "query")
        assert ROUTES[path]["path"] == tuple(p["name"] for p in params if p["in"] == "path")
        assert ROUTES[path]["required"] == tuple(p["name"] for p in params if p["in"] == "query" and p.get("required"))


def test_generated_files_are_current():
    subprocess.run([sys.executable, str(ROOT / "tools" / "specs.py"), "--check"], check=True, capture_output=True)


def test_external_and_dangling_references_fail_closed():
    tool = _tool()
    with pytest.raises(ValueError, match="external"):
        tool._validate_refs({"schema": {"$ref": "https://example.test/schema.json"}}, "synthetic")
    with pytest.raises(ValueError, match="unresolved"):
        tool._validate_refs({"schema": {"$ref": "#/absent"}}, "synthetic")


# --------------------------------------------------------------------------- #
# Synthetic fixtures prove each reviewed nullable correction
# --------------------------------------------------------------------------- #


def test_overrides_validate_null_fixtures_without_mutating_upstream():
    originals = {f.name: json.loads(f.read_text()) for f in (ROOT / "specs" / "upstream").glob("*.json")}
    before = copy.deepcopy(originals)
    effective = _tool().apply_overrides(originals)
    fixtures = json.loads((ROOT / "tests" / "fixtures" / "nullable-responses.json").read_text())
    for fixture in fixtures:
        name, route, body = fixture["spec"], fixture["route"], fixture["body"]
        schema = originals[name]["paths"][route]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
        assert list(OAS30Validator({**schema, "components": originals[name]["components"]}).iter_errors(body))
        schema = effective[name]["paths"][route]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
        assert not list(OAS30Validator({**schema, "components": effective[name]["components"]}).iter_errors(body))
    assert originals == before


def test_overlay_detects_upstream_target_drift():
    originals = {f.name: json.loads(f.read_text()) for f in (ROOT / "specs" / "upstream").glob("*.json")}
    originals["token-unlocks-openapi.json"]["components"]["schemas"]["AllocationTranche"]["properties"]["sources"][
        "nullable"
    ] = True
    with pytest.raises(ValueError, match="no longer needed"):
        _tool().apply_overrides(originals)


# --------------------------------------------------------------------------- #
# Inventory generation cannot invent empirical evidence
# --------------------------------------------------------------------------- #


def test_coverage_is_inventory_only_and_hashes_have_one_owner():
    tool = _tool()
    artifacts = tool._artifacts()
    coverage = artifacts[ROOT / "docs" / "coverage.csv"]
    assert coverage.splitlines()[0] == "family,route_template,operation_id,public_method"
    assert "populated success" not in coverage
    assert "SPEC_SHA256" not in artifacts[ROOT / "src" / "blockworks_client" / "_generated.py"]


def test_changed_snapshot_requires_explicit_retrieval_date(tmp_path, monkeypatch):
    import shutil

    tool = _tool()
    shutil.copytree(ROOT / "specs", tmp_path / "specs")
    spec = tmp_path / "specs" / "upstream" / "charts-openapi.json"
    document = json.loads(spec.read_text())
    document["info"]["description"] = "synthetic changed snapshot"
    spec.write_text(json.dumps(document))
    monkeypatch.setattr(tool, "ROOT", tmp_path)
    with pytest.raises(ValueError, match="retrieved-date"):
        tool._artifacts()
    artifacts = tool._artifacts("2026-09-28")
    manifest = json.loads(artifacts[tmp_path / "specs" / "manifest.json"])
    assert manifest["retrieved_date"] == "2026-09-28"
    assert "populated success" not in artifacts[tmp_path / "docs" / "coverage.csv"]
