# quant-factory backtest engine

This package converts target portfolio weights plus market data into a canonical
`BacktestResult`. It is the shared evaluation/execution seam for the quant repository;
it does not generate signals, choose parameters, or decide whether a strategy is promoted.

This README is exclusively the package **user guide**. If you are changing or reviewing the
package itself, read [`AGENTS.md`](AGENTS.md) instead.

Run every command below from the repository root.

## Choose the correct path

| Need | Public entry point | Engine |
| --- | --- | --- |
| Most strategy research: decision weights → returns/equity | `run_backtest_from_strategy_weights` | `ledger` (recommended explicitly) |
| Already-materialized effective weights and aligned prices | `run_backtest` | `ledger` or ordinary `nautilus` |
| Orders, IOC/TWAP fills, commissions, funding events, holdings, shortfall | prepare, then `run_backtest_from_strategy_weights` | prepared Nautilus only |
| Resting limits evaluated from completed OHLC bars | `prepare_resting_limit_execution`, then `run_resting_limit_backtest` | deterministic OHLC matcher |
| Parquet files from a shell or another process | `qf-backtest run` | configured ordinary engine |
| Sparse targets, reduce-only quantity bounds, and causal account feedback | `run_intent_ledger` | explicit event ledger |
| Cost of a parent-order execution policy (market vs. maker schedules) from 1m OHLCV | `simulate_execution`, then `summarize_execution` | numpy parent-order simulator |

`BacktestConfig()` defaults to `engine="nautilus"` for compatibility. For a normal
weights-to-equity research backtest, specify `engine="ledger"`. Use prepared Nautilus when
execution behavior—not merely portfolio accounting—is part of the question.

## Recommended integration for every strategy package

Every production strategy should emit canonical, decision-time `StrategyWeights`. The connector
applies the declared execution lag, aligns market data, and calls the selected engine.

```python
from datetime import UTC, datetime

import polars as pl
from backtest import BacktestConfig, run_backtest_from_strategy_weights
from strategies import ExecutionTiming, StrategyWeights

market_data = pl.DataFrame(
    {
        "timestamp": [
            datetime(2024, 1, 1, tzinfo=UTC),
            datetime(2024, 1, 2, tzinfo=UTC),
            datetime(2024, 1, 3, tzinfo=UTC),
            datetime(2024, 1, 4, tzinfo=UTC),
        ],
        "BTC": [100.0, 102.0, 101.0, 105.0],
    }
)

strategy_weights = StrategyWeights(
    weights=pl.DataFrame(
        {
            "timestamp": [
                datetime(2024, 1, 1, tzinfo=UTC),
                datetime(2024, 1, 3, tzinfo=UTC),
            ],
            "BTC": [0.50, -0.25],
            "CASH": [0.50, 1.25],
        }
    ),
    assets=["BTC"],
    execution=ExecutionTiming.next_bar(),
    metadata={"strategy": "my_strategy", "version": "v001"},
)
strategy_weights.validate()

result = run_backtest_from_strategy_weights(
    weights=strategy_weights,
    data=market_data,
    config=BacktestConfig(
        engine="ledger",
        initial_capital=100_000.0,
        trade_cost_bps=5.0,
        include_funding=False,
        frequency="daily",
        benchmark="BTC",
    ),
)

print(result.summary())
print(result.to_dataframe())
```

Why this is the preferred repository-wide seam:

- `StrategyWeights.timestamp` means **decision time**, consistently across strategies.
- `ExecutionTiming.next_bar()` prevents a close-derived decision from trading on that same close.
- Sparse decisions are shifted onto the price calendar and forward-filled after they become effective.
- Strategy code stays upstream in `data → features → signals → strategies`; the engine only evaluates intent.

Market `data` may be either:

- **Wide:** `timestamp`, one column per asset. The connector adds `CASH=1.0` to prices.
- **Panel:** `timestamp`, `asset`, `close`. Every requested asset needs a real leading price;
  later gaps may forward-fill, but leading gaps fail closed.

Use `timestamp_col`, `asset_col`, or `price_col` arguments when those column names differ.

## Execution timing

`StrategyWeights` are never assumed to be effective immediately:

| Timing | Meaning | Normal use |
| --- | --- | --- |
| `ExecutionTiming.next_bar()` | decision at row `i`, effective at the next market row | Default; close-derived signals |
| `ExecutionTiming.same_bar()` | decision and target effective on the same row | Only when the decision is causally known before that execution |
| `ExecutionTiming.lagged(n)` | effective `n` market rows after the decision | Explicit operational/research delay |

The connector drops market rows before the first effective target, forward-fills an effective target
until the next one, and fails if the lag removes every target.

Do not pre-shift weights and also declare `next_bar`; that applies the lag twice.

## Sparse decisions with account feedback

Pass `collect_attribution=True` to return `IntentLedgerResult.asset_attribution`:
a daily UTC long table of `timestamp, asset, price, quantity, weight, price_pnl,
funding_pnl, fees`. Prices and quantities are the last actual marks/holdings of
each UTC date; weight is signed marked notional divided by post-fee account NAV.
Price P&L and funding use pre-fill holdings on the original event grid; fees use
actual absolute traded notional. Daily cash flows include exits even when ending
quantity is zero. Missing prices for flat assets stay null. The sum of all asset
price P&L plus funding minus fees reconciles to the account change, including the
first day's change from initial capital. This optional reporting output does not
alter targets, fills, NAV, or the frozen seven-column `BacktestResult` schema.

Use `run_intent_ledger` when a decision depends on actual marked holdings or when
an asset target is null (hold its actual quantity). This is an explicit ledger path;
the ordinary connector, ordinary/prepared Nautilus and effective-weight materialization
reject nullable targets, `quantity_limits` and `quantity_targets`.

Pass a sorted wide `market` frame with `timestamp`, `kind` (`open`, `close`, or
`settlement`), and one price column per risky asset. Do not include `CASH`.
`funding_rates` has the same timestamps and asset columns; each value is the
decimal funding charge **for that event**. Positive rates charge longs and credit
shorts. Omit the frame for zero funding. Missing prices and rates are allowed only
for unheld assets; an executable target or held position requires a real mark.
The chosen benchmark asset must have a complete price series.

```python
from backtest import BacktestConfig, run_intent_ledger
from strategies import ExecutionTiming, StrategyWeights

def decide(timestamp, account):
    # account is strategies.AccountState: nav, cash, quantities, and weights
    # describe actual marked holdings after funding at this event.
    return StrategyWeights(
        weights=decision_row,  # one row at timestamp; nullable risky targets allowed
        quantity_limits=limit_row,  # optional aligned signed remaining-position bounds
        assets=assets,
        execution=ExecutionTiming.next_bar(),
    )

config = BacktestConfig(engine="ledger", metrics=[], benchmark="BTC")
run = run_intent_ledger(
    market=event_prices,
    funding_rates=event_funding,
    decision_times=decision_timestamps,
    decide=decide,
    config=config,
)
replay = run_intent_ledger(
    market=event_prices,
    funding_rates=event_funding,
    decisions=run.decisions,
    config=config,
)
```

A decision fills at the **next event**. Supply the fill event with its causally
available quote; for example, a decision at a completed daily close can fill at
the following daily open. The callback returns one canonical `StrategyWeights`
row for each `decision_times` entry. Replay supplies one multirow
`StrategyWeights` artifact instead of a callback. Both modes use the same account
path. The decision rows must share execution timing, metadata and identity.

For each asset, a null weight holds the actual fill-time quantity. A fully
specified row has numeric `CASH` and sums to one; a row with any null asset
target has null `CASH`. An aligned signed `quantity_limits` value restricts the
**remaining position** at fill: positive permits `[0, min(current, limit)]` for
a current long, negative permits `[max(current, limit), 0]` for a current short,
zero flattens, and null leaves the target unconstrained. The bound is frozen
at decision time and intersects the actual fill-time position, so a position
closed before the fill cannot reopen through an old bound.

An aligned `quantity_targets` value requests an **absolute final held quantity**,
frozen at the decision; it is never recalculated from fill-time NAV or price. This
deliberately narrow mode supports one risky asset, nonnegative long/cash quantities
and no borrowing: multiple risky assets, negative or nonfinite targets, a short
holding or already-negative cash are rejected. A numeric quantity target requires a
null weight target on that asset, null `CASH` and no numeric `quantity_limits` on
that asset. At the fill a reduction sells the difference; an increase buys at most
the requested difference and at most `cash / (quote × (1 + fee_rate))`, charging the
ordinary actual-notional fee. That affordable clip is the only quantity difference;
resulting cash may differ from zero only by floating-point residue (`1e-9` × NAV).
Zero closes the holding; a null quantity target leaves the weight/hold rules in force.
Forced exits take precedence. The fill record adds `requested_quantities` for
quantity-target fills; weight-only fills and the seven-column result are unchanged.
Replaying the artifact with a different `trade_cost_bps` keeps the same requested
quantities and clips only to that account's own fee-affordable cash.

Optional `forced_exits` and `relisted_at` map event timestamps to asset names.
An exit flattens the named position at that event and blocks reentry until its
release event. For terminal or partial-hour settlements, prepare a settlement
event with the causal quote and prorated funding rate; the ledger does not infer
intrabar prices or rates.

The result contains `.backtest` with the standard seven-column dataframe,
`.account` event rows, `.fills` with signed quantities and traded dollars, and
`.decisions` for canonical save/replay. Event spacing may mix hourly closes and
daily opens, so pass `metrics=[]` and calculate performance metrics on an
explicit regular reporting calendar.

## Direct ordinary API

Use `run_backtest` when weights have already been materialized onto the price timeline. Unlike
`StrategyWeights`, direct weight row `i` is already effective for interval `[i, i+1]`.

```python
from datetime import UTC, datetime, timedelta

import polars as pl
from backtest import BacktestConfig, run_backtest

start = datetime(2024, 1, 1, tzinfo=UTC)
timestamps = [start + timedelta(days=offset) for offset in range(4)]

prices = pl.DataFrame(
    {
        "timestamp": timestamps,
        "BTC": [100.0, 100.0, 110.0, 121.0],
        "CASH": [1.0, 1.0, 1.0, 1.0],
    }
)
effective_weights = pl.DataFrame(
    {
        "timestamp": timestamps,
        "BTC": [0.0, 0.5, 0.5, 0.0],
        "CASH": [1.0, 0.5, 0.5, 1.0],
    }
)
funding_rates = pl.DataFrame(
    {
        "timestamp": timestamps,
        "BTC": [0.0, 0.01, -0.02, 0.0],
        "CASH": [0.0, 0.0, 0.0, 0.0],
    }
)

result = run_backtest(
    prices=prices,
    weights=effective_weights,
    funding_rates=funding_rates,
    config=BacktestConfig(
        engine="ledger",
        initial_capital=100_000.0,
        trade_cost_bps=10.0,
        include_funding=True,
        benchmark="BTC",
    ),
)
```

### Ordinary input contract

`prices`, `weights`, and optional `funding_rates` must satisfy all of the following:

- a non-null, sorted, unique timestamp column;
- identical timestamps, row counts, and asset-column sets;
- a `CASH` column;
- finite numeric values everywhere;
- strictly positive prices for every non-CASH asset;
- each weight row sums to `1.0` within absolute tolerance `1e-6`;
- at least two rows to form a return interval.

Negative asset weights and gross exposure above one are allowed; `CASH` is the residual that keeps
the row sum equal to one. Omit `funding_rates` to use zeros. Funding rates are per interval, not
annualized. Positive funding means longs pay and shorts receive. With ledger funding enabled,
`funding_rates.CASH` must be zero.

## Engine semantics

### Ledger: recommended ordinary portfolio book

Set `BacktestConfig(engine="ledger")`.

- Starts all-CASH and rebalances from current pre-trade equity. By default every interval trades.
- Set `rebalance_every_bars=N` (positive integer, ledger only) to trade interval rows
  0, N, 2N, etc., anchored to the first effective row after timing materialization.
  Other rows ignore targets and hold fixed quantities with daily valuation/funding;
  weights and exposures drift. Seven bars means a week only on a complete daily calendar.
  Sparse decisions alone forward-fill targets and do not change this trade schedule.
- Target row `i` is held over `[i, i+1]`; the final target row is not traded.
- Turnover is gross non-CASH traded notional divided by pre-trade equity.
- Initial entry, both legs of asset rotation, and full long/short reversals are charged.
- Cost is traded notional × `trade_cost_bps / 10_000`.
- Funding for `[i, i+1]` uses row `i` and equals
  `−Σ(target_notional × funding_rate)` for non-CASH assets.
- `net_return = price_return + funding_return − cost_return`.
- Non-finite or non-positive equity fails closed.

### Ordinary Nautilus: compatibility default

Set `BacktestConfig(engine="nautilus")` or omit `engine`.

- Replays the effective target schedule as Nautilus bar-market orders.
- Sizes each target from current marked equity.
- Derives the gross price path from the Nautilus portfolio.
- Applies the legacy ordinary funding/cost decomposition afterward.
- Legacy turnover is `0.5 × Σ|w[i+1] − w[i]|`, including CASH changes; it does not charge an
  implicit initial all-CASH-to-first-target transition.
- Disposes each engine instance after success or failure.

Ordinary Nautilus is not the prepared execution model. If order outcomes, fees, holdings,
shortfall, or policy slices matter, use the prepared path below.

## Configuration

```python
BacktestConfig(
    initial_capital=100_000.0,
    trade_cost_bps=5.0,
    include_funding=True,
    frequency="daily",
    metrics=["sharpe", "max_drawdown", "total_return"],
    benchmark="BTC",
    engine="ledger",
    random_seed=42,
)
```

| Field | Meaning |
| --- | --- |
| `initial_capital` | Finite positive starting equity |
| `trade_cost_bps` | Finite non-negative trading cost in basis points |
| `include_funding` | Include supplied funding; omitted funding frames are zeros |
| `frequency` | Metric annualization and ordinary Nautilus bar aggregation |
| `metrics` | Metric names to compute; use `[]` when metrics are not needed |
| `benchmark` | Benchmark asset column; defaults to the first non-CASH asset |
| `engine` | Exactly `"ledger"` or `"nautilus"` |
| `random_seed` | Deterministic engine seed where applicable |
| `rebalance_every_bars` | Ledger trade interval, positive integer; default 1, required for other engines |
| `collect_ledger_detail` | Ledger only, default `False`; also return `BacktestResult.ledger_detail` |

Cross-engine frequencies currently documented for use are `daily`, `1d`, `hourly`, `1h`, `4h`,
`30m`, `15m`, `5m`, `1m`, and `minute`. Do not assume an arbitrary string is supported.

Available metrics are:

```text
total_return, ann_return, ann_vol, sharpe, sortino, max_drawdown,
active_return, tracking_error, information_ratio, avg_turnover,
funding_share, win_rate, calmar, sharpe_se, sharpe_tstat,
sharpe_ci_lower, sharpe_ci_upper, sharpe_adj_autocorr
```

## Reading and persisting results

`BacktestResult` exposes:

- `equity` and `benchmark_equity`: `T` values;
- `price_return`, `funding_return`, `cost_return`, `net_return`, `turnover`: `T-1` intervals;
- `metrics`: requested scalar metrics;
- `engine_used` and `engine_meta`: actual engine identity and diagnostics;
- `execution`: prepared Nautilus `ExecutionResult`, otherwise `None`;
- `resting_limit_execution`: deterministic OHLC resting-limit result, otherwise `None`;
- `ledger_detail`: with `BacktestConfig(engine="ledger", collect_ledger_detail=True)`, the
  ordinary ledger's own per-interval vectors as `LedgerDetail` frames, otherwise `None`.
  `positions` (`timestamp, asset, quantity, price, notional, weight`) and `trades`
  (`timestamp, asset, side, quantity, price, notional, fee`) are stamped at the interval's
  start row `t_i`, the fill. `asset_attribution` (`timestamp, asset, price, quantity, weight,
  price_pnl, funding_pnl, fees`) has every interval × asset at its end row `t_{i+1}`, whose
  equity books that interval's price P&L, funding, and the `t_i` fill's fees; its cumulative
  sum from `initial_capital` reproduces equity to rounding. Timestamps are the input rows'
  (normalize to daily UTC labels yourself before publishing them). Capture copies values the
  loop already computes and does not change equity, returns, turnover, metrics, or
  `to_dataframe()`;
- `summary()`: human-readable metrics;
- `to_dataframe()`: the frozen persistence frame.

`to_dataframe()` prepends zero to each interval stream so all columns have `T` rows. Its columns
are frozen in this exact order:

```text
equity, benchmark_equity, price_return, funding_return,
cost_return, net_return, turnover
```

Persist engine identity and metrics separately rather than changing that dataframe schema:

```python
import json
from pathlib import Path

result.to_dataframe().write_parquet("backtest-result.parquet")
Path("backtest-metadata.json").write_text(
    json.dumps(
        {
            "metrics": dict(result.metrics),
            "engine_used": result.engine_used,
            "engine_meta": result.engine_meta,
        },
        indent=2,
    )
)
```

## Prepared Nautilus execution

Use this path only when the execution model is part of the experiment. Preparation binds the
original decision-time `StrategyWeights` to normalized bars, instrument metadata, reference
closes, an execution calendar, reporting times, optional funding settlements, and an execution
policy before Nautilus is constructed.

```python
from backtest import (
    BacktestConfig,
    prepare_execution_from_strategy_weights,
    run_backtest_from_strategy_weights,
)
from execution import ImmediateMarketPolicy

prepared = prepare_execution_from_strategy_weights(
    weights=strategy_weights,
    asset_instruments=asset_instruments,
    reference_prices=reference_prices,
    bars=bars,
    instrument_specs=instrument_specs,
    execution_calendar=execution_calendar,
    reporting_times=reporting_times,
    policy=ImmediateMarketPolicy(),
    funding_settlements=funding_settlements,
    initial_state=None,
)

result = run_backtest_from_strategy_weights(
    weights=strategy_weights,
    data=None,
    config=BacktestConfig(
        engine="nautilus",
        initial_capital=100_000.0,
        include_funding=True,
    ),
    prepared_execution=prepared,
)

execution = result.execution
assert execution is not None
```

Required prepared data:

| Input | Required form |
| --- | --- |
| `asset_instruments` | Mapping from each `StrategyWeights.assets` name to `execution.InstrumentKey` |
| `reference_prices` | `decision_at, instrument, observed_at, price`; one exact completed-close vector per decision |
| `bars` | `instrument, source_timestamp, ts_event, ts_init, open, high, low, close, volume` |
| `instrument_specs` | `execution.InstrumentSpec` for every instrument |
| `execution_calendar` | Strictly increasing UTC completed-close timestamps |
| `reporting_times` | Strictly increasing UTC account-report timestamps |
| `policy` | `ImmediateMarketPolicy`, `DelayedMarketPolicy`, or `TimeWeightedTakerPolicy` |
| `funding_settlements` | Optional `settlement_id, instrument, settled_at, rate, mark_price` |
| `initial_state` | Optional validated `InitialAccountState` matching configured starting equity |

Frame instrument identities use `VENUE:SYMBOL`, obtainable with `instrument_key_wire(key)`.
Prepared execution requires at least next-bar timing, exact UTC timestamps, complete policy-window
bars, and non-overlapping target windows. Semantic fingerprints reject stale weights or any changed
prepared economic/timing fact.

The prepared run uses pinned Nautilus Trader in a one-shot child process and returns immutable
targets, quantities, IOC intents/outcomes, actual fills and fees, holdings, account points, funding,
and shortfall. It is a deterministic bar-based taker simulation. It does **not** prove live exchange
connectivity, queue position, participation capacity, spread/impact, latency, disconnect recovery,
broker reconciliation, or strategy profitability.

## Deterministic OHLC resting limits

Use this path when a strategy decides at a completed bar close, rests a limit from the next bar,
and only OHLC bars are available. It is a conservative bar model, not a claim about intrabar
sequencing or queue position.

```python
from decimal import Decimal

from backtest import BacktestConfig, prepare_resting_limit_execution, run_resting_limit_backtest
from execution import RestingLimitOrder, RestingLimitPlan

plan = RestingLimitPlan(
    plan_id="btc-entry",
    orders=(
        RestingLimitOrder(
            order_id="buy-1",
            instrument=btc_key,
            quantity=Decimal("0.001"),
            limit_price=Decimal("42000"),
            activate_at=calendar[0],
            expires_at=calendar[-1],
        ),
    ),
    penetration_bps=Decimal("1"),
)
prepared = prepare_resting_limit_execution(
    plan=plan,
    bars=bars,
    instrument_specs=(btc_spec,),
    execution_calendar=calendar,
    reporting_times=calendar,
)
result = run_resting_limit_backtest(
    prepared=prepared,
    config=BacktestConfig(initial_capital=100_000, frequency="1m", metrics=[]),
)
execution = result.resting_limit_execution
```

The activation bar never fills. A buy fills from the next completed bar when
`low <= limit * (1 - penetration_bps / 10_000)`; sells use the symmetric high. Fills occur at the
submitted limit, with taker fees only when the eligible bar opens through it. Expiry is inclusive.
If both sides of an OCO pair touch without an open-through resolution, both are canceled as
ambiguous. The prepared fingerprint binds every plan, bar, spec, funding event, calendar, and
initial-state input.

The matcher cannot reconstruct queue position or an intrabar path. Treat fill assumptions as a
research sensitivity and report ambiguous OCO counts; do not describe these fills as observed
exchange executions.

## Parent-order execution simulator

Use `simulate_execution` to ask: for this asset and trade size, what does each execution policy
cost versus a fairly priced market order at the open? It works from 1-minute OHLCV bars (plus
bid/ask quotes when available) and returns per-order costs and fills as Polars frames. It does
not produce a `BacktestResult`. Callers load bars; the simulator does no lake I/O.

```python
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import polars as pl

from backtest import FillAssumptions, simulate_execution, summarize_execution
from execution import InstrumentKey, InstrumentSpec, ParentOrderPolicy

start = datetime(2026, 1, 1, tzinfo=UTC)
minutes = 8 * 60 + 2  # the longest policy needs an 8h window, the bar before it, and its deadline bar
bars = pl.DataFrame(
    {
        "asset": ["BTC"] * minutes,
        "timestamp": [start + timedelta(minutes=i) for i in range(minutes)],
        "open": [100.0] * minutes,
        "high": [100.2] * minutes,
        "low": [99.8] * minutes,
        "close": [100.0] * minutes,
        "volume": [50.0] * minutes,
    }
)
orders = pl.DataFrame(
    {
        "order_id": ["buy-1"],
        "asset": ["BTC"],
        "decision_at": [start + timedelta(seconds=30)],
        "side": [1],
        "notional": [10_000.0],
    }
)
spec = InstrumentSpec(
    key=InstrumentKey(venue="EXAMPLE", symbol="BTC-PERP"),
    product="perpetual",
    base_currency="BTC",
    quote_currency="USD",
    settlement_currency="USD",
    is_inverse=False,
    multiplier=Decimal("1"),
    price_increment=Decimal("0.01"),
    quantity_increment=Decimal("0.001"),
    min_quantity=Decimal("0.001"),
    max_quantity=Decimal("1000"),
    min_notional=Decimal("5"),
    max_notional=Decimal("10000000"),
    maker_fee_rate=Decimal("0.0001"),
    taker_fee_rate=Decimal("0.0005"),
)
policies = (
    ParentOrderPolicy(name="taker_now", style="market"),  # first = summary baseline
    ParentOrderPolicy(name="passive_fast", style="maker", horizon=timedelta(minutes=30)),
    ParentOrderPolicy(
        name="passive_slow",
        style="maker",
        horizon=timedelta(hours=8),
        child_interval=timedelta(minutes=30),
    ),
)
result = simulate_execution(
    bars=bars,
    orders=orders,
    specs={"BTC": spec},
    policies=policies,
    assumptions=FillAssumptions(assumed_spread_bps=1.0),  # bars carry no bid/ask
)
print(summarize_execution(result))
```

| Input | Required form |
| --- | --- |
| `bars` | `asset, timestamp, open, high, low, close, volume`; optional `trade_count` and `bid, ask` (both or neither, observed at bar close). One row per asset-minute; `timestamp` is the UTC bar open on an exact minute; sorted, unique; `volume` in base units. Include no-trade minutes explicitly (`trade_count == 0`, else `volume == 0`). |
| `orders` | `order_id` (unique), `asset`, `decision_at` (UTC), `side` (+1/-1), `notional` (quote currency) |
| `specs` | `execution.InstrumentSpec` per asset (tick, lot, minimums, maker/taker fees; multiplier 1) |
| `policies` | Required `execution.ParentOrderPolicy` values with unique names; the first is the default `summarize_execution` baseline |
| `assumptions` | `FillAssumptions(touch_fill_prob, participation, assumed_spread_bps, markout_minutes)` |
| `funding` | Optional `asset, timestamp, rate` settlements; positive rate means longs pay |

Policies are defined once in the execution core (`execution.ParentOrderPolicy`), and their
per-minute decisions (`execution.maker_child_lots`, `execution.maker_price`) are the same
functions a live executor would call; this simulator only decides fills from bars. Named presets belong in
an execution `policies` extension (`packages/execution/extensions/policies`).

Semantics:

- The arrival bar is the first bar at or after `decision_at`. Prices for bar t use only bar t-1:
  its bid/ask at close, or without quotes a tick-grid book at its close: the bid on the grid at
  or below `close - spread / 2` and the ask `spread` above it, where `spread` is
  `assumed_spread_bps` rounded to whole ticks (at least one). Costs are measured against the
  arrival bar's reference mid (the midpoint of that bid and ask).
- Target quantity is `notional / arrival_mid` rounded down to the lot; orders below venue
  minimums get `status="below_minimum"` and null costs.
- Market fills the whole target in the arrival bar at `max(open, ask_ref)` (buys; sells mirror),
  paying the taker fee.
- Maker splits the target into children every `child_interval` (each at least one lot and the
  venue minimum at its post price), posts post-only at the reference
  bid (`join`) or one tick better (`improve`), and re-pegs every `repeg_interval`. A post that
  would cross the open (a buy whose open is strictly below its price; sells mirror) is rejected
  for that minute; an open exactly at the price rests and can fill. Only new posts and re-pegs
  are checked (a rejected post is retried the next minute): a resting order whose bar opens
  through its price fills. A bar trading one tick through the price
  fills fully; a touch fills `touch_fill_prob`; fills are capped at `participation` of bar volume.
  At the deadline any remainder is bought at market (`at_deadline="market"`) or left unfilled.
- Every order window needs a complete 1-minute grid from the bar before arrival through the
  deadline bar; a missing minute raises. Markouts past the end of data are null.

Outputs: `result.fills` (one row per fill with price, liquidity, fee, and reference mid) and
`result.orders` (one row per order × policy) with status, quantities, maker share, average
price, participation, and costs in bps of `target_qty * arrival_mid`, positive = worse:
`fee_bps + spread_bps + drift_bps + unfilled_bps + funding_bps = total_bps`, plus
`markout_{h}m_bps` over maker fills (positive = good). `summarize_execution` aggregates per
policy and asset and reports the paired difference against the baseline policy with its
standard error.

Limitations:

- No queue position, order-book replay, or market impact; maker fills are optimistic.
- Fills are deterministic expected values, not random draws. Each fill is rounded down to the
  lot, so touch fills on children of only a few lots are understated (a 1-lot child never fills
  on a touch at `touch_fill_prob < 1`).
- Orders are simulated independently: no interaction or competition between orders.
- Bar volume is the only liquidity signal; taker fills are not capped (see `max_participation`).

## CLI

Write direct ordinary `prices`, `weights`, and optional `funding_rates` frames to Parquet, then run:

```bash
uv run --project packages/platform/backtest qf-backtest run \
  prices.parquet weights.parquet \
  --funding-rates funding.parquet \
  --engine ledger \
  --initial-capital 100000 \
  --trade-cost-bps 5 \
  --frequency daily \
  --benchmark BTC \
  --output result-summary.json \
  --pretty
```

Use `--no-include-funding` when appropriate. The command prints a JSON summary containing
`status`, `metrics`, `rows`, `engine_used`, and `engine_meta`; `--output` writes that same summary,
not the seven-column result frame. Failures emit JSON with `status="error"` and exit code `1`.

## Execution charts

Prepared results can render a single target/instrument execution PNG:

```python
from pathlib import Path
from backtest import render_execution_png

render_execution_png(
    execution=result.execution,
    bars=bars,
    instrument_spec=instrument_spec,
    output=Path("execution.png"),
)
```

The chart is for prepared execution only and shows candles, actual fills, price references, and
planned versus actual cumulative notional.

## Expanding universes with unheld missing prices (ledger opt-in)

Set `BacktestConfig(engine="ledger", allow_inactive_missing_prices=True,
benchmark="BTC")` and pass **wide** prices to the ordinary API or the
`StrategyWeights` connector. Wide prices preserve nulls; the legacy panel
converter forward-fills and is unsuitable when missing marks must stay explicit.

This mode allows a null/NaN risky price only where no effective position needs
it. Every nonzero target requires real finite positive prices at both ends of
its holding interval, including the exit mark when the next target is zero.
Thus new listings can have absent earlier histories without invented prices;
missing held marks still fail closed. Infinity and nonpositive observed risky
prices always fail. Benchmark prices must be complete, even when unheld. Weights,
funding and cash prices retain their ordinary finite-value contracts.

No prices are filled or clipped. Existing strict defaults and Nautilus behavior
are unchanged; this option is rejected for Nautilus. The final target is still
not traded. Strategy code remains responsible for causal eligibility and access.

## Supplemental risk reporting

`sortino_ratio(returns, periods_per_year=365)` computes a zero-target Sortino from
interval returns: `mean(r) / sqrt(mean(min(r, 0)**2)) * sqrt(periods_per_year)`.
All observations enter the downside denominator. Empty or zero-downside samples
return `None`. This follows [Sortino: A Sharper Ratio (CME / Red Rock)](https://www.cmegroup.com/education/files/rr-sortino-a-sharper-ratio.pdf).
The registered engine `sortino` metric uses this corrected denominator and retains
its `0.0` sentinel for undefined results.

`robust_sortino_ratio(returns, periods_per_year=365, upper_quantile=0.99)` clips
returns above their 99th percentile, leaves losses untouched, then applies `sortino_ratio`.
Sortino ignores upside variance, so a few spike days can carry it; the gap between the two
shows how much of the ratio depends on the top 1% of days.

`summarize_path_risk(equity, dates, periods_per_year=365)` returns Sortino over
successive observed NAV intervals, `robust_sortino`, `martin`, `longest_drawdown_days` and
`current_drawdown_days`. Pass a full-resolution path including its starting NAV;
the starting mark contributes no return observation. Dates must increase strictly.
Durations use elapsed calendar days from a peak through recovery (including an
equal high-water mark) or the final observation when still underwater. This is
observed duration, not a prediction of an unrecovered episode's recovery date.
Martin is calendar-day CAGR (`(last / first) ** (365 / elapsed_days) - 1`, zero
cash rate) divided by the Ulcer Index: RMS fractional drawdown over every NAV
observation, including the starting mark. Observations are equally weighted;
use a complete daily path for daily reporting. Unlike Sortino, its annualization
uses elapsed calendar days rather than `periods_per_year`. Missing elapsed time,
zero drawdown or a non-finite ratio returns `None`. This follows
[Peter Martin's Ulcer Performance Index](https://www.tangotools.com/ui/ui.htm).
Both helpers are public imports from `backtest`; they do not alter engine execution
or the persisted result frame. Ordinary engine metrics still use the configured
frequency factor (daily = 252); crypto reporting passes 365 explicitly.
