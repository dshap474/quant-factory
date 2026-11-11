"""Test the production operator command surface without external side effects.

Usage:
    uv run --package quant-factory-production pytest packages/production/tests/test_cli.py -q
"""

from pathlib import Path

import pytest
from production.cli import main

# --------------------------------------------------------------------------- #
# CLI tests
# --------------------------------------------------------------------------- #


def test_list_empty_library_has_no_side_effects(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "packages" / "strategies").mkdir(parents=True)
    (repo_root / "pyproject.toml").write_text("[tool.uv.workspace]\n")
    deployments_root = repo_root / "packages" / "production" / "extensions" / "deployments"
    deployments_root.mkdir(parents=True)

    result = main(
        [
            "list",
            "--repo-root",
            str(repo_root),
            "--deployments-root",
            str(deployments_root),
        ]
    )

    assert result == 0
    assert capsys.readouterr().out == "No deployment bundles found.\n"


def test_list_defaults_to_repo_library_from_subdirectory(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "packages" / "strategies").mkdir(parents=True)
    (repo_root / "pyproject.toml").write_text("[tool.uv.workspace]\n")
    (repo_root / "packages" / "production" / "extensions" / "deployments").mkdir(parents=True)
    subdirectory = repo_root / "packages" / "production"
    monkeypatch.chdir(subdirectory)

    result = main(["list", "--repo-root", str(repo_root)])

    assert result == 0
    assert capsys.readouterr().out == "No deployment bundles found.\n"


def test_validate_missing_definition_returns_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "packages" / "strategies").mkdir(parents=True)
    (repo_root / "pyproject.toml").write_text("[tool.uv.workspace]\n")

    result = main(
        [
            "validate",
            str(tmp_path / "missing" / "deployment.yaml"),
            "--repo-root",
            str(repo_root),
        ]
    )

    assert result == 2
    assert "deployment file does not exist" in capsys.readouterr().err


def test_activation_apply_requires_exact_fingerprint_confirmation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "packages/strategies").mkdir(parents=True)
    (repo_root / "pyproject.toml").write_text("[tool.uv.workspace]\n")
    monkeypatch.setattr("production.cli.deployment_fingerprint", lambda path, root: "a" * 64)

    result = main(
        [
            "activation",
            "apply",
            str(tmp_path / "deployment.yaml"),
            str(tmp_path / "receipt.yaml"),
            "--confirm-fingerprint",
            "b" * 64,
            "--repo-root",
            str(repo_root),
            "--state-root",
            str(tmp_path / "state"),
        ]
    )

    assert result == 2
    assert "fingerprint confirmation does not match" in capsys.readouterr().err
