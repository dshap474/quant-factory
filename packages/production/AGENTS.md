# Production Rules

## Hard Stop: Agents Never Hold Trading Authority

- An agent may design, implement, review, and test production trading code only with fake or
  explicitly non-trading interfaces. An agent must never submit, amend, cancel, or preview a live
  order through a trade-enabled credential; flatten a live position; transfer funds; change margin
  or leverage; or invoke an arbitrary venue mutation.
- An agent must never obtain or use a trade-enabled credential, set a live gate to enabled, create
  or apply live activation authority, arm a deployment, start or enable a live service or timer, or
  deploy a change that can trade. Those actions are human-operator-only and cannot be delegated to
  an agent by a chat instruction, approval, handoff, runbook, or task description.
- Venue credentials, including trade-enabled keys, may be present in the process environment of an
  agent session. Having that access is not authority: an agent never runs a live or
  authenticated-preview path with them. Tests use fake providers and read-only
  public market data.
- Every derivatives deployment must fail closed around an exact human-approved quantity and
  product. Quantities are integers. A maximum, target weight,
  dollar budget, or strategy request is not an exact-size guarantee. Never round up, substitute
  a product, or infer the quantity.
- Instructions are not the security boundary. The implementation and operating environment must
  enforce the human-only authority and exact-size invariants in this
  file. If they do not, the deployment is not eligible for
  live activation.

## Placement

- `src/production/`: shared runtime contracts, discovery, validation, and composition.
- `extensions/adapters/`: venue-specific composition using `packages/execution` core and venue
  adapters.
- `extensions/deployments/<family>/`: one `deployment.yaml`, family policy, and the manual cycle
  entry point. No service, timer, or other scheduling assets: the operator runs every cycle by
  hand. Reference canonical strategy versions; do not copy strategy code, presets, or outputs.
- `extensions/candidates/`: assessment evidence; `extensions/portfolio.yaml`: portfolio membership
  only.
- Operator procedures for actual deployments live with the deployment, outside this package.
- An explicitly configured durable state root outside Git and outside `extensions/`: activation
  receipts, journals, locks, account snapshots, active pointers, and other mutable operating state.

Never delete or rename a deployed family or rewrite a certified release snapshot. Add `releases/` or
`archive/` only when another release or retirement exists.

## Boundaries and authority

Production connects canonical strategies to execution. Strategy logic and `StrategyWeights` belong
in `packages/strategies`; reusable execution mechanics, including sizing, venue connectivity,
reconciliation, execution journals, locks, and kill switches, belong in `packages/execution`.
Production must not become a strategy engine, execution engine, capital allocator, or scheduler.

`list`, `validate`, and `inspect` must not resolve credentials, contact venues, install services,
write runtime state, or submit orders. Dry-run is preview-only. Registration, installation,
scheduling, activation, arming, capital authorization, and host gates remain separate
operator-controlled facts. Tracked files, account provisioning, portfolio membership, tests, and
dry-runs grant no live authority. Deactivation stops new decisions; cancelling orders or flattening
positions requires separate execution authority.

The human operator explicitly provisions each strategy's venue account and key. Record only the
logical provider/account name, credential environment variable names, and readiness blockers in the deployment's
`AGENTS.md`. Account identifiers and capital caps remain external authority bound to the exact
deployment fingerprint; they must match the activation receipt and venue truth. Never infer an
account from available credentials or substitute a venue or product. Provisioning alone does not
authorize provider calls.

Agents may implement and test locally, but never obtain or use trade-enabled credentials; submit,
amend, cancel, or preview live orders; flatten positions; move funds; change margin or leverage;
apply activation; arm deployments; enable live gates, services, or timers; or deploy code that can
trade. These are human-only actions outside the agent session, even with chat approval. The operator
must review the exact release, account, product, quantity, caps, and dry-run evidence before
activation or deployment.

Venue credentials, including trade-enabled keys, may be reachable from an agent session's
environment. The boundary is therefore the fail-closed gates, not credential absence: the
human-only capital gate, the per-run venue gate, the activation receipt, and the arming marker. Agents never
run a live path, set a gate, or create a receipt or marker. Never handle credentials through a
browser or commit credential-bearing identifiers.

## Exact-size derivatives

- External human-controlled authority binds one venue product identifier, multiplier, settlement
  asset, and positive integer contract quantity. Before every opening order, verify current venue
  metadata against those facts; mismatch means no order.
- Opening intent and submitted quantity must equal the exact approved quantity. Weights,
  equity percentages, budgets, and maximums cannot supply fixed-size authority. Enforce
  it independently in runtime composition, execution pretrade, provider preview, and the final wire
  order.
- Existing position plus open-order exposure in the bound product must not exceed the approved
  quantity. Missing, stale, ambiguous, or contradictory facts fail closed.
- Never round up, split the approved quantity into additional creates, retry an ambiguous create,
  substitute contracts, or increase size for buying power. If the exact quantity is not executable,
  submit nothing.
- Maintain independent positive caps on order contracts, position contracts, order notional,
  required margin, fees, slippage, and loss wherever the venue provides the necessary facts. Any
  breach blocks submission.
- Closing may only reduce the verified strategy-owned position in the bound product, never reverse
  or enlarge it. An oversized observed position halts automatic trading; remediation is human-only.
- Verify rejection of zero, unauthorized fractional, smaller, larger, rounded, duplicate, stale,
  mismatched-product, excess-position, and ambiguous-create cases through the production entry
  point. Unit tests cannot authorize activation.
- Spot sizing cannot stand in for derivatives: a separate derivatives adapter must satisfy all these
  invariants.

Run the production package tests, static checks, and workspace lock check before completing changes.

## Capital Telemetry Projection

- `extensions/portfolio.yaml` declares portfolio membership. It is **not authority**: it cannot activate,
  arm, schedule, or authorize anything. Membership is declared there and nowhere else — a
  deployment file, `CAN_TRADE=yes`, or a nonzero position is never sufficient membership.
- `qf-production publish-projection` is run locally by hand and writes
  `db/production/{overview.json, strategies/<family>/{snapshot.json, observations.jsonl, runs.jsonl}}`.
  Snapshots are atomically replaced; the two `.jsonl` histories are append-only.
- The publisher never calls a venue. Capital facts reach it only through the `capital` block that
  `run_once` records in the runtime journal from an already-authenticated cycle. The DB API in turn
  never reads the state root, never resolves a credential, and never calls a venue.
- Every published payload passes `production.observation.assert_redacted`, which fails closed on
  credential-shaped keys, raw identifiers, unexpected hex digests, and key material. Adding a field
  to a published document does not bypass it.
- External operator cash movement lives in `<state-root>/flows/<fingerprint>/flows.jsonl` as
  `{"at": <ISO-8601 UTC>, "amount_usd": <signed decimal>}`. Without it a deposit reads as profit,
  so an unreadable ledger fails closed rather than defaulting to zero.
- Registration, installation, scheduling, activation, arming, gates, deactivation, `CAN_TRADE`, and
  `AUTONOMOUS_LIVE` stay separate facts through the projection. Do not collapse them into a
  "live"/"offline" badge — a closed gate is usually intentional. Only data/signal refreshes may run
  on a schedule; no deployment does, so `SCHEDULED` and `AUTONOMOUS_LIVE` are always `no`.
