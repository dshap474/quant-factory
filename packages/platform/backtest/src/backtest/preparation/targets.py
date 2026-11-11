"""StrategyWeights target translation and policy-window preflight.

Purpose: translate original decision rows into atomic PortfolioTarget values and
prove every unsized policy window has complete calendar/bar coverage.

USAGE:
    >>> from backtest.preparation.targets import translate_targets  # doctest: +SKIP
"""

from __future__ import annotations

from datetime import datetime
from typing import Mapping, Sequence

from execution import (
    DelayedMarketPolicy,
    ImmediateMarketPolicy,
    InstrumentKey,
    PortfolioTarget,
    ReferencePrice,
    TargetWeight,
    TimeWeightedTakerPolicy,
)
from strategies import StrategyWeights

from ..errors import BacktestContractError
from .data import BarCloseIndex
from .validation import require_utc_datetime, to_decimal

ExecutionPolicy = DelayedMarketPolicy | ImmediateMarketPolicy | TimeWeightedTakerPolicy


# --------------------------------------------------------------------------- #
# Decision timestamps and target translation
# --------------------------------------------------------------------------- #


def decision_times(weights: StrategyWeights) -> tuple[datetime, ...]:
    """Return strictly increasing original decision timestamps."""
    if weights.weights.is_empty():
        raise BacktestContractError("weights must contain at least one decision row")
    timestamps: list[datetime] = []
    for index, raw in enumerate(weights.weights.get_column("timestamp")):
        timestamp = require_utc_datetime(raw, f"weights.timestamp[{index}]")
        if timestamps and timestamp <= timestamps[-1]:
            raise BacktestContractError(
                "weights timestamps must be strictly increasing; "
                f"got {timestamps[-1].isoformat()} then {timestamp.isoformat()}"
            )
        timestamps.append(timestamp)
    return tuple(timestamps)


def translate_targets(
    *,
    weights: StrategyWeights,
    decisions: Sequence[datetime],
    instrument_map: Mapping[str, InstrumentKey],
    ordered_keys: Sequence[InstrumentKey],
    calendar: Sequence[datetime],
    reference_prices: Mapping[datetime, tuple[ReferencePrice, ...]],
) -> tuple[PortfolioTarget, ...]:
    """Translate original StrategyWeights rows without timing materialization."""
    lag = weights.execution.derive_lag_bars()
    if lag < 1:
        raise BacktestContractError("execution lag must be >= 1 on the preparation path")
    key_to_asset = {instrument_map[asset]: asset for asset in weights.assets}

    targets: list[PortfolioTarget] = []
    for row_index, (row, decision_at) in enumerate(zip(weights.weights.iter_rows(named=True), decisions, strict=True)):
        earliest = _resolve_earliest_execution(decision_at, calendar, lag)
        target_weights = tuple(
            TargetWeight(
                instrument=key,
                weight=to_decimal(row[key_to_asset[key]], f"weights.{key_to_asset[key]}[{row_index}]"),
            )
            for key in ordered_keys
        )
        targets.append(
            PortfolioTarget(
                target_id=f"t{row_index:04d}:{decision_at.strftime('%Y%m%dT%H%M%S.%fZ')}",
                decision_at=decision_at,
                earliest_execution_at=earliest,
                weights=target_weights,
                cash_weight=to_decimal(row[weights.cash_col], f"weights.{weights.cash_col}[{row_index}]"),
                reference_prices=reference_prices[decision_at],
            )
        )
    return tuple(targets)


def _resolve_earliest_execution(
    decision_at: datetime,
    calendar: Sequence[datetime],
    lag: int,
) -> datetime:
    closes_after_decision = [timestamp for timestamp in calendar if timestamp > decision_at]
    if len(closes_after_decision) < lag:
        raise BacktestContractError(
            f"execution calendar lacks the required lag={lag} close after decision_at={decision_at.isoformat()}"
        )
    return closes_after_decision[lag - 1]


# --------------------------------------------------------------------------- #
# Whole-target window preflight
# --------------------------------------------------------------------------- #


def preflight_policy_windows(
    *,
    targets: Sequence[PortfolioTarget],
    policy: ExecutionPolicy,
    calendar: Sequence[datetime],
    ordered_keys: Sequence[InstrumentKey],
    bar_closes: BarCloseIndex,
) -> None:
    """Require every target leg/close and reject target-window overlap."""
    calendar_set = set(calendar)
    target_ends: list[datetime] = []
    for target in targets:
        scheduled = policy.schedule_times(target.decision_at, target.earliest_execution_at)
        for close_at in scheduled:
            if close_at not in calendar_set:
                raise BacktestContractError(
                    f"policy scheduled close {close_at.isoformat()} for target "
                    f"{target.target_id!r} is not an exact execution-calendar close"
                )
            for key in ordered_keys:
                wire = f"{key.venue}:{key.symbol}"
                if (wire, close_at) not in bar_closes:
                    raise BacktestContractError(
                        f"missing bar for instrument {wire} at policy close "
                        f"{close_at.isoformat()} for target {target.target_id!r}"
                    )
        target_ends.append(scheduled[-1])

    for index in range(1, len(targets)):
        if targets[index].earliest_execution_at <= target_ends[index - 1]:
            raise BacktestContractError(
                "overlapping target windows: "
                f"target {targets[index - 1].target_id!r} ends at "
                f"{target_ends[index - 1].isoformat()}, target {targets[index].target_id!r} "
                f"starts at {targets[index].earliest_execution_at.isoformat()}"
            )
