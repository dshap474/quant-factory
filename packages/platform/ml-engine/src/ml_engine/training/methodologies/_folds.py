"""Build immutable chronological folds for the public training methodologies.

Usage::

    plan = build_fold_plan(
        frame,
        SplitConfig(kind="expanding", min_train_periods=3, eval_periods=2),
        timestamp_col="timestamp",
        row_id_col="row_id",
    )
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports
# --------------------------------------------------------------------------- #

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
import pandas as pd
from signal_analysis.partitions import chronological_purge_mask

from ..config import SplitConfig
from ..validation import _normalized_cutoff


# --------------------------------------------------------------------------- #
# Immutable fold records
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class Fold:
    """One chronological training/evaluation split and its audit metadata."""

    fold: int
    train_indices: tuple[int, ...]
    eval_indices: tuple[int, ...]
    train_row_ids: tuple[Any, ...]
    eval_row_ids: tuple[Any, ...]
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    purge_start: pd.Timestamp | None
    purge_end: pd.Timestamp | None
    embargo_start: pd.Timestamp | None
    embargo_end: pd.Timestamp | None
    eval_start: pd.Timestamp
    eval_end: pd.Timestamp
    train_count: int
    eval_count: int


@dataclass(frozen=True, slots=True)
class FoldPlan:
    """Immutable collection of folds with the input identity context."""

    folds: tuple[Fold, ...]
    timestamp_col: str
    row_id_col: str | None
    period_col: str | None
    unit: str
    row_ids: tuple[Any, ...]
    timestamps: tuple[pd.Timestamp, ...]

    def __iter__(self) -> Iterator[Fold]:
        return iter(self.folds)

    def __len__(self) -> int:
        return len(self.folds)

    def __getitem__(self, index: int) -> Fold:
        return self.folds[index]


# --------------------------------------------------------------------------- #
# Boundary normalization
# --------------------------------------------------------------------------- #


def _timestamps(frame: pd.DataFrame, column: str, *, allow_null: bool = False) -> pd.Series:
    """Normalize one timestamp column to timezone-aware UTC."""

    try:
        values = pd.to_datetime(frame[column], utc=True, errors="raise")
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{column} must contain parseable timestamps") from exc
    if not allow_null and values.isna().any():
        raise ValueError(f"{column} must not contain null timestamps")
    return values


def _identity_token(value: Any) -> tuple[str, str]:
    """Return a deterministic comparable token for a caller identity."""

    return type(value).__name__, repr(value)


def _validate_boundary(
    frame: pd.DataFrame,
    config: SplitConfig,
    columns: tuple[str | None, ...],
) -> None:
    """Validate the standalone split-planner boundary once."""

    if not isinstance(frame, pd.DataFrame):
        raise TypeError("frame must be a pandas.DataFrame")
    if not isinstance(config, SplitConfig):
        raise TypeError("split config must be a SplitConfig")
    if frame.empty:
        raise ValueError("cannot build folds from an empty frame")
    if not frame.columns.is_unique:
        raise ValueError("frame must not contain duplicate columns")
    required = [column for column in columns if column is not None]
    if any(not isinstance(column, str) or not column for column in required):
        raise ValueError("split columns must be non-empty strings")
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise ValueError(f"missing split columns: {missing}")
    if config.train_periods is not None and config.train_periods < config.min_train_periods:
        raise ValueError("train_periods must be at least min_train_periods")


# --------------------------------------------------------------------------- #
# Unit and range construction
# --------------------------------------------------------------------------- #


def _unit_positions(
    frame: pd.DataFrame,
    ordered: np.ndarray,
    timestamp_ns: np.ndarray,
    period_col: str | None,
) -> tuple[tuple[np.ndarray, ...], np.ndarray]:
    """Group sorted positions into contiguous timestamp or configured-period units."""

    if period_col is None:
        labels: list[Any] = [int(timestamp_ns[position]) for position in ordered]
    else:
        period_values = frame[period_col].to_numpy(copy=False)
        labels = []
        for position in ordered:
            value = period_values[position]
            null = pd.isna(value)
            if bool(null) if not hasattr(null, "__len__") else False:
                raise ValueError(f"{period_col} must not contain null period values")
            labels.append(_identity_token(value))

    changes = np.fromiter(
        (labels[index] != labels[index - 1] for index in range(1, len(labels))),
        dtype=bool,
    )
    starts = np.r_[0, np.flatnonzero(changes) + 1]
    ends = np.r_[starts[1:], len(ordered)]
    units = tuple(ordered[start:end] for start, end in zip(starts, ends, strict=True))

    seen: set[Any] = set()
    for start in starts:
        label = labels[int(start)]
        if label in seen:
            raise ValueError("period values must be contiguous in timestamp order")
        seen.add(label)

    codes = np.full(len(frame), -1, dtype=np.int64)
    for code, positions in enumerate(units):
        codes[positions] = code
    return units, codes


def _ranges(
    config: SplitConfig,
    n_units: int,
    *,
    first_eval_start: int | None = None,
) -> list[tuple[int, int, int, int]]:
    """Return train/evaluation unit ranges for the configured policy."""

    evaluation = config.eval_periods
    embargo = config.embargo_periods
    step = config.step_periods or evaluation
    if config.kind == "chronological_holdout":
        if config.train_periods is None:
            eval_start = n_units - evaluation
            train_end = eval_start - embargo
        else:
            train_end = config.train_periods
            eval_start = train_end + embargo
        return [(0, train_end, eval_start, eval_start + evaluation)]

    ranges: list[tuple[int, int, int, int]] = []
    if config.kind == "rolling":
        assert config.train_periods is not None
        default_eval_start = config.train_periods + embargo
    else:
        default_eval_start = config.min_train_periods + embargo
    eval_start = default_eval_start if first_eval_start is None else first_eval_start
    while eval_start < n_units:
        eval_end = eval_start + evaluation
        final_configured_fold = config.max_folds is not None and len(ranges) + 1 == config.max_folds
        if final_configured_fold and config.include_partial_final_window:
            eval_end = n_units
        if eval_end > n_units:
            if not config.include_partial_final_window:
                break
            eval_end = n_units
        train_end = eval_start - embargo
        train_start = (
            0
            if config.kind in {"expanding", "purged"}
            else train_end - int(config.train_periods or 0)
        )
        ranges.append((train_start, train_end, eval_start, eval_end))
        if final_configured_fold:
            break
        eval_start += step
    return ranges


def _flatten(units: tuple[np.ndarray, ...], start: int, end: int) -> np.ndarray:
    """Flatten a non-empty unit slice into input positions."""

    selected = units[start:end]
    return (
        np.concatenate(selected).astype(np.int64, copy=False)
        if selected
        else np.array([], dtype=np.int64)
    )


def _apply_exact_purge(
    base_train: np.ndarray,
    target_end_ns: np.ndarray,
    eval_start_ns: int,
    unit_codes: np.ndarray,
    purge_boundary: Literal["strict", "closed"],
) -> tuple[np.ndarray, np.ndarray, int]:
    """Apply the configured endpoint purge and count retained training periods."""

    endpoint = target_end_ns[base_train]
    trainable = endpoint != np.datetime64("NaT", "ns").view("int64")
    overlaps = np.zeros(len(endpoint), dtype=bool)
    overlaps[trainable] = chronological_purge_mask(
        endpoint[trainable], eval_start_ns, boundary=purge_boundary
    )
    train = base_train[trainable & ~overlaps]
    purge = base_train[overlaps]
    retained_periods = int(np.unique(unit_codes[train]).size)
    return train, purge, retained_periods


def _first_purged_eval_start(
    config: SplitConfig,
    units: tuple[np.ndarray, ...],
    unit_codes: np.ndarray,
    timestamp_ns: np.ndarray,
    target_end_ns: np.ndarray,
) -> int:
    """Find the first evaluation unit retaining the configured training minimum."""

    first_candidate = config.min_train_periods + config.embargo_periods
    last_candidate = (
        len(units) - 1 if config.include_partial_final_window else len(units) - config.eval_periods
    )
    if first_candidate > last_candidate:
        raise ValueError("dataset cannot fit min_train_periods and one complete evaluation window")
    for candidate in range(first_candidate, last_candidate + 1):
        train_end = candidate - config.embargo_periods
        base_train = _flatten(units, 0, train_end)
        eval_start_ns = int(timestamp_ns[units[candidate]].min())
        _, _, retained_periods = _apply_exact_purge(
            base_train,
            target_end_ns,
            eval_start_ns,
            unit_codes,
            config.purge_boundary,
        )
        if retained_periods >= config.min_train_periods:
            return candidate
    raise ValueError("no evaluation boundary retains min_train_periods after purge")


def _bounds(
    timestamp_ns: np.ndarray, indices: np.ndarray
) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
    """Return UTC timestamp bounds for input positions."""

    if indices.size == 0:
        return None, None
    values = timestamp_ns[indices]
    return pd.Timestamp(int(values.min()), tz="UTC"), pd.Timestamp(int(values.max()), tz="UTC")


# --------------------------------------------------------------------------- #
# Public planner
# --------------------------------------------------------------------------- #


def build_fold_plan(
    frame: pd.DataFrame,
    config: SplitConfig,
    *,
    timestamp_col: str,
    row_id_col: str | None = None,
    period_col: str | None = None,
    target_end_col: str | None = None,
    training_cutoff: Any | None = None,
) -> FoldPlan:
    """Build deterministic chronological folds with configurable endpoint purging."""

    _validate_boundary(
        frame,
        config,
        (timestamp_col, row_id_col, period_col, target_end_col),
    )
    if config.kind == "purged" and target_end_col is None:
        raise ValueError("purged split requires target_end_col")

    timestamps = _timestamps(frame, timestamp_col)
    timestamp_ns = timestamps.to_numpy(dtype="datetime64[ns]").view("int64")
    target_ends = (
        _timestamps(frame, target_end_col, allow_null=True) if target_end_col is not None else None
    )
    target_end_ns = (
        target_ends.to_numpy(dtype="datetime64[ns]").view("int64")
        if target_ends is not None
        else None
    )
    cutoff = _normalized_cutoff(training_cutoff)
    eligible = (
        np.flatnonzero(timestamp_ns <= cutoff.value)
        if cutoff is not None
        else np.arange(len(frame))
    )
    if eligible.size == 0:
        raise ValueError("training_cutoff leaves no eligible rows")
    if target_end_ns is not None:
        eligible_target_ends = target_end_ns[eligible]
        observed = eligible_target_ends != np.datetime64("NaT", "ns").view("int64")
        if np.any(eligible_target_ends[observed] < timestamp_ns[eligible][observed]):
            raise ValueError("target_end must be greater than or equal to timestamp")

    row_ids = tuple(range(len(frame))) if row_id_col is None else tuple(frame[row_id_col].tolist())
    tokens = [_identity_token(value) for value in row_ids]
    if row_id_col is not None:
        if frame[row_id_col].isna().any():
            raise ValueError("row identity must not contain null values")
        if len(set(tokens)) != len(tokens):
            raise ValueError("row identity must be unique")

    ordered = np.asarray(
        sorted(
            eligible.tolist(),
            key=lambda position: (timestamp_ns[position], tokens[position], position),
        ),
        dtype=np.int64,
    )
    units, unit_codes = _unit_positions(frame, ordered, timestamp_ns, period_col)
    first_eval_start = None
    if config.kind == "purged":
        assert target_end_ns is not None
        if config.first_eval_period is None:
            first_eval_start = _first_purged_eval_start(
                config,
                units,
                unit_codes,
                timestamp_ns,
                target_end_ns,
            )
        else:
            first_eval_start = config.first_eval_period
            if first_eval_start >= len(units):
                raise ValueError("first_eval_period is outside the available period range")
            train_end = first_eval_start - config.embargo_periods
            base_train = (
                _flatten(units, 0, train_end) if train_end > 0 else np.array([], dtype=np.int64)
            )
            eval_start_ns = int(timestamp_ns[units[first_eval_start]].min())
            _, _, retained_periods = _apply_exact_purge(
                base_train,
                target_end_ns,
                eval_start_ns,
                unit_codes,
                config.purge_boundary,
            )
            if retained_periods < config.min_train_periods:
                raise ValueError("first_eval_period does not retain min_train_periods after purge")
    ranges = _ranges(config, len(units), first_eval_start=first_eval_start)
    if not ranges:
        raise ValueError("fold construction produced no complete evaluation windows")

    folds: list[Fold] = []
    evaluated = np.zeros(len(frame), dtype=bool)
    for fold_number, (
        train_start_unit,
        train_end_unit,
        eval_start_unit,
        eval_end_unit,
    ) in enumerate(ranges):
        if train_start_unit < 0 or train_end_unit <= train_start_unit:
            raise ValueError(f"fold {fold_number} has an empty training window")
        if eval_start_unit < train_end_unit:
            raise ValueError(f"fold {fold_number} has overlapping train/evaluation windows")
        if eval_start_unit >= eval_end_unit or eval_end_unit > len(units):
            raise ValueError(f"fold {fold_number} has an empty evaluation window")

        base_train = _flatten(units, train_start_unit, train_end_unit)
        evaluation = _flatten(units, eval_start_unit, eval_end_unit)
        if evaluation.size == 0:
            raise ValueError(f"fold {fold_number} has an empty evaluation window")
        if evaluated[evaluation].any():
            raise ValueError(
                "evaluation windows overlap; each row may receive at most one OOS prediction"
            )
        evaluated[evaluation] = True

        eval_start = pd.Timestamp(int(timestamp_ns[evaluation].min()), tz="UTC")
        purge = np.array([], dtype=np.int64)
        if config.kind == "purged":
            assert target_end_ns is not None
            train, purge, retained_periods = _apply_exact_purge(
                base_train,
                target_end_ns,
                eval_start.value,
                unit_codes,
                config.purge_boundary,
            )
        else:
            train = base_train
            retained_periods = int(np.unique(unit_codes[train]).size)
        if train.size == 0:
            raise ValueError(f"fold {fold_number} has an empty training window after purge")
        if retained_periods < config.min_train_periods:
            suffix = " after purge" if config.kind == "purged" else ""
            raise ValueError(f"fold {fold_number} does not meet min_train_periods{suffix}")

        embargo = _flatten(units, train_end_unit, eval_start_unit)
        train_start, train_end = _bounds(timestamp_ns, train)
        evaluated_start, evaluated_end = _bounds(timestamp_ns, evaluation)
        purge_start, _ = _bounds(timestamp_ns, purge)
        embargo_start, embargo_end = _bounds(timestamp_ns, embargo)
        purge_end = (
            pd.Timestamp(int(target_end_ns[purge].max()), tz="UTC")
            if target_end_ns is not None and purge.size
            else None
        )
        assert train_start is not None and train_end is not None
        assert evaluated_start is not None and evaluated_end is not None
        folds.append(
            Fold(
                fold=fold_number,
                train_indices=tuple(int(value) for value in train),
                eval_indices=tuple(int(value) for value in evaluation),
                train_row_ids=tuple(row_ids[position] for position in train),
                eval_row_ids=tuple(row_ids[position] for position in evaluation),
                train_start=train_start,
                train_end=train_end,
                purge_start=purge_start,
                purge_end=purge_end,
                embargo_start=embargo_start,
                embargo_end=embargo_end,
                eval_start=evaluated_start,
                eval_end=evaluated_end,
                train_count=int(train.size),
                eval_count=int(evaluation.size),
            )
        )

    return FoldPlan(
        folds=tuple(folds),
        timestamp_col=timestamp_col,
        row_id_col=row_id_col,
        period_col=period_col,
        unit="period" if period_col is not None else "timestamp",
        row_ids=row_ids,
        timestamps=tuple(timestamps.tolist()),
    )


__all__ = ["Fold", "FoldPlan", "build_fold_plan"]
