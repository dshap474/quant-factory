# platform
- What: shared contracts, errors, ingestion, schema, storage, and DB helpers.
- Why: holds mechanics reused by more than one data family.
- Keep: small stable primitives with clear callers across families.
- Avoid: provider adapters, one-family business logic, or public API re-export decisions here.
