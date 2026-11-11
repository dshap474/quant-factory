"""Test-suite path setup for this package.

Purpose: pytest runs this repo with ``--import-mode=importlib``, which does not
put a test file's directory on ``sys.path``.  This makes the shared
``observation_builders`` helper importable by the suites that share it.

USAGE: automatic — pytest loads this file before collecting the suite.
"""

from __future__ import annotations

import sys
from pathlib import Path

# --------------------------------------------------------------------------- #
# Path setup
# --------------------------------------------------------------------------- #

_TESTS_ROOT = str(Path(__file__).resolve().parent)
if _TESTS_ROOT not in sys.path:
    sys.path.insert(0, _TESTS_ROOT)
