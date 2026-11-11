"""Tests for the Data control plane without an installed extension overlay.

USAGE: ``pytest packages/data/tests/unit/test_zero_extension_surface.py -q``
"""

from __future__ import annotations

from pathlib import Path

import data.platform.storage.operational_surface as operational_surface

# --------------------------------------------------------------------------- #
# Zero-extension behavior
# --------------------------------------------------------------------------- #


def test_surface_validation_allows_absent_extension_overlay(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """An installed public wheel has no package-level docs or extension scripts."""
    extensions_root = tmp_path / "extensions"
    monkeypatch.setattr(operational_surface, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(operational_surface, "EXTENSIONS_ROOT", extensions_root)
    monkeypatch.setattr(operational_surface, "PIPELINES_ROOT", extensions_root / "pipelines")
    monkeypatch.setattr(operational_surface, "SCRIPTS_ROOT", extensions_root / "scripts")
    monkeypatch.setattr(
        operational_surface,
        "REQUIRED_DOCS",
        (tmp_path / "AGENTS.md", tmp_path / "README.md"),
    )
    monkeypatch.setattr(operational_surface, "OPERATOR_SCRIPTS", ())

    result = operational_surface.validate_data_operational_surface()

    assert result.valid, str(result)
    assert result.info == [
        "extension pipelines: 0",
        "script utilities: 0",
        "registered scripts: 0",
    ]
