"""A3 black-box rejection scenarios F01-F12.

Purpose: mutate one valid public prepared-path fact at a time and prove unsafe
inputs fail before a usable execution result can escape.

USAGE:
    uv run pytest -q packages/platform/backtest/tests/audit/test_a3_black_box.py
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import polars as pl
import pytest
from backtest.errors import BacktestContractError, BacktestEngineExecutionError

from execution import (
    AccountSnapshot,
    InstrumentKey,
    PositionSnapshot,
    TimeWeightedTakerPolicy,
    size_target_quantities,
)
from strategies import ExecutionTiming, StrategyWeights

from .a3_support import (
    CAL,
    KEY,
    T0,
    WIRE,
    capture_rejection,
    prepare,
    run,
    valid_bars,
    valid_packet,
    valid_references,
    valid_spec,
)

# --------------------------------------------------------------------------- #
# F01-F03: market-data and reference integrity
# --------------------------------------------------------------------------- #


def test_f01_missing_scheduled_bar_rejects_whole_preparation() -> None:
    packet = valid_packet()
    packet["policy"] = TimeWeightedTakerPolicy(3, timedelta(minutes=1))
    packet["bars"] = valid_bars().filter(pl.col("ts_init") != CAL[2])
    evidence = capture_rejection(
        "F01",
        "public preparation",
        lambda: prepare(packet),
        BacktestContractError,
        "missing bar",
    )
    assert evidence.white_box is False


@pytest.mark.parametrize(
    ("case", "references", "fragment"),
    [
        pytest.param("missing", pl.DataFrame(schema=valid_references().schema), "must be non-empty", id="missing"),
        pytest.param(
            "extra",
            pl.concat(
                [
                    valid_references(),
                    pl.DataFrame(
                        {
                            "decision_at": [T0],
                            "instrument": ["BINANCE:ETHUSDT"],
                            "observed_at": [T0],
                            "price": [100.0],
                        }
                    ),
                ]
            ),
            "unknown instrument",
            id="extra",
        ),
        pytest.param("duplicate", pl.concat([valid_references(), valid_references()]), "duplicate", id="duplicate"),
    ],
)
def test_f02_reference_vector_membership_is_exact(
    case: str,
    references: pl.DataFrame,
    fragment: str,
) -> None:
    packet = valid_packet()
    packet["reference_prices"] = references
    evidence = capture_rejection(
        f"F02-{case}",
        "public preparation",
        lambda: prepare(packet),
        BacktestContractError,
        fragment,
    )
    assert evidence.exception == "BacktestContractError"


@pytest.mark.parametrize(
    ("case", "references", "fragment"),
    [
        pytest.param(
            "future",
            valid_references().with_columns(pl.lit(CAL[1]).alias("observed_at")),
            "observed_at must be",
            id="future-observation",
        ),
        pytest.param(
            "wrong-close",
            valid_references().with_columns(pl.lit(101.0).alias("price")),
            "must equal completed bar close",
            id="wrong-close",
        ),
    ],
)
def test_f03_reference_provenance_rejects_future_or_wrong_close(
    case: str,
    references: pl.DataFrame,
    fragment: str,
) -> None:
    packet = valid_packet()
    packet["reference_prices"] = references
    capture_rejection(
        f"F03-{case}",
        "public preparation",
        lambda: prepare(packet),
        BacktestContractError,
        fragment,
    )


# --------------------------------------------------------------------------- #
# F04-F06: timestamps, bars, and calendar
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("case", "mutate", "fragment"),
    [
        pytest.param(
            "naive-calendar",
            lambda packet: packet.update(execution_calendar=(datetime(2024, 6, 1, 12, 0), CAL[1])),
            "UTC",
            id="naive",
        ),
        pytest.param(
            "duplicate-calendar",
            lambda packet: packet.update(execution_calendar=(T0, T0, CAL[1])),
            "strictly increasing",
            id="duplicate",
        ),
        pytest.param(
            "decreasing-reports",
            lambda packet: packet.update(reporting_times=(CAL[2], CAL[1])),
            "strictly increasing",
            id="decreasing",
        ),
        pytest.param(
            "mismatched-reference-decision",
            lambda packet: packet.update(
                reference_prices=valid_references().with_columns(pl.lit(CAL[1]).alias("decision_at"))
            ),
            "missing decision vectors",
            id="mismatched",
        ),
    ],
)
def test_f04_timestamp_contracts_fail_closed(case: str, mutate, fragment: str) -> None:
    packet = valid_packet()
    mutate(packet)
    capture_rejection(
        f"F04-{case}",
        "public preparation",
        lambda: prepare(packet),
        BacktestContractError,
        fragment,
    )


@pytest.mark.parametrize(
    ("case", "column", "value", "fragment"),
    [
        pytest.param("bad-high", "high", 50.0, "bars.high", id="ohlc"),
        pytest.param("zero-close", "close", 0.0, "must be positive", id="price"),
        pytest.param("negative-volume", "volume", -1.0, "non-negative", id="volume"),
        pytest.param("null-close", "close", None, "must not contain nulls", id="null"),
    ],
)
def test_f05_invalid_bar_facts_fail_before_runtime(
    case: str,
    column: str,
    value: float | None,
    fragment: str,
) -> None:
    packet = valid_packet()
    packet["bars"] = valid_bars().with_columns(
        pl.when(pl.col("ts_init") == T0).then(pl.lit(value)).otherwise(pl.col(column)).alias(column)
    )
    capture_rejection(
        f"F05-{case}",
        "public preparation",
        lambda: prepare(packet),
        BacktestContractError,
        fragment,
    )


def test_f06_irregular_calendar_rejected_before_matching() -> None:
    irregular = (T0, CAL[1], CAL[3], CAL[4])
    packet = valid_packet()
    packet["execution_calendar"] = irregular
    packet["bars"] = valid_bars(calendar=irregular)
    packet["reporting_times"] = irregular[:3]
    capture_rejection(
        "F06",
        "public runtime construction",
        lambda: run(packet),
        BacktestContractError,
        "regular",
    )


# --------------------------------------------------------------------------- #
# F07-F10: metadata, weights, funding, and windows
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("case", "operation", "fragment"),
    [
        pytest.param("inverse", lambda: valid_spec(is_inverse=True), "inverse contracts"),
    ],
)
def test_f07_unsupported_instrument_contracts_reject_at_construction(
    case: str,
    operation,
    fragment: str,
) -> None:
    capture_rejection(
        f"F07-{case}",
        "engine-neutral instrument construction",
        operation,
        ValueError,
        fragment,
    )


def test_f07_missing_duplicate_and_fabricated_metadata_reject_in_preparation() -> None:
    for case, specs, fragment in (
        ("missing", (), "missing instruments"),
        ("duplicate", (valid_spec(), valid_spec()), "duplicate InstrumentKey"),
        (
            "fabricated",
            (valid_spec(key=InstrumentKey("BINANCE", "ETHUSDT"), base_currency="ETH"),),
            "missing instruments",
        ),
    ):
        packet = valid_packet()
        packet["instrument_specs"] = specs
        capture_rejection(
            f"F07-{case}",
            "public preparation",
            lambda packet=packet: prepare(packet),
            BacktestContractError,
            fragment,
        )


def test_f08_cash_residual_must_reconcile_exactly() -> None:
    packet = valid_packet()
    packet["weights"] = StrategyWeights(
        weights=pl.DataFrame({"timestamp": [T0], "BTC": [0.8], "CASH": [0.3]}),
        assets=["BTC"],
        execution=ExecutionTiming.next_bar(),
    )
    capture_rejection(
        "F08",
        "public preparation",
        lambda: prepare(packet),
        BacktestContractError,
        "Weights must sum to 1.0",
    )


def _funding_frame(ids: list[str], instruments: list[str], times: list[datetime], marks: list[float]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "settlement_id": ids,
            "instrument": instruments,
            "settled_at": times,
            "rate": [0.001] * len(ids),
            "mark_price": marks,
        }
    )


@pytest.mark.parametrize(
    ("case", "funding", "runtime", "fragment"),
    [
        pytest.param(
            "missing-barrier",
            _funding_frame(["f1"], [WIRE], [CAL[-1] + timedelta(minutes=1)], [100.0]),
            True,
            "lacks complete bar coverage",
            id="barrier",
        ),
        pytest.param(
            "duplicate-id",
            _funding_frame(["f1", "f1"], [WIRE, WIRE], [CAL[2], CAL[3]], [100.0, 100.0]),
            False,
            "duplicate funding settlement_id",
            id="id",
        ),
        pytest.param(
            "duplicate-instrument-time",
            _funding_frame(["f1", "f2"], [WIRE, WIRE], [CAL[2], CAL[2]], [100.0, 100.0]),
            False,
            "duplicate funding (instrument, settled_at)",
            id="pair",
        ),
        pytest.param(
            "invalid-mark",
            _funding_frame(["f1"], [WIRE], [CAL[2]], [0.0]),
            False,
            "mark_price must be positive",
            id="mark",
        ),
    ],
)
def test_f09_funding_events_are_unique_valid_and_barrier_bound(
    case: str,
    funding: pl.DataFrame,
    runtime: bool,
    fragment: str,
) -> None:
    packet = valid_packet()
    packet["funding_settlements"] = funding
    operation = (lambda: run(packet)) if runtime else (lambda: prepare(packet))
    capture_rejection(
        f"F09-{case}",
        "public runtime" if runtime else "public preparation",
        operation,
        BacktestContractError,
        fragment,
    )


def test_f10_policy_off_calendar_and_overlapping_windows_reject() -> None:
    off_calendar = valid_packet()
    off_calendar["policy"] = TimeWeightedTakerPolicy(2, timedelta(seconds=90))
    capture_rejection(
        "F10-off-calendar",
        "public preparation",
        lambda: prepare(off_calendar),
        BacktestContractError,
        "not an exact execution-calendar close",
    )

    overlapping = valid_packet()
    overlapping["policy"] = TimeWeightedTakerPolicy(3, timedelta(minutes=1))
    overlapping["weights"] = StrategyWeights(
        weights=pl.DataFrame(
            {
                "timestamp": [T0, CAL[1]],
                "BTC": [0.5, 0.4],
                "CASH": [0.5, 0.6],
            }
        ),
        assets=["BTC"],
        execution=ExecutionTiming.next_bar(),
    )
    overlapping["reference_prices"] = pl.concat(
        [
            valid_references(),
            valid_references().with_columns(
                pl.lit(CAL[1]).alias("decision_at"),
                pl.lit(CAL[1]).alias("observed_at"),
            ),
        ]
    )
    capture_rejection(
        "F10-overlap",
        "public preparation",
        lambda: prepare(overlapping),
        BacktestContractError,
        "overlapping target windows",
    )


# --------------------------------------------------------------------------- #
# F11-F12: sizing limits and prepared funding mode
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("case", "spec", "weight", "fragment"),
    [
        pytest.param(
            "min-quantity",
            valid_spec(min_quantity=Decimal("600")),
            0.5,
            "below min_quantity",
            id="min-quantity",
        ),
        pytest.param(
            "max-quantity",
            valid_spec(max_quantity=Decimal("10")),
            0.5,
            "exceeds max_quantity",
            id="max-quantity",
        ),
        pytest.param(
            "min-notional",
            valid_spec(min_notional=Decimal("5")),
            0.00001,
            "below min_notional",
            id="min-notional",
        ),
        pytest.param(
            "max-notional",
            valid_spec(max_notional=Decimal("1000")),
            0.5,
            "exceeds max_notional",
            id="max-notional",
        ),
    ],
)
def test_f11_public_runtime_rejects_instrument_trade_limits(
    case: str,
    spec,
    weight: float,
    fragment: str,
) -> None:
    packet = valid_packet()
    packet["instrument_specs"] = (spec,)
    packet["weights"] = StrategyWeights(
        weights=pl.DataFrame({"timestamp": [T0], "BTC": [weight], "CASH": [1 - weight]}),
        assets=["BTC"],
        execution=ExecutionTiming.next_bar(),
    )
    capture_rejection(
        f"F11-{case}",
        "public runtime",
        lambda: run(packet),
        (BacktestContractError, BacktestEngineExecutionError),
        fragment,
        white_box=False,
    )


def test_f11_public_sizing_rejects_non_divisible_current_position() -> None:
    prepared = prepare(valid_packet())
    target = prepared.targets[0]
    account = AccountSnapshot(
        as_of=CAL[0],
        cash=Decimal("100000"),
        equity=Decimal("100000"),
        positions=(PositionSnapshot(KEY, Decimal("0.0005"), Decimal("100")),),
        marks=target.reference_prices,
        cumulative_fees=Decimal("0"),
        cumulative_funding=Decimal("0"),
    )
    capture_rejection(
        "F11-non-divisible",
        "public engine-neutral sizing",
        lambda: size_target_quantities(target, account, (valid_spec(),)),
        ValueError,
        "not aligned",
        "quantity_increment",
        white_box=False,
    )


def test_f12_prepared_path_rejects_disabled_funding_mode() -> None:
    packet = valid_packet()
    capture_rejection(
        "F12",
        "public runtime",
        lambda: run(packet, include_funding=False),
        BacktestContractError,
        "include_funding=False",
    )
