"""Atomic-write tests: a write that dies midway never leaves a torn file at the canonical path.

USAGE: uv run pytest packages/data/tests/unit/test_atomic_writes.py -q
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import polars as pl
import pytest
import yaml
from data.platform.storage import feature_store as feature_store_module
from data.platform.storage.feature_store import FeatureStore, FeatureStoreConfig
from data.platform.storage.parquet_runtime import write_polars_parquet_atomic, write_text_atomic
from data.platform.storage.refresh import _stamp_refresh_log, read_refresh_log

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _torn_write(self: pl.DataFrame, file, *args, **kwargs) -> None:
    Path(file).write_bytes(b"PAR1 torn")
    raise OSError("disk went away")


def _leftovers(directory: Path) -> list[str]:
    return sorted(path.name for path in directory.iterdir() if ".tmp-" in path.name)


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


def test_text_atomic_replaces_whole_file(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "log.json"
    write_text_atomic("old\n", target)
    write_text_atomic("new\n", target)
    assert target.read_text() == "new\n"
    assert _leftovers(target.parent) == []


def test_polars_atomic_keeps_original_when_write_dies(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "data.parquet"
    write_polars_parquet_atomic(pl.DataFrame({"x": [1, 2]}), target)
    monkeypatch.setattr(pl.DataFrame, "write_parquet", _torn_write)

    with pytest.raises(OSError):
        write_polars_parquet_atomic(pl.DataFrame({"x": [3]}), target)

    assert pl.read_parquet(target)["x"].to_list() == [1, 2]


def test_feature_store_writes_data_meta_and_registry_atomically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    written: list[str] = []
    real_parquet, real_text = feature_store_module.write_polars_parquet_atomic, feature_store_module.write_text_atomic
    monkeypatch.setattr(
        feature_store_module,
        "write_polars_parquet_atomic",
        lambda frame, path, **kw: written.append(Path(path).name) or real_parquet(frame, path, **kw),
    )
    monkeypatch.setattr(
        feature_store_module,
        "write_text_atomic",
        lambda text, path: written.append(Path(path).name) or real_text(text, path),
    )
    store = FeatureStore(FeatureStoreConfig(db_root=tmp_path, require_asset_column=False))
    frame = pl.DataFrame({"timestamp": [datetime(2026, 1, 1)], "x": [1.0]})

    version = store.write(frame, resolution="1d", category="demo")

    assert written == ["data.parquet", "meta.yaml", "REGISTRY.yaml"]
    assert pl.read_parquet(version.data_path).height == 1
    assert yaml.safe_load(version.meta_path.read_text())
    assert _leftovers(version.path) == [] and _leftovers(tmp_path / "features") == []


def test_refresh_log_stamp_is_atomic_and_readable(tmp_path: Path) -> None:
    _stamp_refresh_log(tmp_path, "raw/1d/a/a_sync_raw.py")
    _stamp_refresh_log(tmp_path, "raw/1d/b/b_sync_raw.py")
    assert set(read_refresh_log(tmp_path)) == {"raw/1d/a/a_sync_raw.py", "raw/1d/b/b_sync_raw.py"}
    assert json.loads((tmp_path / "data" / "refresh-log.json").read_text())
    assert _leftovers(tmp_path / "data") == []
