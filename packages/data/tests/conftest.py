"""Shared test fixtures for the canonical data package.

Provides hermetic, ephemeral fixtures for testing:
- In-memory DuckDB connections
- Sample parquet files with ZSTD compression
- YAML schema fixtures
- Neutral raw-layout fixtures
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import polars as pl
import pytest
import yaml

# Fixed random seed for reproducibility
RANDOM_SEED = 42


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "slow: marks tests as slow")
    config.addinivalue_line("markers", "integration: marks integration tests")


# ---------------------------------------------------------------------------
# Random / Reproducibility Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def random_seed() -> int:
    """Fixed random seed for reproducibility."""
    return RANDOM_SEED


@pytest.fixture
def rng() -> np.random.Generator:
    """Reproducible random generator."""
    return np.random.default_rng(RANDOM_SEED)


# ---------------------------------------------------------------------------
# DuckDB Fixtures
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Sample Data Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_ohlcv_data(rng: np.random.Generator) -> pl.DataFrame:
    """Generate sample OHLCV data as Polars DataFrame."""
    n = 100
    dates = [datetime(2024, 1, 1) + timedelta(days=i) for i in range(n)]

    # Generate realistic OHLCV data
    base_price = 40000.0
    returns = rng.normal(0, 0.02, n)
    prices = base_price * np.cumprod(1 + returns)

    return pl.DataFrame({
        "timestamp": dates,
        "open": prices * (1 + rng.uniform(-0.01, 0.01, n)),
        "high": prices * (1 + rng.uniform(0, 0.02, n)),
        "low": prices * (1 - rng.uniform(0, 0.02, n)),
        "close": prices,
        "volume": rng.uniform(1e6, 1e8, n),
    })


@pytest.fixture
def sample_parquet_file(
    tmp_path: Path,
    sample_ohlcv_data: pl.DataFrame,
) -> Path:
    """Create a sample parquet file with ZSTD compression."""
    path = tmp_path / "data/raw" / "1d" / "example" / "spot" / "venue" / "asset_spot_venue.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    sample_ohlcv_data.write_parquet(path, compression="zstd", compression_level=3)
    return path


@pytest.fixture
def sample_parquet_snappy(
    tmp_path: Path,
    sample_ohlcv_data: pl.DataFrame,
) -> Path:
    """Create a sample parquet file with SNAPPY compression (for testing validation)."""
    path = tmp_path / "data/raw" / "1d" / "example" / "futures" / "venue" / "asset_futures_venue.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    sample_ohlcv_data.write_parquet(path, compression="snappy")
    return path


# ---------------------------------------------------------------------------
# Schema Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_schema_yaml(tmp_path: Path) -> Path:
    """Create a sample SCHEMA.yaml file."""
    schema = {
        "layer": "data/raw",
        "description": "Raw market data",
        "datasets": {
            "example/asset_spot_venue_1d": {
                "source": "example",
                "asset": "ASSET",
                "product": "spot",
                "exchange": "venue",
                "resolution": "1d",
                "columns": [
                    {"name": "timestamp", "type": "datetime64[us]", "nullable": False},
                    {"name": "open", "type": "float64"},
                    {"name": "high", "type": "float64"},
                    {"name": "low", "type": "float64"},
                    {"name": "close", "type": "float64"},
                    {"name": "volume", "type": "float64"},
                ],
            }
        },
    }
    schema_path = tmp_path / "data/raw" / "SCHEMA.yaml"
    schema_path.parent.mkdir(parents=True, exist_ok=True)
    with open(schema_path, "w") as f:
        yaml.dump(schema, f, default_flow_style=False)
    return schema_path


@pytest.fixture
def sample_master_schema_yaml(tmp_path: Path) -> Path:
    """Create a sample master SCHEMA.yaml file."""
    schema = {
        "version": 1,
        "name": "test-data-lake",
        "description": "Test data lake",
        "conventions": {
            "compression": "zstd",
            "compression_level": 3,
            "timestamp_column": "timestamp",
        },
        "naming_patterns": {
            "data/raw": "{asset}_{product}_{exchange}_{resolution}.parquet",
        },
        "layers": [
            {"name": "data/raw", "description": "Raw data", "path": "raw/"},
        ],
    }
    schema_path = tmp_path / "SCHEMA.yaml"
    with open(schema_path, "w") as f:
        yaml.dump(schema, f, default_flow_style=False)
    return schema_path


# ---------------------------------------------------------------------------
# DB Root Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_root(tmp_path: Path) -> Path:
    """Create a db root directory structure."""
    db = tmp_path / "db"
    (db / "data/raw" / "1d" / "example").mkdir(parents=True, exist_ok=True)
    (db / "features").mkdir(parents=True, exist_ok=True)
    (db / "signals").mkdir(parents=True, exist_ok=True)
    return db


@pytest.fixture
def db_root_with_data(
    db_root: Path,
    sample_ohlcv_data: pl.DataFrame,
) -> Path:
    """Create a db root with sample parquet files."""
    # Add raw data
    parquet_path = db_root / "data/raw" / "1d" / "example" / "spot" / "venue" / "asset_spot_venue.parquet"
    parquet_path.parent.mkdir(parents=True, exist_ok=True)
    sample_ohlcv_data.write_parquet(parquet_path, compression="zstd", compression_level=3)

    # Add schema
    schema = {
        "layer": "data/raw",
        "description": "Raw market data",
        "datasets": {
            "example/asset_spot_venue_1d": {
                "source": "example",
                "asset": "ASSET",
                "columns": [
                    {"name": "timestamp", "type": "datetime64[us]"},
                    {"name": "open", "type": "float64"},
                    {"name": "high", "type": "float64"},
                    {"name": "low", "type": "float64"},
                    {"name": "close", "type": "float64"},
                    {"name": "volume", "type": "float64"},
                ],
            }
        },
    }
    schema_path = db_root / "data/raw" / "SCHEMA.yaml"
    with open(schema_path, "w") as f:
        yaml.dump(schema, f)

    return db_root


# ---------------------------------------------------------------------------
# Feature Registry Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_feature_parquet(
    tmp_path: Path,
    rng: np.random.Generator,
) -> Path:
    """Create a sample feature parquet file."""
    n = 100
    dates = [datetime(2024, 1, 1) + timedelta(days=i) for i in range(n)]

    df = pl.DataFrame({
        "timestamp": dates,
        "momentum_7d": rng.normal(0, 1, n),
        "volatility_30d": rng.uniform(0.1, 0.5, n),
        "volume_ma_14d": rng.uniform(1e7, 1e9, n),
    })

    # Add some nulls to test null_rate calculation
    df = df.with_columns([
        pl.when(pl.col("momentum_7d") > 1.5)
        .then(None)
        .otherwise(pl.col("momentum_7d"))
        .alias("momentum_7d")
    ])

    path = tmp_path / "features" / "btc_momentum.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(path, compression="zstd", compression_level=3)
    return path
