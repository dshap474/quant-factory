# Directional scores

Implemented scope: per-date scoring of a signal's *sign* against a target, asset by
asset, without ranking assets against each other. This is the descriptive building
block for a timing question ("does the signal's sign point the way the target moves?")
as opposed to the selection question cross-sectional IC answers ("does a higher signal
pick a higher target among assets on the same date?"). It does not simulate a
portfolio, apply costs, size, net, compound, annualize, or produce a verdict.

## Public operations

```python
direction.directional_scores(panel, targets, *, target_ids, min_pairs)
```

## Definitions

For each supplied decision date and requested target, the valid pairs are exactly the
eligible finite pairs of `cross_sectional_ic` under the same exclusion precedence:
ineligible, missing signal, nonfinite signal, missing target, invalid target. Over
those `n_valid` pairs with signal `s_i` and target `y_i`:

- `signed_mean = mean_i( sign(s_i) · y_i )`. A unit position that follows the signal's
  sign on every pair earns this on average, in target units. `sign(0) = 0`, so a zero
  signal is a flat position that contributes zero and stays in the denominator.
- `mean_target = mean_i( y_i )` over the identical pairs: the always-long reference.
  Because both means are taken on the same pairs, `signed_mean − mean_target` is a
  paired difference, and the long/flat rule (long when the signal is positive, flat
  otherwise) earns exactly `(signed_mean + mean_target) / 2`.
- `hit_rate = n_hits / (n_hits + n_misses)`, where a pair is a hit when
  `sign(s_i) · sign(y_i) > 0`, a miss when it is `< 0`, and a tie when either side is
  zero. Ties are excluded from the hit rate; when no pair is decided the hit rate is
  null while the means remain finite.

The means use the inference module's compensated summation. `sign(s_i) · y_i` is
exact, so `signed_mean` carries the same rounding as a plain mean over the same pairs.

## Result frame

One row per `(decision_time, target_id)`, sorted by both, with `min_pairs`,
`signed_mean`, `mean_target`, `hit_rate`, `status`, the sign counts
`n_positive_signal` / `n_negative_signal` / `n_zero_signal`, the agreement counts
`n_hits` / `n_misses` / `n_ties`, and the coverage counts `n_total`, `n_eligible`,
`n_valid`, plus one `n_<reason>` column per IC exclusion reason. `status` is `ok`,
`insufficient_pairs` (fewer than `min_pairs` valid pairs; scores null, counts still
reported), or `unavailable_numerical` (a mean did not evaluate to a finite number).

A requested target absent from the target frame is a coverage loss on every date
(`missing_target`), not an error; a target key absent from the signal panel raises,
as in `cross_sectional_ic`. `min_pairs` is an integer in `[1, 2**64)`; booleans are
rejected. An empty typed input returns an empty typed result.

## Invariants the tests hold

Negating the signal negates `signed_mean`, leaves `mean_target` unchanged, and swaps
hits with misses. Scaling the signal by any positive constant changes nothing.
Negating the target negates both means. Dates are separate estimands and row order is
immaterial. Exclusion counts equal those of `cross_sectional_ic` on the same inputs.

## What this is not

It is not a time-series correlation between a signal and a target, and it is not an
aggregate market-timing statistic: assets are never pooled across dates, and dates are
never pooled across assets. A caller wanting a basket-level timing number (the sign of
the average signal against the average target) must compute that aggregate target
separately and declare it. Inference over the dated `signed_mean` series belongs to
`blocks` and `inference`, with the same dependence caveats as for dated IC.
