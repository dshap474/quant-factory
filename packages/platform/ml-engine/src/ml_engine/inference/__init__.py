"""Stable public API for the standalone inference engine.

Usage::

    from ml_engine.inference import InferencePipeline, PredictionResult

Only the classes listed in ``__all__`` are supported package-level exports.
Implementation details remain available from their defining modules when
needed internally.
"""

# --------------------------------------------------------------------------- #
# Public pipeline and result contracts
# --------------------------------------------------------------------------- #

from .pipeline import InferencePipeline
from .result import PredictionResult

__all__ = ["InferencePipeline", "PredictionResult"]
