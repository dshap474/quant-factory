"""Known-answer, endpoint, and precision checks of public return construction.

Usage: uv run pytest packages/platform/signal-analysis/tests/test_targets.py
"""

import math
from decimal import Decimal, localcontext

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from signal_analysis.contracts import validate_targets
from signal_analysis.targets import build_forward_returns

# --------------------------------------------------------------------------- #
# Exact windows and return conventions
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("mode", ["simple", "log"])
def test_hand_derived_returns_and_schema(windows, prices, mode):
    original_windows, original_prices = windows.clone(), prices.clone()
    result = build_forward_returns(windows, prices, return_type=mode)
    expected = [0.1, 0.2, 0.3, 0.4] if mode == "simple" else [math.log(x) for x in (1.1, 1.2, 1.3, 1.4)]
    assert result["target"].to_list() == pytest.approx(expected, abs=1e-12, rel=0)
    assert result["target_status"].to_list() == ["ok"] * 4
    assert result["target_kind"].to_list() == ["price_return"] * 4
    assert result["return_type"].to_list() == [mode] * 4
    assert_frame_equal(result.select(windows.columns), windows)
    assert_frame_equal(windows, original_windows)
    assert_frame_equal(prices, original_prices)
    validate_targets(result)
    assert_frame_equal(result, build_forward_returns(windows.reverse(), prices.reverse(), return_type=mode))


def test_missing_endpoints_never_substitute_nearby_prices(windows, prices):
    entry, exit_ = windows["target_start"][0], windows["target_end"][0]
    retained = prices.filter(
        ((pl.col("asset") == "A") & (pl.col("timestamp") == exit_))
        | ((pl.col("asset") == "B") & (pl.col("timestamp") == entry))
        | (pl.col("asset") == "D")
    )
    decoys = prices.with_columns(pl.col("timestamp") + pl.duration(hours=1))
    result = build_forward_returns(windows, pl.concat([retained, decoys]), return_type="simple")
    assert result["target_status"].to_list() == [
        "missing_entry_price",
        "missing_exit_price",
        "missing_both_prices",
        "ok",
    ]
    assert result["target"].to_list()[:3] == [None, None, None]
    assert result["target"][3] == pytest.approx(0.4, abs=1e-12, rel=0)


@pytest.mark.parametrize("mode", ["simple", "log"])
@pytest.mark.parametrize("bad", [0.0, -1.0, float("nan"), float("inf"), -float("inf")])
def test_invalid_prices_take_precedence_over_missing(windows, prices, bad, mode):
    # Entry is invalid; every exit is absent, so both defects are active.
    broken = prices.head(4).with_columns(pl.lit(bad).alias("price"))
    result = build_forward_returns(windows, broken, return_type=mode)
    assert result["target_status"].to_list() == ["invalid_price"] * 4
    assert result["target"].null_count() == 4
    validate_targets(result)


def test_null_prices_are_missing_and_empty_output_is_typed(windows, prices):
    nulls = prices.with_columns(pl.lit(None, dtype=pl.Float64).alias("price"))
    result = build_forward_returns(windows, nulls, return_type="log")
    assert result["target_status"].to_list() == ["missing_both_prices"] * 4
    empty = build_forward_returns(windows.head(0), prices.head(0), return_type="log")
    assert empty.is_empty()
    assert empty.schema == result.schema


def test_appending_future_data_leaves_targets_unchanged(windows, prices):
    future = prices.with_columns(pl.col("timestamp") + pl.duration(days=90), pl.lit(1e100).alias("price"))
    expected = build_forward_returns(windows, prices, return_type="log")
    actual = build_forward_returns(windows, pl.concat([prices, future]), return_type="log")
    assert_frame_equal(actual, expected)


def test_endpoint_change_is_local_and_extra_columns_do_not_collide(windows, prices):
    original = build_forward_returns(windows, prices, return_type="simple")
    changed = prices.with_columns(
        pl.when((pl.col("asset") == "B") & (pl.col("timestamp") == windows["target_end"][0]))
        .then(50.0)
        .otherwise(pl.col("price"))
        .alias("price")
    )
    actual = build_forward_returns(
        windows.with_columns(pl.lit(999.0).alias("_start_price")), changed, return_type="simple"
    )
    assert actual["target"][1] == -0.5
    assert_frame_equal(actual.filter(pl.col("asset") != "B"), original.filter(pl.col("asset") != "B"))


def test_duplicate_keys_and_bad_return_type_rejected(windows, prices):
    for frame, price_table in (
        (pl.concat([windows, windows.head(1)]), prices),
        (windows, pl.concat([prices, prices.head(1)])),
    ):
        with pytest.raises(ValueError, match="duplicate"):
            build_forward_returns(frame, price_table, return_type="simple")
    with pytest.raises(ValueError, match="return_type"):
        build_forward_returns(windows, prices, return_type="total")


# --------------------------------------------------------------------------- #
# Independent high-precision and metamorphic oracles
# --------------------------------------------------------------------------- #


def _decimal_return(entry: float, exit_: float, mode: str, precision: int) -> float:
    with localcontext() as ctx:
        ctx.prec = precision
        ratio = Decimal.from_float(exit_) / Decimal.from_float(entry)
        return float(ratio.ln() if mode == "log" else ratio - 1)


@pytest.mark.parametrize("mode", ["simple", "log"])
@pytest.mark.parametrize(
    "entry,exit_",
    [
        (1e200, math.nextafter(1e200, math.inf)),
        (1e-200, math.nextafter(1e-200, 0.0)),
        (math.ulp(0.0), 2 * math.ulp(0.0)),
        (1e-300, 1e300),
        (1e300, 1e-300),
        (8.0, 1.0),
        (100.0, 100.0),
        (2.0, 3.0),
        (2.0, math.nextafter(3.0, math.inf)),
        (2.0, 1.0),
        (2.0, math.nextafter(1.0, 0.0)),
    ],
)
def test_returns_against_precision_doubled_decimal_oracle(windows, prices, entry, exit_, mode):
    reference = _decimal_return(entry, exit_, mode, 80)
    assert reference == _decimal_return(entry, exit_, mode, 160)
    inputs = prices.filter(pl.col("asset") == "A").with_columns(pl.Series("price", [entry, exit_]))
    result = build_forward_returns(windows.head(1), inputs, return_type=mode).row(0, named=True)
    if math.isfinite(reference):
        assert result["target_status"] == "ok"
        # Relative accuracy matters for tiny changes; absolute 1e-12 would hide zero.
        assert result["target"] == pytest.approx(reference, rel=1e-12, abs=0)
    else:
        assert result["target_status"] == "invalid_target"
        assert result["target"] is None


@pytest.mark.parametrize("mode", ["simple", "log"])
def test_currency_scale_invariance_and_log_inverse(windows, prices, mode):
    base = build_forward_returns(windows, prices, return_type=mode)
    scaled = build_forward_returns(windows, prices.with_columns(pl.col("price") * 128), return_type=mode)
    assert scaled["target"].to_list() == pytest.approx(base["target"].to_list(), abs=1e-12, rel=0)
    # Swap prices at the same fixed window endpoints: log returns negate.
    if mode == "log":
        swapped = prices.with_columns(pl.col("price").reverse().over("asset"))
        inverse = build_forward_returns(windows, swapped, return_type="log")
        assert inverse["target"].to_list() == pytest.approx([-v for v in base["target"]], abs=1e-12, rel=0)
