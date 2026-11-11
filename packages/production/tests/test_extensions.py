"""Verify deterministic Production extension loading and zero-overlay behavior.

USAGE: ``uv run --package quant-factory-production pytest packages/production/tests/test_extensions.py -q``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from production.contracts import DeploymentValidationError
from production.registry import UnknownRuntimeAdapterError

from production.extensions import load_production_extensions

# --------------------------------------------------------------------------- #
# Zero-extension core
# --------------------------------------------------------------------------- #


def test_core_cli_runtime_status_and_activation_failures_without_extensions(tmp_path: Path) -> None:
    source_root = tmp_path / "src"
    shutil.copytree(Path(__file__).resolve().parents[1] / "src" / "production", source_root / "production")
    repository = tmp_path / "repository"
    (repository / "packages/strategies").mkdir(parents=True)
    (repository / "pyproject.toml").write_text("[project]\nname = 'fixture'\n")
    script = f"""
from pathlib import Path
from types import SimpleNamespace
import production
import production.cli as cli
import production.runtime as runtime
import production.status as status
from production.registry import UnknownRuntimeAdapterError, UnsupportedActivationSchemaError, parse_activation_receipt

definition = SimpleNamespace(
    strategy=SimpleNamespace(family='example-family'),
    execution=SimpleNamespace(venue='missing-adapter'),
)
runtime.validate_deployment = lambda path, root: definition
runtime.deployment_fingerprint = lambda path, root: 'a' * 64
try:
    runtime.run_once(Path('deployment.yaml'), Path({str(repository)!r}), live=False, state_root=Path('state'))
except UnknownRuntimeAdapterError:
    pass
else:
    raise AssertionError('runtime did not return typed missing-adapter error')

status.validate_deployment = lambda path, root: definition
status.deployment_fingerprint = lambda path, root: 'a' * 64
try:
    status.production_status(Path('deployment.yaml'), Path({str(repository)!r}), Path('state'))
except UnknownRuntimeAdapterError:
    pass
else:
    raise AssertionError('status did not return typed missing-adapter error')

cli.find_repo_root = lambda path: Path({str(repository)!r})
cli.validate_deployment = lambda path, root: definition
cli.deployment_fingerprint = lambda path, root: 'a' * 64
try:
    cli._run_activation_apply(SimpleNamespace(
        deployment=Path('deployment.yaml'),
        confirm_fingerprint='a' * 64,
        repo_root=Path({str(repository)!r}),
    ))
except UnknownRuntimeAdapterError:
    pass
else:
    raise AssertionError('activation did not return typed missing-adapter error')

try:
    parse_activation_receipt({{'schema_version': 99}})
except UnsupportedActivationSchemaError:
    pass
else:
    raise AssertionError('activation schema did not return typed unsupported error')
"""
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(source_root)
    subprocess.run([sys.executable, "-c", script], cwd=tmp_path, env=environment, check=True)
    help_result = subprocess.run(
        [sys.executable, "-m", "production", "--help"],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert help_result.returncode == 0, help_result.stderr
    list_result = subprocess.run(
        [sys.executable, "-m", "production", "list", "--repo-root", str(repository)],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert list_result.returncode == 0, list_result.stderr
    assert list_result.stdout.strip() == "No deployment bundles found."


# --------------------------------------------------------------------------- #
# Loader contracts
# --------------------------------------------------------------------------- #


def _write_adapter(path: Path, venue_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'''"""Test adapter."""
from production.registry import RuntimeAdapter, RuntimeExecutionResult, register_runtime_adapter

def register():
    register_runtime_adapter(RuntimeAdapter(
        venue_id={venue_id!r},
        host_trading_gate="TEST_GATE",
        dry_run_activation_required=False,
        activation_compatible=lambda definition, activation: True,
        execute=lambda context, refresh: RuntimeExecutionResult(execution={{}}),
    ))
'''
    )


def test_loader_is_idempotent_and_skips_underscore_entries(tmp_path: Path) -> None:
    _write_adapter(tmp_path / "adapters/example.py", "loader-example")
    _write_adapter(tmp_path / "adapters/_ignored.py", "loader-ignored")
    load_production_extensions(tmp_path)
    load_production_extensions(tmp_path)
    from production.registry import runtime_adapter

    assert runtime_adapter("loader-example").venue_id == "loader-example"
    with pytest.raises(UnknownRuntimeAdapterError, match="loader-ignored"):
        runtime_adapter("loader-ignored")


def test_loader_rejects_duplicate_adapter_ids(tmp_path: Path) -> None:
    _write_adapter(tmp_path / "adapters/first.py", "loader-duplicate")
    _write_adapter(tmp_path / "adapters/second.py", "loader-duplicate")
    with pytest.raises(DeploymentValidationError, match="duplicate runtime adapter ID"):
        load_production_extensions(tmp_path)
