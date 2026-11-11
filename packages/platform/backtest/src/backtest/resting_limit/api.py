"""Public preparation and execution boundary for deterministic resting limits.

Purpose: validate explicit resting plans against completed OHLC bars, bind a
semantic fingerprint, run the pure matcher, and reuse shared accounting/reporting.

USAGE:
    >>> from backtest import prepare_resting_limit_execution  # doctest: +SKIP
    >>> prepared = prepare_resting_limit_execution(...)  # doctest: +SKIP
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Mapping, Sequence

import polars as pl

from execution import (
    FundingSettlement,
    InitialAccountState,
    InstrumentKey,
    InstrumentSpec,
    RestingLimitExecutionResult,
    RestingLimitPlan,
    validate_order_limits,
)

from ..config import BacktestConfig, get_annualization_factor
from ..errors import BacktestContractError, BacktestEngineExecutionError
from ..preparation.data import validate_bars, validate_funding_settlements
from ..preparation.fingerprint import (
    canonical_decimal,
    canonical_value,
    funding_settlement_payload,
    instrument_spec_payload,
    instrument_wire,
    sha256_payload,
    validate_sha256,
)
from ..preparation.initial_state import initial_state_payload
from ..preparation.validation import validate_strictly_increasing_utc
from ..projection import LinearPerpetualProjection, build_result_streams, replay_reporting
from ..result import BacktestResult
from .matcher import match_resting_limit_orders

# --------------------------------------------------------------------------- #
# Prepared input
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class PreparedRestingLimitInput:
    """Validated, normalized, fingerprinted input for the OHLC matcher."""

    plan: RestingLimitPlan
    bars: pl.DataFrame
    instrument_specs: tuple[InstrumentSpec, ...]
    funding_settlements: tuple[FundingSettlement, ...]
    reporting_times: tuple[datetime, ...]
    execution_calendar: tuple[datetime, ...]
    prepared_payload_sha256: str
    initial_state: InitialAccountState | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.plan, RestingLimitPlan):
            raise TypeError("plan must be RestingLimitPlan")
        if not isinstance(self.bars, pl.DataFrame):
            raise TypeError("bars must be a polars DataFrame")
        object.__setattr__(self, "instrument_specs", tuple(self.instrument_specs))
        object.__setattr__(self, "funding_settlements", tuple(self.funding_settlements))
        object.__setattr__(self, "reporting_times", tuple(self.reporting_times))
        object.__setattr__(self, "execution_calendar", tuple(self.execution_calendar))
        validate_sha256(self.prepared_payload_sha256, "prepared_payload_sha256")
        if self.initial_state is not None and not isinstance(self.initial_state, InitialAccountState):
            raise TypeError("initial_state must be InitialAccountState or None")


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def prepare_resting_limit_execution(
    *,
    plan: RestingLimitPlan,
    bars: pl.DataFrame,
    instrument_specs: Sequence[InstrumentSpec],
    execution_calendar: Sequence[datetime],
    reporting_times: Sequence[datetime],
    funding_settlements: pl.DataFrame | None = None,
    initial_state: InitialAccountState | None = None,
) -> PreparedRestingLimitInput:
    """Validate and fingerprint a resting plan without matching any order."""
    try:
        return _prepare(
            plan=plan,
            bars=bars,
            instrument_specs=instrument_specs,
            execution_calendar=execution_calendar,
            reporting_times=reporting_times,
            funding_settlements=funding_settlements,
            initial_state=initial_state,
        )
    except BacktestContractError:
        raise
    except (TypeError, ValueError, InvalidOperation, pl.exceptions.PolarsError) as exc:
        raise BacktestContractError(str(exc)) from exc


def prepared_resting_limit_fingerprint(prepared: PreparedRestingLimitInput) -> str:
    """Recompute the semantic fingerprint for one prepared resting input."""
    if not isinstance(prepared, PreparedRestingLimitInput):
        raise BacktestContractError("prepared must be PreparedRestingLimitInput")
    return _fingerprint(
        plan=prepared.plan,
        bars=prepared.bars,
        instrument_specs=prepared.instrument_specs,
        funding_settlements=prepared.funding_settlements,
        reporting_times=prepared.reporting_times,
        execution_calendar=prepared.execution_calendar,
        initial_state=prepared.initial_state,
    )


def run_resting_limit_backtest(
    *,
    prepared: PreparedRestingLimitInput,
    config: BacktestConfig,
) -> BacktestResult:
    """Run the deterministic OHLC path and return shared BacktestResult streams."""
    if not isinstance(prepared, PreparedRestingLimitInput):
        raise BacktestContractError("prepared must be PreparedRestingLimitInput")
    if not isinstance(config, BacktestConfig):
        raise BacktestContractError("config must be BacktestConfig")
    if not config.include_funding:
        raise BacktestContractError(
            "resting-limit execution rejects include_funding=False; explicit funding settlements must be applied"
        )
    get_annualization_factor(config.frequency)
    if prepared_resting_limit_fingerprint(prepared) != prepared.prepared_payload_sha256:
        raise BacktestContractError("prepared resting-limit payload fingerprint mismatch")

    specs = {spec.key: spec for spec in prepared.instrument_specs}
    try:
        matched = match_resting_limit_orders(
            plan=prepared.plan,
            bar_rows=prepared.bars.to_dicts(),
            instrument_specs=specs,
            execution_calendar=prepared.execution_calendar,
        )
        marks_history = _marks_history(prepared.bars, specs=specs, calendar=prepared.execution_calendar)
        projection = LinearPerpetualProjection(
            initial_cash=(
                prepared.initial_state.cash
                if prepared.initial_state is not None
                else Decimal(str(config.initial_capital))
            ),
            instruments=specs,
            initial_state=prepared.initial_state,
        )
        all_holdings, all_accounts = replay_reporting(
            projection,
            marks=marks_history,
            funding=prepared.funding_settlements,
            fills=matched.fills,
            reporting_times=prepared.execution_calendar,
        )
    except (TypeError, ValueError) as exc:
        raise BacktestEngineExecutionError(f"resting-limit execution failed: {exc}") from exc

    report_set = set(prepared.reporting_times)
    holdings = tuple(point for point in all_holdings if point.timestamp in report_set)
    account_path = tuple(point for point in all_accounts if point.timestamp in report_set)
    execution = RestingLimitExecutionResult(
        plan=prepared.plan,
        outcomes=matched.outcomes,
        fills=matched.fills,
        holdings=holdings,
        account_path=account_path,
        funding_settlements=prepared.funding_settlements,
        initial_state=prepared.initial_state,
        ambiguous_double_touch_count=matched.ambiguous_double_touch_count,
    )
    streams = build_result_streams(
        account_path=account_path,
        fills=matched.fills,
        marks_history=marks_history,
        reporting_times=prepared.reporting_times,
        config=config,
        instrument_specs=specs,
    )
    return BacktestResult(
        equity=streams.equity,
        benchmark_equity=streams.benchmark_equity,
        price_return=streams.price_return,
        funding_return=streams.funding_return,
        cost_return=streams.cost_return,
        net_return=streams.net_return,
        turnover=streams.turnover,
        metrics=streams.metrics,
        engine_used="resting_limit",
        engine_meta={
            "execution_model": "deterministic_ohlc_resting_limit",
            "prepared_payload_sha256": prepared.prepared_payload_sha256,
            "ambiguous_double_touch_count": matched.ambiguous_double_touch_count,
        },
        resting_limit_execution=execution,
    )


# --------------------------------------------------------------------------- #
# Preparation pipeline
# --------------------------------------------------------------------------- #


def _prepare(
    *,
    plan: RestingLimitPlan,
    bars: pl.DataFrame,
    instrument_specs: Sequence[InstrumentSpec],
    execution_calendar: Sequence[datetime],
    reporting_times: Sequence[datetime],
    funding_settlements: pl.DataFrame | None,
    initial_state: InitialAccountState | None,
) -> PreparedRestingLimitInput:
    if not isinstance(plan, RestingLimitPlan):
        raise BacktestContractError("plan must be RestingLimitPlan")
    normalized_plan = RestingLimitPlan(
        plan_id=plan.plan_id,
        orders=tuple(sorted(plan.orders, key=lambda order: order.order_id)),
        penetration_bps=plan.penetration_bps,
    )
    ordered_keys = tuple(sorted({order.instrument for order in normalized_plan.orders}, key=lambda key: key.sort_key()))
    specs = _validate_specs(instrument_specs, ordered_keys)
    spec_by_key = {spec.key: spec for spec in specs}
    wire_to_key = {instrument_wire(key): key for key in ordered_keys}
    calendar = validate_strictly_increasing_utc(execution_calendar, "execution_calendar")
    if len(calendar) < 2:
        raise BacktestContractError("execution_calendar must contain at least two completed bars")
    reporting = validate_strictly_increasing_utc(reporting_times, "reporting_times")
    if not set(reporting) <= set(calendar):
        raise BacktestContractError("reporting_times must be a subset of execution_calendar")
    if reporting[0] != calendar[0] or reporting[-1] != calendar[-1]:
        raise BacktestContractError("reporting_times must include the first and last execution-calendar timestamps")

    validated_bars, closes = validate_bars(bars, set(wire_to_key))
    calendar_series = pl.Series("execution_calendar", calendar, dtype=pl.Datetime("us", "UTC"))
    normalized_bars = validated_bars.filter(pl.col("ts_init").dt.cast_time_unit("us").is_in(calendar_series.implode()))
    _validate_complete_bar_coverage(normalized_bars, wires=set(wire_to_key), calendar=calendar)
    funding = validate_funding_settlements(
        funding_settlements,
        known_wires=set(wire_to_key),
        wire_to_key=wire_to_key,
    )
    if any(item.settled_at not in set(calendar) for item in funding):
        raise BacktestContractError("funding settlement timestamps must belong to execution_calendar")

    eligible_at = _validate_orders(
        normalized_plan,
        calendar=calendar,
        closes=closes,
        specs=spec_by_key,
    )
    _validate_non_overlapping_windows(normalized_plan, eligible_at=eligible_at)
    validated_initial_state = _validate_initial_state(
        initial_state,
        calendar=calendar,
        closes=closes,
        specs=spec_by_key,
    )
    values = {
        "plan": normalized_plan,
        "bars": normalized_bars,
        "instrument_specs": specs,
        "funding_settlements": funding,
        "reporting_times": reporting,
        "execution_calendar": calendar,
        "initial_state": validated_initial_state,
    }
    return PreparedRestingLimitInput(
        **values,
        prepared_payload_sha256=_fingerprint(**values),
    )


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #


def _validate_specs(
    instrument_specs: Sequence[InstrumentSpec],
    ordered_keys: Sequence[InstrumentKey],
) -> tuple[InstrumentSpec, ...]:
    specs = tuple(instrument_specs)
    if any(not isinstance(spec, InstrumentSpec) for spec in specs):
        raise BacktestContractError("instrument_specs must contain InstrumentSpec values")
    by_key = {spec.key: spec for spec in specs}
    if len(by_key) != len(specs):
        raise BacktestContractError("instrument_specs contain duplicate instruments")
    if set(by_key) != set(ordered_keys):
        raise BacktestContractError("instrument_specs must cover plan instruments exactly")
    if any(spec.product != "perpetual" or spec.is_inverse for spec in specs):
        raise BacktestContractError("resting-limit execution supports linear perpetual instruments only")
    return tuple(by_key[key] for key in ordered_keys)


def _validate_complete_bar_coverage(
    bars: pl.DataFrame,
    *,
    wires: set[str],
    calendar: Sequence[datetime],
) -> None:
    actual = {(str(row["instrument"]), row["ts_init"]) for row in bars.select("instrument", "ts_init").to_dicts()}
    expected = {(wire, timestamp) for wire in wires for timestamp in calendar}
    if actual != expected:
        missing = expected - actual
        sample = next(iter(sorted(missing, key=lambda item: (item[0], item[1]))), None)
        detail = f": {sample[0]} @ {sample[1].isoformat()}" if sample is not None else ""
        raise BacktestContractError(f"bars must cover every plan instrument at every execution-calendar close{detail}")


def _validate_orders(
    plan: RestingLimitPlan,
    *,
    calendar: Sequence[datetime],
    closes: Mapping[tuple[str, datetime], Decimal],
    specs: Mapping[InstrumentKey, InstrumentSpec],
) -> dict[str, datetime]:
    calendar_index = {timestamp: index for index, timestamp in enumerate(calendar)}
    eligible_at: dict[str, datetime] = {}
    for order in plan.orders:
        activation_index = calendar_index.get(order.activate_at)
        if activation_index is None:
            raise BacktestContractError(f"order {order.order_id!r} activate_at must belong to execution_calendar")
        if activation_index + 1 >= len(calendar):
            raise BacktestContractError(f"order {order.order_id!r} activation has no later eligible bar")
        if order.expires_at not in calendar_index:
            raise BacktestContractError(f"order {order.order_id!r} expires_at must belong to execution_calendar")
        first_eligible = calendar[activation_index + 1]
        if order.expires_at < first_eligible:
            raise BacktestContractError(f"order {order.order_id!r} expires before its first eligible bar")
        eligible_at[order.order_id] = first_eligible

        spec = specs[order.instrument]
        if order.quantity % spec.quantity_increment != 0:
            raise BacktestContractError(f"order {order.order_id!r} quantity must align to quantity_increment")
        if order.limit_price % spec.price_increment != 0:
            raise BacktestContractError(f"order {order.order_id!r} limit_price must align to price_increment")
        validate_order_limits(order_quantity=order.quantity, price=order.limit_price, spec=spec)
        close = closes[(instrument_wire(order.instrument), order.activate_at)]
        if order.quantity > 0 and order.limit_price >= close:
            raise BacktestContractError(f"buy order {order.order_id!r} is marketable at its activation close")
        if order.quantity < 0 and order.limit_price <= close:
            raise BacktestContractError(f"sell order {order.order_id!r} is marketable at its activation close")
    return eligible_at


def _validate_non_overlapping_windows(
    plan: RestingLimitPlan,
    *,
    eligible_at: Mapping[str, datetime],
) -> None:
    windows: dict[InstrumentKey, dict[str, tuple[datetime, datetime]]] = {}
    for order in plan.orders:
        identity = f"oco:{order.oco_group_id}" if order.oco_group_id is not None else f"order:{order.order_id}"
        windows.setdefault(order.instrument, {})[identity] = (eligible_at[order.order_id], order.expires_at)
    for instrument, instrument_windows in windows.items():
        ordered = sorted(instrument_windows.items(), key=lambda item: (item[1][0], item[0]))
        for previous, current in zip(ordered, ordered[1:], strict=False):
            if current[1][0] <= previous[1][1]:
                raise BacktestContractError(
                    f"overlapping resting-order windows for {instrument_wire(instrument)}: "
                    f"{previous[0]} and {current[0]}"
                )


def _validate_initial_state(
    state: InitialAccountState | None,
    *,
    calendar: Sequence[datetime],
    closes: Mapping[tuple[str, datetime], Decimal],
    specs: Mapping[InstrumentKey, InstrumentSpec],
) -> InitialAccountState | None:
    if state is None:
        return None
    if not isinstance(state, InitialAccountState):
        raise BacktestContractError("initial_state must be InitialAccountState or None")
    if state.as_of != calendar[0]:
        raise BacktestContractError("initial_state.as_of must equal the first execution-calendar timestamp")
    if not {position.instrument for position in state.positions} <= set(specs):
        raise BacktestContractError("initial positions must belong to plan instruments")
    marks = {mark.instrument: mark for mark in state.marks}
    for position in state.positions:
        spec = specs[position.instrument]
        mark = marks[position.instrument]
        if mark.price != closes[(instrument_wire(position.instrument), state.as_of)]:
            raise BacktestContractError("initial marks must equal completed closes at initial_state.as_of")
        if position.quantity % spec.quantity_increment != 0:
            raise BacktestContractError("initial position must align to quantity_increment")
        if abs(position.quantity) > spec.max_quantity:
            raise BacktestContractError("initial position exceeds max_quantity")
        if abs(position.quantity * mark.price * spec.multiplier) > spec.max_notional:
            raise BacktestContractError("initial position exceeds max_notional")
    return state


# --------------------------------------------------------------------------- #
# Fingerprint and reporting primitives
# --------------------------------------------------------------------------- #


def _fingerprint(
    *,
    plan: RestingLimitPlan,
    bars: pl.DataFrame,
    instrument_specs: Sequence[InstrumentSpec],
    funding_settlements: Sequence[FundingSettlement],
    reporting_times: Sequence[datetime],
    execution_calendar: Sequence[datetime],
    initial_state: InitialAccountState | None,
) -> str:
    payload = {
        "model": "deterministic_ohlc_resting_limit_v1",
        "plan": {
            "plan_id": plan.plan_id,
            "penetration_bps": canonical_decimal(plan.penetration_bps),
            "orders": [
                {
                    "order_id": order.order_id,
                    "instrument": instrument_wire(order.instrument),
                    "quantity": canonical_decimal(order.quantity),
                    "limit_price": canonical_decimal(order.limit_price),
                    "activate_at": canonical_value(order.activate_at),
                    "expires_at": canonical_value(order.expires_at),
                    "oco_group_id": order.oco_group_id,
                }
                for order in plan.orders
            ],
        },
        "bars": [{name: canonical_value(value) for name, value in sorted(row.items())} for row in bars.to_dicts()],
        "instrument_specs": [instrument_spec_payload(spec) for spec in instrument_specs],
        "funding_settlements": [funding_settlement_payload(item) for item in funding_settlements],
        "reporting_times": [canonical_value(value) for value in reporting_times],
        "execution_calendar": [canonical_value(value) for value in execution_calendar],
        "initial_state": initial_state_payload(initial_state),
    }
    return sha256_payload(payload)


def _marks_history(
    bars: pl.DataFrame,
    *,
    specs: Mapping[InstrumentKey, InstrumentSpec],
    calendar: Sequence[datetime],
) -> tuple[tuple[datetime, dict[InstrumentKey, Decimal]], ...]:
    wire_to_key = {instrument_wire(key): key for key in specs}
    by_time: dict[datetime, dict[InstrumentKey, Decimal]] = {timestamp: {} for timestamp in calendar}
    for row in bars.select("instrument", "ts_init", "close").to_dicts():
        by_time[row["ts_init"]][wire_to_key[str(row["instrument"])]] = Decimal(str(row["close"]))
    return tuple((timestamp, by_time[timestamp]) for timestamp in calendar)


__all__ = [
    "PreparedRestingLimitInput",
    "prepare_resting_limit_execution",
    "prepared_resting_limit_fingerprint",
    "run_resting_limit_backtest",
]
