"""Tests for the slim public API facade."""

from __future__ import annotations

from types import SimpleNamespace

import features.api as api_module
import pytest
from features.api import FeatureFamily, FeaturesApiError, publish_feature_category, smoke_catalog


def test_api_exposes_only_control_plane_surface() -> None:
    assert hasattr(api_module, "publish_feature_category")
    assert hasattr(api_module, "smoke_catalog")
    assert hasattr(api_module, "validate_catalog")
    assert not hasattr(api_module, "create_pipeline")
    assert not hasattr(api_module, "fit_pipeline")
    assert not hasattr(api_module, "transform_pipeline")
    assert not hasattr(api_module, "FeaturePipeline")


def test_smoke_catalog_instantiates_selected_family(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakeRunner:
        @classmethod
        def from_preset(cls, name: str | None = None, overrides: dict[str, object] | None = None):
            captured["preset"] = name
            captured["overrides"] = dict(overrides or {})
            return cls()

        def run(self) -> None:
            captured["executed"] = True

    monkeypatch.setattr(api_module, "_runner_class", lambda family: FakeRunner)
    monkeypatch.setattr(
        api_module,
        "PUBLISHABLE_FAMILIES",
        {
            "example/family": FeatureFamily(
                category="example/family",
                runner_module="example.runner",
                runner_class="ExampleRunner",
            )
        },
    )

    result = smoke_catalog(category="example/family", execute=True)

    assert result.passed == ["example/family"]
    assert result.failed == {}
    assert result.info == ["example/family: ok"]
    assert captured == {
        "preset": None,
        "overrides": {"save": False},
        "executed": True,
    }


def test_smoke_catalog_reports_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    class BrokenRunner:
        @classmethod
        def from_preset(cls, name: str | None = None, overrides: dict[str, object] | None = None):
            raise RuntimeError("boom")

    monkeypatch.setattr(api_module, "_runner_class", lambda family: BrokenRunner)
    monkeypatch.setattr(
        api_module,
        "PUBLISHABLE_FAMILIES",
        {
            "example/family": FeatureFamily(
                category="example/family",
                runner_module="example.runner",
                runner_class="ExampleRunner",
            )
        },
    )

    result = smoke_catalog()

    assert result.passed == []
    assert result.failed == {"example/family": "boom"}


def test_publish_feature_category_runs_with_explicit_save(monkeypatch: pytest.MonkeyPatch) -> None:
    run_result = SimpleNamespace(version="v2", data_path="/tmp/features", saved=True)
    captured: dict[str, object] = {}

    class FakeRunner:
        def __init__(self):
            self.run_config = SimpleNamespace(
                save=False,
                force=False,
                created_by="feature_runner",
                resolution="1d",
            )

        def run(self):
            captured["save"] = self.run_config.save
            captured["force"] = self.run_config.force
            captured["created_by"] = self.run_config.created_by
            captured["resolution"] = self.run_config.resolution
            return run_result

    class FakeRunnerCls:
        @classmethod
        def from_preset(cls, name: str | None = None, overrides: dict[str, object] | None = None):
            captured["preset"] = name
            captured["overrides"] = dict(overrides or {})
            return FakeRunner()

    monkeypatch.setattr(api_module, "_runner_class", lambda family: FakeRunnerCls)
    monkeypatch.setattr(
        api_module,
        "PUBLISHABLE_FAMILIES",
        {
            "example/family": FeatureFamily(
                category="example/family",
                runner_module="example.runner",
                runner_class="ExampleRunner",
                resolutions=("1d", "5m"),
            )
        },
    )

    result = publish_feature_category(
        category="example/family",
        resolution="5m",
        force=True,
    )

    assert result is run_result
    assert captured["preset"] is None
    assert captured["overrides"] == {"save": True, "force": True, "resolution": "5m"}
    assert captured["save"] is True
    assert captured["force"] is True
    assert captured["created_by"] == "qf_features_publish"
    assert captured["resolution"] == "5m"


def test_publish_feature_category_rejects_unknown_family() -> None:
    with pytest.raises(FeaturesApiError, match="Unknown publishable feature category"):
        publish_feature_category(category="example/family/draft")


def test_publish_feature_category_rejects_undeclared_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        api_module,
        "PUBLISHABLE_FAMILIES",
        {
            "example/family": FeatureFamily(
                category="example/family",
                runner_module="example.runner",
                runner_class="ExampleRunner",
            )
        },
    )

    with pytest.raises(FeaturesApiError, match="Resolution '5m' is not declared"):
        publish_feature_category(category="example/family", resolution="5m")
