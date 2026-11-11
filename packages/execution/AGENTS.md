# Execution rules

Execution owns engine-neutral order mechanics and installation-specific venue connectivity.

## Placement

- `src/execution/`: provider-neutral contracts, sizing, order policies,
  accounting, reconciliation, journals, locks, and order ownership.
- `extensions/venues/` (optional; none ship): an installation's venue plug-ins, with their
  dependencies, tests, safety behavior, and operator assets. Each venue's own `AGENTS.md`
  holds its safety constraints.
- `tests/`: core tests. `README.md` and `docs/architecture.md`: contract and
  implementation documentation.

## Safety boundaries

- Never weaken fail-closed arming, explicit live-cap requirements, preview cap
  checks, or foreign-order refusal; never introduce default caps.
- Operator risk policy (margin mode, leverage, weight and notional caps,
  slippage, snapshot age, foreign-position blocking) lives in TOML rulesets
  (`execution.rulesets`, named files in an installation's `extensions/rulesets/`), not in venue
  code. Every ruleset key is required; one run loads one ruleset. Venue facts (exchange minimums, max leverage) and engine guarantees
  (identity proof, at-most-once submit, prove-flat) are not ruleset knobs.
- A venue may opt in to `net_resize`: a same-side resize trades only the
  difference and does not prove flat. Closes to zero and flips always prove
  flat.
- Read the venue's own `AGENTS.md` before changing a venue. Preserve gate timing
  and submit-boundary checks; do not harmonize differing venue protections.
- Run core and venue tests for execution changes, plus
  `tests/boundary` and `tests/workflow` for changes production calls. A green
  CI run alone does not establish money-path safety.

## Operating authority and recovery

- Live orders require explicit per-trade operator permission. Agents never
  launch live runs. Live venue trades run only through the production adapters
  and `run_transition`; there is no separate manual order CLI.
- Agents must supply an explicit fake `client=` whenever instantiating a venue. Real-client construction or context entry can authenticate and
  write live state even with `dry_run=True`; dry-run does not make this offline.
- Never delete, edit, or clean live journals or lock files under
  `db/execution/live/`. They preserve crash recovery, fill audit evidence, and
  single-instance protection; Git cannot recover this ignored state.
- Use a unique run ID per intent; a run ID whose journal already holds a live
  attempt is refused. `Unresolved` requires reconciliation of the original
  `client_order_id`, never a blind retry or new ID. After an
  interruption without a journal, inspect venue state before any rerun.

## Related docs

- `docs/architecture.md`: descriptive canon for the engine and venue protocol; `README.md` for the core.
