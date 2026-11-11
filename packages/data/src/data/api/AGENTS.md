# api
- What: curated public Python surface for contracts, dataset ops, schema, storage, and surface checks.
- Why: gives callers one stable import path over internal family/platform modules.
- Keep: re-exports and thin boundary helpers only.
- Avoid: provider logic, family-specific orchestration, or direct parquet writes here.
