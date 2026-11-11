"""Inspect tracked deployments and invoke explicit one-shot runtime operations.

USAGE: ``qf-production run-once <deployment> --dry-run``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from production.contracts import DeploymentValidationError
from production.deployment import (
    deployment_as_dict,
    deployment_fingerprint,
    discover_deployments,
    find_repo_root,
    validate_deployment,
)
from production.extensions import load_production_extensions
from production.observation import load_portfolio_manifest
from production.projection import host_facts, publish_projection, strategy_projection
from production.registry import runtime_adapter
from production.runtime import run_once
from production.state import deactivate, install_activation, state_root_from_env, validate_state_root
from production.status import production_status

# --------------------------------------------------------------------------- #
# Parser
# --------------------------------------------------------------------------- #


def build_parser() -> argparse.ArgumentParser:
    """Build the explicit operator CLI."""
    parser = argparse.ArgumentParser(
        prog="qf-production",
        description="Inspect or explicitly run tracked strategy deployments.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    list_parser = subparsers.add_parser("list", help="list statically valid deployment bundles")
    list_parser.add_argument("--deployments-root", type=Path, default=None)
    list_parser.add_argument("--repo-root", type=Path, default=Path.cwd())

    for command in ("validate", "inspect"):
        command_parser = subparsers.add_parser(command, help=f"{command} one deployment bundle")
        command_parser.add_argument("deployment", type=Path)
        command_parser.add_argument("--repo-root", type=Path, default=Path.cwd())

    run_parser = subparsers.add_parser("run-once", help="execute one fresh decision")
    run_parser.add_argument("deployment", type=Path)
    mode = run_parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="provider-backed preview; cannot submit")
    mode.add_argument("--live", action="store_true", help="require activation, arming, gate, and caps")
    run_parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    run_parser.add_argument("--state-root", type=Path, default=None)

    deactivate_parser = subparsers.add_parser("deactivate", help="atomically stop new decisions")
    deactivate_parser.add_argument("deployment", type=Path)
    deactivate_parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    deactivate_parser.add_argument("--state-root", type=Path, default=None)

    status_parser = subparsers.add_parser("status", help="report independent host-local operating facts")
    status_parser.add_argument("deployment", type=Path)
    status_parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    status_parser.add_argument("--state-root", type=Path, default=None)

    publish_parser = subparsers.add_parser(
        "publish-projection",
        help="publish the read-only capital telemetry projection under db/production",
    )
    publish_parser.add_argument("deployment", type=Path, nargs="+")
    publish_parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    publish_parser.add_argument("--state-root", type=Path, default=None)
    publish_parser.add_argument("--db-root", type=Path, default=None)
    publish_parser.add_argument("--portfolio", type=Path, default=None)
    publish_parser.add_argument(
        "--account-alias",
        action="append",
        default=[],
        metavar="FAMILY=ALIAS",
        help="non-secret account alias per family; never an account identifier",
    )
    publish_parser.add_argument("--host-alias", default=None, help="non-secret host alias")
    publish_parser.add_argument("--host-region", default="unknown", help="non-secret host region")

    activation_parser = subparsers.add_parser("activation", help="manage external activation receipts")
    activation_subparsers = activation_parser.add_subparsers(dest="activation_command", required=True)
    apply_parser = activation_subparsers.add_parser("apply", help="atomically install a protected receipt")
    apply_parser.add_argument("deployment", type=Path)
    apply_parser.add_argument("receipt", type=Path)
    apply_parser.add_argument("--confirm-fingerprint", required=True)
    apply_parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    apply_parser.add_argument("--state-root", type=Path, default=None)
    return parser


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #


def _run_list(args: argparse.Namespace) -> int:
    repo_root = find_repo_root(args.repo_root)
    deployments = discover_deployments(
        args.deployments_root or repo_root / "packages/production/extensions/deployments",
        repo_root,
    )
    if not deployments:
        print("No deployment bundles found.")
        return 0
    for path, definition in deployments:
        print(
            "\t".join(
                (
                    definition.strategy.family,
                    definition.strategy.memory_version,
                    definition.execution.venue,
                    str(path),
                )
            )
        )
    return 0


def _run_validate(args: argparse.Namespace) -> int:
    repo_root = find_repo_root(args.repo_root)
    definition = validate_deployment(args.deployment, repo_root)
    fingerprint = deployment_fingerprint(args.deployment, repo_root)
    print(
        f"VALID family={definition.strategy.family} "
        f"memory_version={definition.strategy.memory_version} venue={definition.execution.venue} "
        f"fingerprint={fingerprint}"
    )
    return 0


def _run_inspect(args: argparse.Namespace) -> int:
    repo_root = find_repo_root(args.repo_root)
    payload = deployment_as_dict(validate_deployment(args.deployment, repo_root))
    payload["deployment_fingerprint"] = deployment_fingerprint(args.deployment, repo_root)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _run_once(args: argparse.Namespace) -> int:
    repo_root = find_repo_root(args.repo_root)
    summary = run_once(
        args.deployment,
        repo_root,
        live=bool(args.live),
        state_root=args.state_root,
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def _run_deactivate(args: argparse.Namespace) -> int:
    repo_root = find_repo_root(args.repo_root)
    fingerprint = deployment_fingerprint(args.deployment, repo_root)
    state_root = validate_state_root(args.state_root or state_root_from_env(), repo_root)
    path = deactivate(state_root, fingerprint, at=datetime.now(tz=UTC))
    print(f"DEACTIVATED fingerprint={fingerprint} record={path}")
    return 0


def _run_status(args: argparse.Namespace) -> int:
    repo_root = find_repo_root(args.repo_root)
    state_root = validate_state_root(args.state_root or state_root_from_env(), repo_root)
    for name, value in production_status(args.deployment, repo_root, state_root):
        print(f"{name}={value}")
    return 0


def _alias_map(entries: Sequence[str]) -> dict[str, str]:
    """Parse ``FAMILY=ALIAS`` pairs, refusing anything that is not a pair."""
    mapping: dict[str, str] = {}
    for entry in entries:
        family, separator, alias = entry.partition("=")
        if not separator or not family or not alias:
            raise DeploymentValidationError(f"account alias must be FAMILY=ALIAS: {entry}")
        mapping[family] = alias
    return mapping


def _run_publish_projection(args: argparse.Namespace) -> int:
    load_production_extensions()
    repo_root = find_repo_root(args.repo_root)
    state_root = validate_state_root(args.state_root or state_root_from_env(), repo_root)
    env_db_root = os.environ.get("QUANT_DB_ROOT")
    db_root = args.db_root or (Path(env_db_root).expanduser().resolve() if env_db_root else repo_root / "db")
    manifest_path = args.portfolio or repo_root / "packages" / "production" / "extensions" / "portfolio.yaml"
    manifest = load_portfolio_manifest(manifest_path)
    aliases = _alias_map(args.account_alias)
    host_alias = args.host_alias or os.environ.get("QF_PRODUCTION_HOST_ALIAS")
    if not host_alias:
        raise DeploymentValidationError("--host-alias or QF_PRODUCTION_HOST_ALIAS is required")
    now = datetime.now(tz=UTC)

    projections = {}
    for deployment in args.deployment:
        definition = validate_deployment(deployment, repo_root)
        family = definition.strategy.family
        member = manifest.member(family)
        fingerprint = deployment_fingerprint(deployment, repo_root)
        facts = host_facts(production_status(deployment, repo_root, state_root, now=now))
        projections[family] = strategy_projection(
            portfolio_id=manifest.portfolio_id,
            definition=definition,
            deployment_path=deployment,
            fingerprint=fingerprint,
            facts=facts,
            state_root=state_root,
            account_alias=aliases.get(family, f"{family}-{definition.execution.venue}"),
            host_alias=host_alias,
            host_region=args.host_region,
            max_age_seconds=member.account_snapshot_max_age_seconds,
            included=member.included,
            now=now,
        )
    report = publish_projection(db_root=db_root, manifest=manifest, projections=projections, now=now)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def _run_activation_apply(args: argparse.Namespace) -> int:
    load_production_extensions()
    repo_root = find_repo_root(args.repo_root)
    fingerprint = deployment_fingerprint(args.deployment, repo_root)
    if args.confirm_fingerprint != fingerprint:
        raise DeploymentValidationError("explicit deployment fingerprint confirmation does not match")
    definition = validate_deployment(args.deployment, repo_root)
    runtime_adapter(definition.execution.venue)
    receipt_source = args.receipt.expanduser()
    if not receipt_source.is_absolute():
        receipt_source = (Path.cwd() / receipt_source).absolute()
    if receipt_source == repo_root or repo_root in receipt_source.parents:
        raise DeploymentValidationError("activation receipt source must be outside the repository")
    state_root = validate_state_root(args.state_root or state_root_from_env(), repo_root)
    path = install_activation(receipt_source, state_root, fingerprint)
    print(f"ACTIVATION_APPLIED fingerprint={fingerprint} record={path}")
    return 0


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "list":
            return _run_list(args)
        if args.command == "validate":
            return _run_validate(args)
        if args.command == "inspect":
            return _run_inspect(args)
        if args.command == "run-once":
            return _run_once(args)
        if args.command == "deactivate":
            return _run_deactivate(args)
        if args.command == "status":
            return _run_status(args)
        if args.command == "publish-projection":
            return _run_publish_projection(args)
        if args.command == "activation" and args.activation_command == "apply":
            return _run_activation_apply(args)
    except (DeploymentValidationError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    parser.error(f"unknown command: {args.command}")
    return 2


__all__ = ["build_parser", "main"]
