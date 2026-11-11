"""Features package root."""

from __future__ import annotations

import os
from pkgutil import extend_path

# Return freed pages to the OS at once. Polars' jemalloc otherwise keeps GBs of freed
# memory resident through a panel build, which a run's memory cap counts. jemalloc reads
# this at its first allocation, so it only takes effect when set before polars loads.
# Appended, not setdefault: an imported polars exports its own defaults to the
# environment, which a child process would otherwise inherit in place of these.
_decay = "dirty_decay_ms:0,muzzy_decay_ms:0"
if _decay not in os.environ.get("_RJEM_MALLOC_CONF", ""):
    os.environ["_RJEM_MALLOC_CONF"] = ",".join(filter(None, (os.environ.get("_RJEM_MALLOC_CONF"), _decay)))

from features.extensions import mount_feature_extensions  # noqa: E402

__version__ = "0.1.0"

__path__ = extend_path(__path__, __name__)
mount_feature_extensions()

__all__ = ["__version__"]
