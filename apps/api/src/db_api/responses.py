"""Response and cache helpers for the read-only DB API."""

import time
from collections import OrderedDict
from functools import wraps
from math import ceil
from threading import RLock
from typing import Any

import orjson
import polars as pl
from fastapi import Response


def sample_display_rows(frame: pl.DataFrame, *, max_points: int) -> pl.DataFrame:
    """Return a display-sized row sample while preserving both endpoints."""
    total = frame.height
    if total <= max_points:
        return frame
    stride = ceil(total / max_points)
    return (
        frame.with_row_index("__display_row")
        .filter(
            (pl.col("__display_row") == 0)
            | (pl.col("__display_row") == total - 1)
            | (pl.col("__display_row") % stride == 0)
        )
        .drop("__display_row")
    )


def polars_json_response(data: dict[str, Any], df_key: str = "data") -> Response:
    """Serialize a payload containing one Polars DataFrame."""
    frame = data.pop(df_key)
    if not isinstance(frame, pl.DataFrame):
        raise TypeError(f"Expected Polars DataFrame at payload key: {df_key}")

    frame_json = frame.write_json().encode()
    rest_json = orjson.dumps(data)
    content = rest_json[:-1] + b',"' + df_key.encode() + b'":' + frame_json + b"}"
    return Response(content=content, media_type="application/json")


def polars_nested_json_response(data: Any) -> Response:
    """Serialize nested payloads that may contain Polars DataFrames."""

    def encode(value: Any) -> Any:
        if isinstance(value, pl.DataFrame):
            return orjson.Fragment(value.write_json().encode())
        if isinstance(value, dict):
            return {key: encode(inner) for key, inner in value.items()}
        if isinstance(value, list):
            return [encode(inner) for inner in value]
        return value

    return Response(content=orjson.dumps(encode(data)), media_type="application/json")


def ttl_cache(seconds: int = 60, *, maxsize: int = 128):
    """Cache pure helper results in one process with TTL and LRU bounds."""

    def decorator(fn):
        cache: OrderedDict[tuple, tuple[float, Any]] = OrderedDict()
        lock = RLock()

        @wraps(fn)
        def wrapper(*args, **kwargs):
            key = args + tuple(sorted(kwargs.items()))
            with lock:
                now = time.monotonic()
                cached = cache.get(key)
                if cached is not None and now < cached[0]:
                    cache.move_to_end(key)
                    return cached[1]
                result = fn(*args, **kwargs)
                cache[key] = (now + seconds, result)
                cache.move_to_end(key)
                while len(cache) > maxsize:
                    cache.popitem(last=False)
                return result

        def cache_clear() -> None:
            with lock:
                cache.clear()

        setattr(wrapper, "cache_clear", cache_clear)
        return wrapper

    return decorator
