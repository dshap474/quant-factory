"""Check registered, read-only preset discovery without loading a producer.

USAGE: pytest packages/features/tests/unit/test_preset_discovery.py -q
"""

import yaml
from features.api import PUBLISHABLE_FAMILIES, list_feature_presets

from features.extensions import FeatureFamily

# --------------------------------------------------------------------------- #
# Discovery contract
# --------------------------------------------------------------------------- #


def test_presets_are_registered_top_level_definitions_only(tmp_path, monkeypatch):
    monkeypatch.setitem(PUBLISHABLE_FAMILIES, "test", FeatureFamily(
        category="test", runner_module="not.importable", runner_class="NeverRun",
        presets_dir=tmp_path,
    ))
    for name, category in [("narrow", "test"), ("selected", "test"), ("other", "other")]:
        (tmp_path / f"{name}.yaml").write_text(yaml.safe_dump({"category": category}))
    (tmp_path / "exploration").mkdir()
    (tmp_path / "exploration/hidden.yaml").write_text("category: test")
    result = list_feature_presets("test")
    assert [item["name"] for item in result] == ["narrow", "selected"]
    assert list_feature_presets("absent") == []

