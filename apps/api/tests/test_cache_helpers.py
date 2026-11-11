"""Tests for bounded API cache and shared parquet-index lifecycle."""

from concurrent.futures import ThreadPoolExecutor

import polars as pl
from db_api.dataset_index import get_parquet_index
from db_api.responses import ttl_cache


def test_ttl_cache_is_bounded_and_evicts_least_recently_used():
    calls: list[int] = []

    @ttl_cache(seconds=300, maxsize=2)
    def cached(value: int) -> int:
        calls.append(value)
        return value

    assert cached(1) == 1
    assert cached(2) == 2
    assert cached(1) == 1
    assert cached(3) == 3
    assert cached(2) == 2
    assert calls == [1, 2, 3, 2]


def test_shared_parquet_index_prevents_concurrent_rebuilds(tmp_path, monkeypatch):
    data_dir = tmp_path / "data" / "raw" / "1d" / "sample"
    data_dir.mkdir(parents=True)
    pl.DataFrame({"value": [1]}).write_parquet(data_dir / "data.parquet")

    from db_api import dataset_index

    original_build = dataset_index._build_index
    builds = 0

    def counted_build(*args, **kwargs):
        nonlocal builds
        builds += 1
        return original_build(*args, **kwargs)

    monkeypatch.setattr(dataset_index, "_build_index", counted_build)
    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(lambda _: get_parquet_index(tmp_path, "data"), range(8)))

    assert builds == 1
    assert all(result is results[0] for result in results)
