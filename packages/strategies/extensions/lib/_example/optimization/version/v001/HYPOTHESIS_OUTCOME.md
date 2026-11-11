# v001 — Hypothesis outcome (illustrative)

**Verdict: NOT_TESTED.** This scaffold version sealed without a run, so no economics verdict
exists and none is claimed.

Had a valid run completed, this file would carry the real record, whose shape is:

- The verdict (`SUPPORTED` or `FALSIFIED`) against the SPEC's preregistered criteria — here,
  candidate-minus-control annualized Sharpe delta vs the +0.10 threshold.
- The binding run line, e.g. `Binding run: 20260831T000000Z-v001-momentum-tilt`, naming the one
  run ID the verdict is bound to. A supported/falsified seal is
  valid only when that run's artifact directory exists under `db/research/strategies/example/` — a seal
  claiming economics must bind a real artifact, which is exactly why this scaffold version
  seals as `not_tested` instead.
- What was learned, stated honestly: which part of the hypothesis failed or held, and what that
  closes off or opens up for the next version.

A FALSIFIED verdict still publishes a research candidate surface; it does not delete or hide
anything. Only an explicit operator action changes the working baseline.
