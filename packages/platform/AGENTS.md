# packages/platform — Rules

Platform owns shared, domain-neutral mechanics. Read the owning subsystem's
`AGENTS.md` before changing it.

## Placement

- `backtest/`: strategy-intent preparation, portfolio simulation, reconciliation,
  and reporting.
- `ml-engine/`: generic model training, evaluation, artifacts, and inference.
- `signal-analysis/`: shared signal/target contracts, model-independent partition
  mechanics, descriptive analysis, and explicitly specified statistical inference;
  consuming packages retain clocks, universes, research policy, and promotion gates.
- `family-registry/`: the decorator registry and `extensions/lib` family discovery
  that `signals` and `strategies` subclass; package policy stays in the subclass.
- `clients/<provider>-client/`: external provider API wrappers.
- `config/`: shared non-secret settings, paths, and schema utilities.

## Boundaries

- Platform is public shared core; it has no private `extensions/`. Family,
  strategy, deployment, and other instance-specific behavior belongs to its
  consuming package. Keep dependencies light and consumers on public APIs or CLIs.
- Clients own provider access, not canonical storage, schemas, or canonicalization
  policy. Do not add implicit caches, output paths, durable writes, or schedulers.
  Exports must be caller-directed; an existing exception documented by the owning
  client does not authorize new exceptions.
- Register new clients with their own `pyproject.toml` and root
  `[tool.uv.workspace]` membership. Clients read credentials from named
  environment variables and document each name in their README.

## Authority and validation

- Preserve trading gates and quote-currency allowlists: require the exact enable
  value, default disabled, and never weaken or bypass them. Changing a client's
  import-time versus live environment-read semantics requires operator direction.
- Secret values remain human-operated. Never dump the process environment or
  export credential values.
- Changing pinned versions or breaking artifact/consumer compatibility requires
  operator direction; the owning subsystem declares its pinned surfaces.
- Run each changed subsystem's complete local correctness suite and documented
  quality checks. Engine `src/` changes require the engine's full suite; repository
  CI success is not a substitute. For subsystems covered by repository contracts
  or boundaries, also run `tests/contracts` and `tests/boundary`. Shared-default
  changes require the full repository contract suite and review of every changed
  default and its consumer impact.

Workspace membership: root `pyproject.toml` `[tool.uv.workspace]` is authoritative; never infer
membership from directory presence.

## Map

| When the task is about... | Work in... | Avoid... |
| --- | --- | --- |
| shared repo settings, db root, schema index | `packages/platform/config` | new secret globals or direct env parsing |
| execution simulation, reconciliation, and reporting | `packages/platform/backtest` | strategy-family logic |
| strategy weights to engine-neutral portfolio targets | `packages/platform/backtest` | venue submission or strategy research |
| generic model training and inference | `packages/platform/ml-engine` | financial targets, prediction storage, portfolio construction |
| signal/target contracts, partition mechanics, importance, and statistical analysis | `packages/platform/signal-analysis` | model fitting, universe selection, promotion decisions |
| family runner registration and `extensions/lib` discovery | `packages/platform/family-registry` | family-specific policy or imports from consumers |
| external provider API wrappers | `packages/platform/clients/<provider>-client` | canonical data writes |
