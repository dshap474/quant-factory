# v001 — Hypothesis outcome (illustrative)

**Verdict: NOT_TESTED.** This scaffold version sealed without a run, so no statistical verdict
exists and none is claimed.

Had a valid run completed, this file would carry the real record, whose shape is:

- The verdict (`SUPPORTED` or `FALSIFIED`) against the SPEC's preregistered criteria — here,
  mean OOS Spearman IC vs the +0.02 threshold with its bootstrap lower bound.
- The binding run line, e.g. `Binding run: 20260901T000000Z-v001-momentum-sign`, naming the one
  run ID the verdict is bound to. A supported/falsified seal is
  valid only when that run's artifact directory exists under `db/research/signals/example/` — a seal
  claiming a result must bind a real artifact, which is exactly why this scaffold version seals
  as `not_tested` instead.
- What was learned, stated honestly: which part of the hypothesis failed or held, and what that
  closes off or opens up for the next version.

A FALSIFIED verdict still leaves a research candidate on record; it does not delete or hide
anything. Only an explicit operator action changes the registered runner or its presets, and
that action is what makes a version production.
