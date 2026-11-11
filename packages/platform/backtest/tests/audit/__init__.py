"""Execution-engine synthetic-oracle audit tests.

Purpose: mark the hermetic audit suite as a package so audit-only support code
can use explicit relative imports.

USAGE:
    uv run --project packages/platform/backtest pytest \
      packages/platform/backtest/tests/audit -v
"""
