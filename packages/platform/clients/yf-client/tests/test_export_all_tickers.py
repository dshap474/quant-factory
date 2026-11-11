"""
All Tickers Export Test
---
packages/platform/clients/yf-client/tests/test_export_all_tickers.py
---
Integration test that attempts to enumerate a broad list of Yahoo Finance tickers
via yfinance's built-in ticker list helpers and exports them to CSV in a
temporary directory. Skipped unless YF_CLIENT_INTEGRATION=1. If enumeration is unavailable, the test fails
with a clear error (no mock data).
"""

import csv
import os
from pathlib import Path
from typing import Callable, Iterable, Set

import pytest


@pytest.mark.slow
@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("YF_CLIENT_INTEGRATION") != "1", reason="set YF_CLIENT_INTEGRATION=1 to call Yahoo Finance"
)
def test_export_all_tickers_to_csv(tmp_path: Path):
    """Enumerate tickers via yfinance helper functions and export to CSV."""
    try:
        import yfinance as yf  # type: ignore
    except Exception as e:  # pragma: no cover - environment import failure
        raise AssertionError(f"yfinance import failed: {e}")

    unique_symbols: Set[str] = set()

    # Primary approach (if yfinance exposes helpers)
    helper_names = [n for n in dir(yf) if n.startswith("tickers_") and callable(getattr(yf, n, None))]
    if helper_names:
        for name in sorted(helper_names):
            func: Callable[[], Iterable[str]] = getattr(yf, name)  # type: ignore
            try:
                symbols = func()
                for s in symbols:
                    if isinstance(s, str) and s.strip():
                        unique_symbols.add(s.strip().upper())
            except Exception:
                continue

    # Fallback approach: query Yahoo predefined screeners (public endpoints) and union results
    if not unique_symbols:
        import json
        from urllib import parse, request

        predefined_ids = [
            "most_actives",
            "day_gainers",
            "day_losers",
            "undervalued_growth_stocks",
            "undervalued_large_caps",
            "growth_technology_stocks",
            "aggressive_small_caps",
            "small_cap_gainers",
            "most_shorted_stocks",
        ]

        base = "https://query2.finance.yahoo.com/v1/finance/screener/predefined/saved"
        params = {"scrIds": ",".join(predefined_ids), "count": 250}
        url = f"{base}?{parse.urlencode(params)}"
        with request.urlopen(url, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        # Consolidate symbols from all screener results
        try:
            finance = data.get("finance", {})
            result = finance.get("result", [])
            for group in result:
                for q in group.get("quotes", []) or []:
                    sym = q.get("symbol")
                    if isinstance(sym, str) and sym.strip():
                        unique_symbols.add(sym.strip().upper())
        except Exception:
            pass

    # Basic validation — must have discovered at least some symbols
    if not unique_symbols:
        raise AssertionError("Failed to enumerate any tickers; cannot produce CSV.")

    output_path = tmp_path / "all_tickers.csv"

    with output_path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["symbol"])
        for symbol in sorted(unique_symbols):
            writer.writerow([symbol])

    # Assert CSV exists and contains data
    assert output_path.exists(), "Output CSV was not created"
    assert output_path.stat().st_size > 0, "Output CSV is empty"
