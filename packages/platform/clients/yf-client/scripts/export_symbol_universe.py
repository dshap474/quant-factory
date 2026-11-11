from __future__ import annotations

"""
Export / refresh a best-effort symbol universe for yf-client.

This script:
  - Loads the existing docs/symbols.json (if present).
  - Queries Yahoo Finance via:
      * yfinance `tickers_*` helper functions (if available), and
      * the public predefined screener API
        (https://query2.finance.yahoo.com/v1/finance/screener/predefined/saved)
  - Unions and de-duplicates all discovered tickers.
  - Writes back docs/symbols.json with updated metadata and a sorted symbol list.

Usage (from the yf-client package root):

    uv run python scripts/export_symbol_universe.py

You can run this periodically to grow / refresh the investigation universe.
"""

import json
import sys
from datetime import date
from pathlib import Path
from typing import Iterable, List, Set
from urllib import parse, request

import yfinance as yf  # type: ignore


PREDEFINED_SCREENERS: List[str] = [
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

SCREENER_BASE_URL = "https://query2.finance.yahoo.com/v1/finance/screener/predefined/saved"


def _docs_symbols_path() -> Path:
    here = Path(__file__).resolve()
    package_root = here.parent.parent
    return package_root / "docs" / "symbols.json"


def _load_existing_symbols(path: Path) -> Set[str]:
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        raw_symbols = data.get("symbols", [])
        return {str(s).strip().upper() for s in raw_symbols if str(s).strip()}
    except Exception:
        # If the file is malformed, start fresh rather than failing hard.
        return set()


def _discover_from_yfinance_helpers() -> Set[str]:
    symbols: Set[str] = set()
    helper_names = [
        name for name in dir(yf) if name.startswith("tickers_") and callable(getattr(yf, name, None))
    ]
    for name in sorted(helper_names):
        func = getattr(yf, name)
        try:
            candidates = func()
        except Exception:
            continue
        for s in candidates or []:
            if isinstance(s, str):
                cleaned = s.strip().upper()
                if cleaned:
                    symbols.add(cleaned)
    return symbols


def _discover_from_screeners() -> Set[str]:
    symbols: Set[str] = set()
    for screener_id in PREDEFINED_SCREENERS:
        params = {"scrIds": screener_id, "count": 250}
        url = f"{SCREENER_BASE_URL}?{parse.urlencode(params)}"
        try:
            with request.urlopen(url, timeout=30) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except Exception:
            # Network errors, rate limits (HTTP 429), etc. are treated as soft failures.
            continue

        finance = payload.get("finance", {})
        results = finance.get("result", []) or []
        for group in results:
            for q in group.get("quotes", []) or []:
                sym = q.get("symbol")
                if isinstance(sym, str):
                    cleaned = sym.strip().upper()
                    if cleaned:
                        symbols.add(cleaned)
    return symbols


def _write_symbols(path: Path, symbols: Iterable[str]) -> None:
    symbols_list = sorted({s.strip().upper() for s in symbols if s.strip()})

    payload = {
        "metadata": {
            "description": (
                "Seeded symbol universe for yf-client based on widely traded US and "
                "global equities and ETFs. This is an investigation artifact, not an "
                "authoritative list."
            ),
            "source": "yf-client SYMBOL-UNIVERSE investigation (export_symbol_universe.py)",
            "note": (
                "This file is intentionally partial and should be extended over time "
                "using the strategies described in SYMBOL-UNIVERSE.md "
                "(yfinance tickers_* helpers, Yahoo screeners, and validated external lists)."
            ),
            "last_updated": date.today().isoformat(),
            "symbol_count": len(symbols_list),
        },
        "symbols": symbols_list,
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def main() -> int:
    docs_path = _docs_symbols_path()

    existing = _load_existing_symbols(docs_path)
    print(f"Loaded {len(existing)} existing symbols from {docs_path}", file=sys.stderr)

    from_helpers = _discover_from_yfinance_helpers()
    print(f"Discovered {len(from_helpers)} symbols from yfinance tickers_* helpers", file=sys.stderr)

    from_screeners = _discover_from_screeners()
    print(f"Discovered {len(from_screeners)} symbols from Yahoo predefined screeners", file=sys.stderr)

    combined: Set[str] = set(existing)
    combined.update(from_helpers)
    combined.update(from_screeners)

    print(f"Total combined unique symbols: {len(combined)}", file=sys.stderr)

    _write_symbols(docs_path, combined)
    print(f"Wrote updated symbol universe to {docs_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

