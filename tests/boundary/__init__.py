"""Boundary tests for quant-factory package.

Tests single package boundaries (where two packages meet):
    - B1: qf-data -> features
    - B2: features -> ml
    - B3: ml -> backtest
    - B4: ml -> optimizer (STUB)
    - B6: features -> features.publication control plane
    - B7: ml -> ml.registry
"""
