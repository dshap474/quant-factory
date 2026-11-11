"""Tests for the optional Features extension bootstrap.

USAGE: ``uv run pytest packages/features/tests/unit/test_extensions.py -q``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from features.api import FeatureFamily
from features.registry import FeatureRegistry

import features.extensions as extensions

# --------------------------------------------------------------------------- #
# Catalog registration
# --------------------------------------------------------------------------- #

def test_conflicting_category_fails_loudly(monkeypatch: pytest.MonkeyPatch) -> None:
    meta = {"runner_module": "example.runner", "runner_class": "ExampleRunner",
            "resolutions": ("1d",), "asset_column": False, "description": ""}
    monkeypatch.setattr(FeatureRegistry, "catalog", classmethod(lambda cls: {"example/family": meta}))
    monkeypatch.setattr(FeatureRegistry, "get_presets_dir", classmethod(lambda cls, name: None))
    catalog = {"example/family": FeatureFamily("example/family", "other.runner", "OtherRunner")}

    with pytest.raises(extensions.FeatureExtensionError, match="Duplicate feature category"):
        extensions.bootstrap_feature_extensions(catalog)


def test_mount_skips_archived_family_roots(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    active_src = tmp_path / "active-family" / "src"
    archived_src = tmp_path / "_archive" / "src"
    active_src.mkdir(parents=True)
    archived_src.mkdir(parents=True)
    monkeypatch.setattr(extensions, "FAMILIES_ROOT", tmp_path)
    monkeypatch.setattr(sys, "path", list(sys.path))

    mounted = extensions.mount_feature_extensions()

    assert mounted == (str(active_src),)
    assert str(archived_src) not in sys.path
