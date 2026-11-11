# platform/config

## Codebase Architecture
- Use `packages/platform/config` for non-secret process settings and path constants. Do not add secret handling or `.env` loading here.
- Module: `config`.
- Key APIs: `get_repo_root`, `QUANT_DB_ROOT`, `QUANT_SIGNALS_DIR`, `ROOT_QUANT_FACTORY`, schema helpers (`load_schema_index`, `get_domain_index`), and `get_logger`. Authenticated processes read credentials from the process environment.
- Keep this package small and explicit; avoid hidden indirection.

## Docs
- When local changes alter this package's structure, commands, or boundaries, update its `README.md` and `AGENTS.md`.

## Commands
- Verify through the consumers' tests: `uv run pytest tests/contracts -q`.

## Execution
- Settings come from the existing process environment. This package never reads a repository `.env` file.
- Import remaining non-secret config values from `config`; do not add new provider-secret globals.
- Keep defaults deterministic (`QUANT_DB_ROOT` defaults to `<repo>/db`).

## Gotchas

- `settings.py` is the repo's write-address (`QUANT_DB_ROOT`,
  `QUANT_SIGNALS_DIR`) and holds a live capital gate snapshot — and this
  package has no tests of its own. Treat any edit there as a repo-wide
  change: run `uv run pytest tests/contracts -q` and eyeball every default
  you touched.
