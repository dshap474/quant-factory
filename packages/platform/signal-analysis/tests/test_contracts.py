"""Exercise identity, timing, and metadata contracts through public validators.

Usage: uv run pytest packages/platform/signal-analysis/tests/test_contracts.py
"""

import polars as pl
import pytest

from signal_analysis.contracts import (
    validate_prices,
    validate_signal_panel,
    validate_target_windows,
    validate_targets,
)

# --------------------------------------------------------------------------- #
# Signal and identity contracts
# --------------------------------------------------------------------------- #


def test_valid_and_typed_empty_tables(panel, targets, windows, prices):
    for table, validate in (
        (panel, validate_signal_panel),
        (targets, validate_targets),
        (windows, validate_target_windows),
        (prices, validate_prices),
    ):
        validate(table)
        validate(table.head(0))
        validate(table.with_columns(pl.lit("ignored").alias("extra")))


@pytest.mark.parametrize(
    "column,value",
    [
        ("asset", None),
        ("asset", ""),
        ("asset", " "),
        ("asset", "A "),
        ("decision_time", None),
        ("signal_available_at", None),
        ("eligible", None),
    ],
)
def test_signal_null_identity_or_empty_asset_fails(panel, column, value):
    with pytest.raises(ValueError):
        validate_signal_panel(panel.with_columns(pl.lit(value, dtype=panel.schema[column]).alias(column)))


@pytest.mark.parametrize(
    "change",
    [
        pl.col("decision_time").dt.replace_time_zone(None),
        pl.col("decision_time").cast(pl.Datetime("ns", "UTC")),
        pl.col("signal").cast(pl.Float32),
        pl.col("eligible").cast(pl.Int64),
    ],
)
def test_exact_dtype_required(panel, change):
    with pytest.raises(TypeError):
        validate_signal_panel(panel.with_columns(change))


def test_missing_column_non_table_and_duplicate_signal_fail(panel):
    with pytest.raises(TypeError):
        validate_signal_panel(panel.drop("signal"))
    with pytest.raises(TypeError):
        validate_signal_panel([])
    with pytest.raises(ValueError, match="duplicate"):
        validate_signal_panel(pl.concat([panel, panel.head(1)]))


def test_future_availability_rejected_even_when_ineligible(panel):
    bad = panel.with_columns(
        (pl.col("decision_time") + pl.duration(microseconds=1)).alias("signal_available_at"),
        pl.lit(False).alias("eligible"),
    )
    with pytest.raises(ValueError, match="signal_available_at"):
        validate_signal_panel(bad)


def test_missing_nonfinite_signals_are_coverage_inputs(panel):
    validate_signal_panel(panel.with_columns(pl.Series("signal", [None, float("nan"), float("inf"), -float("inf")])))


# --------------------------------------------------------------------------- #
# Target and price contracts
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "change",
    [
        pl.col("decision_time").alias("target_start"),
        (pl.col("decision_time") - pl.duration(days=1)).alias("target_start"),
        pl.col("target_start").alias("target_end"),
        pl.col("decision_time").alias("target_end"),
    ],
)
def test_strict_future_windows(windows, change):
    with pytest.raises(ValueError, match="decision_time < target_start < target_end"):
        validate_target_windows(windows.with_columns(change))


@pytest.mark.parametrize("column", ["target_id", "target_start", "target_end"])
def test_null_window_fields_fail(windows, column):
    with pytest.raises(ValueError):
        validate_target_windows(windows.with_columns(pl.lit(None, dtype=windows.schema[column]).alias(column)))


@pytest.mark.parametrize("value", ["", " next", "next\t"])
def test_blank_or_padded_target_id_fails(windows, value):
    with pytest.raises(ValueError, match="surrounding whitespace"):
        validate_target_windows(windows.with_columns(pl.lit(value).alias("target_id")))


def test_duplicate_window_and_price_keys_fail(windows, prices):
    with pytest.raises(ValueError, match="duplicate"):
        validate_target_windows(pl.concat([windows, windows.head(1)]))
    with pytest.raises(ValueError, match="duplicate"):
        validate_prices(pl.concat([prices, prices.head(1)]))


@pytest.mark.parametrize(
    "change",
    [
        pl.lit("unknown").alias("target_status"),
        pl.lit("").alias("target_kind"),
        pl.lit(None, dtype=pl.String).alias("return_type"),
        pl.lit("exotic").alias("return_type"),
        pl.lit(None, dtype=pl.Float64).alias("target"),
        pl.lit(float("nan")).alias("target"),
        pl.lit(float("inf")).alias("target"),
        pl.lit("missing_target").alias("target_status"),
    ],
)
def test_inconsistent_target_value_status_or_type_fails(targets, change):
    with pytest.raises(ValueError):
        validate_targets(targets.with_columns(change))


@pytest.mark.parametrize(
    "column,values",
    [
        ("target_kind", ["price_return", "residual", "price_return", "price_return"]),
        ("return_type", ["simple", "log", "simple", "simple"]),
    ],
)
def test_metadata_must_be_consistent_per_identifier(targets, column, values):
    with pytest.raises(ValueError, match="consistent"):
        validate_targets(targets.with_columns(pl.Series(column, values)))


def test_supplied_residuals_allow_typed_null_return_convention(targets):
    supplied = targets.with_columns(
        pl.lit("residual").alias("target_kind"),
        pl.lit(None, dtype=pl.String).alias("return_type"),
    )
    validate_targets(supplied)
    with pytest.raises(ValueError, match="consistent"):
        validate_targets(supplied.with_columns(pl.Series("return_type", [None, "simple", None, None], dtype=pl.String)))


@pytest.mark.parametrize(
    "status",
    [
        "missing_entry_price",
        "missing_exit_price",
        "missing_both_prices",
        "invalid_price",
        "invalid_target",
        "missing_target",
    ],
)
def test_missing_target_statuses_require_null_values(targets, status):
    validate_targets(
        targets.with_columns(
            pl.lit(status).alias("target_status"),
            pl.lit(None, dtype=pl.Float64).alias("target"),
        )
    )
