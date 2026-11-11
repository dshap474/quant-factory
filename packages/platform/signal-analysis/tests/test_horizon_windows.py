"""Known-answer and contract tests for fixed-offset horizon windows.

Usage: ``uv run --no-sync pytest packages/platform/signal-analysis/tests/test_horizon_windows.py -q``.
"""

# --------------------------------------------------------------------------- #
# Imports and fixtures
# --------------------------------------------------------------------------- #

from datetime import datetime, timedelta, timezone

import polars as pl
import pytest

from signal_analysis.contracts import validate_target_windows
from signal_analysis.targets import build_forward_returns, horizon_windows

UTC = pl.Datetime("us", "UTC")
T0 = datetime(2025, 3, 1, tzinfo=timezone.utc)
DAY = timedelta(days=1)


def decisions():
    return pl.DataFrame(
        {"decision_time": [T0, T0, T0 + DAY], "asset": ["A", "B", "A"]},
        schema={"decision_time": UTC, "asset": pl.String},
    )


# --------------------------------------------------------------------------- #
# Known answers
# --------------------------------------------------------------------------- #


def test_offsets_produce_expected_instants_and_pass_the_contract():
    windows = horizon_windows(decisions(), spans={"h9": (DAY, 10 * DAY), "h1": (DAY, 2 * DAY)})
    validate_target_windows(windows)
    assert windows.columns == ["decision_time", "asset", "target_id", "target_start", "target_end"]
    assert windows.height == 6
    row = windows.filter((pl.col("asset") == "B") & (pl.col("target_id") == "h9")).row(0, named=True)
    assert row["target_start"] == T0 + DAY and row["target_end"] == T0 + 10 * DAY
    assert windows["target_id"].to_list()[:2] == ["h1", "h9"]


def test_assets_never_share_a_row_and_feed_the_return_builder():
    windows = horizon_windows(decisions(), spans={"h1": (DAY, 2 * DAY)})
    assert windows.select("decision_time", "asset", "target_id").is_duplicated().sum() == 0
    prices = pl.DataFrame(
        {
            "asset": ["A", "A", "A", "B", "B"],
            "timestamp": [T0 + DAY, T0 + 2 * DAY, T0 + 3 * DAY, T0 + DAY, T0 + 2 * DAY],
            "price": [100.0, 110.0, 121.0, 50.0, 25.0],
        },
        schema={"asset": pl.String, "timestamp": UTC, "price": pl.Float64},
    )
    targets = build_forward_returns(windows, prices, return_type="simple")
    assert targets["target"].to_list() == pytest.approx([0.1, -0.5, 0.1])
    assert targets["target_status"].to_list() == ["ok"] * 3


# --------------------------------------------------------------------------- #
# Contracts
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "span",
    [(timedelta(0), DAY), (-DAY, DAY), (DAY, DAY), (2 * DAY, DAY)],
)
def test_invalid_spans_raise(span):
    with pytest.raises(ValueError, match="0 < start_offset < end_offset"):
        horizon_windows(decisions(), spans={"bad": span})


def test_non_timedelta_span_and_bad_ids_raise():
    with pytest.raises(TypeError):
        horizon_windows(decisions(), spans={"h": (1, 2)})
    with pytest.raises(ValueError):
        horizon_windows(decisions(), spans={" h": (DAY, 2 * DAY)})
    with pytest.raises(ValueError):
        horizon_windows(decisions(), spans={})


def test_duplicate_or_naive_decisions_rejected():
    dup = pl.concat([decisions(), decisions().head(1)])
    with pytest.raises(ValueError, match="duplicate"):
        horizon_windows(dup, spans={"h": (DAY, 2 * DAY)})
    naive = decisions().with_columns(pl.col("decision_time").dt.replace_time_zone(None))
    with pytest.raises(TypeError):
        horizon_windows(naive, spans={"h": (DAY, 2 * DAY)})
