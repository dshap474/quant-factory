# Signal analysis

`quant-factory-signal-analysis` is an import-first numerical library for explicitly
timed targets, descriptive IC, research partitions, model importance, feature
structure, stability, and dependence-aware mean uncertainty. Callers choose the
analysis and its assumptions; results retain coverage and undefined outcomes.

The library never selects a universe, trains a predictive model, chooses a winning
feature, or assigns a promotion verdict. It has no filesystem or network effects.

It is a workspace member: `uv sync --frozen --group dev` installs it, and another member
adds it with `uv add --package <member> quant-factory-signal-analysis`.
Import operations from their concept modules; the package root exposes only version
metadata. The [specification](docs/SPEC.md) defines the complete table contracts.

## Complete example

```python
from datetime import datetime, timedelta, timezone

import polars as pl

from signal_analysis.ic import cross_sectional_ic
from signal_analysis.targets import build_forward_returns

t = datetime(2026, 1, 1, tzinfo=timezone.utc)
entry, exit_ = t + timedelta(days=1), t + timedelta(days=2)
panel = pl.DataFrame({
    "decision_time": [t] * 3,
    "asset": ["A", "B", "C"],
    "signal_available_at": [t] * 3,
    "signal": [1.0, 2.0, 3.0],
    "eligible": [True] * 3,
})
windows = panel.select("decision_time", "asset").with_columns(
    pl.lit("next_session").alias("target_id"),
    pl.lit(entry).alias("target_start"),
    pl.lit(exit_).alias("target_end"),
)
prices = pl.DataFrame({
    "asset": ["A", "B", "C", "A", "B", "C"],
    "timestamp": [entry] * 3 + [exit_] * 3,
    "price": [100.0, 100.0, 100.0, 110.0, 120.0, 130.0],
})
targets = build_forward_returns(windows, prices, return_type="simple")
result = cross_sectional_ic(
    panel, targets, target_ids=["next_session"], method="spearman", min_pairs=3,
)
assert result["status"].to_list() == ["ok"]
assert result["n_valid"].to_list() == [3]
assert abs(result["ic"][0] - 1.0) < 1e-12
print(result)
```

## Public API and contracts

- `signal_analysis.contracts.validate_signal_panel(panel)` checks signal identity,
  exact dtypes, non-null eligibility, and availability by decision time. String
  identifiers must be nonempty with no surrounding whitespace.
- `validate_target_windows(windows)` checks keys and strictly future UTC endpoints.
- `validate_prices(prices)` checks price keys and dtypes; bad values become target
  statuses when constructing returns.
- `validate_targets(targets)` checks target windows, finite-or-null target values,
  status vocabulary, and consistent metadata for each target identifier.
- `signal_analysis.targets.build_forward_returns(windows, prices, *, return_type)`
  joins exact asset/endpoint prices and computes `simple` or `log` returns.
- `signal_analysis.ic.cross_sectional_ic(panel, targets, *, target_ids, method,
  min_pairs)` returns one result per supplied decision date and requested target.
- `validate_feature_frame(frame, *, feature_columns)` checks an explicitly selected
  wide Float64 matrix without filtering observations or claiming timing.
- `validate_feature_panel(panel, *, feature_columns)` additionally checks unique
  `observation_id`, UTC `decision_time`, and the caller's latest availability time
  across selected features, `features_available_at <= decision_time`.

Tables use Polars, Float64 observations, String identifiers, and
`Datetime("us", "UTC")` clocks. Explicitly cast or rename consumer columns before
calling; the library does not guess. Extra columns are ignored. Duplicate keys and
malformed schemas fail even when a row would otherwise be excluded. Schema errors
raise `TypeError`; invalid content/parameters raise `ValueError`.

The return builder preserves each requested window and reports `ok`, missing
endpoint statuses, `invalid_price`, or `invalid_target`. Present bad prices take
precedence over missing endpoints. It emits `target_kind="price_return"` and the
chosen `return_type`. Caller-supplied targets use the same envelope, may additionally
use `missing_target`, and can declare another `target_kind`; their `return_type` is
then either null or a declared `simple`/`log` convention, consistent within each
`target_id`. Keep a null column explicitly typed as String. Null/invalid target values require
a corresponding non-`ok` status; `ok` requires a finite value.

IC results retain `n_total`, `n_eligible`, `n_valid`, and mutually exclusive exclusion
counts, in precedence order: ineligible, missing signal, nonfinite signal, missing
target, invalid target. Counts are UInt64. Every supplied date remains represented,
including dates with zero valid pairs. Missing requested target identifiers produce
coverage losses; requested target keys absent from the panel fail. Both input
tables are validated in full; unrequested valid targets do not enter calculations.

Pearson uses raw values; Spearman uses average ranks for ties. Results preserve sign.
`min_pairs` must be a Python integer in `[2, 2**64)` excluding booleans. It is a
computational minimum. Insufficient pairs or constant inputs produce a null IC and
an explicit status. Unexpected nonfinite numerical correlation raises
`ArithmeticError`. Results and target rows have deterministic sorted order.

## Chapter 7/8 analysis modules

Each operation is independently callable. Import from the named concept module;
there is no global analysis configuration, implicit pipeline, or method registry.

| Module | Public operations | Definition and verification |
| --- | --- | --- |
| `partitions` | `interval_overlap_mask`, `chronological_purge_mask`, `validate_partition_events`, `purged_kfold` | [Interval conventions, grouped evaluation, availability, and embargo](docs/PARTITIONS.md) |
| `importance.mdi` | `mean_decrease_impurity` | [Conventional and AFML zero-excluded tree attribution](docs/IMPORTANCE.md) |
| `importance.permutation` | `permutation_importance` | [Held-out score changes from a fixed predictor, individual or jointly permuted feature groups](docs/IMPORTANCE.md) |
| `importance.single_feature` | `single_feature_importance` | [Scores of supplied, independently fitted one-feature predictions](docs/IMPORTANCE.md) |
| `redundancy` | `feature_correlations`, `correlation_groups` | [Explicit pairwise coverage and grouping without feature selection](docs/STRUCTURE_AND_STABILITY.md) |
| `orthogonalization` | `fit_pca`, `transform_pca`, `eigenvalue_importance_agreement` | [A fixed PCA basis and descriptive component-rank agreement](docs/STRUCTURE_AND_STABILITY.md) |
| `stability` | `assign_eras`, `summarize_metric_stability` | [Caller-defined asset, period, or regime summaries](docs/STRUCTURE_AND_STABILITY.md) |
| `inference` | `newey_west_mean`, `newey_west_paired_difference`, `moving_block_mean`, `moving_block_paired_difference` | [Explicit-calendar Bartlett HAC and nonwrapping moving-block inference](docs/INFERENCE_AND_EVIDENCE.md) |
| `targets` | `horizon_windows` | [Fixed-offset target windows from decision times](docs/CONDITIONAL_AND_PERSISTENCE.md) |
| `quantiles` | `quantile_conditional_means` | [Descriptive mean target within signal-rank quantiles, IC exclusion precedence](docs/CONDITIONAL_AND_PERSISTENCE.md) |
| `persistence` | `signal_rank_autocorrelation` | [Per-date Spearman between a signal and its lagged ranking](docs/CONDITIONAL_AND_PERSISTENCE.md) |
| `direction` | `directional_scores` | [Per-date signed mean, always-long reference, and hit rate of a signal's sign against a target](docs/DIRECTION.md) |
| `blocks` | `block_means`, `block_samples`, `first_insignificant_lag` | [Calendar-anchored block averages of a dated statistic and its decorrelation-lag diagnostic](docs/INFERENCE_AND_EVIDENCE.md) |
| `evidence` | `AnalysisRecord`, `TrialRecord`, `SearchEvidence`, and declaration validators | [References to caller-owned inputs, results, and trial history](docs/INFERENCE_AND_EVIDENCE.md) |
| `selection` | `probabilistic_sharpe`, `deflated_sharpe`, `effective_trials`, `pbo_cscv`, `reality_check`, `holm`, `rademacher_bound` | [Selection-inflation statistics for a grid of return series](docs/INFERENCE_AND_EVIDENCE.md#selection-statistics-for-return-grids) |

Purged K-fold can train on both sides of a test period; it is a research partition,
not a chronological deployment claim. The shared ML adapter preserves
`ml-engine`'s historical pre-evaluation gap and exact-purge behavior. Its gap is
distinct from this module's explicitly specified post-test embargo.

For MDA, callers supply a fixed prediction callable and a scorer with explicit
direction, weights, seed, normalization, and evaluation provenance. For SFI,
`ml-engine` performs independent one-feature fits; pass its `candidate_oos`
predictions and model-feature declarations to analysis. Use `final_refit=False`
when only held-out analysis is wanted. Tree/repetition/fold dispersion is labelled
descriptively; it does not automatically establish a confidence interval.

PCA is a numerical decomposition of the supplied sample. `purpose="training"`
declares how a caller intends to use the basis; it cannot certify that the fit
sample excluded evaluation observations. Reuse the fitted basis when transforming
test data. Importance/PCA rank agreement is a diagnostic, not proof against overfit.

HAC and moving-block inference require a caller-supplied expected session grid.
Missing or nonfinite sessions retain coverage and an unavailable inference result;
they are never removed to create artificial adjacency. Moving blocks require
`n = block_length * integer`, use all overlapping nonwrapping starts, and expose
their conditional standard error separately from a Monte Carlo basic interval.
Lag/block length, confidence level, random seed, and repetition count are explicit.

Block means replace an autocorrelated dated statistic with `floor(N / s)` non-overlapping
calendar blocks of `s` sessions (Paleologo §8.3.1). `s` is explicit, defaults to 30
sessions, and is meant to be swept; the decorrelation lag is a reported diagnostic
that never sets `s`. Blocks anchor to the declared calendar, so a missing session
lowers coverage and never moves an edge; trailing partial blocks and blocks below
`min_coverage` are retained with a non-`ok` status and no mean. `block_samples`
hands the `ok` blocks to the inference operations under the caller's assertion that
dependence is defined in block units.

## Responsibility and limits

Consumers supply real availability times, eligible universes, calendar-resolved
windows, consistently adjusted prices, and data provenance. The library cannot
identify assets omitted upstream or prove supplied timestamps are truthful.
The return-target API requires strictly future entry:
`decision_time < target_start < target_end`.
It does not infer sessions, substitute missing prices, fit residual models, or
construct/train signals. No filesystem, network, tracking, or plotting side effects.

Pooled time-series correlation, selection corrections, calibration, and fitted regime
discovery are not implemented. Quantile means, rank persistence, and directional
scores are descriptive; they are not a simulated portfolio or a turnover model. The new confidence intervals apply to their
specified dated mean or paired-difference estimand; they are not automatic p-values
for a single cross-sectional IC or corrections for repeated research trials.
Positive IC or importance is not profitability or a promotion verdict. Consumers
retain candidate definitions, data references, targets, partitions, dated results,
search history, and holdout access. Evidence validation checks supplied declarations
without resolving references or proving historical completeness.

The supported package environment is Python 3.12 and NumPy 1.26.x;
the new ML dependency inherits this constraint. Executed evidence names the actual
Python, dependency, and OS versions tested. No universal numerical or empirical
correctness claim follows from finite tests.

## Development

From the repository root:

```bash
uv sync --frozen --inexact --package quant-factory-signal-analysis --group dev
uv run --no-sync pytest packages/platform/signal-analysis/tests
uv run --no-sync ruff format --check packages/platform/signal-analysis
uv run --no-sync ruff check packages/platform/signal-analysis
uv run --no-sync ty check packages/platform/signal-analysis/src
uv lock --check
```

`--inexact` preserves other installed workspace tools. Package/boundary changes also
run `uv run --no-sync pytest tests/contracts tests/boundary` in the repository's
development environment.
Build and isolated installation checks use a temporary output directory.
