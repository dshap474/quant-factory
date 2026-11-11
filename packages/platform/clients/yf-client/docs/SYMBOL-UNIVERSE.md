# SYMBOL-UNIVERSE – Yahoo Finance coverage via `yf-client`

This document describes how to approximate and interrogate the **symbol universe** available through Yahoo Finance using `yf-client`. Yahoo does **not** expose a single “all symbols” API; instead, coverage is stitched together from multiple sources.

---

## 1. What counts as the “symbol universe” here?

For `yf-client`, the practical universe is:

- All symbols that:
  - Can be resolved by `YFinanceClient.get_history()` / `get_quote()`, and
  - Are reachable via either:
    - `yfinance`’s built-in helper lists (`yf.tickers_*`), and/or
    - Yahoo Finance public screeners (query2 “predefined” endpoints), and/or
    - Ad‑hoc symbol lists you choose to seed (e.g. from major indices).

There is **no** official “download every ticker” endpoint, so everything below is heuristic and best‑effort.

---

## 2. Current discovery mechanisms

### 2.1. `yfinance` helper functions

The test `tests/test_export_all_tickers.py` shows the first strategy:

- Introspect `yfinance` for helpers named `tickers_*` and call each to union their results:
  - Examples (depending on the installed `yfinance` version):
    - `yf.tickers_sp500()` – S&P 500 constituents
    - `yf.tickers_nasdaq()` – NASDAQ 100 / broader NASDAQ lists
    - `yf.tickers_dow()` – Dow Jones constituents
    - `yf.tickers_other_*()` – region- or index-specific lists
- For each helper:
  - Iterate its returned tickers
  - Normalize to `str.strip().upper()`
  - Add to a `Set[str]` of unique symbols

**Pros**
- Simple, versioned with `yfinance`.
- Focused on widely‑used indices.

**Cons**
- Not exhaustive; relies entirely on which `tickers_*` helpers `yfinance` exposes.

### 2.2. Yahoo Finance “predefined screener” API

When helpers are missing or incomplete, the tests fall back to Yahoo’s public screener endpoint:

- Base URL: `https://query2.finance.yahoo.com/v1/finance/screener/predefined/saved`
- Example params:
  - `scrIds`: comma‑separated list of prebuilt screen IDs
  - `count`: page size (e.g. `250`)
- Example screen IDs used in tests:
  - `most_actives`
  - `day_gainers`
  - `day_losers`
  - `undervalued_growth_stocks`
  - `undervalued_large_caps`
  - `growth_technology_stocks`
  - `aggressive_small_caps`
  - `small_cap_gainers`
  - `most_shorted_stocks`

From the response:

- Navigate `finance.result[*].quotes[*].symbol`
- Normalize and union into the symbol set.

**Pros**
- Uses Yahoo’s own curated universes (actively traded, thematic screens).

**Cons**
- Still **not** a full reference universe.
- Biased toward liquid / popular U.S. names unless more screeners are added.

---

## 3. Existing tooling in this repo

The integration test `tests/test_export_all_tickers.py` already implements a basic “universe export” flow:

- Discovers symbols via `yfinance.tickers_*` helpers and/or the screener API.
- Writes them to:
  - `all_tickers.csv` in pytest's temporary directory
- Asserts that at least some symbols were discovered.

This gives:

- A reproducible CSV of “known” tickers at a point in time.
- A starting point for more detailed analysis (sector, country, listing status, etc.).

---

## 4. Observations

Based on the existing export test and the design of `yf-client`:

- **Universe construction is incremental and heuristic**:
  - Major U.S. indices and popular global indices via `tickers_*`.
  - High‑activity and thematic sets via screeners.
- **No built‑in pagination or cursor** for “all symbols”:
  - Screeners each return up to `count` results.
  - To go deeper, you would:
    - Add more screener IDs (e.g., region‑specific, sector‑specific).
    - Integrate external symbol lists (e.g. exchange reference files) and then *validate* them via `get_quote()` / `get_history()`.

This document does not count total unique symbols or break coverage down by exchange,
country, or asset type.

---

## 5. How to extend the investigation

Ways to extend it:

1. **Quantify the universe size**
   - Count unique symbols in an exported `all_tickers.csv`, with rough breakdowns if available.

2. **Enrich symbols with `get_info`**
   - Sample or batch through the CSV using `YFinanceClient.get_info(symbol)` to collect:
     - `exchange`, `sector`, `industry`, `market_cap`, `country`, etc.
   - Persist enriched data to a secondary CSV or parquet for analysis.

3. **Add more screeners / lists**
   - Identify additional Yahoo screener IDs (e.g., region‑ or sector‑specific).
   - Optionally ingest external official symbol lists (NYSE, NASDAQ, LSE, etc.) and validate them via `get_quote()` to see which are active.

4. **Track stability over time**
   - Periodically rerun the export flow and compare:
     - New symbols vs. removed symbols.
     - Changes in mapping (e.g., delistings, ticker changes).

