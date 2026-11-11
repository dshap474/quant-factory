# Horizon windows, quantile means, eras, and persistence

Implemented scope: fixed-offset target windows, descriptive mean targets within
signal-rank quantiles, predeclared era labels, and the persistence of a signal's
cross-sectional ranking. None of these simulates a portfolio, fits a model, or
produces a verdict; each is a separately defined descriptive aggregation.

## Public operations

```python
targets.horizon_windows(decisions, *, spans)
quantiles.quantile_conditional_means(panel, targets, *, target_ids, n_quantiles, min_pairs)
stability.assign_eras(frame, *, time_col, eras, label_col="era")
persistence.signal_rank_autocorrelation(panel, *, lags, min_pairs, per_date=False)
```

## Horizon windows

`horizon_windows` takes unique `(decision_time, asset)` rows and a mapping from
`target_id` to `(start_offset, end_offset)` timedeltas with
`0 < start_offset < end_offset`. It emits one window per decision and span,
`target_start = decision_time + start_offset`, `target_end = decision_time + end_offset`,
sorted by decision, asset, and target, and validated by `validate_target_windows`.
Offsets are elapsed time, not sessions: a caller whose bars close at a fixed offset
from the bar timestamp resolves that clock before calling. Nothing here looks up
prices or checks that a session exists at the endpoints; `build_forward_returns`
reports missing endpoints as target statuses.

## Quantile conditional means

`quantile_conditional_means` returns `n_quantiles` rows for every supplied
decision date and requested target with `quantile` (1-based), `n_pairs`,
`mean_target`, `status`, and the same exclusion counts as `cross_sectional_ic`,
computed by the same precedence: ineligible, missing signal, nonfinite signal,
missing target, invalid target. Valid pairs are sorted by `(signal, asset)`; the
1-based ordinal rank `k` of `n` pairs falls in quantile `floor((k-1)·q/n) + 1`, so
membership sizes differ by at most one and a tie between signals is broken by
asset name. That tie rule is deterministic, not meaningful; callers with heavy
ties should say so. A date with fewer than `max(min_pairs, n_quantiles)` valid
pairs reports every quantile as `insufficient_pairs` with a null mean and zero
pairs. Means use the compensated sum shared with the inference operations. The
result is the mean target of the assets in each rank bucket on that date. It is
not weighted by capital, rebalanced, netted, or annualized, and a monotone
pattern across buckets is a description, not a test.

## Predeclared eras

`assign_eras` adds a String label column from a sequence of `(label, start, end)`
eras with UTC-aware endpoints. Eras are half-open `[start, end)`: an instant on a
boundary belongs to the era that starts there. Labels must be unique, each era
must satisfy `start < end`, and eras must be in increasing order without overlap;
gaps are allowed and rows outside every era receive a null label. No row is
dropped. Summaries then come from `summarize_metric_stability` grouped by the
label, so era means share its coverage accounting and its descriptive character.

## Rank persistence

`signal_rank_autocorrelation` takes a validated signal panel. For each lag `L` and
each decision date having an `L`-th preceding decision date in the panel, it
computes the Spearman correlation between the signal on the two dates over the
assets that are eligible with finite signals on both, using the IC module's
correlation and its statuses (`insufficient_pairs`, constant sides). Lags count
declared decision dates, never elapsed time; an asset absent from either date is
not paired. The lag-level row reports `n_dates_supplied`, `n_dates_lagged`, the
count of `ok` dates, their mean correlation, and `ok` or `no_valid_dates`;
`per_date=True` returns the dated table instead. A value near one means the
ranking barely moves between dates; that bears on the dependence of consecutive
IC observations and on how often a consumer would trade, but it is neither a
turnover figure nor a measure of skill.

## Verification scope

`tests/test_horizon_windows.py`, `tests/test_quantiles.py`, `tests/test_eras.py`,
and `tests/test_persistence.py` use hand-derived answers: ranks as targets give
quintile means `1.5, 3.5, 5.5, 7.5, 9.5`; `n=7, q=5` gives memberships
`2,1,2,1,1`; exclusion counts are compared against `cross_sectional_ic` on the same
fixture; boundary instants land in the later era; a constant ranking gives
persistence one at every lag and a per-date reversal gives minus one at lag one and
plus one at lag two; an asset present on one date only is not paired; lags over an
irregular date set select the preceding declared date. The tests fail on each of these
defects: ceiling quantile assignment, right-closed eras, lag
measured in elapsed days, ignored eligibility in persistence, and a horizon end
built from the start offset.
