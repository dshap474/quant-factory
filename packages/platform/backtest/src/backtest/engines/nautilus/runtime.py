"""Orchestrate one real Nautilus BacktestEngine for prepared execution.

Purpose: construct venue/instruments/bars/algo/strategy from PreparedExecutionInput,
run the simulation, terminalize IOC outcomes, and assemble BacktestResult.

USAGE:
    >>> from backtest.engines.nautilus.runtime import run_prepared_execution  # doctest: +SKIP
    >>> result = run_prepared_execution(prepared=prepared, config=cfg)  # doctest: +SKIP
"""

from __future__ import annotations

import pickle
import subprocess
import sys
from decimal import Decimal
from typing import Any

import polars as pl

from execution import InstrumentKey, InstrumentSpec

from ...config import BacktestConfig
from ...errors import BacktestContractError, BacktestEngineExecutionError
from ...preparation import PreparedExecutionInput, instrument_key_wire
from ...projection import LinearPerpetualProjection
from ...result import BacktestResult
from .assembly import assemble_backtest_result
from .construction import (
    build_bar,
    build_crypto_perpetual,
    build_immediate_ioc_exec_algorithm,
    calendar_last_bar_type,
    import_nautilus_bundle,
)
from .initial_state import seed_initial_positions
from .strategy import (
    ExecutionRuntimeState,
    attach_cache_orders,
    build_execution_strategy,
    final_reconcile,
    index_funding,
    index_targets_by_earliest,
    terminalize_outcomes,
)

# --------------------------------------------------------------------------- #
# Public entry
# --------------------------------------------------------------------------- #


def run_isolated_prepared_execution(
    *,
    prepared: PreparedExecutionInput,
    config: BacktestConfig,
) -> BacktestResult:
    """Run one prepared engine in a child process that exits after cleanup."""
    completed = subprocess.run(
        [sys.executable, "-m", "backtest.engines.nautilus.worker"],
        input=pickle.dumps((prepared, config)),
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        diagnostic = completed.stderr.decode(errors="replace")[-4000:]
        raise BacktestEngineExecutionError(
            f"isolated Nautilus worker exited with code {completed.returncode}: {diagnostic}"
        )
    try:
        succeeded, payload = pickle.loads(completed.stdout)  # noqa: S301 - trusted local child
    except Exception as exc:  # noqa: BLE001 - malformed child output is a runtime failure
        raise BacktestEngineExecutionError("isolated Nautilus worker returned an invalid response") from exc
    if not succeeded:
        sys.stderr.buffer.write(completed.stderr)
        sys.stderr.buffer.flush()
        error_kind, detail = payload
        if error_kind == "contract":
            raise BacktestContractError(str(detail))
        raise BacktestEngineExecutionError(str(detail))
    if not isinstance(payload, BacktestResult):
        raise BacktestEngineExecutionError("isolated Nautilus worker returned an invalid result")
    return payload


def run_prepared_execution(
    *,
    prepared: PreparedExecutionInput,
    config: BacktestConfig,
) -> BacktestResult:
    """Run the opt-in prepared Nautilus path and return BacktestResult + execution."""
    if not isinstance(prepared, PreparedExecutionInput):
        raise BacktestContractError("prepared must be PreparedExecutionInput")
    if config.include_funding is False:
        raise BacktestContractError(
            "prepared execution path rejects include_funding=False; explicit funding settlements must be applied"
        )

    nt = import_nautilus_bundle()
    specs = _spec_map(prepared.instrument_specs)
    expected_keys = tuple(sorted(specs, key=lambda key: key.sort_key()))
    _validate_funding_barriers(prepared, expected_keys=expected_keys)
    projection = LinearPerpetualProjection(
        initial_cash=(
            prepared.initial_state.cash if prepared.initial_state is not None else Decimal(str(config.initial_capital))
        ),
        instruments=specs,
        initial_state=prepared.initial_state,
    )

    instruments: dict[InstrumentKey, Any] = {}
    bar_types: dict[InstrumentKey, Any] = {}
    id_to_key: dict[str, InstrumentKey] = {}
    for key in expected_keys:
        instrument = build_crypto_perpetual(specs[key], nt=nt)
        instruments[key] = instrument
        bar_types[key] = calendar_last_bar_type(
            instrument.id,
            prepared.execution_calendar,
            nt=nt,
        )
        id_to_key[str(instrument.id)] = key

    state = ExecutionRuntimeState(
        prepared=prepared,
        specs=specs,
        projection=projection,
        instrument_ids=instruments,
        id_to_key=id_to_key,
        bar_types=bar_types,
        nt=nt,
        expected_keys=expected_keys,
        funding_by_time=index_funding(prepared.funding_settlements),
        targets_by_earliest=index_targets_by_earliest(prepared.targets),
    )

    engine = nt["BacktestEngine"](
        config=nt["BacktestEngineConfig"](
            trader_id=nt["TraderId"]("QF-EXEC-001"),
            logging=nt["LoggingConfig"](log_level="ERROR"),
        )
    )
    try:
        engine.add_venue(
            venue=nt["Venue"]("BINANCE"),
            oms_type=nt["OmsType"].NETTING,
            account_type=nt["AccountType"].MARGIN,
            base_currency=nt["USDT"],
            starting_balances=[
                nt["Money"](
                    prepared.initial_state.cash if prepared.initial_state is not None else config.initial_capital,
                    nt["USDT"],
                )
            ],
            default_leverage=Decimal("10"),
            bar_execution=True,
            use_random_ids=False,
            liquidity_consumption=False,
            fee_model=nt["MakerTakerFeeModel"](),
            fill_model=nt["BestPriceFillModel"](),
        )
        for key in expected_keys:
            engine.add_instrument(instruments[key])
        seed_initial_positions(
            engine,
            state=prepared.initial_state,
            instruments=instruments,
            nt=nt,
        )

        bars = _build_all_bars(prepared.bars, instruments=instruments, bar_types=bar_types, nt=nt)
        engine.add_data(bars)
        engine.add_exec_algorithm(build_immediate_ioc_exec_algorithm(nt=nt))
        strategy = build_execution_strategy(state=state, nt=nt)
        engine.add_strategy(strategy)
        engine.run()

        if state.error is not None:
            raise BacktestEngineExecutionError(str(state.error)) from state.error

        attach_cache_orders(state, list(engine.cache.orders()))
        # Final position reconcile against cache.
        _reconcile_end(state, engine=engine)
        outcomes = terminalize_outcomes(state, nt=nt)
        final_reconcile(state)
        return assemble_backtest_result(
            state=state,
            outcomes=outcomes,
            config=config,
            nautilus_version=str(nt["nautilus_version"]),
        )
    except BacktestContractError:
        raise
    except BacktestEngineExecutionError:
        raise
    except Exception as exc:
        raise BacktestEngineExecutionError(f"prepared Nautilus run failed: {exc}") from exc
    finally:
        _cleanup_engine(engine, primary_error=sys.exc_info()[1])


def _cleanup_engine(engine: Any, *, primary_error: BaseException | None) -> None:
    """Attempt orderly end and disposal without masking an active failure."""
    failures: list[str] = []
    for stage in ("end", "dispose"):
        try:
            getattr(engine, stage)()
        except Exception as exc:  # noqa: BLE001 — cleanup must attempt both stages
            failures.append(f"{stage}: {exc}")
    if not failures:
        return
    detail = f"Nautilus cleanup failed during {'; '.join(failures)}"
    if primary_error is not None:
        primary_error.add_note(detail)
        return
    raise BacktestEngineExecutionError(detail)


# --------------------------------------------------------------------------- #
# Construction helpers
# --------------------------------------------------------------------------- #


def _spec_map(specs: tuple[InstrumentSpec, ...]) -> dict[InstrumentKey, InstrumentSpec]:
    out: dict[InstrumentKey, InstrumentSpec] = {}
    for spec in specs:
        if spec.key in out:
            raise BacktestContractError(f"duplicate instrument spec: {instrument_key_wire(spec.key)}")
        out[spec.key] = spec
    if not out:
        raise BacktestContractError("prepared.instrument_specs must be non-empty")
    return out


def _build_all_bars(
    frame: pl.DataFrame,
    *,
    instruments: dict[InstrumentKey, Any],
    bar_types: dict[InstrumentKey, Any],
    nt: dict[str, Any],
) -> list[Any]:
    wire_to_key = {instrument_key_wire(key): key for key in instruments}
    bars: list[Any] = []
    for row in frame.to_dicts():
        wire = str(row["instrument"])
        key = wire_to_key.get(wire)
        if key is None:
            raise BacktestContractError(f"bar for unknown instrument wire: {wire!r}")
        bars.append(
            build_bar(
                {
                    "open": row["open"],
                    "high": row["high"],
                    "low": row["low"],
                    "close": row["close"],
                    "volume": row["volume"],
                    "ts_event": row["ts_event"],
                    "ts_init": row["ts_init"],
                },
                instrument=instruments[key],
                bar_type=bar_types[key],
                nt=nt,
            )
        )
    bars.sort(key=lambda bar: (int(bar.ts_event), str(bar.bar_type.instrument_id)))
    return bars


def _validate_funding_barriers(
    prepared: PreparedExecutionInput,
    *,
    expected_keys: tuple[InstrumentKey, ...],
) -> None:
    """Require every funding event to occur on a complete completed-close barrier."""
    available = {
        (str(row["instrument"]), row["ts_init"]) for row in prepared.bars.select(["instrument", "ts_init"]).to_dicts()
    }
    for settlement in prepared.funding_settlements:
        missing = [
            instrument_key_wire(key)
            for key in expected_keys
            if (instrument_key_wire(key), settlement.settled_at) not in available
        ]
        if missing:
            raise BacktestContractError(
                f"funding settlement {settlement.settlement_id!r} at "
                f"{settlement.settled_at.isoformat()} lacks complete bar coverage: "
                f"{', '.join(missing)}"
            )


def _reconcile_end(state: ExecutionRuntimeState, *, engine: Any) -> None:
    for key in state.expected_keys:
        projected = state.projection.signed_quantity(key)
        instrument_id = state.instrument_ids[key].id
        realized = _cache_net_qty(engine, instrument_id)
        if projected != realized:
            raise BacktestEngineExecutionError(
                f"end-of-run position reconcile failed for {instrument_key_wire(key)}: "
                f"projected={projected} nautilus={realized}"
            )


def _cache_net_qty(engine: Any, instrument_id: Any) -> Decimal:
    cache = engine.cache
    if hasattr(cache, "positions_open"):
        open_pos = [p for p in cache.positions_open() if str(p.instrument_id) == str(instrument_id)]
    else:
        open_pos = []
    if not open_pos and hasattr(cache, "positions"):
        open_pos = [p for p in cache.positions() if str(p.instrument_id) == str(instrument_id)]
    if not open_pos:
        return Decimal(0)
    total = Decimal(0)
    for pos in open_pos:
        if hasattr(pos, "signed_qty"):
            total += Decimal(str(pos.signed_qty))
        else:
            qty = Decimal(str(pos.quantity))
            side = str(getattr(pos, "side", "")).upper()
            total += -qty if "SHORT" in side else qty
    return total
