"""Construct explicit research CV partitions and shared interval exclusions.

Usage: ``purged_kfold(events, n_splits=3, endpoint="closed",
training_as_of=as_of, embargo_periods=0)``. Every mask's True means excluded.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports and immutable partition records
# --------------------------------------------------------------------------- #
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

import numpy as np
import polars as pl
from numpy.typing import NDArray

Endpoint = Literal["closed", "half_open"]
_NAT = np.iinfo(np.int64).min
_UTC = pl.Datetime("us", "UTC")
_EVENT_SCHEMA = pl.Schema(
    {
        "observation_id": pl.String,
        "decision_time": _UTC,
        "target_start": _UTC,
        "target_end": _UTC,
        "label_available_at": _UTC,
    }
)


@dataclass(frozen=True, slots=True)
class PartitionFold:
    """Immutable original-row membership and the policy that produced it."""

    fold: int
    observation_ids: tuple[str, ...]
    train_indices: tuple[int, ...]
    eval_indices: tuple[int, ...]
    purged_indices: tuple[int, ...]
    embargoed_indices: tuple[int, ...]
    unavailable_indices: tuple[int, ...]
    endpoint: Endpoint
    unit: Literal["decision_time", "group"]
    training_as_of: datetime
    embargo_periods: int | None
    embargo_duration: timedelta | None


# --------------------------------------------------------------------------- #
# Public array kernels
# --------------------------------------------------------------------------- #


def _integer_clock(values: NDArray[np.int64], name: str) -> None:
    if not isinstance(values, np.ndarray) or values.ndim != 1 or values.dtype != np.dtype("int64"):
        raise TypeError(f"{name} must be a one-dimensional NumPy int64 array")
    if np.any(values == _NAT):
        raise ValueError(f"{name} must not contain the NaT sentinel")


def _endpoint(endpoint: str) -> None:
    if endpoint not in {"closed", "half_open"}:
        raise ValueError("endpoint must be closed or half_open")


def interval_overlap_mask(
    start: NDArray[np.int64],
    end: NDArray[np.int64],
    reference_start: NDArray[np.int64],
    reference_end: NDArray[np.int64],
    *,
    endpoint: Endpoint,
) -> NDArray[np.bool_]:
    """Mark intervals excluded by any reference overlap, using one common time unit.

    Closed intervals include touching endpoints and points. Half-open intervals
    require positive length. Empty arrays are valid; NaT and implicit casts are not.
    """
    _endpoint(endpoint)
    for name, values in (
        ("start", start),
        ("end", end),
        ("reference_start", reference_start),
        ("reference_end", reference_end),
    ):
        _integer_clock(values, name)
    for left, right in ((start, end), (reference_start, reference_end)):
        if len(left) != len(right):
            raise ValueError("interval start/end arrays must have matching lengths")
        invalid = left > right if endpoint == "closed" else left >= right
        if np.any(invalid):
            raise ValueError("interval endpoints must be ordered; half_open requires positive length")
    if not len(reference_start):
        return np.zeros(len(start), dtype=bool)
    order = np.argsort(reference_start, kind="stable")
    sorted_start = reference_start[order]
    maximum_end = np.maximum.accumulate(reference_end[order])
    last = np.searchsorted(sorted_start, end, side="right" if endpoint == "closed" else "left") - 1
    has_reference = last >= 0
    selected_end = maximum_end[np.maximum(last, 0)]
    reaches_start = selected_end >= start if endpoint == "closed" else selected_end > start
    return has_reference & reaches_start


def chronological_purge_mask(
    label_end: NDArray[np.int64],
    evaluation_start: int,
    *,
    boundary: Literal["strict", "closed"],
) -> NDArray[np.bool_]:
    """Mark historical chronological exclusions: strict >= cutoff, closed > cutoff.

    Boundary names preserve ml-engine's admissibility convention. They are not
    interval topology names. Callers must handle missing labels before this kernel.
    """
    _integer_clock(label_end, "label_end")
    if isinstance(evaluation_start, bool) or not isinstance(evaluation_start, (int, np.integer)):
        raise TypeError("evaluation_start must be an integer in the label clock unit")
    if not _NAT < int(evaluation_start) <= np.iinfo(np.int64).max:
        raise ValueError("evaluation_start must be a non-NaT int64 clock value")
    if boundary not in {"strict", "closed"}:
        raise ValueError("boundary must be strict or closed")
    return label_end >= evaluation_start if boundary == "strict" else label_end > evaluation_start


# --------------------------------------------------------------------------- #
# Event contract and chronological units
# --------------------------------------------------------------------------- #


def validate_partition_events(events: pl.DataFrame, *, endpoint: Endpoint) -> None:
    """Validate generic label information intervals and explicit availability."""
    _endpoint(endpoint)
    if not isinstance(events, pl.DataFrame):
        raise TypeError("events must be a Polars DataFrame")
    schema = dict(_EVENT_SCHEMA)
    if "group" in events.columns:
        schema["group"] = pl.String()
    for name, dtype in schema.items():
        if events.schema.get(name) != dtype:
            raise TypeError(f"column {name!r} must have dtype {dtype}")
        if events[name].null_count():
            raise ValueError(f"column {name!r} must not contain null values")
        if (
            dtype == pl.String
            and events.filter(pl.col(name).eq("") | pl.col(name).ne(pl.col(name).str.strip_chars())).height
        ):
            raise ValueError(f"column {name!r} must contain nonempty strings without surrounding whitespace")
    if events["observation_id"].n_unique() != events.height:
        raise ValueError("observation_id must be unique")
    invalid = (pl.col("decision_time") > pl.col("target_start")) | (pl.col("target_end") > pl.col("label_available_at"))
    invalid |= (
        pl.col("target_start") > pl.col("target_end")
        if endpoint == "closed"
        else pl.col("target_start") >= pl.col("target_end")
    )
    if events.filter(invalid).height:
        raise ValueError(
            "require decision_time <= target_start <= target_end <= label_available_at; half_open is strict"
        )
    if "group" in events.columns:
        chronological = events.sort("decision_time", "observation_id")
        group = chronological["group"].to_list()
        runs = [value for index, value in enumerate(group) if index == 0 or value != group[index - 1]]
        if len(runs) != len(set(runs)):
            raise ValueError("group values must be contiguous in chronological order")
        if events.group_by("decision_time").agg(pl.col("group").n_unique()).filter(pl.col("group") > 1).height:
            raise ValueError("different groups must not share a decision_time")


def _units(events: pl.DataFrame, ordered: NDArray[np.int64]) -> tuple[NDArray[np.int64], ...]:
    labels = (
        events["group"].to_list() if "group" in events.columns else events["decision_time"].cast(pl.Int64).to_list()
    )
    starts = [0] + [index for index in range(1, len(ordered)) if labels[ordered[index]] != labels[ordered[index - 1]]]
    ends = starts[1:] + [len(ordered)]
    return tuple(ordered[start:end] for start, end in zip(starts, ends, strict=True))


def _positive_integer(value: int, name: str, minimum: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be a Python integer >= {minimum}")


def _as_of(value: datetime) -> tuple[datetime, int]:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("training_as_of must be a timezone-aware UTC datetime")
    canonical = value.astimezone(timezone.utc)
    delta = canonical - datetime(1970, 1, 1, tzinfo=timezone.utc)
    return canonical, (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds


def _embargo_mask(
    units: tuple[NDArray[np.int64], ...],
    decision: NDArray[np.int64],
    last_end: int,
    periods: int | None,
    duration: timedelta | None,
) -> NDArray[np.bool_]:
    result = np.zeros(len(decision), dtype=bool)
    if periods is not None:
        remaining = periods
        for positions in units:
            if remaining and np.any(decision[positions] > last_end):
                result[positions] = True
                remaining -= 1
    else:
        assert duration is not None
        micros = (duration.days * 86400 + duration.seconds) * 1_000_000 + duration.microseconds
        # Python integers avoid overflowing a finite int64 timestamp plus duration.
        frontier = min(last_end + micros, int(np.iinfo(np.int64).max))
        for positions in units:
            if np.any((decision[positions] > last_end) & (decision[positions] <= frontier)):
                result[positions] = True
    return result


# --------------------------------------------------------------------------- #
# Public purged K-fold entry point
# --------------------------------------------------------------------------- #


def purged_kfold(
    events: pl.DataFrame,
    *,
    n_splits: int,
    endpoint: Endpoint,
    training_as_of: datetime,
    embargo_periods: int | None = None,
    embargo_duration: timedelta | None = None,
) -> tuple[PartitionFold, ...]:
    """Partition contiguous time/group units with exact purge and future-side embargo.

    Supply exactly one explicit embargo, including zero. Training may come from
    either side of evaluation; training_as_of is a global research availability
    cutoff, not a claim of chronological live OOS fitting. See docs/PARTITIONS.md.
    """
    validate_partition_events(events, endpoint=endpoint)
    _positive_integer(n_splits, "n_splits", 2)
    if (embargo_periods is None) == (embargo_duration is None):
        raise ValueError("supply exactly one of embargo_periods or embargo_duration, including zero")
    if embargo_periods is not None:
        _positive_integer(embargo_periods, "embargo_periods", 0)
    if embargo_duration is not None and (
        not isinstance(embargo_duration, timedelta) or embargo_duration < timedelta(0)
    ):
        raise ValueError("embargo_duration must be a nonnegative timedelta")
    canonical_as_of, cutoff = _as_of(training_as_of)
    if not events.height:
        raise ValueError("cannot partition an empty event table")
    identifiers = tuple(events["observation_id"].to_list())
    decision, start, end, available = (
        events[name].cast(pl.Int64).to_numpy()
        for name in ("decision_time", "target_start", "target_end", "label_available_at")
    )
    ordered = np.asarray(sorted(range(events.height), key=lambda i: (decision[i], identifiers[i])), dtype=np.int64)
    units = _units(events, ordered)
    if n_splits > len(units):
        raise ValueError("n_splits must not exceed the number of chronological units")
    folds: list[PartitionFold] = []
    for number, unit_indices in enumerate(np.array_split(np.arange(len(units)), n_splits)):
        evaluation = np.concatenate([units[index] for index in unit_indices])
        is_eval = np.zeros(events.height, dtype=bool)
        is_eval[evaluation] = True
        unavailable = (available > cutoff) & ~is_eval
        purged = interval_overlap_mask(start, end, start[evaluation], end[evaluation], endpoint=endpoint)
        purged &= ~is_eval & ~unavailable
        embargoed = _embargo_mask(units, decision, int(end[evaluation].max()), embargo_periods, embargo_duration)
        embargoed &= ~is_eval & ~unavailable & ~purged
        train = ~(is_eval | unavailable | purged | embargoed)

        def positions(mask: NDArray[np.bool_]) -> tuple[int, ...]:
            return tuple(int(value) for value in ordered[mask[ordered]])

        folds.append(
            PartitionFold(
                fold=number,
                observation_ids=identifiers,
                train_indices=positions(train),
                eval_indices=positions(is_eval),
                purged_indices=positions(purged),
                embargoed_indices=positions(embargoed),
                unavailable_indices=positions(unavailable),
                endpoint=endpoint,
                unit="group" if "group" in events.columns else "decision_time",
                training_as_of=canonical_as_of,
                embargo_periods=embargo_periods,
                embargo_duration=embargo_duration,
            )
        )
    return tuple(folds)


__all__ = [
    "PartitionFold",
    "interval_overlap_mask",
    "chronological_purge_mask",
    "validate_partition_events",
    "purged_kfold",
]
