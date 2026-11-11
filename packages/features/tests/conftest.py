"""Shared pytest fixtures for migrated feature runtime tests."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import polars as pl
import pytest


def pytest_configure(config):
    """Register local test markers used by the features package."""
    config.addinivalue_line("markers", "unit: Fast, hermetic unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")


@pytest.fixture(scope="session")
def rng() -> np.random.Generator:
    return np.random.default_rng(42)


@pytest.fixture()
def sample_panel_df(rng: np.random.Generator) -> pl.DataFrame:
    rows = 60
    dates = pl.date_range(
        start=dt.date(2024, 1, 1),
        end=dt.date(2024, 2, 29),
        interval="1d",
        eager=True,
    ).head(rows)
    tickers = ["AAPL"] * rows + ["TSLA"] * rows
    prices = np.concatenate(
        [
            np.linspace(100, 120, rows),
            np.linspace(200, 160, rows),
        ]
    )
    noise = rng.normal(0, 0.5, size=prices.shape[0])
    close = prices + noise
    return pl.DataFrame(
        {
            "date": list(dates) * 2,
            "ticker": tickers,
            "close": close,
            "volume": rng.integers(100, 1000, size=prices.shape[0]).astype(float),
        }
    )


@pytest.fixture()
def simple_target_df(sample_panel_df: pl.DataFrame) -> pl.DataFrame:
    return sample_panel_df.with_columns((pl.col("close").pct_change().fill_null(0.0)).alias("target"))


@pytest.fixture()
def clean_panel_df(sample_panel_df: pl.DataFrame) -> pl.DataFrame:
    return sample_panel_df.clone()


@pytest.fixture()
def clean_panel_parquet(clean_panel_df: pl.DataFrame, tmp_path: Path) -> Path:
    path = tmp_path / "clean_panel.parquet"
    clean_panel_df.write_parquet(path)
    return path


@pytest.fixture()
def simple_target_parquet(simple_target_df: pl.DataFrame, tmp_path: Path) -> Path:
    path = tmp_path / "simple_target.parquet"
    simple_target_df.write_parquet(path)
    return path
