# platform ingestion
- What: dataset handler registry, request models, and shared ingestion mechanics.
- Why: powers `DatasetSpec` dispatch from API/CLI into family services.
- Keep: control-plane abstractions and reused ingestion helpers here.
- Avoid: provider-specific business rules unless they are already shared wrappers.
