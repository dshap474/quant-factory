"""Load optional Data implementations from ``packages/data/extensions``.

USAGE: ``load_dataset_extensions()`` registers every installed dataset family.
"""

from __future__ import annotations

import importlib
from pathlib import Path

# --------------------------------------------------------------------------- #
# Extension roots
# --------------------------------------------------------------------------- #

DATA_PACKAGE_ROOT = Path(__file__).resolve().parents[2]
EXTENSIONS_ROOT = DATA_PACKAGE_ROOT / "extensions"
DATASETS_ROOT = EXTENSIONS_ROOT / "datasets"


# --------------------------------------------------------------------------- #
# Dataset loading
# --------------------------------------------------------------------------- #

_datasets_loaded = False


def load_dataset_extensions() -> None:
    """Import installed dataset services once, in deterministic path order."""
    global _datasets_loaded
    if _datasets_loaded or not DATASETS_ROOT.is_dir():
        return

    service_paths = sorted(DATASETS_ROOT.glob("**/service.py"))
    for service_path in service_paths:
        relative = service_path.relative_to(DATASETS_ROOT).with_suffix("")
        module = ".".join(("data", "features", *relative.parts))
        importlib.import_module(module)

    _datasets_loaded = True


__all__ = [
    "DATASETS_ROOT",
    "DATA_PACKAGE_ROOT",
    "EXTENSIONS_ROOT",
    "load_dataset_extensions",
]
