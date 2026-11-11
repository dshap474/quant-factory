"""Conftest for unit tests.

Unit tests should be:
- Fast (< 1 second per test)
- Hermetic (no external dependencies)
- Deterministic (same result every time)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


# ============================================================================
# Path Setup - Add packages to path
# ============================================================================

_repo_root = Path(__file__).parent.parent.parent
_strategies_root = _repo_root / "packages" / "strategies"
_core_root = _repo_root / "packages" / "platform"

# Add strategies package
strategies_src = _strategies_root / "src"
if strategies_src.exists() and str(strategies_src) not in sys.path:
    sys.path.insert(0, str(strategies_src))


# ============================================================================
# Pytest Configuration
# ============================================================================


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "unit: Fast, hermetic unit tests")


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def strategies_root() -> Path:
    """Path to packages/strategies directory."""
    return _strategies_root


@pytest.fixture
def db_root_with_backtests(tmp_path: Path) -> Path:
    """Create a mock db root with sample backtests for testing discovery.

    Structure:
        db/
        └── backtests/
            ├── example-strategy-v1/
            │   └── run-20260104-120000/
            │       ├── backtest.parquet
            │       └── meta.json
            └── example-strategy-v2/
                └── run-20260104-130000/
                    ├── backtest.parquet
                    └── meta.json
    """
    import json

    import polars as pl

    db = tmp_path / "db"
    backtests_dir = db / "backtests"

    # Create example-strategy-v1 backtest
    first_run = backtests_dir / "example-strategy-v1" / "run-20260104-120000"
    first_run.mkdir(parents=True)

    # Minimal backtest.parquet
    equity_df = pl.DataFrame({
        "timestamp": ["2026-01-01", "2026-01-02", "2026-01-03"],
        "equity": [1.0, 1.01, 1.02],
    })
    equity_df.write_parquet(first_run / "backtest.parquet")

    # meta.json
    first_meta = {
        "metrics": {"sharpe": 1.5, "max_drawdown": -0.05, "total_return": 0.02},
        "config": {"preset": "example-strategy-v1"},
        "created_at": "2026-01-04T12:00:00",
    }
    with open(first_run / "meta.json", "w") as f:
        json.dump(first_meta, f)

    # Create second example backtest
    second_run = backtests_dir / "example-strategy-v2" / "run-20260104-130000"
    second_run.mkdir(parents=True)

    equity_df.write_parquet(second_run / "backtest.parquet")

    second_meta = {
        "metrics": {"sharpe": 0.8, "max_drawdown": -0.10, "total_return": 0.05},
        "config": {"preset": "example-strategy-v2"},
        "created_at": "2026-01-04T13:00:00",
    }
    with open(second_run / "meta.json", "w") as f:
        json.dump(second_meta, f)

    return db


