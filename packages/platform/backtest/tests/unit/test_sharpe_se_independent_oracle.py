"""Independent known answers for the platform Sharpe standard error, t-stat and CI.

USAGE: uv run pytest packages/platform/backtest/tests/unit/test_sharpe_se_independent_oracle.py -q
Oracle: Paleologo, Elements of Quantitative Investing, Chapter 3, FAQ 3.1-3.2. For iid returns SE(SR_p) = sqrt((1 + SR_p^2/2)/T) in
per-period units, and Sharpe scales as time^-1/2. With q periods per year,
SR_ann = sqrt(q) SR_p, so SE_ann = sqrt(q) sqrt((1 + SR_p^2/2)/T)
= sqrt((q + SR_ann^2/2)/T); the t-stat does not depend on the frequency label.
SR_p uses the platform's own sample Sharpe convention (ddof=1); the book's 1/T
variance differs at O(1/T) and is not judged here. Tolerance: relative 1e-12
for closed forms; Monte Carlo coverage band fixed at [0.93, 0.97].
"""
from __future__ import annotations

# --------------------------------------------------------------------------- #
# Fixtures and closed forms
# --------------------------------------------------------------------------- #
import math

import numpy as np
import pytest
from backtest.metrics import MetricContext, compute_metrics

NAMES = ["sharpe", "sharpe_se", "sharpe_tstat", "sharpe_ci_lower", "sharpe_ci_upper"]
PERIODS = {"daily": 252.0, "1d": 252.0, "weekly": 52.0, "monthly": 12.0, "1h": 24.0 * 252.0}
REL = 1e-12


def context(returns, frequency):
    r = np.asarray(returns, dtype=float)
    zeros = np.zeros_like(r)
    return MetricContext(equity=np.concatenate([[1.0], np.cumprod(1 + r)]), net_return=r,
                         price_return=r, benchmark_return=zeros, funding_return=zeros,
                         cost_return=zeros, turnover=zeros, frequency=frequency)


def expected(returns, q):
    r = np.asarray(returns, dtype=float)
    t = len(r)
    sr_p = r.mean() / r.std(ddof=1)
    se_p = math.sqrt((1 + sr_p ** 2 / 2) / t)
    sr, se = math.sqrt(q) * sr_p, math.sqrt(q) * se_p
    return dict(sharpe=sr, sharpe_se=se, sharpe_tstat=sr / se,
                sharpe_ci_lower=sr - 1.96 * se, sharpe_ci_upper=sr + 1.96 * se)


def alternating(t=252, mean=0.001, amplitude=0.01):
    return mean + amplitude * (-1.0) ** np.arange(t)


# --------------------------------------------------------------------------- #
# Closed-form annualized standard error and interval
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("frequency", sorted(PERIODS))
def test_annualized_se_tstat_and_interval_match_closed_form(frequency):
    r = alternating()
    actual = compute_metrics(context(r, frequency), NAMES)
    want = expected(r, PERIODS[frequency])
    for name in NAMES:
        assert math.isclose(actual[name], want[name], rel_tol=REL), (name, actual[name], want[name])


def test_equivalent_annualized_form():
    r = alternating(t=500, mean=0.0004, amplitude=0.02)
    actual = compute_metrics(context(r, "daily"), NAMES)
    sr = actual["sharpe"]
    assert math.isclose(actual["sharpe_se"], math.sqrt((252 + sr ** 2 / 2) / 500), rel_tol=REL)


def test_tstat_is_invariant_to_frequency_label_and_se_scales_with_root_periods():
    r = alternating(t=400, mean=0.002, amplitude=0.015)
    by_label = {f: compute_metrics(context(r, f), NAMES) for f in ("daily", "weekly", "monthly")}
    t_daily = by_label["daily"]["sharpe_tstat"]
    for f, values in by_label.items():
        assert math.isclose(values["sharpe_tstat"], t_daily, rel_tol=REL), f
        ratio = values["sharpe_se"] / by_label["daily"]["sharpe_se"]
        assert math.isclose(ratio, math.sqrt(PERIODS[f] / 252.0), rel_tol=REL), f


def test_zero_mean_returns_have_standard_error_root_q_over_t():
    r = 0.01 * (-1.0) ** np.arange(252)
    actual = compute_metrics(context(r, "daily"), NAMES)
    assert abs(actual["sharpe"]) < 1e-12
    assert math.isclose(actual["sharpe_se"], math.sqrt(252 / 252), rel_tol=1e-9)


def test_short_samples_keep_zero_uncertainty_convention():
    actual = compute_metrics(context([0.01], "daily"), ["sharpe_se", "sharpe_tstat"])
    assert actual == {"sharpe_se": 0.0, "sharpe_tstat": 0.0}


# --------------------------------------------------------------------------- #
# Frequentist coverage of the 95% interval under iid normal returns
# --------------------------------------------------------------------------- #
def test_interval_covers_true_annualized_sharpe_near_nominal_rate():
    rng = np.random.default_rng(12345)
    sr_p, t, reps = 0.08, 750, 2000
    true_ann = math.sqrt(252) * sr_p
    covered = 0
    for _ in range(reps):
        r = rng.normal(sr_p * 0.01, 0.01, t)
        m = compute_metrics(context(r, "daily"), ["sharpe_ci_lower", "sharpe_ci_upper"])
        covered += m["sharpe_ci_lower"] <= true_ann <= m["sharpe_ci_upper"]
    assert 0.93 <= covered / reps <= 0.97, covered / reps


# --------------------------------------------------------------------------- #
# Entrypoint
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q", "-p", "no:cacheprovider"]))
