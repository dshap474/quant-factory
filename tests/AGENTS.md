# tests

## Codebase Architecture
- Use top-level `tests/` for cross-package integration lanes; keep single-package unit tests in the owning package's `tests/` directory.
- Lanes: `boundary/` single-package boundary tests (fast, isolated), `workflow/` multi-package workflows, `contracts/` schema/type contract validation, `unit/` shared unit-test conftest and any cross-package unit tests, `fixtures/` shared fixtures.
- Mark boundary/workflow tests with their lane marker (`slow`, `mlx`, `statistical` are extra markers); `contracts/` and `unit/` are selected by path. `pytest.ini` enforces `--strict-markers`.
- New cross-package contracts that must block a merge need a `boundary/` test: `just ci` runs the type check and the production, boundary and workflow lanes; the full `contracts/` lane runs with `just test-contracts`.

## Commands
- Lanes are also exposed as `just test`, `just test-all`, `just test-boundary`, `just test-workflow`, `just test-contracts`.
- Single test: `uv run pytest tests/boundary/test_name.py::test_name -q`

## Execution
- Respect lane timeouts (boundary 10s, workflow 60s); keep slow tests out of the boundary lane.
- Use `fixtures/` for shared test data instead of duplicating fixtures per lane.
- Do not write canonical `db/` outputs from tests; route test artifacts through temporary paths.

