# Pipelines

This feature set publishes `db/features/1d/example/data.parquet`.
It reads derived data only; no raw path is read.

| Dataset handler | Output | Used For |
| --- | --- | --- |
| `packages/data/extensions/datasets/example/service.py` (`example.prices.derived_1d`) | `db/data/derived/1d/example/prices/data.parquet` | `close` per `crypto:BTC`, `us:SPY`, `us:QQQ`, `us:GLD`, `us:TLT`. |

There is no operator pipeline wrapper and no scheduled refresh. Sync `example.prices.sync_1d`, then
`example.prices.derived_1d`, through `qf-data dataset sync` (see the dataset README) before republishing.
