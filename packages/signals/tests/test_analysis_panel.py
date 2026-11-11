"""Known-answer tests for the prediction-frame to signal-analysis adapters.

Usage: uv run --no-sync pytest packages/signals/tests/test_analysis_panel.py -q
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import polars as pl
import pytest
from signals.analysis_panel import prediction_frame_to_signal_panel, price_frame_from_panel

# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

DAY = timedelta(days=1)
UTC = timezone.utc


def _predictions(**overrides: object) -> pl.DataFrame:
    base = {
        "timestamp": [datetime(2024, 1, 1), datetime(2024, 1, 1), datetime(2024, 1, 2)],
        "asset": ["A", "B", "A"],
        "prediction": [0.5, -0.25, float("nan")],
        "close": [10.0, None, 11.0],
    }
    base.update(overrides)
    return pl.DataFrame(base)


# --------------------------------------------------------------------------- #
# Signal panel
# --------------------------------------------------------------------------- #


def test_naive_daily_bar_closes_one_day_later_in_utc() -> None:
    panel = prediction_frame_to_signal_panel(_predictions(), bar_close_offset=DAY)

    assert panel.columns == ["decision_time", "asset", "signal_available_at", "signal", "eligible"]
    assert panel.schema["decision_time"] == pl.Datetime("us", "UTC")
    first = panel.row(0, named=True)
    assert first["decision_time"] == datetime(2024, 1, 2, tzinfo=UTC)
    assert first["signal_available_at"] == first["decision_time"]
    assert first["asset"] == "A"
    assert first["signal"] == 0.5
    assert first["eligible"] is True


def test_date_dtype_input_is_a_utc_bar() -> None:
    frame = _predictions(timestamp=[date(2024, 1, 1), date(2024, 1, 1), date(2024, 1, 2)])
    panel = prediction_frame_to_signal_panel(frame, bar_close_offset=DAY)
    assert panel["decision_time"].to_list()[0] == datetime(2024, 1, 2, tzinfo=UTC)


def test_availability_lag_moves_both_clocks_equally() -> None:
    panel = prediction_frame_to_signal_panel(_predictions(), bar_close_offset=DAY, availability_lag=timedelta(hours=6))
    first = panel.row(0, named=True)
    assert first["decision_time"] == datetime(2024, 1, 2, 6, tzinfo=UTC)
    assert first["signal_available_at"] == first["decision_time"]


def test_eligible_expression_is_honored_and_nonfinite_signals_stay() -> None:
    panel = prediction_frame_to_signal_panel(_predictions(), bar_close_offset=DAY, eligible=pl.col("asset") != "B")
    by_asset = {(row["decision_time"], row["asset"]): row for row in panel.iter_rows(named=True)}
    assert by_asset[(datetime(2024, 1, 2, tzinfo=UTC), "B")]["eligible"] is False
    assert by_asset[(datetime(2024, 1, 2, tzinfo=UTC), "A")]["eligible"] is True
    nan_row = by_asset[(datetime(2024, 1, 3, tzinfo=UTC), "A")]
    assert nan_row["signal"] != nan_row["signal"]


def test_duplicate_keys_fail_through_the_contract() -> None:
    frame = _predictions(timestamp=[datetime(2024, 1, 1)] * 3, asset=["A", "A", "B"])
    with pytest.raises(ValueError, match="duplicate keys"):
        prediction_frame_to_signal_panel(frame, bar_close_offset=DAY)


def test_missing_asset_column_raises() -> None:
    frame = _predictions().drop("asset")
    with pytest.raises(KeyError, match="constant asset column"):
        prediction_frame_to_signal_panel(frame, bar_close_offset=DAY)


def test_tz_aware_input_is_converted_not_shifted() -> None:
    frame = _predictions(
        timestamp=pl.Series(
            [datetime(2024, 1, 1, 2), datetime(2024, 1, 1, 2), datetime(2024, 1, 2, 2)],
            dtype=pl.Datetime("us"),
        ).dt.replace_time_zone("Europe/Berlin")
    )
    panel = prediction_frame_to_signal_panel(frame, bar_close_offset=DAY)
    # 02:00 Berlin (UTC+1) is 01:00 UTC; the offset then adds one day.
    assert panel["decision_time"].to_list()[0] == datetime(2024, 1, 2, 1, tzinfo=UTC)


def test_signal_column_can_be_chosen() -> None:
    frame = _predictions(alt_score=[1.0, 2.0, 3.0])
    panel = prediction_frame_to_signal_panel(frame, signal_col="alt_score", bar_close_offset=DAY)
    assert sorted(panel["signal"].to_list()) == [1.0, 2.0, 3.0]


# --------------------------------------------------------------------------- #
# Price table
# --------------------------------------------------------------------------- #


def test_price_frame_drops_null_prices_and_uses_close_instants() -> None:
    prices = price_frame_from_panel(_predictions(), price_col="close", bar_close_offset=DAY)
    assert prices.columns == ["asset", "timestamp", "price"]
    assert prices.height == 2
    assert prices["asset"].to_list() == ["A", "A"]
    assert prices["timestamp"].to_list() == [datetime(2024, 1, 2, tzinfo=UTC), datetime(2024, 1, 3, tzinfo=UTC)]
    assert prices["price"].to_list() == [10.0, 11.0]


def test_price_frame_keeps_nonpositive_prices_for_the_target_builder() -> None:
    prices = price_frame_from_panel(_predictions(close=[0.0, -1.0, 5.0]), price_col="close", bar_close_offset=DAY)
    assert prices["price"].to_list() == [0.0, 5.0, -1.0]


def test_price_frame_requires_price_column() -> None:
    with pytest.raises(KeyError, match="'spot'"):
        price_frame_from_panel(_predictions(), price_col="spot", bar_close_offset=DAY)
