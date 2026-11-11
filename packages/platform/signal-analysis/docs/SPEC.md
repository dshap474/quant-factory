# Signal analysis

Status: V1 and the §7 expansion implemented. Each concept document
records its own verification scope.
Owner: `packages/platform/signal-analysis`.

## 1. Outcome

Provide reusable tools for understanding and evaluating features, forecasts, and
signals before portfolio construction. A caller supplies observations and an
explicit target; the package returns reproducible measurements and, when supported,
statistical evidence with its assumptions and sample coverage.

The first release delivers one complete path:

**Validate a signal panel → construct or accept explicitly timed return targets →
compute cross-sectional Pearson or Spearman IC → return dated measurements,
coverage counts, and reasons for undefined results.**

V1 is a descriptive analysis foundation. A positive IC is not a promotion verdict.
Dependence-aware inference and trial provenance must be available before using the
package as the evidence engine for a formal signal-promotion round.

## 2. Ownership and dependencies

The package owns generic analysis contracts, target arithmetic, metrics,
uncertainty calculations, and subsequently supported selection corrections.

Consumers own signal construction, point-in-time universe membership, decision
clocks, source selection, benchmark/factor choices, research hypotheses, thresholds,
holdout access, and artifact destinations. They also own the evidence that supplied
timestamps and historical inputs reflect actual production availability.

`ml-engine` continues to own training, fold-local preprocessing, chronological
training-plan configuration, model artifacts, and its existing run tracking.
The §7 expansion moves shared model-independent interval
arithmetic into `signal_analysis.partitions`, consumed through a narrow public
adapter by the existing ML planner. Its pandas boundary, fixed-gap behavior,
purge conventions, and stored artifact format are preserved. Analysis also exposes
standalone research purged K-fold partitions with explicitly chosen interval and
post-test embargo conventions. It accepts fitted-model statistics, prediction
callables, and predictions; it never fits models or constructs a training engine.

`backtest` continues to own portfolio simulation and implementation economics.
Timing regressions that require portfolio returns consume explicitly supplied
returns; signal analysis does not secretly build or simulate a portfolio.

Dependency direction is consumers → `signal_analysis`. The library must import
without features, signals, strategies, research, ML training, private extensions,
credentials, repository data, or a running service. It has no `extensions/`.
Research implementations may inform a rewrite but must never be runtime imports.

## 3. Initial package shape

```text
packages/platform/signal-analysis/
├── pyproject.toml
├── README.md
├── AGENTS.md
├── docs/
│   └── SPEC.md
├── src/signal_analysis/
│   ├── __init__.py
│   ├── py.typed
│   ├── contracts.py
│   ├── targets.py
│   └── ic.py
└── tests/
    ├── test_contracts.py
    ├── test_targets.py
    └── test_ic.py
```

- Distribution: `quant-factory-signal-analysis`; import: `signal_analysis`.
- Use the repository's Hatch-based package convention and compatible Python range.
  Add root uv workspace membership and a workspace source entry during implementation.
- Runtime dependencies: Polars for tables, NumPy for arrays, SciPy for correlation
  primitives. Select constraints compatible with the existing workspace; do not
  change another package's pins to install this one.
- Use `uv`, `ruff`, `ty`, and `pytest`. Tests stay outside installable source.
- Document concept modules as the public API. The package root exports version
  metadata only; do not add a pass-through `api/` layer.
- `contracts.py` owns shared table validation. Keep small types and helpers in their
  owning concept unless genuinely shared. Prefer functions and immutable values.
- Code files follow repository purpose/usage docstrings and section banners.
- Imports perform no I/O. No CLI, registry, plugins, service layer, scheduler,
  global configuration object, database, or plotting dependency in V1.
- `AGENTS.md` routes to platform rules and records package-specific API boundaries;
  the README documents the installed public API and a complete runnable example.

Do not create empty modules for later increments. A module becomes a subpackage
only when its implemented behavior earns a split.

## 4. V1 input contracts

### Signal panel

One signal per call, with a unique `(decision_time, asset)` key:

| Column | Contract |
|---|---|
| `decision_time` | Non-null UTC-aware timestamp of the decision |
| `asset` | Non-null, nonempty string identifier without surrounding whitespace; otherwise opaque to the library |
| `signal_available_at` | Non-null UTC timestamp, no later than `decision_time` |
| `signal` | Float64 value; null/nonfinite values are retained for coverage accounting |
| `eligible` | Non-null boolean membership supplied by the consumer as of the decision |

Use Polars `Datetime("us", "UTC")` for temporal columns. Reject naive timestamps,
duplicate keys, incorrect types, null identity/eligibility, and availability after
the decision. Do not silently coerce, aggregate duplicates, or infer timezone.
Extra columns are allowed but do not influence computation. Inputs are not mutated.

`eligible` describes the consumer's supplied panel, not the entire historical
market. Coverage cannot detect securities omitted upstream. Document this limit.
Weights and multiple signal columns per call remain outside this one-signal IC
API; other concept modules document their own weighted or matrix contracts.

The original one-signal IC API stays unchanged. Separate multi-feature analysis
uses `validate_feature_frame(frame, feature_columns=...)` for an explicitly selected
wide Float64 matrix. It validates names and schema without filtering values or
asserting timing. `validate_feature_panel` additionally requires unique String
`observation_id`, UTC `decision_time`, and UTC `features_available_at` no later than
the decision. The latter is the caller's latest availability timestamp over all
selected features for that observation. It is a declaration, not reconstructed
historical proof. The caller supplies the eligible evaluation sample; methods
document whether missing/nonfinite values are counted or rejected. Neither helper
coerces types, infers clocks, fits a transform, or drops rows.

### Target windows and prices

A window table has unique `(decision_time, asset, target_id)` keys plus non-null
`target_start` and `target_end` UTC timestamps. `target_id` is a nonempty opaque
identifier without surrounding whitespace, with one documented definition within
the caller's experiment.

V1's built-in return target requires:

`decision_time < target_start < target_end`.

This deliberately implements strict future-entry evaluation. Same-instant entry
and contemporaneous diagnostics require a later explicit contract; the library
must not silently shift timestamps to accommodate them.

The caller resolves calendars and offsets into endpoints. V1 does not interpret
an integer as days or trading sessions. Missing sessions cannot shorten a requested
window or cause a positional shift to jump to a different endpoint. Both cumulative
and disjoint horizon windows can be represented without a horizon-ladder framework.

Prices have unique `(asset, timestamp)` keys and a Float64 `price`. Join exact
endpoint timestamps within each asset. No as-of joins, nearest-price substitution,
forward filling, interpolation, or corporate-action adjustment occurs here.
Consumers supply consistently adjusted prices where required.

### Target table

The target builder returns every requested window with `target`, `target_status`,
and `return_type`, retaining its identity and endpoints. `return_type` is `simple`
or `log`; mixed conventions inside one `target_id` are rejected by validation.

Supported statuses are `ok`, `missing_entry_price`, `missing_exit_price`,
`missing_both_prices`, `invalid_price`, and `invalid_target`. A missing/null endpoint price is missing;
a present nonfinite or nonpositive endpoint price is invalid and takes precedence.
For `ok`, the target must be finite. Every other status has a null target.

Caller-supplied targets use the same envelope. Their status vocabulary may also
include `missing_target`; unknown statuses are rejected.
They declare `target_kind` as an explicit nonempty string (built-in builder:
`price_return`); `return_type` may be null or a declared `simple`/`log` convention
for non-price-return targets. Metadata
must be consistent within each `target_id`. V1 can score supplied residual targets
but does not estimate their factor model or certify its causality.

The builder always emits `target_kind`. A valid supplied target still requires
strictly future, ordered endpoints. Target realization time is not proof of when
its value became available to a training process; consumers retain that separate
label-availability information when fitting models.

## 5. V1 public operations

Signatures below define the intended surface, not an additional orchestration layer.

```python
validate_signal_panel(panel: pl.DataFrame) -> None
validate_targets(targets: pl.DataFrame) -> None
validate_target_windows(windows: pl.DataFrame) -> None
validate_prices(prices: pl.DataFrame) -> None

build_forward_returns(
    windows: pl.DataFrame,
    prices: pl.DataFrame,
    *,
    return_type: Literal["simple", "log"],
) -> pl.DataFrame

cross_sectional_ic(
    panel: pl.DataFrame,
    targets: pl.DataFrame,
    *,
    target_ids: Sequence[str],
    method: Literal["pearson", "spearman"],
    min_pairs: int,
) -> pl.DataFrame
```

Validation is performed on both full input tables at each public calculation boundary. A validated wrapper
class, validation cache, alternate backend, and configurable column-name resolver
are unnecessary in V1. Callers rename their input columns explicitly.

`build_forward_returns` implements `exit / entry - 1` for simple returns and
`log(exit) - log(entry)` for log returns. Evaluate simple returns as
`(exit - entry) / entry` to preserve small changes. For log returns, use
`log1p((exit - entry) / entry)` when the absolute relative change is at most 0.5,
and a difference of logs otherwise, avoiding ratio overflow at extreme scales.
These are numerical evaluations of the same mathematical definitions.
Reject malformed windows and duplicate price keys. Preserve missing
or invalid observations as statuses; overflow/nonfinite arithmetic yields
`invalid_target` and a null target rather than a valid-looking result.

`cross_sectional_ic` requires a nonempty, unique list of target identifiers and
an explicitly chosen `2 <= min_pairs < 2**64` (Python integer, excluding booleans). No implicit
absolute-value transformation or sign selection is performed. For every supplied
decision date and requested target, join targets to the signal panel by exact key.
Ignore unrequested target identifiers. Reject requested target rows without a
matching signal-panel key; a panel key without a requested target is a coverage
loss. An entirely missing requested target still produces missing-target results.

Rank within each date's valid pairs, with average ranks for ties. Pearson uses raw
values. Neither operation pools assets and dates, fills missing values, rescales
returns, winsorizes data, or uses full-sample target filtering.

Return one row per `(decision_time, target_id)`, sorted by those columns:

| Field | Meaning |
|---|---|
| `method` | Exact correlation definition used |
| `min_pairs` | Requested computational minimum, not a significance threshold |
| `ic` | Signed correlation or null when undefined |
| `status` | `ok`, `insufficient_pairs`, `constant_signal`, `constant_target`, or `constant_both` |
| `n_total`, `n_eligible`, `n_valid` | Supplied, eligible, and usable pair counts |
| Exclusion counts | `n_ineligible`, `n_missing_signal`, `n_nonfinite_signal`, `n_missing_target`, `n_invalid_target` |

Result identifiers, methods, and statuses are Polars String; IC is nullable
Float64; counts and `min_pairs` are UInt64; decision timestamps use the input's
required UTC type. Preserve this schema even when there are no result rows.

Assign exactly one exclusion reason per row, in the order listed above. Absent
target rows and missing-price/target statuses count as missing targets;
invalid-price/target statuses count as invalid targets. Thus
`n_total = n_valid + sum(exclusion counts)` and
`n_eligible = n_total - n_ineligible`. Other defects on an excluded row remain
visible in the inputs rather than being double-counted in this summary.

Check insufficient pairs before constant-value statuses. Preserve all supplied
dates even when every pair is excluded. An empty, correctly typed panel returns
a correctly typed empty result; requested orphan target rows still fail validation.

V1 returns no p-value, t-statistic, confidence interval, annualized ICIR, or
SUPPORTED/FALSIFIED flag. Do not expose SciPy's default correlation p-values as
finance-valid inference. Do not replace undefined correlations with zero.

## 6. Evidence and provenance boundary

Calculations are deterministic and have no persistence side effects. Each real
consumer experiment must preserve the following before making comparative claims:

- Signal/candidate identity, definition, revision, and freeze/submission time.
- Data snapshot and point-in-time universe references; an explicit unknown marker
  where historical provenance cannot be reconstructed.
- Exact target definitions, clock/calendar resolution, and input fingerprints.
- Package version, code revision, requested metrics, and thresholds chosen in advance.
- Evaluation partitions, OOS provenance, and any fitting/calibration window.
- All tried variants and upstream screening that informed selection, including
  failures and rejected candidates; retain dated result series, not just winners.
- Whether the search history is complete; record later holdout access explicitly.

`evidence.AnalysisRecord`, `TrialRecord`, and `SearchEvidence` validate explicit
caller declarations and opaque references, which may point to existing `ml-engine`
records. They retain complete/unknown search-history declarations without
introducing another tracking system, resolving references, or writing files.
Callers serialize their records when needed. Statistical selection-input methods
remain a separate increment; declarations alone do not correct selection bias.
A local ledger cannot prove a holdout was never inspected outside the workflow.

## 7. Incremental expansion

These increments establish boundaries and order, not permission to implement all
modules during the first release. Each requires a focused contract and tests.

| Increment | Capability | Admission requirement |
|---|---|---|
| 1 | This V1: contracts, timed targets, cross-sectional IC | Acceptance checks in section 10 |
| 2 | Uncertainty, paired baseline comparison, analysis-record schema | Explicit inferential unit, dated samples, resampling/HAC assumptions, seed and tuning parameters, complete/unknown trial provenance |
| 3 | Quantiles, era stability, persistence, time-series IC, horizon analysis | Separate aggregation definitions; predeclared eras/horizons; clear time-series versus cross-sectional estimands |
| 4 | Residualization, redundancy, incremental information | Caller-supplied factors; fit windows and transforms restricted to information available at the decision; explicit benchmark hypothesis |
| 5 | Selection corrections — implemented for returns (Sharpe/Sortino/mean) in `selection`; IC/ICIR unimplemented | Statistic-specific method, complete aligned candidate evidence, declared search family, documented dependence assumptions |
| 6 | Classification, calibration, regime diagnostics | Explicit outcome/label space, probability semantics, baseline, and causal versus retrospective interpretation |

For increment 2, resample paired signal/baseline observations together. Preserve
date dependence and cross-candidate dependence. Do not collapse missing dates into
artificially contiguous blocks. Report observed sample counts; only report an
effective sample size when a named estimator justifies it. Block length equal to
a target horizon is not a proof of independence. Unsupported inference returns an
explicit unavailable result with a reason, not a degenerate confidence interval.

For increment 3, quantile returns are descriptive conditional returns, not a
simulated strategy or an automatically annualizable return stream. Define tie,
weighting, and rebalancing assumptions before reporting portfolio-like quantities.

For increment 5, names/counts alone are insufficient evidence for dependent trials.
DSR applies to its defined Sharpe/return setting, not directly to raw IC. An ICIR
adaptation requires separate derivation and validation. A Rademacher-style sign-flip
max statistic is not interchangeable with the published Rademacher bound.

For increment 6, supervised classification, conditional outcome analysis, and
unsupervised regime recovery are distinct operations. Synthetic recovery tests a
specified generator; it does not establish real-market regime truth.

### 7.1 Implemented Chapter 7/8 expansion

The following independent operations extend V1 without changing its target or IC
semantics. Detailed contracts and verification records are canonical in the linked
concept documents; each records its source interpretation and numerical domain.

| Module | Implemented scope | Contract |
| --- | --- | --- |
| `partitions` | Exact interval overlap, historical chronological purge kernel, independently callable grouped purged K-fold and post-test embargo | [PARTITIONS.md](PARTITIONS.md) |
| `importance.mdi` | Conventional and AFML zero-excluded attribution from supplied tree statistics | [IMPORTANCE.md](IMPORTANCE.md) |
| `importance.permutation` | One held-out partition, supplied fixed predictor/scorer, individual or joint feature-group permutation, raw or AFML-relative score decrease | [IMPORTANCE.md](IMPORTANCE.md) |
| `importance.single_feature` | Scoring aligned predictions from separately fitted one-feature models; no fitting inside analysis | [IMPORTANCE.md](IMPORTANCE.md) |
| `redundancy` | Pearson/Spearman pair relationships with coverage and explicit connected-component grouping, no pruning | [STRUCTURE_AND_STABILITY.md](STRUCTURE_AND_STABILITY.md) |
| `orthogonalization` | Fixed sample-standardized PCA basis, transformation, and descriptive eigenvalue/importance rank agreement | [STRUCTURE_AND_STABILITY.md](STRUCTURE_AND_STABILITY.md) |
| `stability` | Descriptive grouping of supplied dated metric observations, explicit equal/supplied weighting | [STRUCTURE_AND_STABILITY.md](STRUCTURE_AND_STABILITY.md) |
| `inference` | Bartlett Newey-West and nonwrapping moving-block mean/paired-difference inference on an explicit complete calendar | [INFERENCE_AND_EVIDENCE.md](INFERENCE_AND_EVIDENCE.md) |
| `targets.horizon_windows` | Fixed elapsed-time offsets from decision times into the target-window contract | [CONDITIONAL_AND_PERSISTENCE.md](CONDITIONAL_AND_PERSISTENCE.md) |
| `quantiles` | Per-date mean target within ordinal signal-rank quantiles, sharing the IC pair exclusion precedence | [CONDITIONAL_AND_PERSISTENCE.md](CONDITIONAL_AND_PERSISTENCE.md) |
| `stability.assign_eras` | Half-open predeclared era labels for caller frames; overlap and order enforced | [CONDITIONAL_AND_PERSISTENCE.md](CONDITIONAL_AND_PERSISTENCE.md) |
| `persistence` | Per-date Spearman between a signal and its lagged ranking over common eligible assets | [CONDITIONAL_AND_PERSISTENCE.md](CONDITIONAL_AND_PERSISTENCE.md) |
| `direction` | Per-date signed mean, always-long reference, and hit rate of a signal's sign against a target on IC-valid pairs; timing, not ranking | [DIRECTION.md](DIRECTION.md) |
| `blocks` | Calendar-anchored non-overlapping block means of a dated statistic with explicit, sweepable block length; first-insignificant-lag ACF diagnostic | [INFERENCE_AND_EVIDENCE.md](INFERENCE_AND_EVIDENCE.md) |
| `evidence` | Immutable caller declarations of candidates, inputs, trial history, and existing-record references | [INFERENCE_AND_EVIDENCE.md](INFERENCE_AND_EVIDENCE.md) |
| `selection` | PSR, DSR, effective trials, PBO-CSCV, paired White/studentized reality check with Holm, and the Rademacher Anti-Serum bound over a T × N grid of return series | [INFERENCE_AND_EVIDENCE.md](INFERENCE_AND_EVIDENCE.md) |

Research policy remains external. There is no implicit full-suite runner, metric
selection, sign optimization, feature pruning, significance threshold, calendar
inference, fitted regime classifier, or automatic interpretation of a result.
Distributions and raw repeats are retained where returned; a tree/fold/repetition
dispersion is not a dependence-aware inferential standard error. Matrix sample
scope and training/held-out declarations cannot prove historical input causality.

Only observed label-end arithmetic is shared with the existing ML planner. This
does not turn research K-fold into a new production training methodology or alter
the ML planner's pandas boundary, chronological ordering, minimum coverage,
fixed-gap convention, or sealed artifact format. Neither package imports the
other's private implementation. The dependency direction is `ml-engine` to
`signal_analysis`, never the reverse. Its existing supported Python/NumPy range
therefore also bounds this integrated ML environment; wider configurations are
not implied by the ML package's minimum-Python metadata.

These increments implement roadmap items 2 and 3, part of 4, and item 5 for return
series. The roadmap's
"time-series IC" is implemented only in the per-date, per-asset directional form of
`direction` (signed mean and hit rate on IC-valid pairs); a pooled time-series
correlation, fitted residualization, IC/ICIR selection corrections, calibration, and
regime discovery remain unimplemented. They require
their own specifications rather than being inferred from a module name.

## 8. Design decisions

These decisions fix the package's behavior where common practice is ambiguous:

1. Daily cross-sectional demeaning does not change Pearson or Spearman IC. The
   daily mean is constant across assets and has undefined cross-sectional IC.
   Test market timing against a separately defined aggregate time-series outcome.
2. Multi-class state labels cannot be evaluated as binary sign predictions without
   an explicit mapping. F1 is not directly comparable to a class prevalence; score
   the chosen baseline using the same metric and target space.
3. Target windows have actual endpoints. Horizon names and disjoint windows must be
   reconciled in the consumer protocol before any experiment.
4. An IC magnitude anchor such as 0.02 is not a universal threshold. Pearson,
   cosine similarity, and Spearman must not inherit one another's empirical bars.
5. Failure to reject zero effect is not proof of no effect. Statistical evidence
   can be inconclusive; a consumer's failed promotion gate is a separate decision.
6. An OOS loss or R-squared uses predictions produced without fitting to the scored
   outcomes. Fitting a regression on scored observations and reporting its fit is
   a different, descriptive analysis.
7. Changing the number of CV folds for already fixed predictions is not by itself
   a leakage test. Leakage evidence requires the relevant preprocessing, fitting,
   alignment, or input-availability path to be examined.

## 9. Integration


Integrate ML metrics through documented numeric/concept operations when useful.
Keep `ml-engine`'s pandas boundary intact; do not introduce a second dataframe
framework inside it or import a private splitter/metric implementation. A future
array-level public operation must be earned by the integration rather than added
speculatively to V1.

Before calling this a shared operational platform capability, demonstrate a second
independent consumer.

## 10. Acceptance and validation

Tests exercise public operations with independent, small known-answer fixtures.
Do not generate expected results by calling the implementation or using the same
library function that implements the calculation.

| Area | Required evidence |
|---|---|
| Packaging | Installed import succeeds without repository data, credentials, training dependencies, or private extensions; wheel includes `py.typed` |
| Timing | Future-unavailable signals fail; reversed/equal window endpoints fail; exact intended entry/exit are used; missing dates never substitute another price |
| Target arithmetic | Prices 100 → 110 yield simple return 0.1 and log return log(1.1); distinct assets cannot contaminate one another's endpoint joins |
| Target integrity | Missing entry/exit/both and invalid/nonpositive/nonfinite prices retain rows with the specified status; duplicate price keys fail |
| Correlation | Perfect ordering gives +1, reversal gives -1; Spearman for signals (1, 1, 2, 3) against targets (1, 2, 3, 4) is 3/sqrt(10) using average ranks |
| Estimand | A constructed panel with different per-date relationships distinguishes cross-sectional results from pooled correlation |
| Coverage | Every exclusion precedence, accounting identity, all-invalid date, unknown requested target, orphan key, and typed empty input behaves as specified |
| Undefined values | Too few pairs and constant signal/target/both return explicit statuses and null IC, never zero |
| Invariance | Input row order and asset renaming do not change results; positive affine transforms preserve Pearson and order-preserving transforms preserve Spearman |
| Future isolation | Appending prices after a requested exit cannot alter its existing target; changing one target/date cannot change unrelated dates' IC |
| Determinism | Repeated calls produce identical schemas, ordering, statuses, and counts; numerical tolerances are explicitly justified |

Use exact comparisons for identity, status, counts, timestamps, and simple integer
fixtures. For floating arithmetic on well-conditioned Float64 fixtures, begin with
absolute tolerance 1e-12; document any different tolerance by numerical conditioning
or algorithm. Include extreme-but-finite price cases and correlations near constant
inputs so overflow or cancellation does not silently produce a valid result.

Run these gates from the repository root after implementation:

```bash
uv lock --check
uv run --no-sync ruff format --check packages/platform/signal-analysis
uv run --no-sync ruff check packages/platform/signal-analysis
uv run --no-sync ty check packages/platform/signal-analysis/src
uv run --no-sync pytest packages/platform/signal-analysis/tests
uv run --no-sync pytest tests/contracts tests/boundary
```

Build and inspect the distribution in a temporary destination; validate installed
imports in an isolated environment with only declared runtime dependencies. Once
a consumer changes, also run its owning package's required checks. Existing dirty
work or unrelated baseline failures must be reported and left outside this scope.

## 11. Completion criteria

The initial implementation is complete when the documented example executes through
the installed API, all V1 contracts and acceptance checks pass, the package can be
used independently, and the README clearly identifies the capabilities that remain
unimplemented. No runtime stubs should suggest those capabilities
exist. This document does not establish a signal verdict.

## 12. Evidence and design references

- Binding placement: [platform rules](../../AGENTS.md).
- [ML package boundary](../../ml-engine/AGENTS.md).
- [Alphalens v0.4.0 utilities](https://github.com/quantopian/alphalens/blob/v0.4.0/alphalens/utils.py)
  and [performance functions](https://github.com/quantopian/alphalens/blob/v0.4.0/alphalens/performance.py):
  dated IC, entry alignment, coverage loss, and the documented lookahead caveat on
  forward-return z-score filtering. Tagged primary implementation; checked 2026-09-05.
- [Qlib data example](https://qlib.readthedocs.io/en/latest/component/data.html#example)
  and [record templates](https://qlib.readthedocs.io/en/latest/component/recorder.html#record-template):
  explicit T+1/T+2 target and computation/recording separation. Primary development
  documentation checked 2026-09-05; do not treat it as a pinned dependency contract.
- [Newey and West, 1986 working paper](https://www.nber.org/papers/t0055) and
  [Künsch, 1989](https://doi.org/10.1214/aos/1176347265): dependence-aware inference
  precedents, not a universal tuning prescription.
- [Bailey and López de Prado, 2014](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf),
  Eq. 2 and Appendix A.3: DSR's statistic, return moments, and independent-trial
  requirements. Primary author-hosted paper checked 2026-09-05.

The sources support individual constraints. The module layout, V1 limits, result
schemas, and expansion sequence are project engineering decisions.
