# STOP: read this before changing the backtest package

This `AGENTS.md` is the mandatory contributor contract for any person or agent that will edit,
refactor, test, or review the backtest package.

If you only need to **use** the package, read the user guide instead:
[`README.md`](README.md).
The README explains public imports, engine selection, inputs, examples, results, and CLI usage; it
does not define how this package should be changed.

# Backtest contributor guide

## Mission and boundaries

This package is the reusable portfolio backtest and execution-simulation seam for `quant-factory`.
It consumes prices plus target weights and returns a canonical `BacktestResult`.

- Strategies own forecasts, signals, portfolio construction, and decision-time `StrategyWeights`.
- `packages/execution` owns engine-neutral instruments, sizing, order policies, fills, and accounting contracts.
- This package owns strategy-intent translation, ordinary portfolio evaluation, Nautilus adaptation,
  execution projection, and reporting.
- Strategy-specific research, parameter selection, walk-forward orchestration, and promotion decisions do not belong here.
- Parent-order execution-policy cost simulation lives in `execution_sim/`; one-off studies and
  calibration notebooks stay in research sandboxes. The policy type and its per-minute decisions
  belong to the execution core (`execution.ParentOrderPolicy`, `maker_child_lots`, `maker_price`)
  so backtest and live share one copy; `execution_sim/` only decides fills. Never import the
  execution `policies` extension or define named presets here.

Keep the package explicit and small. Do not add an engine plugin registry, strategy framework,
research controller, hidden dependency injection, or generic scenario DSL.

## Public surface

Keep these imports stable and documented in `README.md`:

- `BacktestConfig`
- `BacktestResult`
- `run_backtest`
- `run_backtest_from_strategy_weights`
- `materialize_effective_weights`
- `prepare_execution_from_strategy_weights`
- `PreparedExecutionInput`
- `render_execution_png`
- `prepare_resting_limit_execution`
- `PreparedRestingLimitInput`
- `prepared_resting_limit_fingerprint`
- `run_resting_limit_backtest`
- `run_intent_ledger` and `IntentLedgerResult` for sparse, nullable decision targets with
  actual account feedback passed as `strategies.AccountState`
- `simulate_execution`, `summarize_execution`, `FillAssumptions`, and `ExecutionSimResult` for
  parent-order execution-cost simulation over `execution.ParentOrderPolicy` values

Callers must import from `backtest`, not private engine or preparation modules.

## The six execution paths

1. **Ordinary ledger** — `BacktestConfig(engine="ledger")`.
   Use for most weights-to-equity research across the repository. It is deterministic,
   current-equity based, and explicitly opt-in.
2. **Ordinary Nautilus** — `BacktestConfig(engine="nautilus")`, the compatibility default.
   It replays target weights through Nautilus market orders, while ordinary funding and costs
   remain explicit post-processing under the legacy conventions documented in the README.
3. **Prepared Nautilus execution** — pass `prepared_execution` to
   `run_backtest_from_strategy_weights`. Use when fills, IOC/TWAP policy, fees, funding events,
   holdings, shortfall, or initial account state matter. This path is Nautilus-only.
4. **Deterministic OHLC resting limits** — call `prepare_resting_limit_execution`, then
   `run_resting_limit_backtest`. Use only for explicit resting limits over completed OHLC bars.
   Eligibility begins after activation; this path does not infer queue position or intrabar path.
5. **Event intent ledger** — call `run_intent_ledger` with a prepared event calendar and
   canonical `StrategyWeights` decisions or a causal decision callback. It maintains actual
   quantities, applies event funding, and executes a sparse decision at the next event. This
   opt-in path is ledger-only and returns account/fill/decision evidence separately.
6. **Execution simulator** — `simulate_execution` over 1-minute OHLCV bars (optional bid/ask).
   Answers what each parent-order policy costs versus a fairly priced market order at the open:
   market-at-open, or post-only maker schedules that join the bid from bar t-1 quotes and
   market any remainder at a deadline. Fills are deterministic expected values (through = full,
   touch = `touch_fill_prob`, capped at `participation` of bar volume). It returns per-order costs
   in bps and fills as Polars frames, never a `BacktestResult`. Limits: no queue or impact model,
   maker fills are optimistic, and orders are simulated independently of each other.

Never silently fall back between engines. Reject prepared execution with the ledger.

## Timing contract

- `run_backtest(prices=..., weights=...)` receives an **effective target schedule**.
  Weight row `i` is the portfolio target for interval `[i, i+1]`; no lag is added.
- `StrategyWeights.weights.timestamp` is always a **decision timestamp**.
  `run_backtest_from_strategy_weights` materializes `ExecutionTiming` onto the market-data calendar.
- `ExecutionTiming.next_bar()` is the default and the normal choice for close-derived signals.
- `ExecutionTiming.same_bar()` is allowed only when same-bar execution is genuinely causal.
- Prepared execution requires at least one bar of lag and preserves the original decision rows;
  do not pass materialized effective weights into preparation.

Treat lookahead prevention as a public contract, not a caller convention.

## Input invariants

Ordinary inputs must fail closed:

- timestamps are non-null, sorted, unique, and exactly aligned;
- prices, weights, and funding use identical asset columns;
- `CASH` is present and every weight row sums to `1.0` within absolute tolerance `1e-6`;
- all numeric values are finite;
- every non-CASH price is strictly positive;
- leading panel prices are never fabricated or backward-filled;
- omitted funding means zero funding;
- ledger CASH funding is zero when funding is enabled;
- `initial_capital` is finite and positive, and `trade_cost_bps` is finite and non-negative.

Do not reintroduce silent price clipping, `fill_null(1.0)` for risky assets, relative weight-sum
tolerance, automatic column repair, or implicit timestamp alignment.

## Accounting invariants

### Ledger

- Starts all-CASH and sizes every interval from current pre-trade equity.
- Uses gross non-CASH traded notional for turnover; there is no half-turnover convention.
- Charges initial entry, both legs of rotations, and full long/short reversals.
- Uses funding row `i` for interval `[i, i+1]`; positive funding means longs pay.
- Does not trade the final target row because no following interval exists.
- Fails if equity becomes non-finite or non-positive.

### Ordinary Nautilus

- Sizes target quantities from marked current equity, never initial capital after the first bar.
- Uses actual Nautilus portfolio PnL for the gross price path.
- Retains the documented legacy half-turnover and post-processed cost/funding decomposition.
- Disposes the Nautilus engine on both success and failure.

Do not share turnover helpers between the two ordinary engines; their public conventions differ.

## Result contract

`BacktestResult.to_dataframe()` is a frozen persistence surface with exactly:

```text
equity, benchmark_equity, price_return, funding_return,
cost_return, net_return, turnover
```

It prepends a zero to interval streams so the frame has the same `T` rows as equity.
Do not add engine metadata, metrics, fills, or execution details to these seven columns.
Persist `metrics`, `engine_used`, and `engine_meta` separately. Prepared Nautilus details live in
`result.execution`; deterministic resting-limit details live in `result.resting_limit_execution`.
Ordinary paths leave both as `None`.

## Ownership map

- `api.py` — public ordinary engine dispatch only.
- `config.py` — shared configuration and annualization factors.
- `inputs.py` — shared ordinary input validation and normalization.
- `connectors.py` — `StrategyWeights` timing materialization and panel/wide data alignment.
- `engines/ledger.py` — ordinary current-equity portfolio ledger.
- `intent_ledger.py` — explicit event account ledger for sparse canonical decisions.
- `engines/nautilus/portfolio.py` — ordinary Nautilus weight replay.
- `preparation/` — validated prepared-execution input and semantic fingerprints.
- `engines/nautilus/{runtime,strategy,construction,assembly,worker}.py` — isolated prepared execution.
- `projection/` — deterministic account/holding/funding projection.
- `resting_limit/` — validated preparation, semantic fingerprint, and pure OHLC matcher.
- `execution_sim/` — parent-order policy cost simulator: fill assumptions, numpy fill kernel
  (policy decisions come from the execution core), cost decomposition and summaries.
- `execution_charts/` — prepared-execution chart data and PNG rendering.
- `result.py` and `result_schema.py` — canonical result and frozen dataframe schema.
- `cli.py` — the reusable `qf-backtest run` process boundary.
- `tests/e2e/` — small public-boundary regressions.
- `tests/unit/` — focused contracts and known-answer tests.
- `tests/audit/` — prepared Nautilus oracles, lifecycle, stress, and mutation checks.

Nautilus is an installed, pinned dependency. Do not vendor or fork it inside this package.

## Change workflow

1. Read the README and the owning module before editing.
2. State which public path and invariant are changing.
3. Add the smallest public-entry regression that would fail before the fix.
4. Use a hand-derived known answer, independent oracle, invariant, or metamorphic relation.
5. Make the narrowest production change; do not add infrastructure for one scenario.
6. Update the README when public usage, input semantics, engine selection, or results change.
7. Preserve unrelated dirty work and keep generated artifacts outside the checkout.

Finite tests establish scoped software evidence, not universal mathematical proof or empirical
strategy validity. Never describe a backtest pass as production promotion evidence.

## Verification

Run from the repository root.

```bash
# Fast public boundaries
uv run pytest packages/platform/backtest/tests/e2e -q

# Focused ordinary/unit layer
uv run pytest packages/platform/backtest/tests/unit -q

# Prepared execution, lifecycle, stress, and mutation layer
uv run pytest packages/platform/backtest/tests/audit -q

# Authoritative package verification; intentionally slow
uv run pytest packages/platform/backtest/tests -q

# Static checks
uv run ruff check packages/platform/backtest
uv run ty check --project packages/platform/backtest
git diff --check
```

Build checks must not write `dist/` into the checkout:

```bash
build_dir=$(mktemp -d /tmp/qf-backtest-build.XXXXXX)
uv build --package quant-factory-backtest --out-dir "$build_dir"
```

Remove only the exact temporary directory created for that check. Never loosen tolerances,
refresh frozen oracles, or accept mutation-test collection failures merely to make a check pass.

## Project docs

Usage and package architecture belong in `README.md`.

## Explicit inactive-price ledger mode

The ordinary finite-price defaults above remain mandatory. The documented
`allow_inactive_missing_prices=True` ledger mode additionally supports null/NaN
prices only when no effective entry, carried position, valuation or exit needs
that mark. Validate both endpoints for each nonzero traded target; zeroing the
next target never excuses a missing exit mark. Require a complete explicit
non-CASH benchmark and reject all observed infinity/nonpositive risky prices.
Do not fill prices. The strategy connector must receive wide prices for this
mode because the legacy panel converter forward-fills. Nautilus rejects the mode.
