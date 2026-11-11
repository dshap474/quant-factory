# example feature family

Category `example`, published to `db/features/1d/example/`. Reads the derived `example.prices.derived_1d` table
(see `packages/data/extensions/datasets/example`) and emits one row per `(timestamp, asset)`:

| Column | Meaning |
| --- | --- |
| `close` | Yahoo auto-adjusted close |
| `ret_1d` | `close / close[-1] - 1` per asset |
| `mom_30d` | `close / close[-30] - 1` per asset (bars, not calendar days) |

```bash
uv run qf-features publish example
```
