"""Load, discover, and statically validate tracked deployment bundles.

Usage:
    definition = validate_deployment(
        Path("packages/production/extensions/deployments/example/deployment.yaml"), repo_root
    )
"""

from __future__ import annotations

import hashlib
import json
import tomllib
from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

from production.contracts import (
    DeploymentDefinition,
    DeploymentValidationError,
)

# --------------------------------------------------------------------------- #
# Loading and discovery
# --------------------------------------------------------------------------- #


def load_deployment(path: Path) -> DeploymentDefinition:
    """Load one deployment definition without touching external systems."""

    definition_path = path.resolve()
    if not definition_path.is_file():
        raise DeploymentValidationError(f"deployment file does not exist: {definition_path}")
    try:
        raw = yaml.safe_load(definition_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise DeploymentValidationError(f"could not read deployment file {definition_path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise DeploymentValidationError("deployment document must contain a mapping")
    return DeploymentDefinition.from_mapping(raw)


def discover_deployments(
    deployments_root: Path,
    repo_root: Path,
) -> tuple[tuple[Path, DeploymentDefinition], ...]:
    """Discover direct ``deployments/<family>/deployment.yaml`` bundles."""

    root = deployments_root.resolve()
    if not root.is_dir():
        return ()

    deployments: list[tuple[Path, DeploymentDefinition]] = []
    for path in sorted(root.glob("*/deployment.yaml")):
        definition = validate_deployment(path, repo_root)
        deployments.append((path.resolve(), definition))
    return tuple(deployments)


# --------------------------------------------------------------------------- #
# Repository validation
# --------------------------------------------------------------------------- #


def validate_deployment(
    path: Path,
    repo_root: Path,
) -> DeploymentDefinition:
    """Validate a bundle contract and its canonical strategy references."""

    definition_path = path.resolve()
    definition = load_deployment(definition_path)
    family = definition.strategy.family
    if definition_path.name != "deployment.yaml":
        raise DeploymentValidationError("deployment definition must be named deployment.yaml")
    if definition_path.parent.name != family:
        raise DeploymentValidationError(
            f"deployment folder name must match strategy.family ({definition_path.parent.name!r} != {family!r})"
        )

    root = repo_root.resolve()
    family_root = root / "packages" / "strategies" / "extensions" / "lib" / family
    if not family_root.is_dir():
        raise DeploymentValidationError(f"strategy family does not exist: {family_root}")

    version = definition.strategy.memory_version
    version_paths = (
        family_root / "optimization" / version,
        family_root / "optimization" / "version" / version,
    )
    if not any(candidate.is_dir() for candidate in version_paths):
        raise DeploymentValidationError(f"strategy memory version {version!r} does not exist for {family!r}")

    preset_path = family_root / "presets" / f"{definition.strategy.preset}.yaml"
    if not preset_path.is_file():
        raise DeploymentValidationError(f"strategy preset does not exist: {preset_path}")

    runner_paths = tuple(family_root.glob("src/*/runner.py")) + tuple(family_root.glob("src/*/xs_runner.py"))
    if not runner_paths:
        raise DeploymentValidationError(f"strategy family has no packaged runner: {family_root / 'src'}")
    _validate_strategy_overlay(root, family, runner_paths)
    return definition


def deployment_fingerprint(path: Path, repo_root: Path) -> str:
    """Hash the resolved deployment, packaged strategy, promotion receipt, and canonical final."""
    definition_path = path.resolve()
    definition = validate_deployment(definition_path, repo_root)
    root = repo_root.resolve()
    family_root = root / "packages" / "strategies" / "extensions" / "lib" / definition.strategy.family
    preset = family_root / "presets" / f"{definition.strategy.preset}.yaml"
    packaged_sources = tuple(
        sorted(candidate for candidate in (family_root / "src").rglob("*.py") if candidate.is_file())
    )
    final_root = (
        root
        / "db"
        / "strategies"
        / definition.strategy.family
        / "versions"
        / definition.strategy.memory_version
        / "final"
    )
    if not final_root.is_dir():
        raise DeploymentValidationError(f"canonical strategy final does not exist: {final_root}")
    receipt = final_root / "promotion-receipt.json"
    _validate_promotion_receipt(receipt, definition)
    final_files = tuple(sorted(candidate for candidate in final_root.rglob("*") if candidate.is_file()))
    if not final_files:
        raise DeploymentValidationError(f"canonical strategy final contains no files: {final_root}")

    digest = hashlib.sha256()
    inputs = (("deployment.yaml", definition_path), ("preset.yaml", preset))
    inputs += tuple(
        (f"strategy-src/{candidate.relative_to(family_root / 'src')}", candidate) for candidate in packaged_sources
    )
    inputs += tuple((f"final/{candidate.relative_to(final_root)}", candidate) for candidate in final_files)
    for label, candidate in inputs:
        digest.update(label.encode("utf-8"))
        digest.update(b"\0")
        digest.update(candidate.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _validate_promotion_receipt(path: Path, definition: DeploymentDefinition) -> None:
    """Validate explicit operator promotion provenance without granting runtime authority."""
    if not path.is_file():
        raise DeploymentValidationError(f"canonical final is missing promotion receipt: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DeploymentValidationError(f"could not read promotion receipt: {path}") from exc
    required = {
        "schema_version",
        "family",
        "memory_version",
        "source_run_id",
        "source_manifest_sha256",
        "evidence",
        "promoted_at",
        "promoted_by",
    }
    if not isinstance(payload, dict) or set(payload) != required:
        raise DeploymentValidationError("promotion receipt fields do not match the required contract")
    if payload["schema_version"] != 1:
        raise DeploymentValidationError("promotion receipt schema_version must be 1")
    if payload["family"] != definition.strategy.family:
        raise DeploymentValidationError("promotion receipt family mismatch")
    if payload["memory_version"] != definition.strategy.memory_version:
        raise DeploymentValidationError("promotion receipt memory_version mismatch")
    if payload["evidence"] not in {"SUPPORTED", "FALSIFIED"}:
        raise DeploymentValidationError("promotion receipt evidence must be SUPPORTED or FALSIFIED")
    if not isinstance(payload["source_manifest_sha256"], str) or len(payload["source_manifest_sha256"]) != 64:
        raise DeploymentValidationError("promotion receipt source_manifest_sha256 must be a SHA-256 digest")
    for field in ("source_run_id", "promoted_at", "promoted_by"):
        if not isinstance(payload[field], str) or not payload[field].strip():
            raise DeploymentValidationError(f"promotion receipt {field} must be a non-empty string")


def _validate_strategy_overlay(
    repo_root: Path,
    family: str,
    runner_paths: tuple[Path, ...],
) -> None:
    """Verify private family importability and the public artifact boundary."""

    strategies_pyproject = repo_root / "packages" / "strategies" / "pyproject.toml"
    try:
        project = tomllib.loads(strategies_pyproject.read_text(encoding="utf-8"))
        targets = project["tool"]["hatch"]["build"]["targets"]
        wheel_packages = targets["wheel"]["packages"]
        sdist_excludes = targets["sdist"]["exclude"]
    except (OSError, KeyError, TypeError, tomllib.TOMLDecodeError) as exc:
        raise DeploymentValidationError(
            f"could not read strategies packaging metadata: {strategies_pyproject}"
        ) from exc

    public_boundary_valid = (
        wheel_packages == ["src/strategies"] and isinstance(sdist_excludes, list) and "/extensions/**" in sdist_excludes
    )
    if not public_boundary_valid:
        raise DeploymentValidationError("strategies public artifact boundary is invalid")

    family_src = repo_root / "packages" / "strategies" / "extensions" / "lib" / family / "src"
    for runner_path in runner_paths:
        try:
            relative = runner_path.relative_to(family_src)
        except ValueError as exc:
            raise DeploymentValidationError(f"strategy runner is outside its extension: {runner_path}") from exc
        if len(relative.parts) != 2 or relative.name not in {"runner.py", "xs_runner.py"}:
            raise DeploymentValidationError(f"strategy runner has an invalid extension path: {runner_path}")
        if not (runner_path.parent / "__init__.py").is_file():
            raise DeploymentValidationError(f"strategy runner package is not importable: {runner_path.parent}")


def find_repo_root(start: Path) -> Path:
    """Find the quant-factory root using explicit repository markers."""

    candidate = start.resolve()
    search = (candidate, *candidate.parents)
    for root in search:
        if (root / "pyproject.toml").is_file() and (root / "packages" / "strategies").is_dir():
            return root
    raise DeploymentValidationError(f"could not find quant-factory repository root from {candidate}")


def deployment_as_dict(definition: DeploymentDefinition) -> dict[str, Any]:
    """Return a JSON-serializable normalized deployment definition."""

    return asdict(definition)
