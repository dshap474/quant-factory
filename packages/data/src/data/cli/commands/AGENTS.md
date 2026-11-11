# cli commands
- What: Typer command modules for dataset, schema, and operational-surface commands.
- Why: keeps each CLI command group small and discoverable.
- Keep: command-local parsing and delegation to `data.api`.
- Avoid: adding hidden runtime behavior that bypasses the API layer.
