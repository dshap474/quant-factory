# Research surface comparisons

The version surface endpoint may return an optional `comparison` alongside its original
`benchmark`, metrics and performance data. This distinguishes the experiment's named control
from its contextual market benchmark without rewriting sealed artifacts.

`db_api.research_comparison.load_run_comparison` reads the selected run's declared `control`
provenance and its `candidate_returns.parquet` / `control_returns.parquet` contract from the
run named by the version's `surface.json`. Projected `data.query` reads must exactly match the published candidate returns and dates. The standard
strategy return summarizer computes full-population control metrics before paired display
sampling. The payload identifies its run and includes its dates, daily returns and value path.

Unavailable or invalid control evidence returns `comparison: null` and, when a declared
return contract fails verification, `comparison_issue`. The original validated surface stays
available. Legacy surfaces without this return contract continue to load. No file is created,
repaired, promoted or selected by this read-only route.
