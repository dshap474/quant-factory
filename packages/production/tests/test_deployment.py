"""Test deployment discovery against a hermetic repository fixture.

Usage:
    uv run --package quant-factory-production pytest packages/production/tests/test_deployment.py -q
"""

from pathlib import Path

import pytest
from production.deployment import discover_deployments, validate_deployment

from production import DeploymentValidationError

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _write_repository_family(repo_root: Path, family: str = "example-family") -> None:
    family_root = repo_root / "packages" / "strategies" / "extensions" / "lib" / family
    (family_root / "optimization" / "v001").mkdir(parents=True)
    (family_root / "presets").mkdir()
    (family_root / "presets" / "default.yaml").write_text("name: default\n")
    runner = family_root / "src" / "example_family" / "runner.py"
    runner.parent.mkdir(parents=True)
    runner.write_text('"""Test runner placeholder."""\n')
    (runner.parent / "__init__.py").write_text('"""Test family package."""\n')
    (repo_root / "pyproject.toml").write_text("[tool.uv.workspace]\n")
    (repo_root / "packages" / "strategies" / "pyproject.toml").write_text(
        """[tool.hatch.build.targets.wheel]
packages = ["src/strategies"]

[tool.hatch.build.targets.sdist]
exclude = ["/extensions/**"]
"""
    )


def _write_deployment(deployments_root: Path, family: str = "example-family") -> Path:
    path = deployments_root / family / "deployment.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(
        """schema_version: 2
strategy:
  family: example-family
  memory_version: v001
  preset: default
runtime:
  schedule: "*-*-* 00:05:00"
  timezone: UTC
  max_decision_age_seconds: 60
execution:
  venue: example-venue
  instruments:
    ASSET: EXAMPLE-PERP
"""
    )
    return path


# --------------------------------------------------------------------------- #
# Discovery tests
# --------------------------------------------------------------------------- #


def test_discovery_returns_only_direct_strategy_bundle(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    deployments_root = repo_root / "packages" / "production" / "extensions" / "deployments"
    _write_repository_family(repo_root)
    path = _write_deployment(deployments_root)
    nested_release = path.parent / "releases" / "r001" / "deployment.yaml"
    nested_release.parent.mkdir(parents=True)
    nested_release.write_text(path.read_text())

    deployments = discover_deployments(deployments_root, repo_root)

    assert len(deployments) == 1
    assert deployments[0][0] == path.resolve()
    assert deployments[0][1].strategy.family == "example-family"


def test_bundle_folder_must_match_family(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    deployments_root = repo_root / "packages" / "production" / "extensions" / "deployments"
    _write_repository_family(repo_root)
    path = _write_deployment(deployments_root, family="wrong-folder")

    with pytest.raises(DeploymentValidationError, match="folder name must match"):
        validate_deployment(path, repo_root)


def test_missing_packaged_preset_blocks_deployment(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    deployments_root = repo_root / "packages" / "production" / "extensions" / "deployments"
    _write_repository_family(repo_root)
    path = _write_deployment(deployments_root)
    (repo_root / "packages/strategies/extensions/lib/example-family/presets/default.yaml").unlink()

    with pytest.raises(DeploymentValidationError, match="preset does not exist"):
        validate_deployment(path, repo_root)


def test_missing_packaged_runner_blocks_deployment(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    deployments_root = repo_root / "packages" / "production" / "extensions" / "deployments"
    _write_repository_family(repo_root)
    path = _write_deployment(deployments_root)
    (repo_root / "packages/strategies/extensions/lib/example-family/src/example_family/runner.py").unlink()

    with pytest.raises(DeploymentValidationError, match="has no packaged runner"):
        validate_deployment(path, repo_root)


def test_public_artifact_leaking_extensions_blocks_deployment(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    deployments_root = repo_root / "packages" / "production" / "extensions" / "deployments"
    _write_repository_family(repo_root)
    path = _write_deployment(deployments_root)
    (repo_root / "packages/strategies/pyproject.toml").write_text(
        """[tool.hatch.build.targets.wheel]
packages = ["src/strategies", "extensions/lib/example-family/src/example_family"]

[tool.hatch.build.targets.sdist]
exclude = []
"""
    )

    with pytest.raises(DeploymentValidationError, match="public artifact boundary is invalid"):
        validate_deployment(path, repo_root)
