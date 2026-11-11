"""Boundary test fixtures.

Provides fixtures specific to boundary tests, building on root conftest.py.
"""

from __future__ import annotations

import pytest


# Re-export marker for convenience
pytestmark = pytest.mark.boundary
