# example feature family — Feature Reference

Columns of the published panel at `db/features/1d/example/data.parquet`, one row per
`(timestamp, asset)`.

| Column | Type | Definition |
| --- | --- | --- |
| `timestamp` | datetime | Bar close, timezone-naive UTC |
| `asset` | string | Canonical asset id (e.g. `crypto:BTC`) |
| `close` | float64 | Auto-adjusted close from the derived example price table |
| `ret_1d` | float64 | `close / close[-1] - 1` per asset |
| `mom_30d` | float64 | `close / close[-30] - 1` per asset (bars, not calendar days) |
