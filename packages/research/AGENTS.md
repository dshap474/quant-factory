# packages/research — Rules

Canonical rules for agents working inside `packages/research`. Job: the
exploratory layer — standalone utilities in public `src/`, tracked package
documentation in `docs/`, and local-only user material in `.dev/`, `corpus/`,
and `sandbox/` — outside the data → features → signals → strategies promotion chain.
Surface docs: package `README.md` and each sandbox project's own `AGENTS.md` — a
project AGENTS.md is binding for work inside that project.

Every rule below is unenforced by code — that is why it is written down. What
tests and contracts already enforce is deliberately absent.

Research is the explicit exception to the repo-wide `src/` plus `extensions/`
split: it has no `extensions/` directory. The repository ships
empty `src/`, `docs/`, `corpus/`, and `sandbox/` skeletons.
Personal working files, user corpus, and sandbox contents are local-only and gitignored.

## Boundary

- Research is import-terminal: nothing outside this package imports it, and
  it must stay that way. Promotion means rewriting into the owning production
  package, never importing a `sandbox/` module across the boundary.
- `db/research/**` is a shared write namespace (strategies candidate runs
  land there too) and it is gitignored: new artifacts are invisible to
  `git status` and never committed. Never "clean up" under `db/` — losses have no diff and
  no recovery.
- A project that must not be promoted says so in its own
  `AGENTS.md`.

## Sandbox limits

- Sandboxes run locally and are limited to paper trading, testnet accounts, and read-only
  integrations. Identity checks, confirmations, and signatures remain human steps.
- Read secrets from the environment, never from Git. Credentials a sandbox uses must be read-only or
  testnet-only with no real-value funds; mainnet signers, even unfunded, are excluded. Existing
  package boundaries and live-trading restrictions still apply.
- Humans deploy: provisioning remote infrastructure, installing persistent services or schedules,
  and activating live trading are never done from a sandbox.

## Production API contract (frozen)

- `apps/api` exposes stable logical `corpus/`, `sandbox/`, `src/`, and `docs/` routes
  (`_RESEARCH_DOC_ROOTS` in `db_api/routers/research.py` — anything else
  403s); sandbox discovery uses `sandbox/*/viz.json` (malformed JSON
  silently delists a project). Never add or rename a top-level surface
  without updating that router in the same change; a project whose internal
  layout is also hard-coded there says so in its own `AGENTS.md`.
- Where code defines a layout that docs describe (corpus item
  layout, db-api paths), the code contract wins: never change the code to
  match a disagreeing doc — that orphans existing artifacts. Fix the
  doc instead.

## Repo-wide blast radius

- Sandbox projects are deliberately outside the repository workspace because
  the repository ships no sandbox implementations.
- The repo contract test scans public code under `src/`, not the ignored local
  sandbox. Public research code may not contain literal `Path("db/...")`
  storage paths.

## Verification

- `uv lock --check` after any member `pyproject.toml` edit.
- `uv run pytest tests/contracts/test_db_root_contracts.py -q` after adding
  research code that touches `db/` paths.

Project-specific gotchas live in that sandbox project's own `AGENTS.md`,
next to the code — append new gotchas there, never here.
