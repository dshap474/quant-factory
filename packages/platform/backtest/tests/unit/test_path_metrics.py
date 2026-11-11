"""Known-answer zero-target downside and calendar-duration fixtures.

USAGE: uv run pytest packages/platform/backtest/tests/unit/test_path_metrics.py -q
"""

from datetime import date, timedelta
from math import sqrt

import pytest
from backtest import sortino_ratio, summarize_path_risk

# --------------------------------------------------------------------------- #
# Independent fixtures: exact shortfalls and dated peak/recovery events
# --------------------------------------------------------------------------- #


def test_sortino_uses_all_observations_and_explicit_calendar() -> None:
    # Shortfalls: 0, -.1, -.1, 0. Mean=.025, RMS=.1/sqrt(2).
    assert sortino_ratio([.2, -.1, -.1, .1], periods_per_year=365) == pytest.approx(sqrt(45.625), rel=1e-12)
    assert sortino_ratio([.2, -.1], periods_per_year=365) == pytest.approx(sqrt(182.5), rel=1e-12)
    assert sortino_ratio([-.1], periods_per_year=365) == pytest.approx(-sqrt(365), rel=1e-12)
    assert sortino_ratio([.2, 0], periods_per_year=365) is None
    assert sortino_ratio([], periods_per_year=365) is None


def test_durations_include_recovery_and_censored_final_episode() -> None:
    # Jan 2 peak recovers Jan 6 (4 days); Jan 6 peak still underwater Jan 8 (2 days).
    days = [date(2024, 1, 1) + timedelta(days=i) for i in [0, 1, 2, 5, 7]]
    result = summarize_path_risk([100, 110, 90, 110, 100], days)
    assert result["longest_drawdown_days"] == 4
    assert result["current_drawdown_days"] == 2
    recovered = summarize_path_risk([100, 110, 90, 110], days[:4])
    assert recovered["longest_drawdown_days"] == 4
    assert recovered["current_drawdown_days"] == 0
    flat = summarize_path_risk([100, 100], days[:2])
    assert flat == {"sortino": None, "robust_sortino": None, "martin": None, "longest_drawdown_days": 0,
                    "current_drawdown_days": 0}


def test_path_excludes_initial_anchor_from_sortino() -> None:
    # Successive returns .2, -.1 -> same exact two-observation oracle above.
    days = [date(2024, 1, i) for i in [1, 2, 3]]
    assert summarize_path_risk([100, 120, 108], days)["sortino"] == pytest.approx(sqrt(182.5), rel=1e-12)


def test_martin_uses_calendar_cagr_and_all_observed_drawdowns() -> None:
    # One calendar year, ending +10%; drawdowns 0, 0, -25%, -1/12.
    days = [date(2023, 1, 1), date(2023, 4, 1), date(2023, 7, 1), date(2024, 1, 1)]
    result = summarize_path_risk([100, 120, 90, 110], days)
    assert result["martin"] == pytest.approx(.1 / sqrt(5 / 288), rel=1e-12)
    assert summarize_path_risk([100, 90], [days[0], days[-1]])["martin"] == pytest.approx(-sqrt(2))
    assert summarize_path_risk([100, 110], [days[0], days[-1]])["martin"] is None
    assert summarize_path_risk([100], days[:1])["martin"] is None


def test_martin_is_scale_invariant_and_sensitive_to_return_order() -> None:
    days = [date(2023, 1, 1) + timedelta(days=i) for i in range(5)]
    alternating = [100, 112, 100.8, 112.896, 101.6064]
    clustered = [100, 112, 125.44, 112.896, 101.6064]
    a = summarize_path_risk(alternating, days)
    b = summarize_path_risk(clustered, days)
    assert a["sortino"] == pytest.approx(b["sortino"])
    a_martin, b_martin = a["martin"], b["martin"]
    assert a_martin is not None and b_martin is not None
    assert a_martin > b_martin
    assert summarize_path_risk([v * 1_000 for v in alternating], days)["martin"] == pytest.approx(a["martin"])


@pytest.mark.parametrize("returns,factor", [([float("nan")], 365), ([.1], 0), ([.1], float("inf"))])
def test_invalid_sortino_inputs_fail(returns, factor) -> None:
    with pytest.raises(ValueError):
        sortino_ratio(returns, periods_per_year=factor)


def test_invalid_path_calendar_fails() -> None:
    with pytest.raises(ValueError, match="strictly increasing"):
        summarize_path_risk([100, 90], [date(2024, 1, 1)] * 2)
