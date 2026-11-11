# Backtest testing guide

The package test suite is hermetic and ephemeral: it uses fixed timestamps and
generated market data,
makes no network or cloud calls, and writes temporary files only through
pytest's `tmp_path`.

## Run the suite

From the repository root:

```bash
# Small public-boundary suite: CLI, ordinary Nautilus, connector, and ledger edges
uv run pytest packages/platform/backtest/tests/e2e/test_public_contracts.py -q

# Fast unit layer
uv run pytest packages/platform/backtest/tests/unit -q

# Prepared-execution and resting-limit audit layer, including lifecycle and mutation checks
uv run pytest packages/platform/backtest/tests/audit -q


# Complete package
uv run pytest packages/platform/backtest/tests -q
```

The complete audit is intentionally much slower than the E2E and unit layers.
Use the focused commands during development and the complete command before
publishing changes to engine accounting or lifecycle behavior.

## Test structure

```text
tests/
├── e2e/
│   └── test_public_contracts.py  # process and public API known-answer tests
├── unit/                         # focused engine, metric, connector, and schema tests
├── oracles/                      # scripts that regenerate the frozen reference fixtures
├── audit/                        # prepared Nautilus and resting-limit invariants and mutations
```

## Oracle rules

- Use hand-derived values or an independent implementation for accounting expectations.
- Test production behavior through a public entry point whenever the failure is observable there.
- Keep timestamps fixed and UTC-aware in new E2E fixtures.
- State `rtol` and `atol`; do not loosen a tolerance merely to make a failure pass.
- Use `tmp_path` for parquet, JSON, images, subprocess inputs, and other artifacts.
- Add a slow Nautilus scenario only when it covers a distinct plausible defect class.

## Stopping rule

The ledger and prepared-execution paths already have dense analytic,
metamorphic, lifecycle, stress, and mutation coverage. Prefer a small regression
for a demonstrated bug over another scenario matrix, test DSL, snapshot corpus,
container, or live-data test.
