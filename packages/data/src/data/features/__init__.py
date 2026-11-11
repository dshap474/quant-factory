"""Compatibility namespace for optional dataset extensions.

USAGE: existing ``data.features.<family>`` imports resolve installed datasets.
"""

from data.extensions import DATASETS_ROOT

# --------------------------------------------------------------------------- #
# Compatibility namespace
# --------------------------------------------------------------------------- #

if DATASETS_ROOT.is_dir():
    __path__.append(str(DATASETS_ROOT))
