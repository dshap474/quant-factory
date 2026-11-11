"""Workflow test fixtures.

Provides fixtures specific to workflow tests, building on root conftest.py.
"""

from __future__ import annotations

import pytest


# Re-export marker for convenience
pytestmark = pytest.mark.workflow
