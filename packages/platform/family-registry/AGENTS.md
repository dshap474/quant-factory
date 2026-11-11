# family-registry

Read [platform rules](../AGENTS.md).

- Domain-neutral: no imports from `signals`, `strategies`, or any family. Consumers
  subclass `FamilyRegistry`; package-specific policy stays in the subclass.
- No import-time I/O. Discovery runs only on `populate()` or first catalog read.
- Run `uv run pytest packages/platform/family-registry` plus the signals and
  strategies suites when changing behavior.
