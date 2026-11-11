"""Event-driven account ledger for canonical decision-time StrategyWeights.

USAGE:
    result = run_intent_ledger(
        market=event_prices, funding_rates=event_funding,
        decision_times=decision_times, decide=decide,
        config=BacktestConfig(engine="ledger", metrics=[]),
    )
    replay = run_intent_ledger(market=event_prices, decisions=result.decisions,
                               funding_rates=event_funding, config=config)
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from copy import copy, deepcopy
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from math import isfinite
from typing import TYPE_CHECKING, Any

import numpy as np
import polars as pl

from .config import BacktestConfig
from .errors import BacktestContractError, BacktestEngineExecutionError, BacktestUnsupportedFeatureError
from .inputs import _validate_timestamp_index
from .metrics import MetricContext, compute_metrics
from .result import BacktestResult
from .returns import compute_benchmark_equity

if TYPE_CHECKING:
    from strategies import AccountState, StrategyWeights

# --------------------------------------------------------------------------- #
# Public result contract
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class IntentLedgerResult:
    """Canonical backtest plus account, fill, and replayable decision evidence."""

    backtest: BacktestResult
    account: pl.DataFrame
    fills: tuple[dict[str, Any], ...]
    decisions: StrategyWeights
    asset_attribution: pl.DataFrame | None = None


# --------------------------------------------------------------------------- #
# Event and decision validation
# --------------------------------------------------------------------------- #


def _validate_events(
    market: pl.DataFrame,
    funding_rates: pl.DataFrame | None,
) -> tuple[list[str], np.ndarray, np.ndarray, list[datetime], list[str]]:
    if "timestamp" not in market.columns or "kind" not in market.columns:
        raise BacktestContractError("market requires timestamp and kind columns")
    _validate_timestamp_index(market, "timestamp", "market")
    if market.height < 2:
        raise BacktestContractError("market requires at least two events")
    assets = [name for name in market.columns if name not in {"timestamp", "kind"}]
    if not assets or "CASH" in assets:
        raise BacktestContractError("market requires risky asset columns and no CASH column")
    kinds = market.get_column("kind").to_list()
    if any(kind not in {"open", "close", "settlement"} for kind in kinds):
        raise BacktestContractError("market.kind must be open, close, or settlement")
    timestamps = market.get_column("timestamp").to_list()
    if any(ts.tzinfo is None for ts in timestamps):
        raise BacktestContractError("market timestamps must be timezone-aware")
    try:
        prices = market.select(assets).to_numpy().astype(np.float64)
    except (TypeError, ValueError) as exc:
        raise BacktestContractError("market prices must be numeric") from exc
    if np.isinf(prices).any() or np.any(np.isfinite(prices) & (prices <= 0)):
        raise BacktestContractError("observed market prices must be finite and positive")
    if funding_rates is None:
        funding = np.zeros_like(prices)
    else:
        if set(funding_rates.columns) != {"timestamp", *assets}:
            raise BacktestContractError("funding_rates must have timestamp and exact market assets")
        _validate_timestamp_index(funding_rates, "timestamp", "funding_rates")
        if not funding_rates.get_column("timestamp").equals(market.get_column("timestamp")):
            raise BacktestContractError("funding_rates timestamps must match market exactly")
        try:
            funding = funding_rates.select(assets).to_numpy().astype(np.float64)
        except (TypeError, ValueError) as exc:
            raise BacktestContractError("funding_rates must be numeric") from exc
        if np.isinf(funding).any():
            raise BacktestContractError("observed funding rates must be finite")
    return assets, prices, funding, timestamps, kinds


def _validate_lifecycle(
    events: Mapping[datetime, Sequence[str]] | None,
    timestamps: Sequence[datetime],
    assets: Sequence[str],
    name: str,
) -> dict[datetime, tuple[str, ...]]:
    known_times, known_assets = set(timestamps), set(assets)
    result: dict[datetime, tuple[str, ...]] = {}
    for ts, names in (events or {}).items():
        selected = tuple(names)
        if ts not in known_times or len(set(selected)) != len(selected) or set(selected) - known_assets:
            raise BacktestContractError(f"{name} requires event timestamps and unique market assets")
        result[ts] = selected
    return result


def _check_targets(targets: np.ndarray, cash: Any) -> None:
    if np.isnan(targets).any():
        if cash is not None:
            raise BacktestContractError("CASH must be null when any target is null")
    elif cash is None or not isfinite(float(cash)) or not np.isclose(
        float(targets.sum()) + float(cash), 1.0, rtol=0, atol=1e-6
    ):
        raise BacktestContractError("fully specified weights including CASH must sum to one")
    if np.isinf(targets).any():
        raise BacktestContractError("decision targets must be finite or null")


def _check_limits(limits: np.ndarray) -> None:
    if np.isinf(limits).any():
        raise BacktestContractError("quantity_limits must be finite or null")


def _check_quantities(quantities: np.ndarray, targets: np.ndarray, limits: np.ndarray, cash: Any) -> None:
    """Absolute final-quantity targets: one risky asset, finite, nonnegative, null weight/CASH/limit there."""
    numeric = ~np.isnan(quantities)
    if not numeric.any():
        return
    if len(quantities) != 1:
        raise BacktestContractError("quantity_targets support exactly one risky asset")
    if np.isinf(quantities).any() or (quantities[numeric] < 0).any():
        raise BacktestContractError("quantity_targets must be finite and nonnegative")
    if not np.isnan(targets[numeric]).all() or cash is not None:
        raise BacktestContractError("a numeric quantity target requires null weight target and null CASH")
    if not np.isnan(limits[numeric]).all():
        raise BacktestContractError("quantity_targets and quantity_limits cannot both be numeric on one asset")


def _aligned_row(frame: pl.DataFrame | None, timestamp: datetime, assets: list[str], name: str) -> np.ndarray:
    """One decision's aligned limit/quantity row by asset name; all-null when the frame is absent."""
    if frame is None:
        return np.full(len(assets), np.nan)
    if sorted(frame.columns) != sorted(["timestamp", *assets]):
        raise BacktestContractError(f"{name} columns must align to assets")
    if frame.height != 1 or frame.get_column("timestamp")[0] != timestamp:
        raise BacktestContractError(f"{name} timestamp must match decision")
    row = frame.row(0, named=True)
    return np.asarray([float(row[a]) if row[a] is not None else np.nan for a in assets])


def _decision_row(
    intent: StrategyWeights, timestamp: datetime, assets: list[str]
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Targets, limits and quantity targets of one accepted decision; positional in market order."""
    weights, limits_frame = intent.weights, intent.quantity_limits
    if intent.assets != assets or intent.cash_col != "CASH" or weights.height != 1:
        raise BacktestContractError("each decision must be one canonical StrategyWeights row over market assets")
    columns = weights.columns
    if (columns[0] != "timestamp" or columns[-1] != "CASH" or columns[1:-1] != assets
            or (limits_frame is not None and limits_frame.columns != ["timestamp", *assets])):
        return _decision_row_by_name(intent, timestamp, assets)
    row = weights.row(0)
    if row[0] != timestamp:
        raise BacktestContractError("decision timestamp must equal the account event timestamp")
    if intent.execution.derive_lag_bars() != 1:
        raise BacktestUnsupportedFeatureError("intent ledger requires ExecutionTiming.next_bar()")
    targets = np.asarray([float(value) if value is not None else np.nan for value in row[1:-1]])
    _check_targets(targets, row[-1])
    limits = np.full(len(assets), np.nan)
    if limits_frame is not None:
        if limits_frame.height != 1 or limits_frame.get_column("timestamp")[0] != timestamp:
            raise BacktestContractError("quantity_limits timestamp must match decision")
        limits = np.asarray([float(value) if value is not None else np.nan for value in limits_frame.row(0)[1:]])
        _check_limits(limits)
    quantities = _aligned_row(intent.quantity_targets, timestamp, assets, "quantity_targets")
    _check_quantities(quantities, targets, limits, row[-1])
    return targets, limits, quantities


def _decision_row_by_name(
    intent: StrategyWeights, timestamp: datetime, assets: list[str]
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if intent.assets != assets or intent.cash_col != "CASH" or intent.weights.height != 1:
        raise BacktestContractError("each decision must be one canonical StrategyWeights row over market assets")
    if intent.weights.get_column("timestamp")[0] != timestamp:
        raise BacktestContractError("decision timestamp must equal the account event timestamp")
    if intent.execution.derive_lag_bars() != 1:
        raise BacktestUnsupportedFeatureError("intent ledger requires ExecutionTiming.next_bar()")
    row = intent.weights.row(0, named=True)
    targets = np.asarray([float(row[a]) if row[a] is not None else np.nan for a in assets])
    _check_targets(targets, row["CASH"])
    limits = np.full(len(assets), np.nan)
    if intent.quantity_limits is not None:
        if intent.quantity_limits.columns != ["timestamp", *assets]:
            raise BacktestContractError("quantity_limits columns must align to assets")
        if intent.quantity_limits.height != 1 or intent.quantity_limits.get_column("timestamp")[0] != timestamp:
            raise BacktestContractError("quantity_limits timestamp must match decision")
        limit_row = intent.quantity_limits.row(0, named=True)
        limits = np.asarray([float(limit_row[a]) if limit_row[a] is not None else np.nan for a in assets])
        _check_limits(limits)
    quantities = _aligned_row(intent.quantity_targets, timestamp, assets, "quantity_targets")
    _check_quantities(quantities, targets, limits, row["CASH"])
    return targets, limits, quantities


def _stored(one: StrategyWeights) -> StrategyWeights:
    """Private copy of an accepted decision; its fields already passed __post_init__ and validate()."""
    stored = copy(one)
    stored.weights, stored.assets = one.weights.clone(), list(one.assets)
    stored.metadata = deepcopy(one.metadata)
    stored.quantity_limits = one.quantity_limits.clone() if one.quantity_limits is not None else None
    stored.quantity_targets = one.quantity_targets.clone() if one.quantity_targets is not None else None
    return stored


DECISION_CHUNK = 256  # accepted decisions per fold of the combined artifact
QUANTITY_CASH_TOLERANCE = 1e-9  # relative to pre-fill NAV: ordinary floating-point residue of the affordable clip


def _quantity_fill(
    quantities: np.ndarray, held: np.ndarray, quote: np.ndarray, cash: float, nav: float, cost_bps: float,
    assets: list[str], ts: datetime,
) -> tuple[np.ndarray, dict[str, float]]:
    """Final quantity for a frozen absolute target: reduce to it, or buy at most the fee-affordable difference."""
    if (held < 0).any():
        raise BacktestUnsupportedFeatureError("quantity_targets do not support a short holding")
    if cash < -QUANTITY_CASH_TOLERANCE * max(1.0, nav):
        raise BacktestUnsupportedFeatureError("quantity_targets do not support negative cash (no borrowing)")
    cash = max(cash, 0.0)
    proposed = held.copy()
    (j,) = np.flatnonzero(~np.isnan(quantities))
    target = float(quantities[j])
    if target != held[j]:
        if not isfinite(quote[j]):
            raise BacktestContractError(f"missing executable quote at {ts}")
        if target < held[j]:
            proposed[j] = target
        else:
            affordable = cash / (float(quote[j]) * (1.0 + cost_bps / 10_000))
            proposed[j] = held[j] + min(target - held[j], affordable)
    return proposed, {assets[j]: target}


# --------------------------------------------------------------------------- #
# Replay of a validated decision artifact
# --------------------------------------------------------------------------- #


def _replay_rows(
    decisions: StrategyWeights, assets: list[str]
) -> list[tuple[np.ndarray, np.ndarray, np.ndarray] | None] | None:
    """Per-row (targets, limits, quantities) of an entry-validated canonical Float64 artifact; None replays row by row.

    Slicing a validated artifact cannot change a row's timestamps, columns, nulls or finiteness, so
    only the sums are re-checked: the one-row Python sum of ``validate()`` and the numpy sum of
    ``_decision_row``. A row failing either is None and goes through the per-row path at its
    event, which raises the exact error there.
    """
    weights, limits_frame, quantity_frame = decisions.weights, decisions.quantity_limits, decisions.quantity_targets
    schema = weights.schema

    def aligned(frame: pl.DataFrame | None) -> bool:
        return frame is None or (frame.columns == ["timestamp", *assets]
                                 and all(dtype == pl.Float64 for dtype in frame.dtypes[1:]))

    if not (decisions.assets == assets and decisions.cash_col == "CASH"
            and decisions.execution.derive_lag_bars() == 1
            and all(schema[name] == pl.Float64 for name in (*assets, "CASH"))
            and aligned(limits_frame) and aligned(quantity_frame)):
        return None
    targets = np.ascontiguousarray(weights.select(assets).to_numpy(), dtype=np.float64)
    cash = weights.get_column("CASH").to_list()
    limits = (None if limits_frame is None
              else np.ascontiguousarray(limits_frame.select(assets).to_numpy(), dtype=np.float64))
    quantities = (None if quantity_frame is None
                  else np.ascontiguousarray(quantity_frame.select(assets).to_numpy(), dtype=np.float64))
    rows: list[tuple[np.ndarray, np.ndarray, np.ndarray] | None] = []
    for k, cash_k in enumerate(cash):
        target = targets[k]
        limit = np.full(len(assets), np.nan) if limits is None else limits[k]
        quantity = np.full(len(assets), np.nan) if quantities is None else quantities[k]
        if cash_k is not None and abs(float(sum(target.tolist()) + cash_k) - 1.0) > 1e-6:
            rows.append(None)
            continue
        try:
            _check_targets(target, cash_k)
            _check_limits(limit)
            _check_quantities(quantity, target, limit, cash_k)
        except BacktestContractError:
            rows.append(None)
            continue
        rows.append((target, limit, quantity))
    return rows


def _replay_decisions(decisions: StrategyWeights) -> StrategyWeights:
    """The replayed artifact, equal to concatenating its accepted one-row copies."""
    return replace(
        decisions, weights=decisions.weights.rechunk(), assets=list(decisions.assets),
        metadata=deepcopy(decisions.metadata),
        quantity_limits=decisions.quantity_limits.rechunk() if decisions.quantity_limits is not None else None,
        quantity_targets=decisions.quantity_targets.rechunk() if decisions.quantity_targets is not None else None,
        observed_through=decisions.observed_through.rechunk() if decisions.observed_through is not None else None,
    )


def _attribution_frame(days: list[tuple[Any, ...]], assets: list[str]) -> pl.DataFrame:
    """One frame equal to concatenating the per-day [timestamp, asset, marks, cash flows] frames."""
    n, k = len(assets), len(days)
    names = ("price", "quantity", "weight", "price_pnl", "funding_pnl", "fees")
    return pl.DataFrame({
        "timestamp": pl.Series("timestamp", [day[0] for day in days]).gather(np.repeat(np.arange(k), n)),
        "asset": pl.Series("asset", assets).gather(np.tile(np.arange(n), k)),
        **{name: np.concatenate([day[j + 1] for day in days]) for j, name in enumerate(names)},
    }).with_columns(pl.col("price").fill_nan(None))


# --------------------------------------------------------------------------- #
# Stateful ledger
# --------------------------------------------------------------------------- #


def run_intent_ledger(
    *,
    market: pl.DataFrame,
    funding_rates: pl.DataFrame | None = None,
    decision_times: Sequence[datetime] | None = None,
    decide: Callable[[datetime, AccountState], StrategyWeights] | None = None,
    decisions: StrategyWeights | None = None,
    forced_exits: Mapping[datetime, Sequence[str]] | None = None,
    relisted_at: Mapping[datetime, Sequence[str]] | None = None,
    config: BacktestConfig | None = None,
    collect_attribution: bool = False,
) -> IntentLedgerResult:
    """Execute sparse decisions on the next event using actual quantities.

    ``market`` is a sorted wide event grid with timestamp, kind, and risky asset
    prices. ``funding_rates`` supplies the decimal charge for each event, not an
    annualized rate. A decision at event i fills at event i+1. Callback and replay
    use the same fill/accounting path; exactly one input mode is required.
    The callback receives the marked account as ``strategies.AccountState``.
    ``collect_attribution`` adds daily UTC asset marks and actual price/funding/
    fee cash flows, without changing execution. Missing flat-asset prices remain null.
    A numeric ``quantity_targets`` value (one risky asset, long/cash) requests that absolute
    final quantity: reductions sell the difference; increases buy at most the difference and
    at most ``cash / (quote * (1 + fee))``. The fill then records ``requested_quantities``.
    """
    from strategies import AccountState, StrategyWeights

    cfg = config or BacktestConfig(engine="ledger")
    if cfg.engine != "ledger":
        raise BacktestUnsupportedFeatureError("intent ledger requires engine='ledger'")
    if cfg.rebalance_every_bars != 1 or cfg.allow_inactive_missing_prices:
        raise BacktestUnsupportedFeatureError("intent ledger does not use ordinary ledger rebalance or missing-price modes")
    if cfg.collect_ledger_detail:
        raise BacktestUnsupportedFeatureError("collect_ledger_detail is ordinary-ledger only; use collect_attribution")
    if cfg.metrics:
        raise BacktestUnsupportedFeatureError(
            "intent ledger event intervals are irregular; pass metrics=[] and compute reporting-period metrics separately"
        )
    if (decide is None) == (decisions is None):
        raise BacktestContractError("provide exactly one of decide or decisions")
    assets, prices, funding, timestamps, kinds = _validate_events(market, funding_rates)
    exits = _validate_lifecycle(forced_exits, timestamps, assets, "forced_exits")
    releases = _validate_lifecycle(relisted_at, timestamps, assets, "relisted_at")
    timestamp_to_index = {ts: i for i, ts in enumerate(timestamps)}
    if decisions is not None:
        decisions.validate()
        planned = decisions.weights.get_column("timestamp").to_list()
        if decision_times is not None and list(decision_times) != planned:
            raise BacktestContractError("decision_times must match replay artifact")
        decision_times = planned
    if decision_times is None or not decision_times:
        raise BacktestContractError("at least one decision timestamp is required")
    if list(decision_times) != sorted(set(decision_times)) or any(ts not in timestamp_to_index for ts in decision_times):
        raise BacktestContractError("decision_times must be unique sorted market timestamps")
    if decision_times[-1] == timestamps[-1]:
        raise BacktestContractError("last decision has no next event for execution")
    decision_set = set(decision_times)
    replay_rows = {ts: i for i, ts in enumerate(decision_times)}

    n = len(assets)
    column = {name: j for j, name in enumerate(assets)}
    cash = float(cfg.initial_capital)
    quantity = np.zeros(n)
    last_mark = np.full(n, np.nan)
    blocked: set[str] = set()
    pending: tuple[datetime, np.ndarray, np.ndarray, np.ndarray] | None = None
    account_rows: list[dict[str, Any]] = []
    fills: list[dict[str, Any]] = []
    # Accepted decisions, folded into one combined artifact every DECISION_CHUNK so a long
    # wide run never holds thousands of one-row frames; concat of the folds equals concat of all.
    first_decision: StrategyWeights | None = None
    decision_folds: list[StrategyWeights] = []
    decision_chunk: list[StrategyWeights] = []
    n_accepted = 0
    price_pnl_rows: list[float] = []
    funding_pnl_rows: list[float] = []
    fee_rows: list[float] = []
    traded_rows: list[float] = []
    attribution_days: list[tuple[Any, ...]] = []
    daily_price, daily_funding, daily_fees = (np.zeros(n) for _ in range(3))
    # Replay of a validated canonical artifact reads its rows once instead of slicing each one.
    replay = _replay_rows(decisions, assets) if decisions is not None else None
    finite_prices, finite_funding = np.isfinite(prices), np.isfinite(funding)

    for i, (ts, quote, rates) in enumerate(zip(timestamps, prices, funding, strict=True)):
        for name in releases.get(ts, ()):
            blocked.discard(name)
        blocked.update(exits.get(ts, ()))
        held = quantity != 0
        if (held & ~finite_prices[i]).any():
            raise BacktestContractError(f"missing held mark at {ts}")
        held_quantity, held_quote = quantity[held], quote[held]
        if i == 0:
            price_pnl = 0.0
        else:
            if (held & ~finite_prices[i - 1]).any():
                raise BacktestContractError(f"missing previous held mark at {ts}")
            move = held_quote - last_mark[held]
            price_pnl = float(np.dot(held_quantity, move))
        if cfg.include_funding:
            if (held & ~finite_funding[i]).any():
                raise BacktestContractError(f"missing held funding at {ts}")
            held_rates = rates[held]
            funding_pnl = -float(np.dot(held_quantity * held_quote, held_rates))
        else:
            funding_pnl = 0.0
        if collect_attribution:
            if i:
                daily_price[held] += held_quantity * move
            if cfg.include_funding:
                daily_funding[held] -= held_quantity * held_quote * held_rates
        cash += funding_pnl
        pre_nav = float(cash + np.dot(held_quantity, held_quote))
        pre_gross = float(np.abs(held_quantity * held_quote).sum())
        if not isfinite(pre_nav) or pre_nav <= 0:
            raise BacktestEngineExecutionError(f"intent ledger equity exhausted at {ts}")

        due = pending is not None
        exit_names = set(exits.get(ts, ()))
        requested: dict[str, float] | None = None
        if pending is not None:
            decision_ts, targets, limits, quantities = pending
            pending = None
            proposed = quantity.copy()
            numeric = np.isfinite(targets)
            is_blocked = np.zeros(n, dtype=bool)
            is_blocked[[column[name] for name in blocked]] = True
            capped = np.isfinite(limits)
            # A blocked asset, a zero cap, or a cap without a same-signed holding needs no quote.
            closing = capped & ((limits == 0) | (quantity == 0) | (np.sign(limits) != np.sign(quantity)))
            required = numeric & (targets != 0) & ~(is_blocked | closing)
            if np.any(required & ~np.isfinite(quote)):
                raise BacktestContractError(f"missing executable quote at {ts}")
            proposed[numeric] = targets[numeric] * pre_nav / np.where(required[numeric], quote[numeric], 1.0)
            # A cap keeps at most min(|current|, |cap|, |requested|) on the held side; otherwise flat.
            side = np.sign(quantity)
            keep = capped & (quantity != 0) & (side == np.sign(limits)) & (np.sign(limits) == np.sign(proposed))
            bound = np.minimum(np.minimum(np.abs(quantity), np.abs(limits)), np.abs(proposed))
            proposed = np.where(keep, side * bound, np.where(capped, 0.0, proposed))
            # Forced exit/blocking takes precedence: a blocked asset's quantity target is not executed.
            quantities = np.where(is_blocked, np.nan, quantities)
            if not np.isnan(quantities).all():
                proposed, requested = _quantity_fill(quantities, quantity, quote, cash, pre_nav,
                                                     cfg.trade_cost_bps, assets, ts)
            proposed[is_blocked] = 0.0
            fill_kind = "rebalance"
        elif exit_names and any(quantity[column[name]] != 0 for name in exit_names):
            decision_ts = None
            proposed = quantity.copy()
            proposed[[column[name] for name in exit_names]] = 0.0
            fill_kind = "forced_exit"
        else:
            proposed = None
            decision_ts = None
            fill_kind = "none"

        if proposed is None:
            # No order: the change is identically zero, so traded, fee and the cash debit are exact zeros.
            traded_dollars = 0.0
            fee = traded_dollars * cfg.trade_cost_bps / 10_000
            cash -= 0.0 + fee
        else:
            change = proposed - quantity
            active = change != 0
            if np.any(active & ~np.isfinite(quote)):
                raise BacktestContractError(f"missing executable quote at {ts}")
            traded_dollars = float(np.abs(change[active] * quote[active]).sum())
            fee = traded_dollars * cfg.trade_cost_bps / 10_000
            if collect_attribution:
                daily_fees[active] += np.abs(change[active] * quote[active]) * cfg.trade_cost_bps / 10_000
            cash -= float(np.dot(change[active], quote[active])) + fee
            quantity = proposed
        nav = pre_nav - fee
        if not isfinite(nav) or nav <= 0 or not isfinite(cash):
            raise BacktestEngineExecutionError(f"intent ledger fill exhausted equity at {ts}")
        if requested is not None and cash < -QUANTITY_CASH_TOLERANCE * max(1.0, pre_nav):
            raise BacktestEngineExecutionError(f"quantity target fill left negative cash at {ts}")
        notionals = np.zeros(n)
        if proposed is None:
            notionals[held] = held_quantity * held_quote
        else:
            if due or fill_kind == "forced_exit":
                record = dict(kind=fill_kind, decision=decision_ts, timestamp=ts, pre_fee_nav=pre_nav,
                              fee_dollars=fee, traded_dollars=traded_dollars, post_fee_nav=nav,
                              trades={assets[j]: float(change[j] * quote[j]) for j in np.flatnonzero(active)},
                              quantities=dict(zip(assets, quantity.tolist(), strict=True)))
                if requested is not None:
                    record["requested_quantities"] = requested
                fills.append(record)
            held = quantity != 0
            notionals[held] = quantity[held] * quote[held]
        long = float(notionals[notionals > 0].sum())
        short = float(-notionals[notionals < 0].sum())
        account_rows.append(
            dict(timestamp=ts, kind=kinds[i], nav_pre=pre_nav,
                 gross_pre=pre_gross, nav=nav, cash=cash, gross=long + short,
                 long=long, short=short, funding=funding_pnl, fee=fee,
                 traded=traded_dollars, held=int(held.sum()))
        )
        if i:
            price_pnl_rows.append(price_pnl)
            funding_pnl_rows.append(funding_pnl)
            fee_rows.append(fee)
            traded_rows.append(traded_dollars)
        elif funding_pnl != 0 or fee != 0:
            raise BacktestContractError("first event cannot charge funding or trade")
        last_mark = quote  # a row of prices, which is never written
        if collect_attribution and (
            i == len(timestamps) - 1
            or timestamps[i + 1].astimezone(UTC).date() != ts.astimezone(UTC).date()
        ):
            attribution_days.append((
                ts.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0), quote.copy(),
                quantity.copy(), notionals / nav, daily_price.copy(), daily_funding.copy(), daily_fees.copy(),
            ))
            daily_price.fill(0)
            daily_funding.fill(0)
            daily_fees.fill(0)

        if ts in decision_set:
            if pending is not None:
                raise BacktestContractError("new decision arrived before previous decision filled")
            replayed = replay[replay_rows[ts]] if replay is not None else None
            if replayed is not None:
                pending = (ts, *replayed)
                continue
            if decide is None:
                assert decisions is not None
                one = decisions.slice(replay_rows[ts], 1)
            else:
                state = AccountState(
                    timestamp=ts, nav=nav, cash=cash,
                    quantities=dict(zip(assets, quantity.tolist(), strict=True)),
                    weights=dict(zip(assets, (notionals / nav).tolist(), strict=True)),
                )
                one = decide(ts, state)
            if not isinstance(one, StrategyWeights):
                raise BacktestContractError("decision callback must return canonical StrategyWeights")
            one.validate()
            one = _stored(one)
            target, limit, requested_quantity = _decision_row(one, ts, assets)
            first = first_decision or one
            if (one.execution, one.metadata, one.strategy_id, one.version) != (
                first.execution, first.metadata, first.strategy_id, first.version
            ):
                raise BacktestContractError("all decisions must share execution timing, metadata and identity")
            pending = (ts, target, limit, requested_quantity)
            first_decision = first
            decision_chunk.append(one)
            n_accepted += 1
            if len(decision_chunk) == DECISION_CHUNK:
                decision_folds.append(StrategyWeights.concat(decision_chunk))
                decision_chunk = []

    if pending is not None:
        raise BacktestContractError("last decision was not filled")
    if replay is not None:
        assert decisions is not None
        combined = _replay_decisions(decisions)
        n_decisions = len(decision_times)
    else:
        if decision_chunk:
            decision_folds.append(StrategyWeights.concat(decision_chunk))
        combined = StrategyWeights.concat(decision_folds)
        n_decisions = n_accepted
    equity = np.asarray([row["nav"] for row in account_rows], dtype=np.float64)
    pre_equity = equity[:-1]
    price_return = np.asarray(price_pnl_rows) / pre_equity
    funding_return = np.asarray(funding_pnl_rows) / pre_equity
    cost_return = np.asarray(fee_rows) / pre_equity
    net_return = equity[1:] / pre_equity - 1.0
    turnover = np.asarray(traded_rows) / pre_equity
    benchmark = compute_benchmark_equity(
        prices_df=market, asset_cols=assets, initial_capital=cfg.initial_capital,
        benchmark=cfg.benchmark or cfg.benchmark_asset,
    )
    benchmark_values = benchmark.to_numpy().astype(np.float64)
    metrics = compute_metrics(
        MetricContext(
            equity=equity, net_return=net_return, price_return=price_return,
            benchmark_return=np.diff(benchmark_values) / benchmark_values[:-1],
            funding_return=funding_return, cost_return=cost_return, turnover=turnover,
            frequency=cfg.frequency,
        ),
        list(cfg.metrics),
    )
    backtest = BacktestResult(
        equity=pl.Series("equity", equity), benchmark_equity=benchmark,
        price_return=pl.Series("price_return", price_return),
        funding_return=pl.Series("funding_return", funding_return),
        cost_return=pl.Series("cost_return", cost_return),
        net_return=pl.Series("net_return", net_return),
        turnover=pl.Series("turnover", turnover), metrics=metrics,
        engine_used="ledger", engine_meta={"accounting": "intent_ledger", "rows": len(timestamps),
                                           "decisions": n_decisions},
    )
    return IntentLedgerResult(backtest, pl.DataFrame(account_rows), tuple(fills), combined,
                              _attribution_frame(attribution_days, assets) if collect_attribution else None)
