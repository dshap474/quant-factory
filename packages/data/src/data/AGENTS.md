# data
- What: generalized package entrypoints plus `api`, `query`, `cli`, `config`, and `platform`.
- Why: keeps upstream raw/derived data work behind one dataset control plane.
- Keep: public imports narrow and route behavior into the owning child folder. Use `data.query` for read-only parquet access; use `data.api` for dataset control-plane writes/materialization.
- Avoid: provider clients or family logic; those belong under `packages/data/extensions`.
