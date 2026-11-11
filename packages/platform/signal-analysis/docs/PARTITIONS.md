# Chapter 7 partitions and compatibility

This module implements model-independent Chapter 7 purging and future-side
embargo for research cross-validation. It does not fit or score an estimator.
Chronological training planning, pandas normalization, and model artifacts remain
in `ml-engine`.

## Source and specification

Source: *Advances in Financial Machine Learning*, Chapter 7, sections 7.4.1–7.4.3.
For a train label interval
`[a,b]` and evaluation label interval `[c,d]`, closed overlap means their
intersection is nonempty: `a <= d and c <= b`. This covers containment in either
direction, equality, and touching endpoints. `half_open` instead treats intervals
as `[a,b)` and requires `a < d and c < b`; zero-length intervals are rejected.

The source's displayed empty-intersection expression in 7.4.1 conflicts with its
prose and three overlap conditions. We implement nonempty intersection. Snippet
7.3 also permits some boundary equalities that differ from the closed-interval
prose. The public endpoint option is required so these conventions are explicit.
Purging uses the exact union of evaluation intervals, preserving gaps; no shortcut
replaces that union with its convex hull. Variable and nested intervals are valid.

## Public API and domains

`interval_overlap_mask(start, end, reference_start, reference_end, *, endpoint)`
accepts one-dimensional NumPy int64 arrays in one caller-declared common time
unit. Paired arrays have equal lengths; int64-min (the datetime NaT sentinel) and
reversed intervals are invalid. Empty arrays are valid. Each True marks an
interval excluded because it overlaps at least one reference interval. Sorting
reference starts and using prefix maximum ends implements the union query without
an N by M allocation. No timestamp subtraction or floating-point conversion occurs.

`chronological_purge_mask(label_end, evaluation_start, *, boundary)` exposes the
historical ML endpoint rule, with True meaning excluded. `strict` excludes
`end >= evaluation_start`; `closed` excludes `end > evaluation_start`. These
names describe the admissible training cutoff, not the interval topology above.
NaT is rejected by this public kernel; ML filters missing endpoints before calling
it and keeps those rows score-only as before.

`purged_kfold(events, *, n_splits, endpoint, training_as_of, embargo_periods=None,
embargo_duration=None)` requires exactly one embargo argument, including an
explicit zero. `n_splits` is at least two and no larger than the number of units.

The event schema is separate from V1's strictly future price-return targets:

| Column | Contract |
|---|---|
| `observation_id` | Unique nonempty String without surrounding whitespace |
| `decision_time` | Non-null Datetime(us, UTC), scheduling coordinate |
| `target_start`, `target_end` | Non-null Datetime(us, UTC), label information interval |
| `label_available_at` | Non-null Datetime(us, UTC), declared fitting availability |
| `group` (optional) | Nonempty String, contiguous in chronological order |

Require `decision_time <= target_start <= target_end <= label_available_at`,
with strict `target_start < target_end` for half-open intervals. These constraints
are validated over the full table. Callers may include extra columns. Inputs are
never mutated. No available-at timestamp is inferred from a label endpoint.

Sort by decision time and observation identity. Without `group`, each distinct
decision time is one split unit. With `group`, each contiguous group is one unit;
different groups cannot share a decision time. Split units into contiguous blocks
using K-fold integer division (earlier folds receive the remainder). Every row is
evaluated exactly once; training candidates come from both sides of each block.
Group cohesion applies to evaluation assignment and embargo. Interval purging and
availability exclusions are rowwise and can retain part of a training group.

`embargo_periods` counts whole chronological units containing decisions after the
latest evaluation label endpoint. It counts observed units, not rows, days, or an
inferred calendar. `embargo_duration` is a nonnegative `timedelta`, measuring actual
elapsed microseconds: decisions in `(latest evaluation end, end + duration]`
activate whole-unit embargo. A group straddling an embargo boundary is excluded
as a whole. Zero disables embargo. Neither option applies a pre-evaluation gap.
Both embargo conventions begin strictly after the latest evaluation label end,
independently of `endpoint`: a decision exactly equal to that end is not embargoed
and may remain trainable under `half_open` if it does not otherwise overlap.
For example, evaluation labels `[0,1)` and `[1,2)` can retain a training label
`[2,3)` even with positive embargo. This explicit convention differs from
mechanically extending the last half-open evaluation interval before purging.

`training_as_of` is a required timezone-aware UTC-equivalent Python datetime.
Training labels with `label_available_at > training_as_of` are excluded; equality
is available. This is a supplied global fitting cutoff for research CV. It does
not mean future-side training was possible at the evaluation decision time.
Evaluation rows are retained even if their labels were not yet available at this
cutoff; subsequent scoring must establish its own outcome availability.

Each immutable `PartitionFold` preserves original input positions, an immutable
observation-ID mapping, fold identity, endpoint convention, unit type, and embargo
and availability settings. Its train/evaluation/purged/embargoed/unavailable
position tuples partition all supplied rows. Assign exactly one role in this order:
evaluation, unavailable, purged, embargoed, train. Tuples are in chronological and
identity order. Empty training sets are explicit results; consumers own minimum
sample requirements. Deterministic IDs survive row permutations; position indices
always refer to the caller's original table.

## ML migration

Only the numeric endpoint decision inside `_apply_exact_purge` delegates to the
public chronological kernel. ML's existing `SplitConfig`, public Fold/FoldPlan,
period-range planning, minimum retained periods, metadata, pandas input boundary,
cutoffs, and fixed-gap workflows remain unchanged. ML's `embargo_periods` continues
to mean its historical **pre-evaluation gap**. The research K-fold operation does
not add a new ML training methodology or change sealed artifacts.

## Verification plan and scope

Use exact equality for integer membership, IDs, metadata, and UTC microseconds;
there is no floating-point error budget or convergence study for discrete interval
membership. Independent anchors enumerate hand-derived nesting/touching outcomes
and full fold memberships on irregular dates. A bounded doubled-integer grid oracle
constructs sets of points inside intervals, then intersects those sets; it does not
reuse production comparison expressions or its sorted-prefix algorithm.

Orthogonal checks cover translation, permutation, interval-union decomposition,
disjoint/conserved role coverage, every observation evaluated once, whole-group
assignment/embargo, invalid schema and time domains, NaT, and overflow-adjacent
integer boundaries. Historical ML tests exercise the public production planner
through strict/closed boundaries, variable horizons, missing labels, duplicate
times, groups, and explicit pre-evaluation gaps.

These checks establish scoped code conformance only. Purging and embargo are not
proof of independence, reliable real-world availability, freedom from selection
bias, economic usefulness, or live chronological forecasting validity. The chapter's
example percentage is not a universal embargo recommendation or package default.

