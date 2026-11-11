"""Bounded read-only orderbook heatmaps and intact selected snapshots.

USAGE: orderbook_heatmap(db_root, path, start=None, band_percent=2)
"""

from functools import lru_cache
from math import ceil, floor
from pathlib import Path

import polars as pl
from data.query import (
    AggregationSpec,
    ParquetCollectionQuery,
    aggregate_parquet_collection,
    get_parquet_collection_metadata,
    query_parquet_collection,
)
from fastapi import HTTPException

from .dataset_charts import _resolve_parquet_path
from .parquet import fingerprint, read_parquet_schema

# --------------------------------------------------------------------------- #
# Read boundary
# --------------------------------------------------------------------------- #

COLUMNS = ("timestamp", "midprice", "price", "size", "side")
ROW_LIMIT = 300_000
PRICE_BIN_WIDTH = 100.0


def _validate(db_root: Path, path: str) -> None:
    target = _resolve_parquet_path(db_root, "data", path, action="orderbook charts")
    if not set(COLUMNS).issubset(read_parquet_schema(target, db_root=db_root)):
        raise HTTPException(422, "This dataset does not contain orderbook snapshots")


def _read(db_root: Path, path: str, start: int, end: int) -> pl.DataFrame:
    frame = query_parquet_collection(
        ParquetCollectionQuery(
            scope="data",
            path_glob=path,
            columns=COLUMNS,
            integer_column="timestamp",
            integer_min=start,
            integer_max=end,
            limit=ROW_LIMIT + 1,
        ),
        db_root=db_root,
    ).frame
    if frame.height > ROW_LIMIT:
        raise HTTPException(422, "This window exceeds 300,000 levels; choose a shorter window")
    return frame


# --------------------------------------------------------------------------- #
# Public chart payloads
# --------------------------------------------------------------------------- #


def orderbook_heatmap(db_root: Path, path: str, *, start: int | None, band_percent: float, hours: int) -> dict:
    _validate(db_root, path)
    bounds = aggregate_parquet_collection(
        ParquetCollectionQuery(
            scope="data",
            path_glob=path,
            aggregations=(AggregationSpec("min", "timestamp", "first"), AggregationSpec("max", "timestamp", "last")),
            limit=None,
        ),
        db_root=db_root,
    ).frame.row(0, named=True)
    if bounds["first"] is None:
        return {
            "first": None,
            "last": None,
            "start": None,
            "end": None,
            "snapshots": [],
            "cells": [],
            "price_min": 0,
            "price_step": PRICE_BIN_WIDTH,
            "price_bins": 0,
            "snapshot_count": 0,
        }
    first, last = int(bounds["first"]), int(bounds["last"])
    start = max(first, min(start if start is not None else first, last))
    end = min(start + hours * 3600 - 1, last)
    # Discover small snapshot keys first, then retain only sampled books from
    # bounded one-hour scans. A 1D view never materializes a full day of levels.
    keys = (
        aggregate_parquet_collection(
            ParquetCollectionQuery(
                scope="data",
                path_glob=path,
                integer_column="timestamp",
                integer_min=start,
                integer_max=end,
                group_by=("timestamp", "midprice"),
                aggregations=(AggregationSpec("count_star", alias="levels"),),
                limit=10_001,
            ),
            db_root=db_root,
        )
        .frame.select("timestamp", "midprice")
        .sort("timestamp", "midprice")
    )
    count = keys.height
    if count > 10_000:
        raise HTTPException(422, "This window exceeds 10,000 books; choose a shorter window")
    indices = list(range(0, count, max(1, ceil(count / 179))))
    if count and indices[-1] != count - 1:
        indices.append(count - 1)
    keys = keys[indices].with_row_index("snapshot")
    pieces = []
    for chunk_start in range(start, end + 1, 3600):
        chunk_end = min(chunk_start + 3600 - 1, end)
        chunk_keys = keys.filter(pl.col("timestamp").is_between(chunk_start, chunk_end))
        if chunk_keys.height:
            pieces.append(_read(db_root, path, chunk_start, chunk_end).join(chunk_keys, on=["timestamp", "midprice"]))
    sampled = (
        pl.concat(pieces)
        if pieces
        else pl.DataFrame(
            schema={
                "timestamp": pl.UInt32,
                "midprice": pl.Float64,
                "price": pl.Float64,
                "size": pl.Float64,
                "side": pl.String,
                "snapshot": pl.UInt32,
            }
        )
    )
    snapshots = keys.select("timestamp", "midprice").to_dicts()
    # Aggregate complete zero-aligned bins before applying the visible range.
    # Cropping never changes a bin's size or its physical width.
    binned = sampled.with_columns((pl.col("price") / PRICE_BIN_WIDTH).floor().cast(pl.Int64).alias("bin"))
    binned = binned.group_by("snapshot", "bin").agg(
        pl.col("size").sum(),
        pl.col("midprice").first(),
        pl.col("size").filter(pl.col("side") == "bid").sum().alias("bid_size"),
        pl.col("size").filter(pl.col("side") == "ask").sum().alias("ask_size"),
    )
    if band_percent:
        binned = binned.filter(
            ((pl.col("bin") + 1) * PRICE_BIN_WIDTH >= pl.col("midprice") * (1 - band_percent / 100))
            & (pl.col("bin") * PRICE_BIN_WIDTH <= pl.col("midprice") * (1 + band_percent / 100))
        )
    cells = []
    minimum, bin_count = 0.0, 0
    if binned.height:
        first_bin = int(binned["bin"].min())
        minimum = first_bin * PRICE_BIN_WIDTH
        bin_count = int(binned["bin"].max()) - first_bin + 1
        cells = (
            binned.with_columns(pl.col("bin") - first_bin)
            .sort("snapshot", "bin")
            .select("snapshot", "bin", "size", "bid_size", "ask_size")
            .rows()
        )
    return {
        "first": first,
        "last": last,
        "start": start,
        "end": end,
        "snapshots": snapshots,
        "cells": cells,
        "price_min": minimum,
        "price_step": PRICE_BIN_WIDTH,
        "price_bins": bin_count,
        "snapshot_count": count,
    }


def orderbook_depth(db_root: Path, path: str, *, timestamp: int, midprice: float) -> dict:
    _validate(db_root, path)
    frame = _read(db_root, path, timestamp, timestamp).filter(pl.col("midprice") == midprice).sort("price")
    return {"timestamp": timestamp, "midprice": midprice, "levels": frame.select("price", "size", "side").to_dicts()}


# --------------------------------------------------------------------------- #
# Exchange-specific historical calibration
# --------------------------------------------------------------------------- #


def orderbook_historical_scale(db_root: Path, path: str) -> dict:
    """Calibrate fixed bins across a deterministic sample of the stored family."""
    _validate(db_root, path)
    parts = path.split("/")
    if len(parts) != 7 or parts[:2] != ["raw", "1m"] or parts[3] != "orderbook":
        raise HTTPException(422, "Historical calibration requires a monthly raw 1m orderbook family")
    glob = "/".join(parts[:4]) + "/*/*/" + parts[-1]
    metadata = get_parquet_collection_metadata(scope="data", path_glob=glob, db_root=db_root)
    signatures = tuple(
        (file.path, fingerprint(Path(file.absolute_path), db_root=db_root)[0], file.file_size_bytes)
        for file in metadata.files
    )
    return _historical_scale_cached(str(db_root.resolve()), glob, signatures)


@lru_cache(maxsize=16)
def _historical_scale_cached(root: str, family: str, signatures: tuple[tuple[str, int, int], ...]) -> dict:
    sizes = []
    books = 0
    first = None
    last = None
    requested = 0
    for path, _, _ in signatures:
        bounds = aggregate_parquet_collection(
            ParquetCollectionQuery(
                scope="data",
                path_glob=path,
                aggregations=(
                    AggregationSpec("min", "timestamp", "first"),
                    AggregationSpec("max", "timestamp", "last"),
                ),
                limit=None,
            ),
            db_root=root,
        ).frame.row(0, named=True)
        if bounds["first"] is None:
            continue
        low, high = int(bounds["first"]), int(bounds["last"])
        first = low if first is None else min(first, low)
        last = high if last is None else max(last, high)
        # Sixteen evenly spaced minute-grid timestamps per monthly partition,
        # including both endpoints. Missing books are skipped without filling.
        timestamps = sorted({floor((low + (high - low) * index / 15) / 60) * 60 for index in range(16)})
        requested += len(timestamps)
        for timestamp in timestamps:
            frame = _read(Path(root), path, timestamp, timestamp)
            books += frame.select("timestamp", "midprice").unique().height
            if frame.height:
                bins = frame.with_columns((pl.col("price") / PRICE_BIN_WIDTH).floor().cast(pl.Int64).alias("bin"))
                sizes.extend(bins.group_by("timestamp", "midprice", "bin").agg(pl.col("size").sum())["size"].to_list())
    if not sizes:
        raise HTTPException(422, "No populated historical price bins are available for this family")
    values = pl.Series(sizes)
    return {
        "p50": float(values.quantile(0.50, interpolation="linear")),
        "p90": float(values.quantile(0.90, interpolation="linear")),
        "p95": float(values.quantile(0.95, interpolation="linear")),
        "p99": float(values.quantile(0.99, interpolation="linear")),
        "price_step": PRICE_BIN_WIDTH,
        "first": first,
        "last": last,
        "sample_books": books,
        "sample_bins": len(sizes),
        "requested_books": requested,
        "partitions": len(signatures),
        "family": family,
        "method": "16 evenly spaced snapshots per monthly partition; populated fixed price bins; pooled percentiles",
    }
