"""Verify selected-version validation without mandatory strategy prose.

USAGE: .venv/bin/python -B -m pytest packages/strategies/tests/unit/test_alignment.py -q
"""

from __future__ import annotations

import pytest
import strategies.alignment as alignment

# --------------------------------------------------------------------------- #
# Isolated family
# --------------------------------------------------------------------------- #


@pytest.fixture
def family(tmp_path, monkeypatch):
    root = tmp_path / "extensions/lib/demo"
    (root / "presets").mkdir(parents=True)
    (root / "optimization/version/v003").mkdir(parents=True)
    info = {"presets_dir": "lib/demo/presets", "default_preset": "selected", "status": "active"}
    monkeypatch.setattr(alignment, "STRATEGIES_ROOT", tmp_path)
    monkeypatch.setattr(alignment, "get_strategy_info", lambda _: info)
    return root, info


# --------------------------------------------------------------------------- #
# Explicit selection and legacy compatibility
# --------------------------------------------------------------------------- #


def test_selected_preset_works_without_master_document(family):
    root, _ = family
    (root / "presets/selected.yaml").write_text("memory_version: v003\n")
    (root / "optimization/v006").mkdir()

    assert alignment.resolve_active_memory_version("demo") == "v003"
    result = alignment.validate_strategy_alignment("demo")
    assert result.valid, result.errors
    assert "v003" in result.info[0]
    assert not (root / "optimization/STRATEGY_MASTER_DOC.md").exists()


def test_preset_declaration_takes_precedence_over_legacy_prose(family):
    root, _ = family
    (root / "presets/selected.yaml").write_text("memory_version: v003\n")
    (root / "optimization/STRATEGY_MASTER_DOC.md").write_text("- Active memory version: `v001`\n")

    assert alignment.resolve_active_memory_version("demo") == "v003"
    assert alignment.validate_strategy_alignment("demo").valid


def test_unmigrated_preset_can_read_existing_legacy_declaration(family):
    root, _ = family
    (root / "presets/selected.yaml").write_text("strategy: {}\n")
    (root / "optimization/STRATEGY_MASTER_DOC.md").write_text("- Active memory version: `v003`\n")

    assert alignment.resolve_active_memory_version("demo") == "v003"
    assert alignment.validate_strategy_alignment("demo").valid


# --------------------------------------------------------------------------- #
# Missing and invalid declarations must not select another version
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "body",
    ["memory_version: null\n", "memory_version: v17\n", "memory_version: 17\n", "- v003\n", "memory_version: [\n"],
)
def test_invalid_preset_is_reported_without_legacy_fallback(family, body):
    root, _ = family
    (root / "presets/selected.yaml").write_text(body)
    (root / "optimization/STRATEGY_MASTER_DOC.md").write_text("- Active memory version: `v003`\n")

    result = alignment.validate_strategy_alignment("demo")
    assert not result.valid
    assert "invalid version declaration" in result.errors[0]


def test_missing_declaration_does_not_infer_selection_from_version_directories(family):
    root, _ = family
    (root / "presets/selected.yaml").write_text("strategy: {}\n")

    assert alignment.resolve_active_memory_version("demo") is None
    result = alignment.validate_strategy_alignment("demo")
    assert not result.valid
    assert "must declare memory_version" in result.errors[0]


def test_selected_version_must_exist(family):
    root, _ = family
    (root / "presets/selected.yaml").write_text("memory_version: v001\n")

    result = alignment.validate_strategy_alignment("demo")
    assert not result.valid
    assert "has no version directory" in result.errors[0]


def test_planned_family_needs_no_invented_version_or_master_document(family):
    root, info = family
    info["status"] = "planned"
    (root / "presets/selected.yaml").write_text("strategy: {}\n")

    result = alignment.validate_strategy_alignment("demo")
    assert result.valid, result.errors
    assert "no selected memory version" in result.info[0]
