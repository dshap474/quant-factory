"""Independent known-answer tests for public backtest metrics.

USAGE:
    uv run pytest packages/platform/backtest/tests/unit/test_metrics.py -q
"""

from __future__ import annotations

from math import sqrt

import numpy as np
import pytest
from backtest.metrics import MetricContext, compute_metrics

# --------------------------------------------------------------------------- #
# Context builder
# --------------------------------------------------------------------------- #


def _ctx(
    *,
    net_return: np.ndarray,
    benchmark_return: np.ndarray | None = None,
    price_return: np.ndarray | None = None,
    funding_return: np.ndarray | None = None,
    cost_return: np.ndarray | None = None,
    turnover: np.ndarray | None = None,
    frequency: str = "daily",
) -> MetricContext:
    benchmark = benchmark_return if benchmark_return is not None else np.zeros_like(net_return)
    price = price_return if price_return is not None else net_return.copy()
    funding = funding_return if funding_return is not None else np.zeros_like(net_return)
    cost = cost_return if cost_return is not None else np.zeros_like(net_return)
    turn = turnover if turnover is not None else np.zeros_like(net_return)

    equity = np.empty(len(net_return) + 1, dtype=np.float64)
    equity[0] = 1.0
    if len(net_return) > 0:
        equity[1:] = np.cumprod(1.0 + net_return)

    return MetricContext(
        equity=equity,
        net_return=net_return,
        price_return=price,
        benchmark_return=benchmark,
        funding_return=funding,
        cost_return=cost,
        turnover=turn,
        frequency=frequency,
    )


# --------------------------------------------------------------------------- #
# Known-answer metrics
# --------------------------------------------------------------------------- #


def test_core_metrics_match_hand_derived_mixed_return_oracle() -> None:
    net_return = np.array([0.10, -0.04, -0.06, 0.02], dtype=np.float64)
    context = _ctx(
        net_return=net_return,
        price_return=np.array([0.10, -0.02, -0.04, 0.03], dtype=np.float64),
        funding_return=np.array([0.01, -0.01, 0.02, 0.0], dtype=np.float64),
        cost_return=np.array([0.002, 0.002, 0.002, 0.002], dtype=np.float64),
        turnover=np.array([0.5, 1.0, 0.25, 0.75], dtype=np.float64),
    )

    metrics = compute_metrics(
        context,
        ["sortino", "max_drawdown", "calmar", "avg_turnover", "funding_share", "win_rate"],
    )

    # Mean return is 0.5%; annual return is 1.26. Downside squared
    # shortfalls total 0.0052 across ALL four observations, and the
    # peak-to-trough path from 1.10 to 0.99264 is a 9.76% drawdown.
    expected_downside_volatility = sqrt(0.0013) * sqrt(252.0)
    assert metrics["sortino"] == pytest.approx(1.26 / expected_downside_volatility)
    assert metrics["max_drawdown"] == pytest.approx(0.0976)
    assert metrics["calmar"] == pytest.approx(1.26 / 0.0976)
    assert metrics["avg_turnover"] == pytest.approx(0.625)
    assert metrics["funding_share"] == pytest.approx(0.02 / 0.082)
    assert metrics["win_rate"] == pytest.approx(0.5)


def test_new_chapter3_metrics_match_expected_formulas() -> None:
    net_return = np.array([0.01, 0.02, 0.00, 0.03], dtype=np.float64)
    benchmark_return = np.array([0.005, 0.01, -0.005, 0.015], dtype=np.float64)
    ctx = _ctx(net_return=net_return, benchmark_return=benchmark_return)

    metrics = compute_metrics(
        ctx,
        [
            "sharpe",
            "active_return",
            "tracking_error",
            "information_ratio",
            "sharpe_se",
            "sharpe_tstat",
            "sharpe_ci_lower",
            "sharpe_ci_upper",
            "sharpe_adj_autocorr",
        ],
    )

    factor = 252.0
    active = net_return - benchmark_return
    expected_sharpe = np.mean(net_return) * factor / (np.std(net_return, ddof=1) * sqrt(factor))
    expected_active_return = np.mean(active) * factor
    expected_tracking_error = np.std(active, ddof=1) * sqrt(factor)
    expected_information_ratio = expected_active_return / expected_tracking_error
    # Lo (2002) iid SE of the per-period Sharpe, scaled by sqrt(factor) like the Sharpe itself:
    # sqrt(factor) * sqrt((1 + SR_p^2 / 2) / T) == sqrt((factor + SR_ann^2 / 2) / T).
    per_period = expected_sharpe / sqrt(factor)
    expected_sharpe_se = sqrt(factor) * sqrt((1.0 + per_period**2 / 2.0) / len(net_return))
    expected_sharpe_tstat = expected_sharpe / expected_sharpe_se
    rho1 = np.corrcoef(net_return[:-1], net_return[1:])[0, 1]
    expected_sharpe_adj = expected_sharpe * sqrt((1.0 - rho1) / (1.0 + rho1))

    assert metrics["sharpe"] == pytest.approx(expected_sharpe)
    assert metrics["active_return"] == pytest.approx(expected_active_return)
    assert metrics["tracking_error"] == pytest.approx(expected_tracking_error)
    assert metrics["information_ratio"] == pytest.approx(expected_information_ratio)
    assert metrics["sharpe_se"] == pytest.approx(expected_sharpe_se)
    assert metrics["sharpe_tstat"] == pytest.approx(expected_sharpe_tstat)
    assert metrics["sharpe_ci_lower"] == pytest.approx(expected_sharpe - 1.96 * expected_sharpe_se)
    assert metrics["sharpe_ci_upper"] == pytest.approx(expected_sharpe + 1.96 * expected_sharpe_se)
    assert metrics["sharpe_adj_autocorr"] == pytest.approx(expected_sharpe_adj)


def test_sharpe_standard_error_is_annualized_like_the_sharpe() -> None:
    # Hand values: mean 0.005, sample std sqrt(1.1e-3 / 3), SR_p = 0.2611164839,
    # per-period SE sqrt((1 + SR_p^2 / 2) / 4) = 0.5084513028, annualized x sqrt(252).
    ctx = _ctx(net_return=np.array([0.01, -0.01, 0.03, -0.01], dtype=np.float64))
    metrics = compute_metrics(ctx, ["sharpe", "sharpe_se", "sharpe_tstat", "sharpe_ci_lower"])
    assert metrics["sharpe"] == pytest.approx(0.2611164839335467 * sqrt(252.0), rel=1e-12)
    assert metrics["sharpe_se"] == pytest.approx(8.07141420525098, rel=1e-12)
    assert metrics["sharpe_tstat"] == pytest.approx(0.2611164839335467 / 0.5084513027544795, rel=1e-12)
    assert metrics["sharpe_ci_lower"] == pytest.approx(metrics["sharpe"] - 1.96 * 8.07141420525098, rel=1e-12)


def test_tracking_error_and_information_ratio_return_zero_for_zero_active_risk() -> None:
    net_return = np.array([0.01, 0.01, 0.01], dtype=np.float64)
    ctx = _ctx(net_return=net_return, benchmark_return=net_return.copy())

    metrics = compute_metrics(ctx, ["tracking_error", "information_ratio"])

    assert metrics["tracking_error"] == 0.0
    assert metrics["information_ratio"] == 0.0


def test_sharpe_significance_metrics_return_zero_for_insufficient_data() -> None:
    net_return = np.array([0.01], dtype=np.float64)
    ctx = _ctx(net_return=net_return)

    metrics = compute_metrics(
        ctx,
        ["sharpe_se", "sharpe_tstat", "sharpe_ci_lower", "sharpe_ci_upper", "sharpe_adj_autocorr"],
    )

    assert metrics["sharpe_se"] == 0.0
    assert metrics["sharpe_tstat"] == 0.0
    assert metrics["sharpe_ci_lower"] == 0.0
    assert metrics["sharpe_ci_upper"] == 0.0
    assert metrics["sharpe_adj_autocorr"] == 0.0


def test_sharpe_adjusted_autocorr_returns_zero_when_lag1_autocorr_undefined() -> None:
    net_return = np.array([0.01, 0.01, 0.01, 0.01], dtype=np.float64)
    ctx = _ctx(net_return=net_return)

    metrics = compute_metrics(ctx, ["sharpe_adj_autocorr"])

    assert metrics["sharpe_adj_autocorr"] == 0.0


def test_compute_metrics_rejects_unknown_metric_name() -> None:
    ctx = _ctx(net_return=np.array([0.01, 0.02], dtype=np.float64))

    with pytest.raises(ValueError, match="Unknown metric"):
        compute_metrics(ctx, ["unknown_metric"])


def test_sortino_equal_losses_and_single_loss_have_nonzero_downside() -> None:
    # Four observations: mean=.025, downside RMS=.1/sqrt(2), ratio=sqrt(31.5).
    result = compute_metrics(_ctx(net_return=np.array([.2, -.1, -.1, .1])), ["sortino"])
    assert result["sortino"] == pytest.approx(sqrt(31.5), rel=1e-12)
    # Two observations: mean=.05, downside RMS=.1/sqrt(2).
    result = compute_metrics(_ctx(net_return=np.array([.2, -.1])), ["sortino"])
    assert result["sortino"] == pytest.approx(sqrt(126), rel=1e-12)
