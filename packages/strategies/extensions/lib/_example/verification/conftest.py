"""Mount the example family's source so these tests import it by its bare package name.

USAGE: pytest loads this file automatically for tests below this directory.
The underscore folder keeps the example out of family discovery, so its ``src/`` is not on
``sys.path`` by default.
"""

# --------------------------------------------------------------------------- #
# Family sources
# --------------------------------------------------------------------------- #
import sys
from pathlib import Path

SRC = str(Path(__file__).resolve().parents[1] / "src")
if SRC not in sys.path:
    sys.path.append(SRC)
