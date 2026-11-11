"""Benchmarks API router: daily close series that extensions register on the application.

The core ships no benchmarks; an installed extension calls ``register_benchmark`` with a
loader that returns a ``[timestamp, close]`` daily frame.

USAGE:
    register_benchmark(app, "IDX", "Example index daily close", load_index, label="Index")
    GET /api/benchmarks
    GET /api/benchmarks/IDX?start_date=2024-01-01
"""

# --------------------------------------------------------------------------- #
# Imports
# --------------------------------------------------------------------------- #

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import polars as pl
from fastapi import APIRouter, FastAPI, HTTPException, Query, Request

from ..config import settings
from ..responses import polars_json_response

# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #

router = APIRouter()

BenchmarkLoader = Callable[[Path], pl.DataFrame]
"""``db_root`` -> daily ``timestamp`` (Datetime) and ``close`` (Float64) rows; raise HTTPException when absent."""


@dataclass(frozen=True)
class Benchmark:
    ticker: str
    label: str
    description: str
    loader: BenchmarkLoader


def register_benchmark(
    app: FastAPI, ticker: str, description: str, loader: BenchmarkLoader, *, label: str | None = None
) -> None:
    """Serve ``loader``'s close series as ``/api/benchmarks/{ticker}`` on one application."""
    key = ticker.strip().upper()
    if not key or "/" in key:
        raise ValueError(f"Invalid benchmark ticker: {ticker!r}")
    current = registered_benchmarks(app)
    if key in current:
        raise ValueError(f"Benchmark {key!r} is already registered")
    app.state.benchmarks = {**current, key: Benchmark(key, label or key, description, loader)}


def registered_benchmarks(app: FastAPI) -> dict[str, Benchmark]:
    """Return the application's benchmarks in registration order; none by default."""
    return getattr(app.state, "benchmarks", {})


# --------------------------------------------------------------------------- #
# HTTP entry points
# --------------------------------------------------------------------------- #


@router.get("")
def list_benchmarks(request: Request) -> list[dict[str, str]]:
    """List registered benchmark tickers in registration order."""
    return [
        {"ticker": item.ticker, "label": item.label, "description": item.description}
        for item in registered_benchmarks(request.app).values()
    ]


def _date_bound(value: str, name: str) -> str:
    try:
        datetime.strptime(value[:10], "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid {name} format. Use YYYY-MM-DD")
    return value[:10]


@router.get("/{ticker}")
def get_benchmark(
    request: Request,
    ticker: str,
    start_date: str | None = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: str | None = Query(None, description="End date (YYYY-MM-DD)"),
):
    """Get benchmark price data for a registered ticker."""
    ticker = ticker.upper()
    benchmarks = registered_benchmarks(request.app)
    if ticker not in benchmarks:
        raise HTTPException(
            status_code=404,
            detail=f"Benchmark '{ticker}' not found. Available: {list(benchmarks)}",
        )

    df = benchmarks[ticker].loader(settings.db_root)
    if start_date:
        start = _date_bound(start_date, "start_date")
        df = df.filter(pl.col("timestamp").dt.date() >= pl.lit(start).str.to_date())
    if end_date:
        end = _date_bound(end_date, "end_date")
        df = df.filter(pl.col("timestamp").dt.date() <= pl.lit(end).str.to_date())

    # Convert timestamp to ISO 8601 string for JSON serialization
    df = df.with_columns(pl.col("timestamp").dt.strftime("%Y-%m-%dT%H:%M:%SZ").alias("timestamp"))
    return polars_json_response({"ticker": ticker, "total_rows": len(df), "data": df})
