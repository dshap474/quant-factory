"""Mechanical helpers for canonical parquet persistence and sync behavior."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pandas as pd
import polars as pl


class DeltaTableWriteRefused(RuntimeError):
    """A legacy whole-file writer was pointed into a Delta table directory."""


def refuse_delta_target(path: Path) -> None:
    """Raise ``DeltaTableWriteRefused`` if ``path`` is, or lies inside, a directory holding ``_delta_log/``.

    The lake decides the format: once a table is Delta, only the Delta write engine may write it.
    Sidecars under ``<table>/_qf/`` are allowed.
    """
    path = Path(path).absolute()
    for directory in (path, *path.parents):
        if (directory / "_delta_log").is_dir():
            if "_qf" in path.relative_to(directory).parts[:1]:
                return
            raise DeltaTableWriteRefused(
                f"refusing a legacy write to {path}: {directory} is a Delta table; "
                "write it through data.platform.storage.delta_tables.write_slice"
            )


def refuse_delta_descendants(root: Path) -> None:
    """Raise ``DeltaTableWriteRefused`` if any directory below ``root`` holds ``_delta_log/``.

    A whole-directory replace (``atomic_swap_directory``) would otherwise rename a Delta table away.
    """
    root = Path(root)
    if not root.is_dir():
        return
    for current, dirs, _files in os.walk(root):
        if "_delta_log" in dirs:
            raise DeltaTableWriteRefused(
                f"refusing to replace {root}: it contains the Delta table {current}; "
                "move the table out or write it through delta_tables.write_slice"
            )
        dirs[:] = [d for d in dirs if not d.startswith(".")]


def coerce_utc_timestamp(value: object) -> pd.Timestamp | None:
    if value is None:
        return None

    timestamp = value if isinstance(value, pd.Timestamp) else pd.Timestamp(value)
    if pd.isna(timestamp):
        return None
    if timestamp.tzinfo is None:
        return timestamp.tz_localize(UTC)
    return timestamp.tz_convert(UTC)


def _numeric_epoch_to_milliseconds(series: pd.Series) -> pd.Series:
    """Normalize seconds/ms/us/ns epoch values independently per row."""
    numeric = pd.to_numeric(series, errors="coerce")
    result = pd.Series(pd.NA, index=series.index, dtype="Float64")
    present = numeric.notna()
    if not present.any():
        return result.astype("Int64")

    absolute = numeric.abs()
    ns_mask = present & (absolute >= 100_000_000_000_000_000)
    us_mask = present & (absolute >= 100_000_000_000_000) & ~ns_mask
    ms_mask = present & (absolute >= 100_000_000_000) & ~ns_mask & ~us_mask
    s_mask = present & ~ns_mask & ~us_mask & ~ms_mask

    result.loc[ns_mask] = numeric.loc[ns_mask] / 1_000_000
    result.loc[us_mask] = numeric.loc[us_mask] / 1_000
    result.loc[ms_mask] = numeric.loc[ms_mask]
    result.loc[s_mask] = numeric.loc[s_mask] * 1_000
    return result.round().astype("Int64")


def latest_timestamp(
    frame: pd.DataFrame,
    *,
    candidate_columns: tuple[str, ...] = ("date", "timestamp", "time"),
) -> pd.Timestamp | None:
    if frame.empty:
        return None

    candidates: list[pd.Timestamp | None] = []
    if isinstance(frame.index, pd.DatetimeIndex) and len(frame.index) > 0:
        candidates.append(coerce_utc_timestamp(frame.index.max()))

    for column in candidate_columns:
        if column not in frame.columns:
            continue
        series = frame[column]
        if column in {"timestamp", "time"}:
            numeric_ms = _numeric_epoch_to_milliseconds(series).dropna()
            if numeric_ms.empty:
                parsed = pd.to_datetime(series, utc=True, errors="coerce").dropna()
                if not parsed.empty:
                    candidates.append(coerce_utc_timestamp(parsed.max()))
                continue
            candidates.append(coerce_utc_timestamp(pd.to_datetime(numeric_ms.max(), unit="ms", utc=True)))
        else:
            parsed = pd.to_datetime(series, utc=True, errors="coerce").dropna()
            if not parsed.empty:
                candidates.append(coerce_utc_timestamp(parsed.max()))

    valid = [candidate for candidate in candidates if candidate is not None]
    return max(valid) if valid else None


def normalize_time_column(series: pd.Series) -> pd.Series:
    if pd.api.types.is_datetime64_any_dtype(series):
        ts = pd.to_datetime(series, utc=True, errors="coerce")
        epoch_ms = (ts.astype("int64") // 1_000_000).astype("Int64")
        epoch_ms[ts.isna()] = pd.NA
        return epoch_ms

    return _numeric_epoch_to_milliseconds(series)


def dedupe_frame(
    frame: pd.DataFrame,
    *,
    dedupe_keys: list[str] | None = None,
    sort_columns: list[str] | None = None,
    index_preferred: bool = True,
) -> pd.DataFrame:
    working = frame.copy()
    if dedupe_keys:
        working = working.drop_duplicates(subset=dedupe_keys, keep="last")
    elif index_preferred and isinstance(working.index, pd.DatetimeIndex):
        working = working.loc[~working.index.duplicated(keep="last")]

    if index_preferred and isinstance(working.index, pd.DatetimeIndex):
        return working.sort_index()

    if sort_columns:
        present = [column for column in sort_columns if column in working.columns]
        if present:
            return working.sort_values(present).reset_index(drop=True)
    return working.reset_index(drop=True)


def merge_frames(
    existing: pd.DataFrame | None,
    new: pd.DataFrame,
    *,
    dedupe_keys: list[str] | None = None,
    sort_columns: list[str] | None = None,
    index_preferred: bool = True,
) -> pd.DataFrame:
    if existing is None or existing.empty:
        return dedupe_frame(
            new,
            dedupe_keys=dedupe_keys,
            sort_columns=sort_columns,
            index_preferred=index_preferred,
        )
    merged = pd.concat([existing, new], axis=0)
    return dedupe_frame(
        merged,
        dedupe_keys=dedupe_keys,
        sort_columns=sort_columns,
        index_preferred=index_preferred,
    )


def write_pandas_parquet_atomic(
    frame: pd.DataFrame,
    path: Path,
    *,
    index: bool,
    compression: str = "zstd",
    compression_level: int = 3,
) -> Path:
    refuse_delta_target(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp-{uuid4().hex}")
    frame.to_parquet(tmp_path, index=index, compression=compression, compression_level=compression_level)
    tmp_path.replace(path)
    return path


def write_polars_parquet_atomic(
    frame: pl.DataFrame | pl.LazyFrame,
    path: Path,
    *,
    compression: str = "zstd",
    compression_level: int = 3,
    row_group_size: int | None = None,
    metadata: dict[str, str] | None = None,
) -> Path:
    """Write ``frame`` to a temp file beside ``path`` and rename it into place; a LazyFrame streams."""
    refuse_delta_target(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp-{uuid4().hex}")
    write = frame.sink_parquet if isinstance(frame, pl.LazyFrame) else frame.write_parquet
    write(
        tmp_path,
        compression=compression,
        compression_level=compression_level,
        row_group_size=row_group_size,
        metadata=metadata,
    )
    tmp_path.replace(path)
    return path


def write_text_atomic(text: str, path: Path) -> Path:
    refuse_delta_target(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.tmp-{uuid4().hex}")
    tmp_path.write_text(text, encoding="utf-8")
    tmp_path.replace(path)
    return path


def atomic_swap_directory(staging_dir: Path, canonical_dir: Path, *, run_id: str) -> tuple[Path | None, Path]:
    refuse_delta_target(canonical_dir)
    refuse_delta_descendants(canonical_dir)
    backup_dir = canonical_dir.with_name(f".{canonical_dir.name}__backup_{run_id}")
    if backup_dir.exists():
        raise FileExistsError(f"Backup directory already exists: {backup_dir}")

    if canonical_dir.exists():
        canonical_dir.rename(backup_dir)
    else:
        backup_dir = None

    try:
        staging_dir.rename(canonical_dir)
    except Exception:
        if backup_dir is not None and backup_dir.exists() and not canonical_dir.exists():
            backup_dir.rename(canonical_dir)
        raise

    return backup_dir, canonical_dir


def new_batch_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%d-%H%M%S")


__all__ = [
    "atomic_swap_directory",
    "coerce_utc_timestamp",
    "dedupe_frame",
    "latest_timestamp",
    "merge_frames",
    "new_batch_id",
    "normalize_time_column",
    "write_pandas_parquet_atomic",
    "write_polars_parquet_atomic",
    "write_text_atomic",
]
