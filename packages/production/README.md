# Production

`packages/production/` is the provider-neutral control plane for operating canonical strategies.
It validates tracked definitions, fingerprints immutable inputs, stores external authority outside
Git, orchestrates one decision, reports host facts, and publishes redacted capital telemetry.

The runtime is inactive by default. It never installs or enables automation and has no command
that combines activation, arming, capital authority, and scheduling.

## Structure

```text
packages/production/
├── src/production/                 # public control plane and registries
├── tests/                          # provider- and family-neutral core tests
└── extensions/                     # installation-specific, not in published packages
    ├── adapters/                   # venue composition
    ├── deployments/                # family deployment bundles (no scheduling assets)
    ├── candidates/                 # assessment evidence only
    └── portfolio.yaml              # membership, never authority
```

The public core depends only on PyYAML and the public Strategies package. Installed extensions
register concrete runtime adapters, additional activation schemas, and independent family gates.
An absent overlay is valid: imports and CLI help work, `list` is empty, and a request for an
uninstalled adapter fails with a typed validation error.

## Deployment Bundles

One deployment is a direct child of `extensions/deployments`:

```text
extensions/deployments/<family>/
├── deployment.yaml                # tracked definition, not activation authority
├── register.py                    # optional family-only policy registration
├── run_cycle.py                   # optional manual cycle entry point (no timer)
├── releases/                      # optional certified releases
└── archive/                       # immutable historical evidence
```

`deployment.yaml` references the canonical memory version and preset owned by
`packages/strategies`. Validation binds the deployment, packaged strategy sources, preset,
promotion receipt, and canonical final into one deterministic fingerprint.

## Commands

```bash
uv run --package quant-factory-production qf-production list
uv run --package quant-factory-production qf-production list --deployments-root packages/production/extensions/deployments
uv run --package quant-factory-production qf-production validate packages/production/extensions/deployments/<family>/deployment.yaml
uv run --package quant-factory-production qf-production inspect packages/production/extensions/deployments/<family>/deployment.yaml
uv run --package quant-factory-production qf-production status packages/production/extensions/deployments/<family>/deployment.yaml
uv run --package quant-factory-production qf-production activation apply packages/production/extensions/deployments/<family>/deployment.yaml /protected/operator-receipt.yaml --confirm-fingerprint <fingerprint>
uv run --package quant-factory-production qf-production run-once packages/production/extensions/deployments/<family>/deployment.yaml --dry-run
uv run --package quant-factory-production qf-production deactivate packages/production/extensions/deployments/<family>/deployment.yaml
```

`list`, `validate`, `inspect`, and `status` are read-only. Activation installation validates a
protected operator file and atomically installs it only after exact fingerprint confirmation; it
does not arm, call a venue, alter host units, or grant capital authority. Deactivation stops new
decisions only and never flattens or cancels.

## State, Secrets, and Authority

Mutable state belongs in an explicitly configured durable root outside the repository. Activation
receipts, arming markers, deactivation records, journals, locks, account snapshots, and active
pointers never belong in Git or under `extensions/`.

Credentials come only from the process environment. A tracked deployment, portfolio membership, passing tests,
installed units, a schedule, or an open host gate does not by itself authorize live execution.
