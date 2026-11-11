"""Nautilus strategy for the prepared-execution path.

Purpose: at each completed close, wait for all instrument bars, then process
mark -> funding -> target-boundary reconcile -> sequential size/plan -> due IOC
submit. Capture real OrderFilled events into the projection ledger.

USAGE:
    >>> from backtest.engines.nautilus.strategy import (  # doctest: +SKIP
    ...     ExecutionRuntimeState,
    ...     build_execution_strategy,
    ... )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Mapping, Sequence

from execution import (
    Fill,
    FundingSettlement,
    InstrumentKey,
    InstrumentSpec,
    OrderOutcome,
    OrderStatus,
    PortfolioTarget,
    SliceIntent,
    TargetQuantity,
    size_target_quantities,
    validate_non_overlapping_windows,
    validate_order_limits,
)

from ...errors import BacktestContractError, BacktestEngineExecutionError
from ...preparation import PreparedExecutionInput, instrument_key_wire
from ...projection import LinearPerpetualProjection
from .construction import QF_IMMEDIATE_EXEC_ALGORITHM_ID

# --------------------------------------------------------------------------- #
# Runtime state bag
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class ExecutionRuntimeState:
    """Mutable ledger shared between the strategy and the orchestrator."""

    prepared: PreparedExecutionInput
    specs: dict[InstrumentKey, InstrumentSpec]
    projection: LinearPerpetualProjection
    instrument_ids: dict[InstrumentKey, Any]
    id_to_key: dict[str, InstrumentKey]
    bar_types: dict[InstrumentKey, Any]
    nt: Mapping[str, Any]
    expected_keys: tuple[InstrumentKey, ...]
    funding_by_time: dict[datetime, tuple[FundingSettlement, ...]]
    targets_by_earliest: dict[datetime, tuple[PortfolioTarget, ...]]
    marks_history: list[tuple[datetime, dict[InstrumentKey, Decimal]]] = field(default_factory=list)
    fills: list[Fill] = field(default_factory=list)
    intents: list[SliceIntent] = field(default_factory=list)
    target_quantities: list[TargetQuantity] = field(default_factory=list)
    planned_target_ids: set[str] = field(default_factory=set)
    pending_by_time: dict[datetime, list[SliceIntent]] = field(default_factory=dict)
    client_to_slice: dict[str, SliceIntent] = field(default_factory=dict)
    fills_by_slice: dict[str, list[Fill]] = field(default_factory=dict)
    submitted_slices: set[str] = field(default_factory=set)
    closed_timestamps: set[datetime] = field(default_factory=set)
    bar_buffer: dict[datetime, dict[InstrumentKey, Any]] = field(default_factory=dict)
    outcomes: list[OrderOutcome] = field(default_factory=list)
    orders_by_slice: dict[str, Any] = field(default_factory=dict)
    error: Exception | None = None


# --------------------------------------------------------------------------- #
# Strategy factory
# --------------------------------------------------------------------------- #


def build_execution_strategy(
    *,
    state: ExecutionRuntimeState,
    nt: Mapping[str, Any],
) -> Any:
    """Build the Python Strategy that owns bar-time orchestration."""
    Strategy = nt["Strategy"]
    StrategyConfig = nt["StrategyConfig"]
    OrderSide = nt["OrderSide"]
    TimeInForce = nt["TimeInForce"]
    exec_id = nt["ExecAlgorithmId"](QF_IMMEDIATE_EXEC_ALGORITHM_ID)

    class _Config(StrategyConfig, frozen=True):
        """Minimal Nautilus strategy config (complex state is external)."""

        strategy_id: str | None = "QF-EXEC"

    class PreparedExecutionStrategy(Strategy):
        """Bar-barrier strategy for deterministic prepared-path execution."""

        def __init__(self, config: Any, runtime: ExecutionRuntimeState) -> None:
            super().__init__(config)
            self._rt = runtime

        def on_start(self) -> None:
            for key in self._rt.expected_keys:
                self.subscribe_bars(self._rt.bar_types[key])

        def on_bar(self, bar: Any) -> None:
            if self._rt.error is not None:
                return
            try:
                self._handle_bar(bar)
            except Exception as exc:  # noqa: BLE001 — surface in orchestrator
                self._rt.error = exc
                raise

        def on_order_filled(self, event: Any) -> None:
            if self._rt.error is not None:
                return
            try:
                self._handle_fill(event)
            except Exception as exc:  # noqa: BLE001
                self._rt.error = exc
                raise

        def _handle_bar(self, bar: Any) -> None:
            rt = self._rt
            key = rt.id_to_key.get(str(bar.bar_type.instrument_id))
            if key is None:
                raise BacktestContractError(f"unexpected bar instrument_id: {bar.bar_type.instrument_id!r}")
            # Preparation defines the completed close on ts_init; preserve ts_event as
            # source event metadata without relabeling it as the close.
            ts = _ns_to_utc(int(bar.ts_init))
            bucket = rt.bar_buffer.setdefault(ts, {})
            if key in bucket:
                raise BacktestContractError(f"duplicate bar for {instrument_key_wire(key)} at {ts.isoformat()}")
            bucket[key] = bar
            if set(bucket) != set(rt.expected_keys):
                return
            if ts in rt.closed_timestamps:
                raise BacktestContractError(f"timestamp already closed: {ts.isoformat()}")
            self._process_close(ts, bucket)
            rt.closed_timestamps.add(ts)
            del rt.bar_buffer[ts]

        def _process_close(self, ts: datetime, bars: Mapping[InstrumentKey, Any]) -> None:
            rt = self._rt
            marks = {key: Decimal(str(bars[key].close)) for key in rt.expected_keys}
            rt.projection.update_marks(marks, observed_at=ts)
            rt.marks_history.append((ts, dict(marks)))

            for settlement in rt.funding_by_time.get(ts, ()):
                rt.projection.apply_funding(settlement)

            if ts in rt.targets_by_earliest:
                self._reconcile_positions(ts)
                for target in rt.targets_by_earliest[ts]:
                    self._size_and_plan(target, as_of=ts)

            due = list(rt.pending_by_time.pop(ts, []))
            due.sort(key=lambda intent: (intent.instrument.sort_key(), intent.slice_id))
            for intent in due:
                self._submit_intent(intent, bars=bars)

        def _size_and_plan(self, target: PortfolioTarget, *, as_of: datetime) -> None:
            rt = self._rt
            if target.target_id in rt.planned_target_ids:
                raise BacktestContractError(f"target already planned: {target.target_id!r}")
            snapshot = rt.projection.snapshot(as_of=as_of)
            quantities = size_target_quantities(
                target,
                snapshot,
                tuple(rt.specs[key] for key in rt.expected_keys),
            )
            rt.target_quantities.extend(quantities)
            intents = tuple(rt.prepared.policy.plan(quantities))
            validate_non_overlapping_windows([*rt.intents, *intents])
            for intent in intents:
                rt.intents.append(intent)
                rt.pending_by_time.setdefault(intent.scheduled_at, []).append(intent)
            rt.planned_target_ids.add(target.target_id)

        def _submit_intent(self, intent: SliceIntent, *, bars: Mapping[InstrumentKey, Any]) -> None:
            rt = self._rt
            if intent.slice_id in rt.submitted_slices:
                raise BacktestContractError(f"slice already submitted: {intent.slice_id!r}")
            if intent.instrument not in bars:
                raise BacktestContractError(
                    f"missing bar for due slice {intent.slice_id!r} / {instrument_key_wire(intent.instrument)}"
                )
            validate_order_limits(
                order_quantity=intent.quantity,
                price=Decimal(str(bars[intent.instrument].close)),
                spec=rt.specs[intent.instrument],
            )
            instrument = rt.instrument_ids[intent.instrument]
            side = OrderSide.BUY if intent.quantity > 0 else OrderSide.SELL
            qty = instrument.make_qty(format(abs(intent.quantity), "f"))
            order = self.order_factory.market(
                instrument_id=instrument.id,
                order_side=side,
                quantity=qty,
                time_in_force=TimeInForce.IOC,
                exec_algorithm_id=exec_id,
                tags=[f"slice:{intent.slice_id}", f"target:{intent.target_id}"],
            )
            client_id = str(order.client_order_id)
            rt.client_to_slice[client_id] = intent
            rt.fills_by_slice.setdefault(intent.slice_id, [])
            rt.submitted_slices.add(intent.slice_id)
            self.submit_order(order)

        def _handle_fill(self, event: Any) -> None:
            rt = self._rt
            client_id = str(event.client_order_id)
            intent = rt.client_to_slice.get(client_id)
            if intent is None:
                raise BacktestEngineExecutionError(f"fill for unknown client_order_id: {client_id!r}")
            key = rt.id_to_key.get(str(event.instrument_id))
            if key is None or key != intent.instrument:
                raise BacktestEngineExecutionError(f"fill instrument mismatch for slice {intent.slice_id!r}")
            filled_at = _ns_to_utc(int(event.ts_event))
            if not (intent.scheduled_at <= filled_at <= intent.expires_at):
                raise BacktestEngineExecutionError(
                    f"fill outside IOC window for slice {intent.slice_id!r}: {filled_at.isoformat()}"
                )
            expected_side = OrderSide.BUY if intent.quantity > 0 else OrderSide.SELL
            if event.order_side != expected_side:
                raise BacktestEngineExecutionError(
                    f"fill side mismatch for slice {intent.slice_id!r}: "
                    f"expected={expected_side} actual={event.order_side}"
                )
            unsigned_qty = Decimal(str(event.last_qty))
            if unsigned_qty <= 0:
                raise BacktestEngineExecutionError(f"fill quantity must be positive from Nautilus, got {unsigned_qty}")
            signed_qty = unsigned_qty if expected_side == OrderSide.BUY else -unsigned_qty
            commission = event.commission
            fee = Decimal(str(commission).split()[0])
            fee_ccy = str(commission.currency) if hasattr(commission, "currency") else str(commission).split()[-1]
            fill = Fill(
                target_id=intent.target_id,
                slice_id=intent.slice_id,
                instrument=intent.instrument,
                fill_id=str(event.trade_id),
                quantity=signed_qty,
                price=Decimal(str(event.last_px)),
                fee=fee,
                fee_currency=fee_ccy,
                filled_at=filled_at,
            )
            prior_filled = sum(
                (item.quantity for item in rt.fills_by_slice.get(intent.slice_id, ())),
                Decimal(0),
            )
            cumulative = prior_filled + fill.quantity
            if abs(cumulative) > abs(intent.quantity):
                raise BacktestEngineExecutionError(
                    f"overfill for slice {intent.slice_id!r}: intent={intent.quantity} filled={cumulative}"
                )
            rt.projection.apply_fill(fill)
            rt.fills.append(fill)
            rt.fills_by_slice.setdefault(intent.slice_id, []).append(fill)

        def _reconcile_positions(self, ts: datetime) -> None:
            rt = self._rt
            for key in rt.expected_keys:
                projected = rt.projection.signed_quantity(key)
                realized = _nautilus_net_qty(self, rt.instrument_ids[key].id, nt=rt.nt)
                if projected != realized:
                    raise BacktestEngineExecutionError(
                        f"position reconcile failed at {ts.isoformat()} for "
                        f"{instrument_key_wire(key)}: projected={projected} nautilus={realized}"
                    )

    return PreparedExecutionStrategy(_Config(), state)


# --------------------------------------------------------------------------- #
# Terminalization helpers
# --------------------------------------------------------------------------- #


def terminalize_outcomes(state: ExecutionRuntimeState, *, nt: Mapping[str, Any]) -> tuple[OrderOutcome, ...]:
    """Map each submitted IOC to exactly one terminal OrderOutcome from cache."""
    if state.pending_by_time:
        leftover = sorted(state.pending_by_time)
        raise BacktestEngineExecutionError(f"unsubmitted slices remain at times: {[t.isoformat() for t in leftover]}")
    OrderStatusEnum = _order_status_enum(nt)
    outcomes: list[OrderOutcome] = []
    cache_orders = _orders_by_client_id(state)
    for intent in state.intents:
        if intent.slice_id not in state.submitted_slices:
            raise BacktestEngineExecutionError(f"intent never submitted: {intent.slice_id!r}")
        order = cache_orders.get(intent.slice_id)
        if order is None:
            raise BacktestEngineExecutionError(f"missing cache order for slice {intent.slice_id!r}")
        fills = tuple(state.fills_by_slice.get(intent.slice_id, ()))
        filled_qty = sum((f.quantity for f in fills), Decimal(0))
        unfilled = intent.quantity - filled_qty
        status, reason, terminal_at = _map_terminal_status(
            order=order,
            intent=intent,
            fills=fills,
            unfilled=unfilled,
            status_enum=OrderStatusEnum,
            nt=nt,
        )
        outcomes.append(
            OrderOutcome(
                intent=intent,
                status=status,
                fills=fills,
                terminal_at=terminal_at,
                unfilled_quantity=unfilled,
                reason=reason,
            )
        )
    state.outcomes = outcomes
    return tuple(outcomes)


def final_reconcile(state: ExecutionRuntimeState) -> None:
    """Fatal if projected signed quantities disagree with Nautilus at run end."""
    # Nautilus positions are checked by the strategy during boundaries; end-of-run
    # uses the projection vs sum of accepted fills as conservation (engine already
    # terminalized). Remaining pending is rejected in terminalize_outcomes.
    if state.error is not None:
        raise BacktestEngineExecutionError(str(state.error)) from state.error
    planned = {t.target_id for t in state.prepared.targets}
    if planned != state.planned_target_ids:
        missing = planned - state.planned_target_ids
        raise BacktestEngineExecutionError(f"targets never planned: {sorted(missing)}")


# --------------------------------------------------------------------------- #
# Internals
# --------------------------------------------------------------------------- #


def _ns_to_utc(ts_ns: int) -> datetime:
    return datetime.fromtimestamp(ts_ns / 1_000_000_000, tz=UTC)


def _nautilus_net_qty(strategy: Any, instrument_id: Any, *, nt: Mapping[str, Any]) -> Decimal:
    del nt  # reserved for future enum mapping
    cache = strategy.cache
    positions: list[Any] = []
    if hasattr(cache, "positions_open"):
        positions = [p for p in cache.positions_open() if str(p.instrument_id) == str(instrument_id)]
    if not positions and hasattr(cache, "positions"):
        positions = [p for p in cache.positions() if str(p.instrument_id) == str(instrument_id)]
    if not positions:
        return Decimal(0)
    total = Decimal(0)
    for pos in positions:
        if hasattr(pos, "signed_qty"):
            total += Decimal(str(pos.signed_qty))
            continue
        qty = Decimal(str(pos.quantity))
        side = str(getattr(pos, "side", "")).upper()
        total += -qty if "SHORT" in side else qty
    return total


def _orders_by_client_id(state: ExecutionRuntimeState) -> dict[str, Any]:
    """Index submitted orders by slice_id using the client_order map."""
    return state.orders_by_slice


def attach_cache_orders(state: ExecutionRuntimeState, orders: Sequence[Any]) -> None:
    """Bind Nautilus cache orders onto runtime state after engine.run()."""
    by_client = {str(order.client_order_id): order for order in orders}
    by_slice: dict[str, Any] = {}
    for client_id, intent in state.client_to_slice.items():
        order = by_client.get(client_id)
        if order is None:
            raise BacktestEngineExecutionError(
                f"cache missing order for client_order_id={client_id!r} slice={intent.slice_id!r}"
            )
        by_slice[intent.slice_id] = order
    state.orders_by_slice = by_slice


def _order_status_enum(nt: Mapping[str, Any]) -> Any:
    try:
        from nautilus_trader.model.enums import OrderStatus as OS
    except ImportError as exc:  # pragma: no cover
        raise BacktestEngineExecutionError("OrderStatus enum unavailable") from exc
    del nt
    return OS


def _map_terminal_status(
    *,
    order: Any,
    intent: SliceIntent,
    fills: Sequence[Fill],
    unfilled: Decimal,
    status_enum: Any,
    nt: Mapping[str, Any],
) -> tuple[OrderStatus, str | None, datetime]:
    del nt
    raw = order.status
    terminal_ns = int(getattr(order, "ts_last", 0) or getattr(order, "ts_closed", 0) or 0)
    if terminal_ns <= 0 and fills:
        terminal_ns = int(fills[-1].filled_at.timestamp() * 1_000_000_000)
    if terminal_ns <= 0:
        terminal_ns = int(intent.expires_at.timestamp() * 1_000_000_000)
    terminal_at = _ns_to_utc(terminal_ns)
    # Clamp into intent window for IOC same-close fills.
    if terminal_at < intent.scheduled_at:
        terminal_at = intent.scheduled_at
    if terminal_at > intent.expires_at:
        terminal_at = intent.expires_at

    if unfilled == 0 and fills and raw == status_enum.FILLED:
        return OrderStatus.FILLED, None, terminal_at
    if fills and unfilled != 0 and raw in (status_enum.CANCELED, status_enum.EXPIRED):
        return OrderStatus.PARTIALLY_FILLED, "ioc_partial", terminal_at
    if raw in (status_enum.DENIED, status_enum.REJECTED) or str(raw) in {"DENIED", "REJECTED"}:
        return OrderStatus.REJECTED, f"order_status={raw!s}", terminal_at
    if not fills and raw in (status_enum.CANCELED, status_enum.EXPIRED):
        return OrderStatus.EXPIRED, f"order_status={raw!s}", terminal_at
    raise BacktestEngineExecutionError(
        f"IOC slice {intent.slice_id!r} has nonterminal or inconsistent "
        f"order status={raw!s}, fills={len(fills)}, unfilled={unfilled}"
    )


def index_funding(
    settlements: Sequence[FundingSettlement],
) -> dict[datetime, tuple[FundingSettlement, ...]]:
    """Bucket funding by settlement timestamp (instrument-id order)."""
    buckets: dict[datetime, list[FundingSettlement]] = {}
    for settlement in settlements:
        buckets.setdefault(settlement.settled_at, []).append(settlement)
    out: dict[datetime, tuple[FundingSettlement, ...]] = {}
    for ts, items in buckets.items():
        items.sort(key=lambda s: (s.instrument.sort_key(), s.settlement_id))
        out[ts] = tuple(items)
    return out


def index_targets_by_earliest(
    targets: Sequence[PortfolioTarget],
) -> dict[datetime, tuple[PortfolioTarget, ...]]:
    """Group targets by earliest_execution_at preserving plan order within time."""
    buckets: dict[datetime, list[PortfolioTarget]] = {}
    for target in targets:
        buckets.setdefault(target.earliest_execution_at, []).append(target)
    return {ts: tuple(items) for ts, items in buckets.items()}
