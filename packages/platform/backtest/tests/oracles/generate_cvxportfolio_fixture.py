"""Offline cvxportfolio oracle fixture generator for the ordinary ledger.

Constructs all market data in memory, forces cash returns to zero, performs no
network download, and prints a frozen multi-asset current-equity fixture plus
provenance. Normal tests consume only the frozen numeric values; this module is
not named ``test_*`` and must never be imported by collected tests.

cvxportfolio is used as a **price-only** cross-check. Linear trading costs are
intentionally excluded: a two-period microfixture did not confirm identical
public-API cost semantics with the ledger's gross non-CASH turnover convention.
cvxportfolio does not verify ledger costs or perpetual funding.

USAGE:
    uv run --isolated --with cvxportfolio==1.5.1 \\
      python packages/platform/backtest/tests/oracles/generate_cvxportfolio_fixture.py

Published PyPI wheel SHA-256 (cvxportfolio 1.5.1):
    9c02954c23c095b59a97959eff8b757f164f78e159a5d630ce43ea36c14d0619
"""

from __future__ import annotations

import importlib.metadata
import math
import sys

# --------------------------------------------------------------------------- #
# Fixture market data (in-memory only)
# --------------------------------------------------------------------------- #

INITIAL_VALUE = 1_000_000.0
PRICES = {
    "A": [100.0, 101.0, 103.0, 102.0, 105.0],
    "B": [50.0, 49.0, 51.0, 52.0, 50.0],
}
WEIGHTS = {
    "A": [0.6, 0.5, 0.4, 0.55, 0.55],
    "B": [0.4, 0.5, 0.6, 0.45, 0.45],
}
PUBLISHED_WHEEL_SHA256 = "9c02954c23c095b59a97959eff8b757f164f78e159a5d630ce43ea36c14d0619"


# --------------------------------------------------------------------------- #
# Independent reference formulation (stdlib only)
# --------------------------------------------------------------------------- #


def ordinary_ledger_equity(
    *,
    prices: dict[str, list[float]],
    weights: dict[str, list[float]],
    initial: float,
) -> list[float]:
    """Price-only current-equity ordinary ledger (no costs, no funding)."""
    assets = list(prices)
    n = len(next(iter(prices.values())))
    qty = {a: 0.0 for a in assets}
    cash = float(initial)
    equity = [cash]
    for i in range(n - 1):
        p_i = {a: prices[a][i] for a in assets}
        p_n = {a: prices[a][i + 1] for a in assets}
        w_i = {a: weights[a][i] for a in assets}
        current = {a: qty[a] * p_i[a] for a in assets}
        e_pre = cash + sum(current.values())
        target = {a: w_i[a] * e_pre for a in assets}
        qty = {a: target[a] / p_i[a] for a in assets}
        cash = e_pre - sum(target.values())
        price_pnl = sum(target[a] * (p_n[a] / p_i[a] - 1.0) for a in assets)
        e_next = e_pre + price_pnl
        cash = e_next - sum(qty[a] * p_n[a] for a in assets)
        equity.append(e_next)
    return equity


# --------------------------------------------------------------------------- #
# cvxportfolio differential oracle
# --------------------------------------------------------------------------- #


def cvxportfolio_equity() -> tuple[str, list[float]]:
    """Run the public cvxportfolio simulator on explicit in-memory returns."""
    import cvxportfolio as cvx  # ty: ignore[unresolved-import]
    import pandas as pd

    version = importlib.metadata.version("cvxportfolio")
    index = pd.date_range("2024-01-01", periods=len(PRICES["A"]), freq="D")
    prices = pd.DataFrame(PRICES, index=index, dtype=float)

    # cvxportfolio applies returns at row i after the row-i target. Retain a final
    # zero-return row so its reported value series has the ledger's T points.
    returns = prices.shift(-1).div(prices).sub(1.0).fillna(0.0)
    returns["cash"] = 0.0
    targets = pd.DataFrame(WEIGHTS, index=index, dtype=float)
    targets["cash"] = 1.0 - targets.sum(axis=1)

    simulator = cvx.MarketSimulator(
        returns=returns,
        costs=[],
        cash_key="cash",
        min_history=pd.Timedelta(0),
        round_trades=False,
    )
    result = simulator.backtest(
        cvx.FixedWeights(targets),
        initial_value=INITIAL_VALUE,
    )
    return version, [float(value) for value in result.v.to_list()]


# --------------------------------------------------------------------------- #
# Entry
# --------------------------------------------------------------------------- #


def main() -> int:
    try:
        version, cvx_equity = cvxportfolio_equity()
    except ImportError as exc:
        print(f"cvxportfolio is required: {exc}", file=sys.stderr)
        print(
            "Run: uv run --isolated --with cvxportfolio==1.5.1 "
            "python packages/platform/backtest/tests/oracles/generate_cvxportfolio_fixture.py",
            file=sys.stderr,
        )
        return 1

    reference_equity = ordinary_ledger_equity(
        prices=PRICES,
        weights=WEIGHTS,
        initial=INITIAL_VALUE,
    )
    if len(cvx_equity) != len(reference_equity) or any(
        not math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-6)
        for actual, expected in zip(cvx_equity, reference_equity, strict=True)
    ):
        print(f"cvxportfolio={cvx_equity!r}", file=sys.stderr)
        print(f"reference={reference_equity!r}", file=sys.stderr)
        print("cvxportfolio price path disagrees with the independent reference", file=sys.stderr)
        return 1

    print("# ordinary-ledger cvxportfolio fixture (price-only)")
    print(f"cvxportfolio_version = {version!r}")
    print(f"published_cvxportfolio_wheel_sha256 = {PUBLISHED_WHEEL_SHA256!r}")
    print("source_tag = 'in-memory market data; cash returns forced to 0; no network'")
    print("scope = 'price-only; costs and perpetual funding are NOT verified by cvxportfolio'")
    print(f"initial_value = {INITIAL_VALUE!r}")
    print(f"prices = {PRICES!r}")
    print(f"weights = {WEIGHTS!r}")
    print(f"cvxportfolio_equity_curve = {cvx_equity!r}")
    print(f"reference_equity_curve = {reference_equity!r}")
    print(f"terminal_equity = {cvx_equity[-1]!r}")
    print()
    print("# Paste cvxportfolio_equity_curve into test_ledger_engine._CVX_EQUITY_CURVE if regenerating")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
