# example dataset family

Credential-free daily prices from Yahoo Finance (via `yf-client`) for `BTC-USD`, `SPY`, `QQQ`, `GLD` and `TLT`.
It is the first link of the public example chain: `data/example` → `features/example`, which both `signals/example` and `strategies/_example` read.

| Dataset | Path | Columns |
| --- | --- | --- |
| `example.prices.sync_1d` | `db/data/raw/1d/example/prices/` | `timestamp, symbol, open, high, low, close, volume` |
| `example.prices.derived_1d` | `db/data/derived/1d/example/prices/` | `timestamp, asset, close` |

Prices are Yahoo's auto-adjusted series. Row `T` is the completed bar for `T`; the current UTC day is never written.
Timing caveat: adjusted series are rewritten when later dividends and splits arrive, so a past row's
level can differ from what was known at that close. Returns are unaffected between adjustments; a
family that needs strict point-in-time levels should land unadjusted bars and its own adjustment
factors instead.
Asset ids are canonical: `BTC-USD` → `crypto:BTC`, `SPY` → `us:SPY`.

```bash
uv run qf-data dataset sync --spec-json '{"dataset_id":"example.prices.sync_1d","family":"example","kind":"data/raw","target":"canonical_data_raw"}'
uv run qf-data dataset sync --spec-json '{"dataset_id":"example.prices.derived_1d","family":"example","kind":"data/derived","target":"canonical_data_derived"}'
```

Pass `"assets": [...]` (Yahoo symbols) to sync a different list.
