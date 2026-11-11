# qf-strategies Package Testing Guide

## Overview

This package follows the **Hermetic, Ephemeral, Agent-Ready Testing Standard**.

Tests are organized into tiers:
- **Unit tests**: Hermetic, no network, fast execution
- **Extension tests**: an installation's own catalog and family integration under `extensions/`

## Quick Start

```bash
# Run unit tests (from repo root)
cd /path/to/quant-factory && uv run pytest packages/strategies/tests -v


# Run with coverage
uv run pytest packages/strategies/tests --cov=strategies --cov-report=term-missing
```

## Test Structure

```
tests/
├── test_contracts.py             # StrategyWeights contract validation
├── test_version_conformance.py   # every active version has the AGENTS.md §5 shape
└── unit/                         # hermetic unit tests, one file per src module
```

Unit tests are hermetic (no network), fast, and isolated.

## Markers

- `@pytest.mark.slow` - Slow tests (if any)
- `@pytest.mark.integration` - Integration tests (future)

## CI Integration

The test suite is designed for CI:
- All tests are deterministic
- No flaky tests allowed
- Fast execution (< 5 seconds total)
