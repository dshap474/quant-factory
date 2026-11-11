# Feature structure and stability

These pure operations describe caller-supplied observations. They do not select
features, fit predictive estimators, discover regimes, assess significance, or
certify training/test isolation. The concept modules are public; the package root
continues to expose version metadata only. Dependencies remain NumPy, Polars,
SciPy, and the Python standard library. No function reads or writes artifacts.

## Source and equation map

Research source: López de Prado, *Advances in Financial Machine Learning* (2018),
Chapter 8, especially sections 8.2–8.5 and snippets 8.5–8.6.
Chapter 7 sections 7.3–7.4 supply the separate leakage/purging/embargo context.
These sources are research inputs, not runtime dependencies.

| Source/definition | Equation and implementation | Assumptions and limits |
| --- | --- | --- |
| Ch8 §8.3 linear substitution | `redundancy.feature_correlations`: signed Pearson covariance divided by centered norms; Spearman is Pearson of pair-local average ranks | Correlation is descriptive dependence, not incremental predictive importance; zero linear correlation does not imply independence |
| Ch8 §8.4.2 standardization | `orthogonalization.fit_pca`: `Z[t,j] = (X[t,j] - mu[j]) / sigma[j]`, `sigma² = sum((X-mu)²)/(T-1)` | Complete finite fit rows; sample scale ddof=1 matches the snippet's pandas sample standard deviation; constants explicitly have scale 1 and zero fit deviations |
| Ch8 §8.4.2 decomposition | SVD `Z=USV'`; loadings `W=V`, covariance eigenvalues `lambda=S²/(T-1)`; `transform_pca` returns `P=ZW` | Book Gram eigenvalues equal `(T-1)*lambda`. On the fit sample `P'P=(T-1)diag(lambda)`; transformed future data need not be orthogonal |
| Ch8 snippet 8.5 truncation | Caller supplies `n_components`, or None retains `min(T,N)` components | No implicit 95% threshold, positive-eigenvalue filtering, or feature deletion. The snippet's positive-eigenvalue comment is not implemented by its displayed code; this API instead reports numerical rank and retains requested zero directions |
| Ch8 snippet 8.6 agreement | `eigenvalue_importance_agreement`: SciPy additive hyperbolic weighted Kendall, `rank=True`, `additive=True`; pair exchange weight `1/(r_i+1)+1/(r_j+1)` | Two decreasing lexicographic rankings `(eigenvalue,importance)` and `(importance,eigenvalue)` are computed and their tie-adjusted coefficients averaged; ranks start at zero. Larger scores rank higher |
| Ch8 §§8.2,8.5 cross-instrument/period questions | `stability.summarize_metric_stability`: `mean=sum(w*x)/sum(w)`, `std_population=sqrt(sum(w*(x-mean)²)/sum(w))` within explicit feature/metric/groups | Descriptive aggregation of supplied observations is distinct from refitting an estimator on stacked data. Population dispersion uses ddof=0, and is not an SE or confidence interval |

SciPy's installed `weightedtau` documentation specifies symmetric lexicographic
ranking and weighted tie normalization (Vigna, 2015, *A weighted correlation index
for rankings with ties*). Ties in eigenvalues or importance are retained; arbitrary
component numbering does not break a tied score. The coefficient does not treat
the magnitude of a gap as additional agreement. Finite negative importances are
allowed, with larger values meaning more important. Finite negative eigenvalues
are rejected. No p-value is returned.

The book presents high PCA/importance rank agreement as confirmatory evidence.
This implementation makes the narrower claim that the rankings agree. PCA is
unsupervised, but fitting preprocessing on scored/test observations can still leak
information. A purpose declaration of `training` does not prove that the caller
used training-only rows. Predictive callers fit preprocessing within their
`ml-engine` training partitions and retain the appropriate Chapter 7 timing
controls. A basis fitted to the full sample remains descriptive. No rank
coefficient proves generalization, excludes overfitting, or supplies a promotion
threshold. Purging alone is not proof of independence.

## Public operations and sample contracts

```python
from signal_analysis.redundancy import feature_correlations, correlation_groups
from signal_analysis.orthogonalization import (
    PCABasis, fit_pca, transform_pca, eigenvalue_importance_agreement,
)
from signal_analysis.stability import summarize_metric_stability

pairs = feature_correlations(
    selected_rows, feature_columns=["momentum", "trend"],
    sample_scope="declared asset universe, January training observations",
    method="spearman", min_pairs=3,
)
groups = correlation_groups(pairs, threshold=0.8, absolute=True)
basis = fit_pca(
    train_rows, feature_columns=["momentum", "trend"],
    fit_sample_scope="fold 1 training rows", purpose="training", n_components=None,
)
test_components = transform_pca(test_rows, basis)
summary = summarize_metric_stability(
    dated_observations, group_by=["asset", "era"], weighting="supplied",
    sample_scope="frozen experiment, caller-defined eras",
)
```

The snippets illustrate interfaces; callers supply the named input tables.
`feature_columns` is a nonempty unique sequence of trimmed names selecting
Float64 Polars columns. Extra columns are ignored. The generic numeric-frame
contract deliberately asserts no row identity, chronology, eligibility, or
availability. Callers select rows and retain those identities and timestamps.
Scope strings are nonempty trimmed declarations, not executable selection rules.
No API fills, winsorizes, clips, imputes, or chooses sample rows implicitly.

### Redundancy

Every lexicographically sorted unordered pair, including diagonals, has one row:
`feature_left`, `feature_right`, `sample_scope`, `method`, `min_pairs`, nullable
`correlation`, `status`, and UInt64 `n_total`, `n_valid`, `n_missing_pair`,
`n_nonfinite_pair`. A null in either feature excludes a pair first; a nonfinite
value excludes the remaining pair second. Counts reconcile exactly. A feature
self-correlation is undefined if it is constant, rather than forced to 1.
`min_pairs` is an explicit Python integer in `[2,2**64)`, excluding booleans.

Statuses are `insufficient_pairs`, then `constant_both`, `constant_left`,
`constant_right`, or `ok`. Empty supplied rows still produce the feature-pair
inventory with insufficient counts. Pairwise deletion can produce a matrix that
is not positive semidefinite; it is not an input to the PCA fit operation. Pearson
uses raw values and Spearman ranks only the valid observations for that pair.
This API pools exactly its supplied rows, so callers must explicitly subset for
per-asset or per-period correlations when those are the intended estimands.

`correlation_groups` accepts one complete `feature_correlations` result.
A graph edge meets `correlation >= threshold`, or `abs(correlation) >= threshold`
when `absolute=True`. Threshold bounds are `[-1,1]` signed and `[0,1]` absolute.
Undefined pairs supply no edge. Connected-component membership is transitive;
not every two members must meet the pair threshold. The group label is its
lexicographically smallest feature name. Every feature is returned, including
isolated and constant features, with threshold, sign treatment, method and scope.
No member is designated a representative or selected for removal.

### PCA and component agreement

PCA fitting requires at least two complete finite rows. No pairwise deletion is
used. Input feature order is saved. `n_components` must be explicitly supplied
as None or an integer in `[1,min(T,N)]`, excluding booleans. Fit output is a frozen
`PCABasis` whose returned fields contain immutable tuples: original feature names,
rounded means, two-part centering data, sample scales, loadings (features ×
components), descending sample covariance eigenvalues, explained-variance ratios,
constant feature names, numerical rank, fit count, scope, purpose, and status.
Statuses are `ok`, `rank_deficient`, and `no_variation`. Numerical rank uses
`eps*max(T,N)*largest_singular_value`; it is a floating-point diagnostic, not an
automatic component selection. All-constant fit samples have zero eigenvalues and
**null/None explained-variance ratios**, because their variance denominator is zero.

A canonical loading sign makes repeated identical calls easier to compare, but
repeated eigenvalues have non-unique eigenvectors. Compare the complete repeated
subspace through its projector or reconstruction, not individual loading signs.
A requested cut through a repeated eigenspace has no uniquely preferred direction.
When `N>T`, None retains only `T` directions: fit reconstruction remains possible,
but an arbitrary future row may contain omitted null-space variation.

`transform_pca(frame, basis)` aligns by saved names, preserves row order, ignores
extra columns, and rejects missing features or nonfinite values. Results are
Float64 `PC_1`, `PC_2`, etc., including a typed empty result. The basis is never
refitted. New values in a formerly constant feature use its fitted mean and scale
1; this variation is not silently zeroed, though retained loadings may omit it.
Callers preserve row identities beside the resulting component table.

Agreement input requires unique trimmed `component:String` identities and
`eigenvalue:Float64`, `importance:Float64`. Callers align these identities to the
same fitted components and comparable importance definition. Output is one row
with scope, exact method name, nullable agreement, status, and the same pair
coverage counts as redundancy. Fewer than two usable pairs or a constant ranking
returns an explicit null with `insufficient_pairs`, `constant_eigenvalue`,
`constant_importance`, or `constant_both`. No rank comparison silently substitutes
original-feature importance for component importance.

### Dated stability

Inputs have a unique `(observation_time, asset, feature, metric)` identity:
`observation_time` is non-null `Datetime("us","UTC")`; identifiers are non-null,
nonempty trimmed Strings; `value` is Float64 and may be missing or nonfinite.
Optional caller grouping columns must be non-null trimmed Strings. Duplicate
identities are rejected even when group labels differ. The `metric` identifier
must denote one comparable definition and unit within the caller's experiment;
the library cannot infer this from its name. Dated raw evidence remains with the
caller rather than being replaced by a summary.

`group_by=[]` pools supplied observation rows within each feature/metric.
`group_by=["asset"]` returns separate asset summaries; adding `era` or `regime`
uses the caller's labels. Nothing fits regimes or chooses era boundaries.
`stability.assign_eras` labels rows from predeclared half-open eras (see
[CONDITIONAL_AND_PERSISTENCE.md](CONDITIONAL_AND_PERSISTENCE.md)); the boundaries
remain the caller's declaration.
An equal-weight row mean gives more influence to assets with more observations;
it is not an equal-asset mean. `weighting="equal"` gives each usable row weight 1.
`weighting="supplied"` requires finite, nonnegative Float64 `weight` on **every**
row, including rows with missing metrics. Callers can supply inverse asset counts
for an equal-asset estimand if that matches their intended coverage policy.

Output retains feature/metric/groups, sample scope, weighting, nullable `mean`,
`std_population`, `minimum`, `maximum`, and `status`. Coverage includes UInt64
`n_total`, `n_valid`, `n_missing`, `n_nonfinite`, `n_zero_weight`, `n_dates`,
`n_dates_supplied`, `n_assets`, `n_assets_supplied`, plus usable `weight_sum`, first
and last supplied observation times, and first and last valid times. Exclusion
precedence is missing, nonfinite, then zero weight; counts reconcile exactly.
`n_dates` counts distinct timestamps of usable positive-weight observations, not
calendar days or effective independent samples. Entirely invalid groups retain
all supplied coverage and null metrics with `no_valid_observations`. Typed empty
inputs produce typed empty results. No absent timestamp, security, group, or
observation omitted upstream is inferred or counted as a missing row.

## Numerical methods, evidence, and limits

All calculations use CPU Float64. Inputs have caller-defined units; correlation,
standardized PCA scores and rank agreement are dimensionless. Stability means
and dispersions retain the metric's unit. There is no annualization, return
compounding, currency conversion, calendar approximation, model inference or
serialization path. These are closed-form reductions/SVD, so discretization
order and iterative convergence studies do not apply.

Redundancy subtracts an anchor before scaling, preserving adjacent finite floats,
and halves opposite extremes when subtraction would overflow. PCA stores a
two-part center to preserve variation between adjacent large floats; SVD avoids
squaring a poorly conditioned covariance matrix before decomposition. Subnormal
nonconstant fit scales are explicitly unsupported because their relative
representation error can destroy centering; unrepresentable scales/scores raise
`ArithmeticError`. Constant inputs remain supported. Rank deficiency does not
raise. Stability accumulates weighted sums and second moments as exact rational
values of the supplied Float64 observations and weights. The mean is rounded
once; dispersion rounds the exact variance's square root directly to Float64
using integer midpoint comparisons and ties-to-even. This preserves tiny
positive weights, cancellation residuals, constant subnormals and maximum-finite
moments without intermediate products overflowing or underflowing. An
unrepresentable usable weight sum or moment raises `ArithmeticError`.
No nonfinite computed moment is returned with status `ok`.

Public-entry tests are in `test_redundancy.py`, `test_orthogonalization.py`, and
`test_stability.py`. The independent oracle portfolio includes:

- Hand Pearson reversals and Spearman midrank answer `3/sqrt(10)`, pair counts,
  affine/monotone invariance, extreme and adjacent-float values.
- An analytically rank-one two-feature PCA with covariance eigenvalues `(2,0)`
  and projector whose four entries are `1/2`; repeated-eigenvalue subspace,
  reconstruction, orthogonality, sample centering, column alignment, fixed-fit
  future transformations, constants, and more features than fit rows.
- Chapter 8 snippet 8.6's independent six-pair answer `61/75`; an exhaustive
  Fraction-based weighted pair oracle with tie denominators, independent of
  SciPy's mergesort algorithm; reversal, ties, coverage and undefined ranks.
- Weighted masses `(1/4,3/4)` at `(1,3)`, giving mean `5/2` and population
  dispersion `sqrt(3)/2`; distinct asset, pooled-row, weighted-asset and era
  estimands; coverage identities and deterministic row reordering.
- Decimal90 moments for seven zeros plus three `1e308` observations, and the
  independent-review regression with values `(0,1e308)` and weights
  `(1e200,1e-200)`, whose finite mean is about `1e-92` and dispersion `1e108`.
  Both input orders are tested. Normalizing weights first would falsely return
  zero for both moments. A second independent-review regression uses values
  `(-1e100,1e50,0)` and weights `(1e-200,1,1e-20)`: anchoring deviations on
  the tiny-weight first observation incorrectly yields dispersion 1 instead of
  about `1e40`. Three row orders agree with a Decimal700 reference.
- A seeded 24-case Decimal800 exponent campaign remains in the suite; a separate
  1,000-case run covered the same `10^-300` through `10^300` value/weight strata
  without a discrepancy at relative tolerance `1e-12`. This wider tolerance
  accommodates rounding across disparate exponent scales and small mixtures.

Small well-conditioned Float64 results use absolute tolerance `1e-12` and zero
relative tolerance; this covers ordinary LAPACK and square-root-weight rounding.
Large/tiny Decimal-reference moments use relative tolerance `1e-14` and zero
absolute tolerance so small nonzero contributions cannot pass as zero. Identifiers,
counts, schemas, statuses and immutable metadata use exact comparisons. Six
in-memory seeded faults were detected by their focused public tests: replacing
`T-1` with `T`, omitting PCA feature scaling, changing additive rank weights to
multiplicative, restoring first-row stability centering, normalizing weights
before square roots, and replacing Spearman average ties with ordinal ranks.
The source files were unchanged during those fault-sensitivity runs. These
finite tests support scoped implementation conformance; they do not establish
empirical predictive value, universal numerical correctness, or cross-platform
bitwise equality of repeated-eigenvalue bases.
