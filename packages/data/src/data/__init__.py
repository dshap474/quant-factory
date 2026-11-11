"""Canonical runtime package for quant-factory data contracts and tooling."""

import os

# Return freed pages to the OS at once. Polars' jemalloc otherwise keeps GBs of freed
# memory resident through a whole-market build, which a run's memory cap counts. jemalloc
# reads this at its first allocation, so it only takes effect when set before polars loads.
# Appended, not setdefault: an imported polars exports its own defaults to the
# environment, which a child process would otherwise inherit in place of these.
_decay = "dirty_decay_ms:0,muzzy_decay_ms:0"
if _decay not in os.environ.get("_RJEM_MALLOC_CONF", ""):
    os.environ["_RJEM_MALLOC_CONF"] = ",".join(filter(None, (os.environ.get("_RJEM_MALLOC_CONF"), _decay)))

__version__ = "0.1.0"

__all__ = ["__version__"]
