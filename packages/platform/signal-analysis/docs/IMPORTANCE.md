# Feature importance: AFML Chapter 8

Source: Marcos López de Prado, *Advances in Financial Machine Learning* (2018),
Chapter 8 §§8.3–8.4, snippets 8.2–8.4; evaluation semantics follow Chapter 7
§§7.3–7.5.

These operations measure supplied fitted-model outputs. Training, fold-local
preprocessing, selection, and artifacts belong to `ml-engine`. A caller must
preserve actual train/test membership, information intervals, purge/embargo choices,
and model provenance. Explicit held-out declarations and model-feature tables
check the supplied contract; they cannot prove that fitting respected it.

For an ML-engine run with `keep_fold_models=True`, an MDA callback can call
`result.predict_fold(pd.DataFrame(x, columns=features), candidate=name, fold=fold)`.
This applies the fold's fitted preprocessing as well as its estimator, preserving
the same predictive procedure used for `candidate_oos`. Calling a raw
`result.fold_models` estimator on raw features bypasses learned preprocessing.
The analysis library still does not import or fit the training engine.

## Public operations and mathematical mapping

Import from `signal_analysis.importance.mdi`, `.permutation`, and `.single_feature`.
No training library is imported by these modules.

| Operation | Input and estimand | Output |
| --- | --- | --- |
| `mean_decrease_impurity` | Wide tree statistics: String `tree_id`, explicitly selected Float64 feature columns. Each tree sums to one within 1e-12, or is all zero. Nonnegative finite values required. | `.raw` retains each tree/feature and inclusion mask; `.summary` retains raw means, sample tree dispersion, normalization denominator and counts. |
| `permutation_importance` | One caller-declared held-out partition. Wide features plus unique String `observation_id`, UTC-us `decision_time` and `features_available_at`, Float64 `target` and `sample_weight`. Targets and features must be finite without hidden filtering. Only features must be available by decision; held-out targets are realized later and excluded from fitting. | `.raw` retains baseline and permuted scores, directed decrease, denominator, normalized importance, permutation indices and canonical observation IDs; `.summary` describes repetitions within this partition. |
| `single_feature_importance` | Long scalar OOS predictions: `feature, partition_id, model_id, observation_id, decision_time, target, prediction, sample_weight`. Separate `model_features(partition_id, model_id, feature_columns: List[String])` declares exactly one feature per model. | `.predictions` preserves supplied observations; `.raw` scores every feature/partition; `.summary` describes equal-weight fold scores. |

Identifiers must be nonempty trimmed strings. SFI requires the exact same
observations, times, targets and weights for every feature within every partition,
and every feature in every partition. It rejects duplicate observation records,
multifeature declarations and undeclared/unused models. Scalar predictions cover
regression, binary probabilities and numeric labels. Multiclass probability tables
are deferred; the MDA callback can return a two-dimensional prediction matrix.
Scorers own label/probability semantics, probability class order, and their complete
mathematical definition. `score_name` records that definition's caller-chosen name.

### MDI

For supplied tree importance `v[t,j]`, conventional MDI computes
`a[j] = mean_t(v[t,j])`, retaining zeros, then `I[j] = a[j] / sum_j(a[j])`.
Zero-split trees therefore do not alter normalized attribution. The
`afml_zero_excluded` option computes each `a[j]` only from nonzero tree values
before the same final normalization, following snippet 8.2. A zero may mean
unselected, unsplittable, or no impurity reduction; selecting this option does not
certify which interpretation applies. The book motivates it using one randomly
considered feature per split. The library does not prescribe estimator settings.

The raw sample standard deviation uses `ddof=1`. `scaled_tree_dispersion` is
that value divided by `sqrt(total trees)` and by `sum(a)`, matching snippet 8.2
including its total-tree denominator when some zeros were excluded. One included
tree has undefined sample dispersion. A feature with no nonzero values under
AFML mode has null attribution; all-zero attribution has an explicit status.
MDI is in-sample and subject to correlated-feature substitution and split-variable
bias. It is not evidence of predictive value.

### MDA / permutation importance

Let `s0` be baseline held-out score, `sp` the score after permutation, and
`d = +1` for greater-is-better or `-1` otherwise. Raw importance is
`d * (s0 - sp)`. It preserves negative importance. `afml_relative` divides this
by `d * (score_optimum - sp)`. Thus accuracy with optimum one reproduces
`(s0-sp)/(1-sp)` and negative log loss with optimum zero reproduces
`(s0-sp)/(-sp)` from snippet 8.3. Positive loss with direction minimize and
optimum zero is algebraically equivalent. No metric or optimum is inferred.
Scores beyond the declared optimum, zero denominators, invalid predictions and
nonfinite arithmetic return explicit null/status results rather than zero.
Exceptions from user callbacks propagate; invalid callback shape raises.

The caller supplies both `predict(X)` and `scorer(y, prediction, sample_weight)`;
weights are finite and nonnegative, remain attached to the original outcome
rows, and are passed unchanged to every score. An all-zero weight fold is
undefined. Callbacks receive copies to prevent mutation of later calculations.
The callable must represent a fixed fitted model; stateful retraining callbacks
violate the caller's contract and cannot be detected by numeric inspection.

Canonical row order is observation ID order. A local RNG with explicit UInt64
seed generates one full row permutation per group/repetition. By default each
feature is permuted alone. An optional `feature_groups` mapping jointly permutes
all named columns with the same row order, preserving their internal relation.
Groups may overlap because each perturbation starts from the original matrix.
This is feature grouping, not block permutation or within-stratum row shuffling;
those sampling schemes are deferred. Permuting correlated features alone can
understate joint value; perturbation can also create off-support feature vectors.

`repetition_sample_std` measures perturbation variability within one fold.
It is not the across-fold quantity in snippet 8.3, nor an inferential standard
error. Repetitions do not create new independent evaluation observations.
Combine raw records across externally fitted folds only with a stated aggregation.

### SFI

SFI is the OOS score of a model fitted using only feature `j`, separately for each
fold. It is not correlation with a raw feature and is not permutation importance.
Scores retain their supplied direction; a lower loss remains better.
Each fold is scored with its own observation weights, then fold scores are averaged
equally as in snippet 8.4. That snippet uses NumPy `std` (`ddof=0`), unlike the
sample `std` in snippets 8.2 and 8.3. `fold_population_std` and
`scaled_fold_dispersion = std / sqrt(total folds)` preserve this convention.
Neither is automatically a dependence-valid uncertainty estimate.

Invalid predictions or undefined scorer results retain the entire fold with a
null score; no rows are silently removed. Summary counts identify valid and total
folds, and `partial` explicitly labels summaries omitting undefined folds.
SFI avoids substitution by fitting alone, but misses interactions. Strong joint
performance can coexist with chance-level single-feature performance.

For integration, configure `ml_engine.training.CandidateConfig` with
`feature_cols=(feature,)` separately for each feature. `TrainingPipeline` retains
all folds/candidates in `TrainingResult.candidate_oos`; use that table rather than
`oos_predictions`, which can select only winning candidates. Map explicit model
and partition IDs and attach the same evaluation weights before calling SFI.
`final_refit=False` avoids an unnecessary full-data refit for this analysis.

## Verification specification

Known-answer fixtures distinguish conventional and zero-excluding MDI; weighted
accuracy versus unweighted scoring; positive and negative score direction; raw
versus AFML-relative normalization; and population versus sample dispersion.
Invariants include tree/feature order, observation-row order, weight scaling,
callback isolation, irrelevant-column zero effects, and joint-group preservation.
Boundary cases cover empty/duplicate/invalid records, no-split trees, zero weights,
nonfinite predictions, zero normalization denominators and explicit provenance.

Float64 well-conditioned arithmetic uses absolute error 1e-12, bounding roundoff
well below the fixtures' substantive differences. Exact identity/count/status
checks use equality. Seeded synthetic informative/redundant/noise/interaction
benchmarks use broad mechanism-specific bounds, not a required exact ranking.
Their held-out training, if needed, uses public `ml-engine` APIs on generated data.
There is no real-data or real-model performance claim. These finite tests are
scoped code verification, not proof of model validity or investment value.
No discretization/solver convergence test applies to these finite aggregations.

Numeric regression coverage also includes representable `1e308` score moments,
exact cancellation with a small surviving mean, and adjacent scores around
`1e16`. Means use compensated summation, with exact rational fallback if the sum
overflows although its average remains finite. Dispersion centers at an observed
value before scaling, retaining small spreads; only overflowing differences use
raw-value scaling. Truly unrepresentable moments raise `ArithmeticError`.
MDI uses the same reduction for within-tree statistics. These cases use exact
structural references and relative roundoff budgets of 1e-14 (zero absolute
allowance for small positive references).

Verify with `uv run pytest
packages/platform/signal-analysis/tests/test_importance_*.py -q -W error`. Synthetic benchmark
assertions require informative and exact-redundant SFI accuracy above 0.98,
noise and XOR single-feature accuracy within [0.35, 0.65], joint XOR accuracy
above 0.98, low noise MDI, and a substantial joint-feature permutation drop.
These are broad generator-specific behavior checks, not universal rankings.

Raw directed score differences outside Float64 retain a null `raw_decrease`
and `nonfinite_decrease` status. The relative mode currently preserves that
undefined result even if a ratio evaluated with wider arithmetic could be finite.
