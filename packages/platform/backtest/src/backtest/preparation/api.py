"""Opt-in StrategyWeights preparation boundary for the execution path.

Purpose: translate original decision-time ``StrategyWeights`` into validated,
engine-neutral inputs for the later Nautilus simulation.

USAGE:
    >>> from backtest import prepare_execution_from_strategy_weights  # doctest: +SKIP
    >>> prepared = prepare_execution_from_strategy_weights(  # doctest: +SKIP
    ...     weights=weights,
    ...     asset_instruments=asset_instruments,
    ...     reference_prices=reference_prices,
    ...     bars=bars,
    ...     instrument_specs=instrument_specs,
    ...     execution_calendar=calendar,
    ...     reporting_times=reporting_times,
    ...     policy=ImmediateMarketPolicy(),
    ... )
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import InvalidOperation
from typing import Mapping, Sequence

import polars as pl

from execution import (
    DelayedMarketPolicy,
    FundingSettlement,
    ImmediateMarketPolicy,
    InitialAccountState,
    InstrumentKey,
    InstrumentSpec,
    PortfolioTarget,
    TimeWeightedTakerPolicy,
)
from strategies import ExecutionMode, StrategyWeights

from ..errors import BacktestContractError, BacktestUnsupportedFeatureError
from .data import (
    validate_bars,
    validate_funding_settlements,
    validate_reference_prices,
)
from .fingerprint import (
    canonical_decimal,
    canonical_value,
    funding_settlement_payload,
    instrument_spec_payload,
    instrument_wire,
    sha256_payload,
    validate_sha256,
)
from .fingerprint import (
    strategy_weights_fingerprint as _strategy_weights_fingerprint,
)
from .initial_state import initial_state_payload, validate_initial_state
from .targets import (
    ExecutionPolicy,
    decision_times,
    preflight_policy_windows,
    translate_targets,
)
from .validation import validate_strictly_increasing_utc

# --------------------------------------------------------------------------- #
# Public prepared input
# --------------------------------------------------------------------------- #


@dataclass(frozen=True, slots=True)
class PreparedExecutionInput:
    """Validated preparation inputs for execution; this is not a simulated result."""

    targets: tuple[PortfolioTarget, ...]
    bars: pl.DataFrame
    instrument_specs: tuple[InstrumentSpec, ...]
    funding_settlements: tuple[FundingSettlement, ...]
    reporting_times: tuple[datetime, ...]
    execution_calendar: tuple[datetime, ...]
    policy: ExecutionPolicy
    strategy_weights_sha256: str
    prepared_payload_sha256: str
    initial_state: InitialAccountState | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "targets", tuple(self.targets))
        if not self.targets:
            raise ValueError("targets must be non-empty")
        if any(not isinstance(target, PortfolioTarget) for target in self.targets):
            raise TypeError("targets must contain PortfolioTarget values")
        target_ids = [target.target_id for target in self.targets]
        if len(set(target_ids)) != len(target_ids):
            raise ValueError("duplicate target_id in prepared execution")
        validate_sha256(self.strategy_weights_sha256, "strategy_weights_sha256")
        validate_sha256(self.prepared_payload_sha256, "prepared_payload_sha256")
        if self.initial_state is not None and not isinstance(self.initial_state, InitialAccountState):
            raise TypeError("initial_state must be InitialAccountState or None")


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def prepare_execution_from_strategy_weights(
    *,
    weights: StrategyWeights,
    asset_instruments: Mapping[str, InstrumentKey],
    reference_prices: pl.DataFrame,
    bars: pl.DataFrame,
    instrument_specs: Sequence[InstrumentSpec],
    execution_calendar: Sequence[datetime],
    reporting_times: Sequence[datetime],
    policy: ExecutionPolicy,
    funding_settlements: pl.DataFrame | None = None,
    initial_state: InitialAccountState | None = None,
) -> PreparedExecutionInput:
    """Validate and translate original decision rows without engine work."""
    if weights.quantity_limits is not None or getattr(weights, "quantity_targets", None) is not None or weights.weights.select(weights.assets).null_count().sum_horizontal().sum() > 0:
        raise BacktestUnsupportedFeatureError(
            "nullable targets, quantity_limits and quantity_targets require the explicit run_intent_ledger path"
        )
    try:
        return _prepare(
            weights=weights,
            asset_instruments=asset_instruments,
            reference_prices=reference_prices,
            bars=bars,
            instrument_specs=instrument_specs,
            execution_calendar=execution_calendar,
            reporting_times=reporting_times,
            policy=policy,
            funding_settlements=funding_settlements,
            initial_state=initial_state,
        )
    except BacktestContractError:
        raise
    except (TypeError, ValueError, InvalidOperation, pl.exceptions.PolarsError) as exc:
        raise BacktestContractError(str(exc)) from exc


def instrument_key_wire(key: InstrumentKey) -> str:
    """Return the documented ``VENUE:SYMBOL`` frame identity."""
    if not isinstance(key, InstrumentKey):
        raise BacktestContractError("key must be InstrumentKey")
    return _instrument_wire(key)


def strategy_weights_fingerprint(weights: StrategyWeights) -> str:
    """Hash every strategy-weight fact that can change prepared orders."""
    try:
        return _strategy_weights_fingerprint(weights)
    except BacktestContractError:
        raise
    except (TypeError, ValueError, InvalidOperation) as exc:
        raise BacktestContractError(str(exc)) from exc


def prepared_execution_fingerprint(prepared: PreparedExecutionInput) -> str:
    """Hash every prepared fact that can change orders or reported economics."""
    if not isinstance(prepared, PreparedExecutionInput):
        raise BacktestContractError("prepared must be PreparedExecutionInput")
    return _prepared_payload_fingerprint(
        targets=prepared.targets,
        bars=prepared.bars,
        instrument_specs=prepared.instrument_specs,
        funding_settlements=prepared.funding_settlements,
        reporting_times=prepared.reporting_times,
        execution_calendar=prepared.execution_calendar,
        policy=prepared.policy,
        strategy_weights_sha256=prepared.strategy_weights_sha256,
        initial_state=prepared.initial_state,
    )


# --------------------------------------------------------------------------- #
# Preparation pipeline
# --------------------------------------------------------------------------- #


def _prepare(
    *,
    weights: StrategyWeights,
    asset_instruments: Mapping[str, InstrumentKey],
    reference_prices: pl.DataFrame,
    bars: pl.DataFrame,
    instrument_specs: Sequence[InstrumentSpec],
    execution_calendar: Sequence[datetime],
    reporting_times: Sequence[datetime],
    policy: ExecutionPolicy,
    funding_settlements: pl.DataFrame | None,
    initial_state: InitialAccountState | None,
) -> PreparedExecutionInput:
    if not isinstance(weights, StrategyWeights):
        raise BacktestContractError("weights must be StrategyWeights")
    if weights.execution.mode is ExecutionMode.SAME_BAR:
        raise BacktestContractError(
            "ExecutionMode.SAME_BAR is rejected on the preparation path; use next_bar or lag_bars"
        )
    weights.validate()
    if not isinstance(policy, (DelayedMarketPolicy, ImmediateMarketPolicy, TimeWeightedTakerPolicy)):
        raise BacktestContractError(
            "policy must be DelayedMarketPolicy, ImmediateMarketPolicy, or TimeWeightedTakerPolicy"
        )
    instrument_map = _validate_asset_instruments(weights.assets, asset_instruments)
    ordered_keys = tuple(sorted(instrument_map.values(), key=lambda key: key.sort_key()))
    wire_to_key = {_instrument_wire(key): key for key in ordered_keys}
    known_wires = set(wire_to_key)
    calendar = validate_strictly_increasing_utc(execution_calendar, "execution_calendar")
    reporting = validate_strictly_increasing_utc(reporting_times, "reporting_times")
    decisions = decision_times(weights)
    specs = _validate_instrument_specs(instrument_specs, ordered_keys)
    validated_bars, bar_closes = validate_bars(bars, known_wires)
    references = validate_reference_prices(
        reference_prices,
        expected_decisions=decisions,
        known_wires=known_wires,
        wire_to_key=wire_to_key,
        bar_closes=bar_closes,
    )
    funding = validate_funding_settlements(
        funding_settlements,
        known_wires=known_wires,
        wire_to_key=wire_to_key,
    )

    targets = translate_targets(
        weights=weights,
        decisions=decisions,
        instrument_map=instrument_map,
        ordered_keys=ordered_keys,
        calendar=calendar,
        reference_prices=references,
    )
    preflight_policy_windows(
        targets=targets,
        policy=policy,
        calendar=calendar,
        ordered_keys=ordered_keys,
        bar_closes=bar_closes,
    )
    validated_initial_state = validate_initial_state(
        initial_state,
        targets=targets,
        specs=specs,
    )
    values = {
        "targets": targets,
        "bars": validated_bars,
        "instrument_specs": specs,
        "funding_settlements": funding,
        "reporting_times": reporting,
        "execution_calendar": calendar,
        "policy": policy,
        "strategy_weights_sha256": _strategy_weights_fingerprint(weights),
        "initial_state": validated_initial_state,
    }
    return PreparedExecutionInput(
        **values,
        prepared_payload_sha256=_prepared_payload_fingerprint(**values),
    )


# --------------------------------------------------------------------------- #
# Identity and instrument metadata
# --------------------------------------------------------------------------- #


def _instrument_wire(key: InstrumentKey) -> str:
    return instrument_wire(key)


def _prepared_payload_fingerprint(
    *,
    targets: Sequence[PortfolioTarget],
    bars: pl.DataFrame,
    instrument_specs: Sequence[InstrumentSpec],
    funding_settlements: Sequence[FundingSettlement],
    reporting_times: Sequence[datetime],
    execution_calendar: Sequence[datetime],
    policy: ExecutionPolicy,
    strategy_weights_sha256: str,
    initial_state: InitialAccountState | None,
) -> str:
    payload = {
        "strategy_weights_sha256": strategy_weights_sha256,
        "targets": [_target_payload(target) for target in targets],
        "bars": [{name: canonical_value(value) for name, value in sorted(row.items())} for row in bars.to_dicts()],
        "instrument_specs": [instrument_spec_payload(spec) for spec in instrument_specs],
        "funding_settlements": [funding_settlement_payload(item) for item in funding_settlements],
        "reporting_times": [canonical_value(value) for value in reporting_times],
        "execution_calendar": [canonical_value(value) for value in execution_calendar],
        "policy": _policy_payload(policy),
        "initial_state": initial_state_payload(initial_state),
    }
    return sha256_payload(payload)


def _target_payload(target: PortfolioTarget) -> dict[str, object]:
    return {
        "target_id": target.target_id,
        "decision_at": canonical_value(target.decision_at),
        "earliest_execution_at": canonical_value(target.earliest_execution_at),
        "weights": [
            [_instrument_wire(weight.instrument), canonical_decimal(weight.weight)] for weight in target.weights
        ],
        "cash_weight": canonical_decimal(target.cash_weight),
        "reference_prices": [
            [
                _instrument_wire(reference.instrument),
                canonical_decimal(reference.price),
                canonical_value(reference.observed_at),
            ]
            for reference in target.reference_prices
        ],
    }


def _policy_payload(policy: ExecutionPolicy) -> dict[str, object]:
    if isinstance(policy, ImmediateMarketPolicy):
        return {"kind": "immediate"}
    if isinstance(policy, DelayedMarketPolicy):
        return {
            "kind": "delayed_market",
            "delay": _timedelta_microseconds(policy.delay),
        }
    return {
        "kind": "twap",
        "slice_count": policy.slice_count,
        "interval": _timedelta_microseconds(policy.interval),
    }


def _timedelta_microseconds(value: timedelta) -> int:
    return (value.days * 86400 + value.seconds) * 1_000_000 + value.microseconds


def _validate_asset_instruments(
    assets: Sequence[str],
    asset_instruments: Mapping[str, InstrumentKey],
) -> dict[str, InstrumentKey]:
    if not assets:
        raise BacktestContractError("weights.assets must be non-empty")
    if missing := [asset for asset in assets if asset not in asset_instruments]:
        raise BacktestContractError(f"asset_instruments missing mappings for: {', '.join(missing)}")
    if extra := sorted(set(asset_instruments) - set(assets)):
        raise BacktestContractError(f"asset_instruments contain unmapped extras: {', '.join(extra)}")

    mapped: dict[str, InstrumentKey] = {}
    seen: set[InstrumentKey] = set()
    for asset in assets:
        key = asset_instruments[asset]
        if not isinstance(key, InstrumentKey):
            raise BacktestContractError(f"asset_instruments[{asset!r}] must be InstrumentKey")
        if key in seen:
            raise BacktestContractError(f"duplicate InstrumentKey mapping for {_instrument_wire(key)}")
        seen.add(key)
        mapped[asset] = key
    return mapped


def _validate_instrument_specs(
    instrument_specs: Sequence[InstrumentSpec],
    ordered_keys: Sequence[InstrumentKey],
) -> tuple[InstrumentSpec, ...]:
    specs = tuple(instrument_specs)
    if any(not isinstance(spec, InstrumentSpec) for spec in specs):
        raise BacktestContractError("instrument_specs must contain InstrumentSpec values")
    keys = [spec.key for spec in specs]
    if len(set(keys)) != len(keys):
        raise BacktestContractError("instrument_specs contain duplicate InstrumentKey values")
    expected, actual = set(ordered_keys), set(keys)
    if difference := expected - actual:
        names = ", ".join(_instrument_wire(key) for key in sorted(difference, key=lambda key: key.sort_key()))
        raise BacktestContractError(f"instrument_specs missing instruments: {names}")
    if difference := actual - expected:
        names = ", ".join(_instrument_wire(key) for key in sorted(difference, key=lambda key: key.sort_key()))
        raise BacktestContractError(f"instrument_specs contain extra instruments: {names}")
    by_key = {spec.key: spec for spec in specs}
    return tuple(by_key[key] for key in ordered_keys)
