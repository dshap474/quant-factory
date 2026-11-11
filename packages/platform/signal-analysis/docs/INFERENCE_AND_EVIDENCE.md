# Dated inference and caller-owned evidence

Implemented scope: means and paired mean differences using named Bartlett HAC and
moving-block estimators, validation of supplied analysis/search declarations, and
selection-inflation statistics for grids of return series.
These operations neither fit a model nor establish a signal-promotion verdict.

## Public operations and inferential unit

`signal_analysis.inference` provides:

```python
newey_west_mean(samples, *, calendar, calendar_id, inferential_unit,
               max_lag, confidence_level)
newey_west_paired_difference(samples, *, calendar, calendar_id,
                            inferential_unit, max_lag, confidence_level)
moving_block_mean(samples, *, calendar, calendar_id, inferential_unit,
                  block_length, n_resamples, seed, confidence_level)
moving_block_paired_difference(samples, *, calendar, calendar_id,
                               inferential_unit, block_length, n_resamples,
                               seed, confidence_level)
```

Each returns a one-row Polars table. Mean input columns are `decision_time` and
`value`; paired input columns are `decision_time`, `candidate`, and `baseline`.
Value columns must be Float64. Times must be nonnull `Datetime("us", "UTC")` and
unique. Extra columns have no effect. Inputs are not mutated. Malformed schemas,
duplicate identities, off-calendar observations, or invalid tuning types raise
TypeError/ValueError. Integers are Python integers excluding booleans, below 2**64.

The caller supplies a calendar table containing every expected `decision_time` in
the evaluation period, including dates without usable observations. Its sorted
rows define consecutive **analysis sessions**, not elapsed-time increments. A
Friday-to-Monday step may be one session when explicitly declared that way.
`calendar_id` identifies that definition; `inferential_unit` names the dated
statistic (for example, `cross_sectional_spearman_ic`). Both are nonempty, trimmed
strings. The package cannot detect an omitted expected date that the caller also
omitted from its declared calendar. Irregular elapsed times are supported only
under the caller's assertion that lag dependence is defined in these session units;
this does not implement a continuous-time covariance estimator.

The estimand is the mean over declared sessions or the mean of
`candidate - baseline` at each session. Paired members are always retained or
excluded together. It is not the difference of means on independently selected
dates. Equal session weighting is fixed; asset weighting and cross-sectional
aggregation must already have produced the dated input statistic. Means and SEs
have the input statistic's units; variances have squared units. No annualization,
currency conversion, p-value, effective sample size, trial correction, sign
selection, or target-horizon tuning occurs.

## Coverage and unavailable inference

The result retains `start_time`, `end_time`, `n_expected`, `n_observed`, `n_valid`,
`n_missing`, and `n_nonfinite`. `n_missing` includes absent calendar rows and rows
with any null required value. Among the remaining rows, any nonfinite required
value counts in `n_nonfinite`. Thus:

`n_expected = n_valid + n_missing + n_nonfinite`.

`n_observed` counts submitted rows, including unusable rows. `estimate` retains the
observed finite-row mean when representable; it is **not** an imputation or an
estimate certified for the full calendar when coverage is incomplete.

| Status | Meaning |
|---|---|
| `ok` | Requested computation is available under documented assumptions |
| `unavailable_gap_or_missing` | At least one calendar row is absent, null, or nonfinite |
| `unavailable_insufficient_observations` | Fewer than two observations, or HAC lag is at least n |
| `unavailable_degenerate` | Estimated variance is zero, including constant block means |
| `unavailable_numerical` | Subtraction, SE, or interval arithmetic is not representable, rounded endpoints coincide, or HAC variance becomes negative |
| `unavailable_insufficient_resamples` | Requested Monte Carlo tail has fewer than one expected draw |
| `unavailable_degenerate_resamples` | Both empirical CI quantiles coincide |

Gaps are never dropped and relabeled as adjacent sessions for inference. Unsupported
results have null interval endpoints. Bootstrap can retain a valid exact
conditional SE when its Monte Carlo interval is unavailable; the explicit
`standard_error_kind` distinguishes it from HAC. An observed zero estimated
variance does not produce a misleading zero-width interval.

## Bartlett Newey-West mean uncertainty

For n complete dated values, let `u[t] = x[t] - mean(x)`. With explicitly supplied
integer `L = max_lag`, `0 <= L < n`, the estimator is

```text
Q = sum(t=0..n-1) u[t]^2
    + 2 sum(lag=1..L) (1 - lag/(L+1))
        sum(t=lag..n-1) u[t] u[t-lag]
Var_hat(mean) = Q / n^2
SE = sqrt(Q) / n
CI = mean +/- NormalQuantile(1-alpha/2) SE
alpha = 1 - confidence_level
```

Each lag covariance uses denominator n, not n-lag. No n/(n-1) correction is
applied. L=0 is the uncorrected heteroskedastic mean variance. The result records
`method=newey_west_bartlett`, `max_lag`, and
`standard_error_kind=hac_no_finite_sample_correction`.

The public `_hac` path maps lag weights, the factor two, lag index bounds, and
n-squared normalization directly to this equation. `_center` first subtracts a
reference observation when representable, then scales residuals before inner
products, avoiding gratuitous overflow/underflow and loss of small deviations
around a large location. The scalar mean uses compensated `math.fsum` before
division, retaining tiny cancellation residuals. If that sum overflows it computes
the exact rational mean of the Float64 inputs and rounds once. If a nonzero
exact mean rounds to zero, the result is unavailable. Nonrepresentable paired differences are
reported unavailable rather than silently clipped.

The interval is an asymptotic normal approximation for a stable mean with adequate
moments and weak enough serial dependence for a central limit theorem and
consistent HAC estimation. HAC allows heteroskedasticity under its regularity
conditions; it does not solve structural breaks, long memory, endogenous sample
selection, leakage, or arbitrary missingness. Consistency requires an appropriate
lag sequence as n grows; accepting a finite caller-selected L is not a guarantee
that it captures all dependence. Two observations are a computational minimum,
not an assurance of inferential reliability.

## Moving-block mean uncertainty

The implemented method is Künsch's overlapping, nonwrapping construction for the
arithmetic mean. Require `1 <= block_length < n` and exactly
`n = k * block_length` for an integer k. A nondivisible length raises ValueError;
there is no last-block trim, padding, wrapping, or automatic tuning.

For length l there are `m = n-l+1` candidate blocks starting at positions
`0,...,n-l`. Their means are b[j]. For each replicate choose k starts independently
and uniformly with replacement and average their block means. For the mean this
is exactly the average of the n observations in the concatenated blocks; paired
differences use those same indices for both members. Use local
`Generator(PCG64(seed))`, with caller-supplied `seed` and `n_resamples >= 2`.
The global NumPy random state is untouched.

The **exact conditional bootstrap** standard error, independent of RNG and repeat
count, is:

```text
bootstrap_center = mean(b)
Var_star(mean_star) = sum((b[j]-bootstrap_center)^2) / (m*k)
```

`_integer_blocks` expresses finite binary Float64 inputs with a common power-of-two
denominator and accumulates rolling block totals as exact Python integers. This
preserves small block sums under cancellation, without centering or rounding
individual observations first. `_bootstrap` centers these exact totals around
their conditional mean before computing a scaled Float64 norm divided by
sqrt(m*k), then restores the original units. It reports
`standard_error_kind=exact_conditional_block_mean_variance`. This is exact for the
conditional resampling distribution, not the unknown sampling variance.

For the Monte Carlo **basic interval**, each delta is `mean_star - mean`, as in the
paper's distributional approximation. It is not recentered by `E_star(mean_star)`.
With delta quantiles q_low and q_high the interval is
`[mean - q_high, mean - q_low]`. Quantiles use NumPy's explicit `inverted_cdf`
convention: empirical order statistic `ceil(B*p)` using one-based ranks, without
interpolation. Draw totals and order statistics also remain exact integers;
basic inversion `2*mean - quantile(mean_star)` rounds only its final bounds to
Float64. This preserves both large common levels and small cancellation residuals.
A nonzero SE that rounds to zero is numerically unavailable. Integer storage and
arithmetic add overhead, especially for samples spanning extreme binary exponents;
the algorithm uses linear rolling-block construction and one set of indices per
draw, without materializing concatenated observation arrays.
Results retain `quantile_method`, `seed`, `n_resamples`, and
`expected_tail_draws = B*alpha/2`. If that quantity is below one the CI is
unavailable. A value above one does not establish precise tail estimation;
the diagnostic lets callers choose a suitable repeat budget. Identical empirical
tail quantiles also make the interval unavailable.

Nonwrapping blocks give edge observations unequal marginal inclusion probabilities.
For `(0,0,0,4)` and l=2, block means are `(0,0,2)`, the conditional mean is 2/3,
and the original mean is 1. The exact conditional variance is 4/9, computed around
2/3; CI deltas remain centered on the original statistic 1. This finite-sample
centering difference is deliberately preserved. No undocumented bias correction
or replacement by an IID bootstrap occurs.

The method assumes a stationary process in declared session time with adequate
moments and short-range dependence. The paper's validity results impose explicit
mixing/moment and block-growth conditions. The usual increasing block length with
l/n tending to zero is a necessary tuning pattern in those results, not sufficient
by itself for arbitrary processes. A block length equal to a target horizon does
not prove independence. No CI correctness claim is made for long memory,
nonstationarity, missing grids, or an arbitrary finite block choice.

## Calendar-anchored block means and decorrelation lag

`signal_analysis.blocks` provides:

```python
block_means(samples, *, calendar, calendar_id, inferential_unit,
            block_length=30, min_coverage=1.0)
block_samples(blocks, *, baseline=None)
first_insignificant_lag(values, *, max_lag)
```

Source: Paleologo, *Elements of Quantitative Investing* §8.3.1. When a dated
statistic shows sizable autocorrelation up to lag `s`, replace it with
`floor(N / s)` non-overlapping, contiguous block averages and treat those as the
observations. The source prescribes inspecting the autocorrelation plot to choose
`s`; it gives no fixed value. Here `s = block_length` is an explicit parameter in
calendar sessions (default 30) that a caller may sweep and must report. The
decorrelation lag from `first_insignificant_lag` is a diagnostic to inform that
choice and is never applied automatically.

`block_means` takes the same `decision_time`/`value` samples and expected calendar
as the inference operations. Blocks begin at the first calendar session and
contain `block_length` consecutive sessions; `block_start` and `block_end` are the
first and last sessions of the block (closed). One row per block reports
`n_expected`, `n_observed`, `n_valid`, `n_missing`, `n_nonfinite`, the compensated
`mean` of the valid values, and a status: `ok` when the block is complete in the
calendar and `n_valid >= min_coverage * n_expected`; `insufficient_coverage`
otherwise; `empty` with no valid value; `incomplete_trailing` for a final block
shorter than `block_length`. Only `ok` rows carry a mean. Missing sessions and
nonfinite values reduce coverage and never shift an edge; a trailing remainder is
never averaged (the source discards it).

`block_samples` returns `(samples, calendar)` for the inference operations built
from `ok` blocks keyed on `block_start`. With `baseline`, both block frames must
share identical edges and the samples carry `candidate`/`baseline` means for
blocks that are `ok` in both, so a paired comparison uses the same blocks on each
side. Passing this calendar to `newey_west_mean` with `max_lag=0` yields the iid
block-mean interval of the source; `moving_block_mean` with `block_length=1` is
always divisible and gives a basic bootstrap interval over blocks. Either call is
made under the caller's assertion that dependence is defined in block units and
that the excluded blocks, visible in the block table, are disclosed with the
result. Fewer blocks than a caller's predeclared floor is that caller's verdict
to state; the library imposes none.

`first_insignificant_lag` reports the biased sample autocorrelations at lags
`1..max_lag`, `sum((x_t-m)(x_{t+k}-m)) / sum((x_t-m)^2)`, the large-sample
white-noise band `1.96/sqrt(n)`, and the smallest lag whose autocorrelation lies
inside that band. It requires `n >= max_lag + 2` finite values; constant input is
`unavailable_degenerate`, nonfinite input is `unavailable_nonfinite`, and no lag
inside the band within `max_lag` is `unavailable_no_insignificant_lag` with the
autocorrelations retained. The band is a descriptive reference, not a test.

## Supplied evidence declarations

`signal_analysis.evidence` defines frozen `AnalysisRecord`, `TrialRecord`, and
`SearchEvidence` dataclasses with `validate_analysis_record` and
`validate_search_evidence`. Validation happens when explicitly called; construction
alone is not a validated wrapper. `dataclasses.asdict` preserves the supplied
fields for caller-directed serialization; callers encode the datetime in their
chosen format. There is no filesystem/network access, persistence, registry,
serializer, model fitting, or second experiment tracker.

An analysis record retains candidate identity/revision and UTC freeze time, plus
references for data, universe, target/clock definition, input fingerprint, package
version, code revision, metrics/settings, predeclared protocol/thresholds,
partitions/OOS provenance, fitting windows, and dated results. References may point
to existing ml-engine records. A literal `unknown` preserves unreconstructed
provenance; references are opaque and their contents/existence are not inspected.

A search declaration names its family, explicitly marks completeness as `complete`
or `unknown`, supplies history and holdout-access references, and retains a tuple
of unique trial IDs with candidate/result references and `completed`, `failed`, or
`rejected` status. A `complete` declaration cannot use `unknown` as its history
reference. This checks declaration consistency, not truth: omitted trials or
external holdout access cannot be detected. `holdout_access_reference="unknown"`
does not assert that no access occurred. Completeness is insufficient evidence for
any specific selection correction; aligned dated candidate evidence and a separate
statistic-specific contract would still be required. Return-series selection
statistics (DSR, PBO, reality check, Holm, Rademacher bound) are implemented in
`selection` below; none is applied to raw IC or ICIR.

## Selection statistics for return grids

`signal_analysis.selection` measures how much a configuration picked from a grid
of return series is inflated by the pick. It does not remove the bias, choose a
configuration, or gate anything. Input is a `T × N` Float64 array of aligned
per-period returns (rows oldest first, columns configurations) with optional
column names; nonfinite input raises `ValueError` (callers drop or zero-fill
dates). Each operation returns a plain dict, or `{"available": False, "reason"}`
when the sample cannot support the statistic (too few rows, fewer than two
columns, zero variance, undefined bootstrap statistic).

```python
probabilistic_sharpe(returns_1d, *, benchmark_sharpe=0.0)
effective_trials(returns_2d)
deflated_sharpe(returns_2d, selected, *, trials=None)
pbo_cscv(returns_2d, *, blocks=16)
reality_check(candidates_2d, bases_2d, *, statistic="sharpe", block=28,
              draws=2000, seed=7, periods_per_year=365, names=None)
holm(pvalues)
rademacher_bound(returns_2d, *, block=7, draws=2000, seed=7, delta=0.05,
                 periods_per_year=365, selected=None, standardize=True, names=None,
                 metric="sharpe")
```

- **PSR** (Bailey & López de Prado): `Z[(SR − SR*)·√(T−1) / √(1 − γ3·SR + (γ4−1)/4·SR²)]`
  with per-period SR, skewness γ3 and raw kurtosis γ4 from population moments.
- **Effective trials**: `(Σλ)²/Σλ²` over correlation-matrix eigenvalues, in [1, N].
  A dependence summary, not a count of independent hypotheses.
- **DSR**: PSR of the selected column at
  `SR* = √V[SR_n]·((1−γ)Z⁻¹[1−1/N] + γZ⁻¹[1−1/(Ne)])`, V the ddof=1 variance of
  per-period Sharpe across the grid's columns, N the raw column count or a supplied
  trial count (for example effective trials). √V follows the paper's
  cross-trial dispersion, not the selected series' own Sharpe standard error. A grid of near-identical
  configurations has small V and therefore a small SR* — DSR then says little
  about selection; read it with PBO and the reality check.
- **PBO (CSCV)**: T is trimmed to a multiple of `blocks` by dropping the oldest
  rows (reported). For every one of C(S, S/2) in-sample halves, the in-sample
  Sharpe winner's out-of-sample rank ω = rank/(N+1) (ties averaged) gives
  λ = ln(ω/(1−ω)); PBO = share(λ ≤ 0). The splits share one sample, so a single
  PBO on pure noise varies widely around 0.5 (standard deviation ≈ 0.2 across
  seeds for N = 20).
- **Reality check**: paired circular block bootstrap with identical row draws for
  all columns (`starts = rng.integers(0, n, ceil(n/block))`, rows
  `(starts + arange(block))[:n] mod n`). Deltas `d̂ = f(cand) − f(base)` with f a
  Sharpe (population std), Sortino (`mean/√mean(min(x,0)²)`), both annualized by
  √periods_per_year, or mean (× periods_per_year). White's raw p uses
  `max(B − d̂) ≥ max d̂`; the Hansen-style studentized p uses
  `max((B − d̂)/se) ≥ max t` with `se = B.std(ddof=1)`. Per-candidate one-sided
  p-values are Holm step-down adjusted. The bootstrap null recenters each
  candidate on its observed delta; it assumes the block length covers the
  dependence and that the grid is the complete family.
- **Rademacher bound** (Paleologo, *Elements of Quantitative Investing* ch. 8):
  rows averaged over non-overlapping `block`-row blocks (incomplete tail dropped),
  `R̂ = E_ε[max_n ε·x_n/T]` over `draws` Rademacher vectors, T the block count.
  `metric="sharpe"` (default) is Procedure 8.2 / Theorem 8.4 for sub-Gaussian
  metrics: `θ − 2R̂ − 3√(2 ln(2/δ)/T) − √(2 ln(2N/δ)/T)`. The book z-scores each
  return by its predicted volatility; a returns-only grid has none, so
  `standardize=True` divides each column by its full-sample std as the stand-in
  (θ = per-period Sharpe; pass `standardize=False` for pre-z-scored returns).
  Annualized values multiply by √periods_per_year. `metric="ic"` is Procedure 8.1
  on cosine ICs (|x| ≤ 1 required, never standardized): `θ − 2R̂ − 2√(ln(2/δ)/T)`.
  Each bound reports `rademacher_positive` (eq. 8.6, θ − 2R̂ > 0).
  This is the published bound, not a sign-flip max-statistic test.

`strategies.research_surface.publish_research_surface` runs these on every
published grid of at least two configurations; see the strategies rules.

## Source map and access provenance

Sources were consulted on **2026-09-06**. The engineering API, explicit calendar,
coverage policy, and unavailable statuses are project decisions, not quotations
or claimed exact book interfaces.

- **López de Prado, Advances in Financial Machine Learning (2018), Chapters 7–8**:
  the chapter sections were read in full. Chapter 7 §7.3 and exercise 7.5 separate
  dependent observations from repeated-selection bias; Chapter 8 §8.1 motivates
  preserving the entire search, and §§8.3–8.4 motivate paired performance
  contrasts. Its fold-level `sd/sqrt(k)` examples do not establish valid
  time-series uncertainty here.
- **Same book, §11.5 and §§14.7.2–14.7.3**: the pertinent sections were read for
  all-trial disclosure and Sharpe-specific selection scope. These motivate record
  provenance, not implementation of Sharpe corrections for IC.
- **Elements of Quantitative Investing, §6.3.4**:
  directly states the Bartlett covariance weights. It supplements the primary
  paper rather than supplying an invented finite-sample adjustment.
- **Newey and West, A Simple, Positive Semi-Definite, Heteroskedasticity and
  Autocorrelation Consistent Covariance Matrix**, NBER Technical Working Paper 55,
  revised February 1986, [primary PDF](https://www.nber.org/system/files/working_papers/t0055/t0055.pdf):
  equations (4)–(6), Theorems 1–2, printed pages 2–5 support normalization,
  Bartlett weights, positive semidefiniteness, and regularity conditions. No
  runtime source access is required.
- **Künsch (1989), The Jackknife and the Bootstrap for General Stationary
  Observations**, Annals of Statistics 17(3), 1217–1241,
  [DOI](https://doi.org/10.1214/aos/1176347265),
  [author-uploaded manuscript](https://www.researchgate.net/profile/Hans-Kuensch/publication/2355926_The_Jackknife_and_the_Bootstrap_for_General_Stationary_Observations/links/56753dbc08ae0ad265bff7bd/The-Jackknife-and-the-Bootstrap-for-General-Stationary-Observations.pdf):
  §2.3 equations (2.7)–(2.11) define draws, n=kl, centering, and conditional
  variance; §3.2 equations (3.13)–(3.15) and Theorems 3.4–3.5 justify the
  arithmetic-mean distribution and limits. The discrete empirical-quantile
  convention and insufficient-resolution status are explicit implementation
  choices for the paper's stated bootstrap distributional approximation.

## Verification scope

`tests/test_inference.py` calls the public operations. Exact Fraction arithmetic
forms an independent all-pairs Toeplitz quadratic oracle for HAC (including every
lag through n-1), while production accumulates by lag. Tiny bootstrap oracles
enumerate resampled observation tuples and their exact conditional distribution,
independently of the block-mean variance implementation. Anchors include HAC
variance 25/64 for `(1,2,3,4), L=1`, bootstrap variance 1/3 for the same sample with
l=2, and the asymmetric edge-centering example above.

Complementary tests cover location/scale/time-reversal invariance, paired swap and
common-component cancellation, deterministic RNG and input sorting, null/NaN/Inf
accounting, preservation of missing calendar rows, timezone/identity rejection,
empty/singleton/constant samples, unsupported block lengths, tail resolution,
Float64 extremes, and small deviations around a large common location. Tolerances
are absolute 1e-12 for moderate well-conditioned cases, 1e-14 relative at extreme
scale, and exact comparisons for identifiers/counts/statuses. These allow ordinary
Float64 reduction error while distinguishing wrong factors, weights, lag limits,
variance centering, and normalization. The targeted public tests fail on each of
these defects: dropping the HAC factor two, using sqrt(n)
instead of n for mean-SE normalization, replacing conditional bootstrap variance
with MSE around the sample mean, recentering bootstrap deltas around their
conditional mean, and silently closing missing dates.

Largest-value scaling followed by `np.mean` loses the representable residual in `(1e308,1,-1e308)`, reporting zero instead of
1/3, so the implementation uses compensated accumulation; regressions also include a residual of
1e-308 that would underflow under that scaling, repeated smallest subnormals, and
an explicitly rejected overflow/underflow fallback case.

A fixed-seed stationary Gaussian AR(1) ensemble compares HAC mean variance with
the independently known finite-n variance from covariance-pair counts and checks
broad interval coverage. The generator has phi=0.5 and innovation variance 0.75;
n=512, 160 paths, L=12. Predeclared variance-ratio and coverage bands permit
finite-bandwidth bias and Monte Carlo error. This is scoped process evidence,
not a theorem, market validation, or precise universal coverage estimate.
No discretized differential equation/solver is used, so numerical convergence
order tests do not apply. Statistical tuning remains a caller responsibility.

`tests/test_blocks.py` uses exact Fraction block and autocorrelation oracles, a
hand-built twelve-session calendar with one missing session, trailing and empty
blocks, weekend-gapped session calendars, the cancellation fixture
`(1e308, 1, -1e308, 0)`, paired edge agreement, hand-off to both inference
operations, seeded AR(1) versus white noise for the lag diagnostic, and
scale/location invariance. The public tests fail on each of these defects: anchoring block edges to observed rows instead of the
calendar, reporting a trailing partial block as `ok`, an unbiased `n/(n-k)`
autocorrelation scaling, a `1.0/sqrt(n)` band, and ignoring the baseline status in
paired block samples.
