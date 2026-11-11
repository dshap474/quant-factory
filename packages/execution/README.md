# quant-factory-execution

Purpose: provide engine-neutral execution contracts for quant-factory.

Usage: import the curated `execution` surface to size one atomic portfolio
target, plan bounded market-taker slices, and reconcile immutable events.

This package owns immutable DTOs, deterministic target sizing and slice
policies, pure reconciliation identities, and the venue-neutral live
transition engine (see Live trading). It does not import Nautilus,
strategies, backtest, or provider loaders.

## Usage

```python
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from execution import (
    AccountSnapshot,
    DelayedMarketPolicy,
    ImmediateMarketPolicy,
    InstrumentKey,
    InstrumentSpec,
    PortfolioTarget,
    ReferencePrice,
    TargetWeight,
    TimeWeightedTakerPolicy,
    size_target_quantities,
)

utc = timezone.utc
instrument = InstrumentKey(venue="EXAMPLE", symbol="ASSET-QUOTE")
# Build InstrumentSpec, PortfolioTarget, AccountSnapshot, then:
# quantities = size_target_quantities(target, account, (spec,))
# intents = ImmediateMarketPolicy().plan(quantities)
```

## Scope

This package owns the engine-neutral execution layer: supported instrument metadata, atomic
portfolio targets, sequential quantity sizing, per-order quantity/notional validation, immediate,
delayed, and time-weighted taker policies, parent-order maker/market policies,
immutable execution events, funding/accounting
identities, and reconciliation helpers.

The StrategyWeights bridge and Nautilus adapter live in `packages/platform/backtest`. This package
must remain independent of strategies, backtest, Nautilus, and provider loaders.

The delivered contracts support provider-neutral linear instrument metadata, market-taker intent
planning, and explicit resting-limit/OCO plans for the deterministic OHLC model owned by
`packages/platform/backtest`. Concrete venue support and validation belong in an installation's `extensions/venues/` plug-ins; none ship.

## Live trading

`execution.transition.run_transition(venue, target_weight=..., dry_run=...)` is the one live
engine: authorize, lock, read venue truth, close any position, prove flat, re-size, open the
target, prove the result. Each venue is a plug-in implementing the small `Venue` protocol under
`extensions/venues/` (none ship); adding a venue
means adding one `Venue`, not a new engine. See `docs/architecture.md`.

## Signed fees

Fees use a signed cost convention throughout fills, account projections, and
shortfall: positive values are charges, negative values are rebates. Cash changes
by `-fee`; maker fee rates may be negative. Actual provider fees retain their sign,
including maker rebates, and must remain finite. Provider-specific
fee currency checks still apply.

## Parent-order policies

`ParentOrderPolicy` describes how one parent order is worked: `style="market"` (all at once), or
`style="maker"` — a post-only schedule that starts a child every `child_interval` over `horizon`,
prices it with `maker_price` (join the near touch, or improve one tick without crossing), sizes it
with `maker_child_lots` (remainder spread over the children left, never below one lot or the venue minimum),
re-pegs every `repeg_interval` (never if `None`), and at the deadline markets the remainder or leaves it.

These per-minute decisions are the one copy shared by `backtest.simulate_execution` (which decides
fills from 1-minute bars) and live executors (which get fills from the venue). Named presets belong
in an `extensions/policies` overlay. A venue works maker policies live through `execution.maker`;
a venue without maker support submits market IOC orders only.

## Resting-limit research contracts


`RestingLimitOrder` and `RestingLimitPlan` describe signed, full-fill resting orders without
claiming execution. The backtest package validates completed-bar activation, matches OHLC touches,
and returns `RestingLimitExecutionResult` using the shared `Fill` and accounting DTOs. These
contracts do not model partial fills, volume, queue position, spread, or tick-path ordering.
