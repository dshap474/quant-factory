"""Boundary tests for the strategy control-plane contracts.

These carry the ``boundary`` marker so they run in ``just ci``.
The package-level ``strategies`` test suite is not part of that gate, so this is
the gate that makes the registry/catalog, canonical-preset durability,
archive-isolation, and preset/version alignment contracts enforced by
``strategies.api`` fail PRs instead of drifting silently.

USAGE: .venv/bin/python -B -m pytest tests/boundary/test_strategy_control_plane_boundary.py -q
"""

from __future__ import annotations

import pytest

# --------------------------------------------------------------------------- #
# Public control-plane boundary
# --------------------------------------------------------------------------- #

pytestmark = pytest.mark.boundary


def test_strategy_catalog_validates_without_errors():
    from strategies import validate_strategy_catalog

    result = validate_strategy_catalog()

    assert result.errors == [], result.errors


def test_strategy_alignment_validates_without_errors():
    from strategies import validate_alignment

    result = validate_alignment()

    assert result.errors == [], result.errors
