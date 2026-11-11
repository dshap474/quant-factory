"""Root conftest.py for quant-factory integration tests.

Provides cross-package fixtures that wire multiple packages together.
All fixtures are hermetic (no external deps) and ephemeral (auto-cleanup).

Fixture Hierarchy:
    Session-scoped (created once):
        - rng (random generator)
        - session_tmp_dir
        - sample_ohlcv_100_rows
        - sample_ohlcv_1000_rows
        - sample_ohlcv_10000_rows
        - multi_asset_ohlcv

    Function-scoped (per test):
        - populated_db (writes sample parquet to db_root)
        - backtest_config
        - job_spec
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Generator

import numpy as np
import pandas as pd
import polars as pl
import pytest
import yaml
from hypothesis.configuration import set_hypothesis_home_dir

if TYPE_CHECKING:
    from numpy.random import Generator as NPGenerator


# ============================================================================
# Constants
# ============================================================================

RANDOM_SEED = 42
_hypothesis_storage: tempfile.TemporaryDirectory[str] | None = None


# ============================================================================
# Pytest Configuration
# ============================================================================


def pytest_configure(config):
    """Register custom markers."""
    global _hypothesis_storage

    _hypothesis_storage = tempfile.TemporaryDirectory(prefix="quant-factory-hypothesis-")
    set_hypothesis_home_dir(_hypothesis_storage.name)
    config.addinivalue_line("markers", "boundary: Single package boundary tests")
    config.addinivalue_line("markers", "workflow: Multi-package workflow tests")
    config.addinivalue_line("markers", "e2e: End-to-end system tests")
    config.addinivalue_line("markers", "slow: Tests taking > 30 seconds")
    config.addinivalue_line("markers", "mlx: Tests requiring Apple Silicon MLX")
    config.addinivalue_line("markers", "statistical: Property-based/statistical tests")


def pytest_unconfigure() -> None:
    """Delete temporary Hypothesis storage when pytest exits."""
    global _hypothesis_storage

    if _hypothesis_storage is not None:
        _hypothesis_storage.cleanup()
        _hypothesis_storage = None


def pytest_sessionfinish(session: pytest.Session) -> None:
    """Delete pytest-cov data after its reports have been generated."""
    if hasattr(session.config, "workerinput") or not session.config.pluginmanager.hasplugin("_cov"):
        return

    coverage_files = [Path.cwd() / ".coverage", *Path.cwd().glob(".coverage.*")]
    for coverage_file in coverage_files:
        if coverage_file.is_file():
            coverage_file.unlink()


# ============================================================================
# Session-Scoped Fixtures (created once, shared across all tests)
# ============================================================================


@pytest.fixture(scope="session")
def rng() -> NPGenerator:
    """Reproducible random generator for all tests."""
    return np.random.default_rng(RANDOM_SEED)


@pytest.fixture(scope="session")
def random_seed() -> int:
    """Fixed random seed for reproducibility."""
    return RANDOM_SEED


@pytest.fixture(scope="session")
def session_tmp_dir() -> Generator[Path, None, None]:
    """Session-scoped temp directory for expensive fixtures."""
    path = Path(tempfile.mkdtemp(prefix="qf_integ_"))
    yield path
    shutil.rmtree(path, ignore_errors=True)


# ============================================================================
# Data Generation Helpers
# ============================================================================


def _generate_ohlcv(rng: NPGenerator, n_rows: int, start_price: float = 100.0) -> pl.DataFrame:
    """Generate realistic OHLCV data with proper price dynamics.

    Uses Geometric Brownian Motion for realistic price series.

    Properties guaranteed:
        1. Realistic price dynamics (GBM with drift)
        2. OHLC constraint: low <= open,close <= high
        3. No nulls or NaN values
        4. Monotonic timestamps (1h frequency)
        5. Volume follows log-normal distribution
        6. Deterministic given seed
    """
    # Geometric Brownian motion for realistic prices
    drift = 0.0001  # Small positive drift
    volatility = 0.02  # 2% hourly volatility
    returns = rng.normal(drift, volatility, n_rows)
    close = start_price * np.exp(np.cumsum(returns))

    # OHLC with realistic spreads (ensure constraints are met)
    spread_high = rng.uniform(0.001, 0.03, n_rows)
    spread_low = rng.uniform(0.001, 0.03, n_rows)
    high = close * (1 + spread_high)
    low = close * (1 - spread_low)

    # Open is between low and high
    open_pct = rng.uniform(0, 1, n_rows)
    open_ = low + open_pct * (high - low)

    # Volume follows log-normal distribution
    volume = rng.lognormal(10, 1, n_rows)

    # Generate timestamps (1h frequency)
    timestamps = pd.date_range("2020-01-01", periods=n_rows, freq="1h")

    return pl.DataFrame({
        "timestamp": timestamps,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })


def _generate_multi_asset_ohlcv(
    rng: NPGenerator,
    assets: list[str],
    n_rows_per_asset: int,
) -> pl.DataFrame:
    """Generate panel data with multiple assets for cross-asset tests.

    Each asset has its own price dynamics with different starting prices
    and slight correlation through a common market factor.
    """
    dfs = []
    base_prices = {"BTC": 40000.0, "ETH": 2500.0, "SOL": 100.0}

    for asset in assets:
        start_price = base_prices.get(asset, 100.0)
        df = _generate_ohlcv(rng, n_rows_per_asset, start_price=start_price)
        df = df.with_columns(pl.lit(asset).alias("asset"))
        dfs.append(df)

    return pl.concat(dfs)


# ============================================================================
# Data Fixtures
# ============================================================================


@pytest.fixture(scope="session")
def sample_ohlcv_100_rows(rng: NPGenerator) -> pl.DataFrame:
    """Small OHLCV dataset for quick boundary tests."""
    return _generate_ohlcv(rng, n_rows=100)


@pytest.fixture(scope="session")
def sample_ohlcv_1000_rows(rng: NPGenerator) -> pl.DataFrame:
    """Medium OHLCV dataset for workflow tests (realistic CV splits)."""
    return _generate_ohlcv(rng, n_rows=1000)


@pytest.fixture(scope="session")
def sample_ohlcv_10000_rows(rng: NPGenerator) -> pl.DataFrame:
    """Large OHLCV dataset for E2E tests."""
    return _generate_ohlcv(rng, n_rows=10000)


@pytest.fixture(scope="session")
def multi_asset_ohlcv(rng: NPGenerator) -> pl.DataFrame:
    """Panel data with multiple assets for cross-asset tests.

    Contains BTC, ETH, and SOL with 500 rows each.
    """
    return _generate_multi_asset_ohlcv(rng, assets=["BTC", "ETH", "SOL"], n_rows_per_asset=500)


@pytest.fixture
def sample_features_df(sample_ohlcv_1000_rows: pl.DataFrame) -> pd.DataFrame:
    """Sample features DataFrame derived from OHLCV data."""
    df = sample_ohlcv_1000_rows.to_pandas()

    # Create simple technical features
    df["return_1"] = df["close"].pct_change()
    df["return_5"] = df["close"].pct_change(5)
    df["return_10"] = df["close"].pct_change(10)
    df["volatility_10"] = df["return_1"].rolling(10).std()
    df["volatility_20"] = df["return_1"].rolling(20).std()
    df["ma_ratio_10_20"] = df["close"].rolling(10).mean() / df["close"].rolling(20).mean()
    df["volume_ma_10"] = df["volume"].rolling(10).mean()

    # Add target (next period return - CONTINUOUS for better CV metrics)
    # Using continuous returns avoids constant predictions in small CV folds
    df["target"] = df["close"].pct_change().shift(-1)

    # Drop NaN rows
    df = df.dropna()

    return df


# ============================================================================
# Catalog Fixtures (qf-data)
# ============================================================================


@pytest.fixture
def db_root(tmp_path: Path) -> Path:
    """Create a db root directory structure."""
    db = tmp_path / "db"
    (db / "raw" / "1d" / "vendorb").mkdir(parents=True, exist_ok=True)
    (db / "raw" / "1d" / "vendorc").mkdir(parents=True, exist_ok=True)
    (db / "features").mkdir(parents=True, exist_ok=True)
    (db / "signals").mkdir(parents=True, exist_ok=True)
    return db


@pytest.fixture
def sample_schema_yaml(db_root: Path) -> Path:
    """Create a sample SCHEMA.yaml file in the db root."""
    schema = {
        "version": 1,
        "name": "test-data-lake",
        "description": "Test data lake for integration tests",
        "conventions": {
            "compression": "zstd",
            "compression_level": 3,
            "timestamp_column": "timestamp",
        },
        "naming_patterns": {
            "raw": "{asset}_{product}_{exchange}_{resolution}.parquet",
        },
        "layers": [
            {"name": "raw", "description": "Raw data", "path": "raw/"},
            {"name": "features", "description": "Engineered features", "path": "features/"},
            {"name": "signals", "description": "Trading signals", "path": "signals/"},
        ],
    }
    schema_path = db_root / "SCHEMA.yaml"
    with open(schema_path, "w") as f:
        yaml.dump(schema, f, default_flow_style=False)
    return schema_path


@pytest.fixture
def populated_db(
    sample_ohlcv_1000_rows: pl.DataFrame,
    db_root: Path,
    sample_schema_yaml: Path,
) -> Path:
    """db_root with pre-written OHLCV parquet in raw."""
    raw_path = db_root / "raw" / "1d" / "index" / "btc.parquet"
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    sample_ohlcv_1000_rows.write_parquet(raw_path, compression="zstd", compression_level=3)
    return db_root


# ============================================================================
# Backtest Fixtures
# ============================================================================


@pytest.fixture
def backtest_config():
    """Default BacktestConfig for tests."""
    try:
        from backtest import BacktestConfig
        return BacktestConfig(
            trade_cost_bps=10.0,
            frequency="hourly",
        )
    except ImportError:
        pytest.skip("backtest package not available")


@pytest.fixture
def sample_prices_for_backtest(sample_ohlcv_100_rows: pl.DataFrame) -> pl.DataFrame:
    """Prices DataFrame formatted for backtest.

    Includes CASH column for proper weight normalization.
    """
    return sample_ohlcv_100_rows.select([
        pl.col("timestamp"),
        pl.col("close").alias("BTC"),
    ]).with_columns(
        pl.lit(1.0).alias("CASH"),
    )


@pytest.fixture
def sample_weights_for_backtest(sample_ohlcv_100_rows: pl.DataFrame, rng: NPGenerator) -> pl.DataFrame:
    """Weights DataFrame for backtest.

    Weights sum to 1.0 per row (includes CASH allocation).
    """
    n = len(sample_ohlcv_100_rows)
    btc_weights = rng.uniform(0.2, 0.8, n)  # BTC allocation 20-80%
    cash_weights = 1.0 - btc_weights  # Remainder in cash

    return sample_ohlcv_100_rows.select([
        pl.col("timestamp"),
    ]).with_columns([
        pl.Series("BTC", btc_weights),
        pl.Series("CASH", cash_weights),
    ])


# ============================================================================
# Signal Fixtures
# ============================================================================


# ============================================================================
# Utility Fixtures
# ============================================================================


@pytest.fixture
def output_dir(tmp_path: Path) -> Path:
    """Temporary output directory."""
    output = tmp_path / "output"
    output.mkdir()
    return output


@pytest.fixture
def artifacts_dir(tmp_path: Path) -> Path:
    """Temporary artifacts directory."""
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    return artifacts
