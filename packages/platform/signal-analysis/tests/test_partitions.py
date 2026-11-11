"""Verify Chapter 7 partitions with independent discrete and hand-derived oracles.

Usage: ``uv run pytest packages/platform/signal-analysis/tests/test_partitions.py``.
Expected memberships never call production interval helpers.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports and independent fixtures
# --------------------------------------------------------------------------- #
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

import numpy as np
import polars as pl
import pytest

from signal_analysis.partitions import (
    chronological_purge_mask,
    interval_overlap_mask,
    purged_kfold,
    validate_partition_events,
)

_BASE = datetime(2026, 1, 1, tzinfo=timezone.utc)
_AS_OF = _BASE + timedelta(days=100)


def _array(values: list[int]) -> np.ndarray:
    return np.asarray(values, dtype=np.int64)


def _events() -> pl.DataFrame:
    # Calendar days deliberately skip 2, 4..9, 12..19.
    decisions = [0, 1, 3, 10, 11, 20]
    ends = [0, 3, 5, 12, 13, 20]
    return pl.DataFrame(
        {
            "observation_id": [f"o{i}" for i in range(6)],
            "decision_time": [_BASE + timedelta(days=value) for value in decisions],
            "target_start": [_BASE + timedelta(days=value) for value in decisions],
            "target_end": [_BASE + timedelta(days=value) for value in ends],
            "label_available_at": [_BASE + timedelta(days=value) for value in ends],
        }
    )


def _folds(events: pl.DataFrame | None = None, **kwargs: object) -> tuple:
    options = {"n_splits": 3, "endpoint": "closed", "training_as_of": _AS_OF, "embargo_periods": 1}
    options.update(kwargs)
    return purged_kfold(_events() if events is None else events, **options)


def _grid(interval: tuple[int, int], half_open: bool) -> set[int]:
    # Doubled integer lattice includes every endpoint and every interior segment
    # for this bounded integer domain. Build actual sets, then intersect them.
    left, right = interval
    return set(range(2 * left, 2 * right + (0 if half_open else 1)))


# --------------------------------------------------------------------------- #
# Independent interval oracles and invariants
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("endpoint", "expected"),
    [
        ("closed", [False, True, True, True, True, True, True, False]),
        ("half_open", [False, False, True, True, True, True, False, False]),
    ],
)
def test_hand_drawn_containment_and_touching(endpoint: str, expected: list[bool]) -> None:
    # Relative to [2,5]: before, touches left, crosses left, inside, envelopes,
    # crosses right, touches right, after. No training-left-only shortcut works.
    start = _array([-3, 0, 1, 3, 0, 4, 5, 6])
    end = _array([-1, 2, 3, 4, 7, 6, 7, 8])
    assert interval_overlap_mask(start, end, _array([2]), _array([5]), endpoint=endpoint).tolist() == expected


def test_closed_points_and_exact_union_gaps() -> None:
    actual = interval_overlap_mask(
        _array([0, 1, 3, 5]), _array([0, 1, 3, 5]), _array([0, 4]), _array([1, 5]), endpoint="closed"
    )
    assert actual.tolist() == [True, True, False, True]
    with pytest.raises(ValueError, match="positive length"):
        interval_overlap_mask(_array([1]), _array([1]), _array([0]), _array([2]), endpoint="half_open")


@pytest.mark.parametrize("endpoint", ["closed", "half_open"])
def test_bounded_exhaustive_grid_set_oracle(endpoint: str) -> None:
    half_open = endpoint == "half_open"
    intervals = [(a, b) for a in range(-3, 4) for b in range(a + int(half_open), 4)]
    starts, ends = _array([a for a, _ in intervals]), _array([b for _, b in intervals])
    for first in intervals:
        for second in intervals:
            reference = _grid(first, half_open) | _grid(second, half_open)
            expected = [bool(_grid(candidate, half_open) & reference) for candidate in intervals]
            actual = interval_overlap_mask(
                starts, ends, _array([first[0], second[0]]), _array([first[1], second[1]]), endpoint=endpoint
            )
            assert actual.tolist() == expected


@pytest.mark.parametrize("endpoint", ["closed", "half_open"])
def test_translation_permutation_and_union_decomposition(endpoint: str) -> None:
    start, end = _array([-4, 1, 5, 2, 10]), _array([1, 7, 9, 3, 12])
    reference_start, reference_end = _array([8, -3, 2]), _array([10, 0, 4])
    expected = interval_overlap_mask(start, end, reference_start, reference_end, endpoint=endpoint)
    translated = interval_overlap_mask(
        start + 90, end + 90, reference_start + 90, reference_end + 90, endpoint=endpoint
    )
    assert np.array_equal(expected, translated)
    order = _array([4, 2, 0, 3, 1])
    permuted = interval_overlap_mask(
        start[order], end[order], reference_start[::-1], reference_end[::-1], endpoint=endpoint
    )
    assert np.array_equal(expected[order], permuted)
    separate = np.zeros(len(start), dtype=bool)
    for index in range(len(reference_start)):
        separate |= interval_overlap_mask(
            start, end, reference_start[index : index + 1], reference_end[index : index + 1], endpoint=endpoint
        )
    assert np.array_equal(expected, separate)


def test_integer_extremes_and_empty_sets_do_not_overflow() -> None:
    low, high = int(np.iinfo(np.int64).min) + 1, int(np.iinfo(np.int64).max)
    assert interval_overlap_mask(
        _array([low, high]), _array([low, high]), _array([low]), _array([high]), endpoint="closed"
    ).tolist() == [True, True]
    assert interval_overlap_mask(_array([0]), _array([1]), _array([]), _array([]), endpoint="closed").tolist() == [
        False
    ]
    assert interval_overlap_mask(_array([]), _array([]), _array([0]), _array([1]), endpoint="closed").shape == (0,)


@pytest.mark.parametrize("boundary, expected", [("strict", [False, True, True]), ("closed", [False, False, True])])
def test_chronological_cutoff_names_preserve_historical_admissibility(boundary: str, expected: list[bool]) -> None:
    assert chronological_purge_mask(_array([4, 5, 6]), 5, boundary=boundary).tolist() == expected


@pytest.mark.parametrize("bad", [np.array([1.0]), np.array([[1]], dtype=np.int64), [1]])
def test_array_kernels_reject_implicit_casts(bad: object) -> None:
    with pytest.raises(TypeError, match="int64"):
        interval_overlap_mask(bad, _array([2]), _array([0]), _array([1]), endpoint="closed")
    with pytest.raises(TypeError, match="int64"):
        chronological_purge_mask(bad, 3, boundary="strict")


def test_array_kernels_reject_nat_invalid_lengths_bounds_and_policy() -> None:
    with pytest.raises(ValueError, match="NaT"):
        chronological_purge_mask(_array([int(np.iinfo(np.int64).min)]), 0, boundary="strict")
    with pytest.raises(ValueError, match="matching lengths"):
        interval_overlap_mask(_array([1]), _array([]), _array([]), _array([]), endpoint="closed")
    with pytest.raises(ValueError, match="ordered"):
        interval_overlap_mask(_array([2]), _array([1]), _array([]), _array([]), endpoint="closed")
    with pytest.raises(ValueError, match="endpoint"):
        interval_overlap_mask(_array([]), _array([]), _array([]), _array([]), endpoint="other")
    with pytest.raises(ValueError, match="boundary"):
        chronological_purge_mask(_array([1]), 0, boundary="other")
    for value in [int(np.iinfo(np.int64).min), 2**63]:
        with pytest.raises(ValueError, match="int64"):
            chronological_purge_mask(_array([1]), value, boundary="strict")
    with pytest.raises(TypeError, match="integer"):
        chronological_purge_mask(_array([1]), True, boundary="strict")


# --------------------------------------------------------------------------- #
# Public K-fold memberships, availability, and group cohesion
# --------------------------------------------------------------------------- #


def test_hand_derived_irregular_kfold_memberships_and_future_training() -> None:
    folds = _folds()
    assert [(f.eval_indices, f.train_indices, f.purged_indices, f.embargoed_indices) for f in folds] == [
        ((0, 1), (4, 5), (2,), (3,)),
        ((2, 3), (0,), (1, 4), (5,)),
        ((4, 5), (0, 1, 2), (3,), ()),
    ]
    assert all(not f.unavailable_indices for f in folds)
    assert folds[0].observation_ids == ("o0", "o1", "o2", "o3", "o4", "o5")
    assert folds[0].unit == "decision_time"
    assert folds[0].endpoint == "closed"
    assert folds[0].training_as_of == _AS_OF
    assert folds[0].embargo_periods == 1
    assert folds[0].embargo_duration is None
    with pytest.raises(FrozenInstanceError):
        folds[0].train_indices = ()


def test_period_embargo_and_elapsed_time_are_different_on_irregular_dates() -> None:
    short = _folds(embargo_periods=None, embargo_duration=timedelta(days=5))[0]
    touching = _folds(embargo_periods=None, embargo_duration=timedelta(days=7))[0]
    zero = _folds(embargo_periods=None, embargo_duration=timedelta(0))[0]
    assert short.embargoed_indices == ()
    assert short.train_indices == (3, 4, 5)
    assert touching.embargoed_indices == (3,)
    assert zero.train_indices == short.train_indices
    assert touching.embargo_duration == timedelta(days=7)
    assert _folds(embargo_periods=0)[0].train_indices == short.train_indices


def test_unavailable_precedes_purge_and_embargo_and_evaluation_is_retained() -> None:
    events = _events().with_columns(
        pl.when(pl.col("observation_id").is_in(["o2", "o3"]))
        .then(pl.lit(_AS_OF + timedelta(days=1)))
        .otherwise(pl.col("label_available_at"))
        .alias("label_available_at")
    )
    folds = _folds(events)
    assert folds[0].unavailable_indices == (2, 3)
    assert folds[0].purged_indices == folds[0].embargoed_indices == ()
    assert folds[1].eval_indices == (2, 3)
    exact_cutoff = _folds(events, training_as_of=_AS_OF + timedelta(days=1))[0]
    assert exact_cutoff.unavailable_indices == ()


def test_role_coverage_and_identity_are_invariant_under_input_permutation() -> None:
    events = _events()
    reordered = events[[4, 2, 5, 0, 3, 1]]
    baseline, shuffled = _folds(events), _folds(reordered)
    roles = ["train_indices", "eval_indices", "purged_indices", "embargoed_indices", "unavailable_indices"]
    assert sorted(i for fold in baseline for i in fold.eval_indices) == list(range(events.height))
    for original, permuted in zip(baseline, shuffled, strict=True):
        all_positions = [i for role in roles for i in getattr(original, role)]
        assert sorted(all_positions) == list(range(events.height))
        for role in roles:
            original_ids = tuple(original.observation_ids[i] for i in getattr(original, role))
            shuffled_ids = tuple(permuted.observation_ids[i] for i in getattr(permuted, role))
            assert original_ids == shuffled_ids


def test_duplicate_decision_times_stay_in_one_evaluation_unit() -> None:
    events = _events()
    extra = events.head(1).with_columns(pl.lit("second-at-zero").alias("observation_id"))
    folds = _folds(pl.concat([events, extra]), embargo_periods=0)
    assert folds[0].eval_indices == (0, 6, 1)
    assert all((0 in fold.eval_indices) == (6 in fold.eval_indices) for fold in folds)


def test_groups_define_kfold_and_embargo_units_and_purge_remains_rowwise() -> None:
    days = [0, 1, 3, 4, 9, 10, 20, 21]
    times = [_BASE + timedelta(days=day) for day in days]
    events = pl.DataFrame(
        {
            "observation_id": [f"g{i}" for i in range(8)],
            "decision_time": times,
            "target_start": times,
            "target_end": times,
            "label_available_at": times,
            "group": ["a", "a", "b", "b", "c", "c", "d", "d"],
        }
    )
    first = _folds(events, n_splits=2)[0]
    assert first.eval_indices == (0, 1, 2, 3)
    assert first.embargoed_indices == (4, 5)
    assert first.train_indices == (6, 7)
    assert first.unit == "group"
    # Evaluation interval ends halfway through group c. Its first row is purged;
    # the entire straddling group is embargoed, so its remaining row is excluded.
    changed = events.with_columns(
        pl.when(pl.col("observation_id") == "g3")
        .then(pl.lit(_BASE + timedelta(days=9, hours=12)))
        .otherwise(pl.col(name))
        .alias(name)
        for name in ["target_end", "label_available_at"]
    )
    first = _folds(changed, n_splits=2)[0]
    assert first.purged_indices == (4,)
    assert first.embargoed_indices == (5,)
    assert first.train_indices == (6, 7)
    duration = _folds(changed, n_splits=2, embargo_periods=None, embargo_duration=timedelta(hours=12))[0]
    assert duration.embargoed_indices == (5,)


def test_half_open_kfold_touching_boundaries_and_remainder_distribution() -> None:
    events = _events().with_columns((pl.col("target_start") + timedelta(hours=1)).alias("target_end"))
    events = events.with_columns(pl.col("target_end").alias("label_available_at"))
    folds = _folds(events, n_splits=4, endpoint="half_open", embargo_periods=0)
    assert [fold.eval_indices for fold in folds] == [(0, 1), (2, 3), (4,), (5,)]
    assert all(not fold.purged_indices for fold in folds)


def test_half_open_embargo_retains_decision_equal_to_last_test_endpoint() -> None:
    times = [_BASE + timedelta(days=day) for day in range(6)]
    ends = [time + timedelta(days=1) for time in times]
    events = pl.DataFrame(
        {
            "observation_id": [f"o{index}" for index in range(6)],
            "decision_time": times,
            "target_start": times,
            "target_end": ends,
            "label_available_at": ends,
        }
    )
    # Test labels are [0,1) and [1,2). The training label [2,3) touches but
    # does not overlap them. Both embargo conventions begin strictly after 2;
    # they exclude the decision at 3 while retaining the decision exactly at 2.
    for policy in (
        {"embargo_periods": 1},
        {"embargo_periods": None, "embargo_duration": timedelta(days=1)},
    ):
        first = _folds(events, endpoint="half_open", **policy)[0]
        assert first.eval_indices == (0, 1)
        assert first.train_indices == (2, 4, 5)
        assert first.embargoed_indices == (3,)
        assert first.purged_indices == ()


def test_all_overlapping_labels_return_explicit_empty_train() -> None:
    events = _events().with_columns(pl.lit(_AS_OF).alias("target_end"), pl.lit(_AS_OF).alias("label_available_at"))
    assert all(fold.train_indices == () for fold in _folds(events))


# --------------------------------------------------------------------------- #
# Rejection and no-mutation contracts
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "column", ["observation_id", "decision_time", "target_start", "target_end", "label_available_at"]
)
def test_required_columns_and_nulls_fail_closed(column: str) -> None:
    events = _events()
    with pytest.raises(TypeError, match=column):
        _folds(events.drop(column))
    with pytest.raises(ValueError, match="null"):
        _folds(events.with_columns(pl.lit(None).cast(events.schema[column]).alias(column)))


def test_invalid_identity_groups_timing_and_timezone_fail_closed() -> None:
    events = _events()
    with pytest.raises(ValueError, match="unique"):
        _folds(events.with_columns(pl.lit("same").alias("observation_id")))
    for value in ["", " padded "]:
        with pytest.raises(ValueError, match="nonempty"):
            _folds(events.with_columns(pl.lit(value).alias("observation_id")))
    with pytest.raises(ValueError, match="contiguous"):
        _folds(events.with_columns(pl.Series("group", ["a", "b", "a", "c", "d", "e"])))
    extra = events.head(1).with_columns(pl.lit("extra").alias("observation_id"))
    with pytest.raises(ValueError, match="share"):
        _folds(pl.concat([events, extra]).with_columns(pl.Series("group", ["a", "b", "c", "d", "e", "f", "other"])))
    for column, value in [("target_start", _BASE - timedelta(days=1)), ("label_available_at", _BASE)]:
        with pytest.raises(ValueError, match="require"):
            _folds(events.with_columns(pl.lit(value).alias(column)))
    with pytest.raises(TypeError, match="decision_time"):
        _folds(events.with_columns(pl.col("decision_time").dt.replace_time_zone(None)))
    with pytest.raises(TypeError, match="group"):
        _folds(events.with_columns(pl.lit(1).alias("group")))
    with pytest.raises(TypeError, match="Polars"):
        validate_partition_events([], endpoint="closed")


@pytest.mark.parametrize(
    "options",
    [
        {"n_splits": 1},
        {"n_splits": True},
        {"n_splits": 7},
        {"embargo_periods": -1},
        {"embargo_periods": False},
        {"embargo_periods": None},
        {"embargo_duration": timedelta(0)},
        {"embargo_periods": None, "embargo_duration": timedelta(days=-1)},
        {"embargo_periods": None, "embargo_duration": 1},
        {"training_as_of": datetime(2026, 1, 1)},
        {"training_as_of": _AS_OF.astimezone(timezone(timedelta(hours=1)))},
    ],
)
def test_invalid_partition_configuration(options: dict) -> None:
    with pytest.raises(ValueError):
        _folds(**options)


def test_empty_events_rejected_and_inputs_unchanged() -> None:
    events = _events()
    before = events.clone()
    _folds(events)
    assert events.equals(before)
    with pytest.raises(ValueError, match="empty"):
        _folds(events.head(0))
