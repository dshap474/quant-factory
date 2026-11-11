"""Public import contract tests for the slimmed shared features package."""

from __future__ import annotations

import importlib
import importlib.util


def test_import_matrix_resolves() -> None:
    modules = [
        "features",
        "features.api",
        "features.cli",
        "features.publication",
        "features.publication.validation",
    ]
    for module_name in modules:
        assert importlib.import_module(module_name) is not None


def test_shared_symbols_point_to_current_owners() -> None:
    from features.publication import (
        bootstrap_feature_packages,
        publish_feature_frame,
        validate_feature_frame,
    )
    from features.publication.validation import (
        validate_feature_frame as publication_validate_feature_frame,
    )

    assert bootstrap_feature_packages() is None
    assert callable(publish_feature_frame)
    assert validate_feature_frame is publication_validate_feature_frame


def test_research_modules_live_outside_the_core() -> None:
    for name in ("analysis", "evaluation", "selection", "factors", "transforms"):
        assert importlib.util.find_spec(f"features.{name}") is None


def test_old_feature_umbrella_namespaces_are_removed() -> None:
    removed_modules = [
        "features.feature.evaluation",
        "features.feature.generation",
        "features.feature.generation.definitions",
        "features.feature.generation.factors",
        "features.feature.pipeline",
        "features.feature.targets",
        "features.feature.catalog",
        "features.feature.runner",
        "features.feature.template",
    ]
    for module_name in removed_modules:
        try:
            spec = importlib.util.find_spec(module_name)
        except ModuleNotFoundError:
            spec = None
        assert spec is None


def test_publication_does_not_export_experiment_helpers() -> None:
    import features.publication as publication_module

    assert not hasattr(publication_module, "FeatureLibraryManager")
    assert not hasattr(publication_module, "FeatureRegistry")
    assert not hasattr(publication_module, "FeatureRunner")
    assert not hasattr(publication_module, "GraphExportResult")
    assert not hasattr(publication_module, "export_hamilton_graph_json")
