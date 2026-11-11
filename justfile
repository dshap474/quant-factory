# Repository commands. USAGE: just help | just dev | just kill
set shell := ["bash", "-cu"]

# List every public command (dev/kill manage the Viz app).
help:
    @just --list

# Install the Python development environment.
bootstrap:
    uv sync --frozen --group dev
    git config core.hooksPath .githooks

# Start or reuse Viz and print its URL; DEV_OPEN=1 also opens a browser.
dev:
    uv run python apps/viz/scripts/dev.py start

# Stop this checkout's Viz API, web, and optional control processes.
kill:
    uv run python apps/viz/scripts/dev.py stop

# Type-check the platform configuration package.
type:
    uv run ty check packages/platform/config/src/config

# Run the default repository tests.
test:
    uv run pytest tests/boundary tests/workflow -q

# Run all repository test groups.
test-all:
    uv run pytest tests -q

# Verify package boundaries.
test-boundary:
    uv run pytest tests/boundary -q -m boundary --timeout=10

# Verify repository workflows.
test-workflow:
    uv run pytest tests/workflow -q -m workflow --timeout=60

# Run production-package tests.
test-production:
    uv run --package quant-factory-production pytest packages/production/tests -q

# Verify package contracts.
test-contracts:
    uv run pytest tests/contracts -q --timeout=30

# Run repository tests in parallel.
test-parallel:
    uv run pytest tests/boundary tests/workflow -q -n auto

# Audit Python dependency vulnerabilities. PYSEC-2026-4217 (fsspec's unused Kerchunk
# reference parser) stays ignored while nautilus-trader 1.224.0 caps fsspec at 2026.1.0.
security:
    uv run pip-audit --ignore-vuln PYSEC-2026-4217

# Run the standard local CI checks.
ci:
    just type
    just test-production
    just test-boundary
    just test-workflow
