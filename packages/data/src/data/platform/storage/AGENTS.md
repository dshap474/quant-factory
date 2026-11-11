# platform storage
- What: feature store/catalog, parquet runtime, feature loading, and operational-surface registry checks.
- Why: centralizes shared storage mechanics used across families and operators.
- Keep: reusable persistence helpers, registry validation, and loader composition here.
- Avoid: provider fetching, family orchestration, or strategy-specific storage here.
