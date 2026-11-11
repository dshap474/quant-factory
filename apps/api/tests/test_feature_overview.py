"""Verify snapshot statistics, preset projections, and read-only freshness.

USAGE: pytest apps/api/tests/test_feature_overview.py -q
"""

from datetime import datetime

import polars as pl
import pytest
import yaml
from db_api.dataset_profiles import profile_parquet_features
from db_api.feature_overview import feature_overview
from db_api.routers.features import _preset_columns
from fastapi import HTTPException
from features.api import PUBLISHABLE_FAMILIES

from features.extensions import FeatureFamily

# --------------------------------------------------------------------------- #
# Fixture and known-answer checks
# --------------------------------------------------------------------------- #


@pytest.fixture
def panel(tmp_path, monkeypatch):
    presets = tmp_path / "presets"
    presets.mkdir()
    for name, config in {
        "selected": {"feature_columns": ["close"]},
        "missing": {"feature_columns": ["absent"]},
        "recipe": {},
    }.items():
        (presets / f"{name}.yaml").write_text(yaml.safe_dump({"category": "test", "resolution": "1d", **config}))
    monkeypatch.setitem(PUBLISHABLE_FAMILIES, "test", FeatureFamily(
        category="test", runner_module="must.not.import", runner_class="NeverRun",
        presets_dir=presets,
    ))
    target = tmp_path / "features/1d/test/data.parquet"
    target.parent.mkdir(parents=True)
    pl.DataFrame({
        "timestamp": [datetime(2024, 1, 1), datetime(2024, 1, 2), datetime(2024, 2, 1)],
        "asset": ["A", "B", "A"], "close": [1.0, None, 3.0],
        "flag": [1.0, 1.0, 1.0], "broken": [float("inf"), float("nan"), None],
    }).write_parquet(target)
    target.with_name("meta.yaml").write_text(yaml.safe_dump({"stats": {"include_context": False}}))
    return tmp_path, "1d/test/data.parquet", target


def test_overview_uses_finite_cells_and_real_subset_denominator(panel):
    root, path, target = panel
    before = target.read_bytes()
    result = feature_overview(root, path)
    presets = {item["name"]: item for item in result["presets"]}
    assert result["build"]["rows"] == 3
    assert result["build"]["assets"] == 2
    assert presets["full"]["summary"] == {
        "features": 3, "coverage": 5 / 9, "null_cells": 2, "invalid_cells": 2,
        "empty_features": 1, "constant_features": 1,
    }
    assert presets["selected"]["summary"]["coverage"] == 2 / 3
    assert presets["selected"]["summary"]["invalid_cells"] == 0
    assert [point["coverage"] for point in presets["selected"]["coverage"]] == [0.5, 1.0]
    assert [point["assets"] for point in presets["selected"]["coverage"]] == [2, 1]
    assert not presets["recipe"]["available"]
    assert presets["recipe"]["summary"] is None
    assert presets["missing"]["missing_columns"] == ["absent"]
    assert result["analysis"] == {"correlation": "missing", "ic": "missing"}
    assert target.read_bytes() == before


def test_replacement_invalidates_snapshot_cache_and_analysis_is_not_assumed_current(panel):
    root, path, target = panel
    original = feature_overview(root, path)
    pl.DataFrame({"timestamp": [datetime(2025, 1, 1)], "asset": ["C"], "close": [9.0]}).write_parquet(target)
    target.with_name("analysis_cluster_heatmap.parquet").touch()
    updated = feature_overview(root, path)
    assert original["build"]["id"] != updated["build"]["id"]
    assert updated["build"]["rows"] == 1
    assert updated["analysis"]["correlation"] == "unverified"


def test_preset_profile_projects_before_count_sort_and_pagination(panel):
    root, path, _ = panel
    columns = _preset_columns(path, "selected")
    result = profile_parquet_features(root, "features", path, columns=columns, page_size=1)
    assert result["feature_columns"] == 1
    assert result["total_features"] == 1
    assert [item["name"] for item in result["features"]] == ["close"]
    for preset in ["recipe", "unknown", "../../secrets"]:
        with pytest.raises(HTTPException):
            _preset_columns(path, preset)
    with pytest.raises(HTTPException):
        profile_parquet_features(root, "features", path, columns=("absent",))
