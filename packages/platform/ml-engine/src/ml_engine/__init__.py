"""Generic tabular predictive-pipeline package.

The package root intentionally exports version metadata only. Import runtime
classes from :mod:`ml_engine.training` and :mod:`ml_engine.inference`.

Usage::

    import ml_engine

    print(ml_engine.__version__)
"""

# --------------------------------------------------------------------------- #
# Version metadata
# --------------------------------------------------------------------------- #

__version__ = "0.1.0"

# --------------------------------------------------------------------------- #
# Public package surface
# --------------------------------------------------------------------------- #

__all__ = ("__version__",)
