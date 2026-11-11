"""Operational surface validation, freshness and refresh commands for the data CLI.

USAGE: ``uv run qf-data surface-status --check``; ``uv run qf-data refresh --cadence daily --dry-run``;
``uv run qf-data refresh --cadence daily --jobs 1``.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

import typer

import data.api as api


def _human_bytes(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} TB"


_ISSUES_SHOWN = 3


def register(app: typer.Typer) -> None:
    @app.command("surface-validate")
    def surface_validate() -> None:
        """Validate the `packages/data` package docs and registry-listed scripts."""
        try:
            result = api.validate_data_operational_surface()
        except Exception as exc:
            typer.echo(f"Surface validation failed: {exc}", err=True)
            raise typer.Exit(code=1) from exc

        typer.echo(str(result))
        if not result.valid:
            raise typer.Exit(code=1)

    @app.command("surface-status")
    def surface_status(
        db_root: Annotated[Path | None, typer.Option("--db-root", help="Optional db root override.")] = None,
        check: Annotated[
            bool,
            typer.Option("--check", help="Exit 1 if any daily/weekly pipeline is stale or fails a quality check."),
        ] = False,
        as_json: Annotated[bool, typer.Option("--json", help="Emit JSON instead of a table.")] = False,
    ) -> None:
        """Report parquet footprint, age of the newest data, cadence staleness, and quality issues."""
        try:
            statuses = api.collect_data_surface_status(db_root=db_root)
        except Exception as exc:
            typer.echo(f"Surface status failed: {exc}", err=True)
            raise typer.Exit(code=1) from exc

        now = datetime.now(timezone.utc)
        if as_json:
            payload = [
                {
                    "script": status.script,
                    "contract": status.contract,
                    "cadence": status.cadence,
                    "surface": status.surface,
                    "parquet_files": status.parquet_files,
                    "total_bytes": status.total_bytes,
                    "latest_write": status.latest_write.isoformat() if status.latest_write else None,
                    "last_refresh": status.last_refresh.isoformat() if status.last_refresh else None,
                    "newest_data": status.newest_data.isoformat() if status.newest_data else None,
                    "basis": status.basis,
                    "age_days": round(age, 3) if (age := status.age_days(now)) is not None else None,
                    "stale": status.is_stale(now),
                    "issues": list(status.issues),
                }
                for status in statuses
            ]
            typer.echo(json.dumps(payload, indent=2))
        else:
            typer.echo(
                f"{'STATE':<5} {'AGE(D)':>8}  {'NEWEST (UTC)':<17} {'BASIS':<5} {'CADENCE':<9} "
                f"{'FILES':>6} {'SIZE':>9} {'ISSUES':>6}  PIPELINE"
            )
            for status in statuses:
                age = status.age_days(now)
                state = "STALE" if status.is_stale(now) else ("none" if status.latest_update is None else "ok")
                age_text = f"{age:8.1f}" if age is not None else f"{'-':>8}"
                latest = status.latest_update
                latest_text = latest.strftime("%Y-%m-%d %H:%M") if latest is not None else "-"
                typer.echo(
                    f"{state:<5} {age_text}  {latest_text:<17} {status.basis:<5} {status.cadence:<9} "
                    f"{status.parquet_files:>6} {_human_bytes(status.total_bytes):>9} {len(status.issues):>6}  "
                    f"{status.script}"
                )

        if check:
            stale = [status for status in statuses if status.is_stale(now)]
            flagged = [status for status in statuses if status.issues]
            if stale:
                typer.echo(f"{len(stale)} pipeline(s) stale for their cadence:", err=True)
                for status in stale:
                    typer.echo(f"  - {status.script} ({status.cadence})", err=True)
            if flagged:
                typer.echo(f"{len(flagged)} pipeline(s) failed a quality check:", err=True)
                for status in flagged:
                    typer.echo(f"  - {status.script}", err=True)
                    for issue in status.issues[:_ISSUES_SHOWN]:
                        typer.echo(f"      {issue}", err=True)
                    if len(status.issues) > _ISSUES_SHOWN:
                        typer.echo(f"      ... and {len(status.issues) - _ISSUES_SHOWN} more (see --json)", err=True)
            if stale or flagged:
                raise typer.Exit(code=1)

    @app.command("refresh")
    def refresh(
        resolution: Annotated[
            str | None, typer.Option("--resolution", help="Only one pipeline resolution, e.g. 1d; default all.")
        ] = None,
        cadence: Annotated[
            str | None, typer.Option("--cadence", help="Only daily or weekly pipelines; default both.")
        ] = None,
        match: Annotated[str | None, typer.Option("--match", help="Only pipelines whose path contains this.")] = None,
        dry_run: Annotated[bool, typer.Option("--dry-run", help="Print the steps without running them.")] = False,
        step_timeout: Annotated[
            float,
            typer.Option("--step-timeout", help="Minutes before a step and everything it started is killed."),
        ] = api.STEP_TIMEOUT_SECONDS / 60,
        jobs: Annotated[
            int, typer.Option("--jobs", min=1, help="Steps running at once; 1 = one at a time in plan order.")
        ] = api.DEFAULT_JOBS,
        memory_gb: Annotated[
            float | None,
            typer.Option(
                "--memory-gb",
                help="Most memory the whole run may use (kernel-enforced on Linux); default $QF_REFRESH_MEMORY_GB, "
                f"else {api.DEFAULT_MEMORY_GB:g}.",
            ),
        ] = None,
        no_memory_cap: Annotated[
            bool, typer.Option("--no-memory-cap", help="Do not run steps in a systemd scope with MemoryMax.")
        ] = False,
    ) -> None:
        """Run every registered pipeline with a refresh command, raw before derived, independent steps in parallel."""
        plan = api.refresh_plan(resolution=resolution, cadence=cadence, match=match)
        if not plan:
            typer.echo("No pipelines match.", err=True)
            raise typer.Exit(code=1)
        try:
            needs = api.resolve_needs(plan)
        except ValueError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc
        if memory_gb is not None and memory_gb <= 0:
            raise typer.BadParameter("must be > 0", param_hint="--memory-gb")
        memory_gb = api.default_memory_gb() if memory_gb is None else memory_gb
        if dry_run:
            estimates = api.step_estimates(plan)
            for index, entry in enumerate(plan, start=1):
                typer.echo(f"{index:>3}. {entry.cadence:<9} {entry.path} {entry.refresh}".rstrip())
                typer.echo(
                    f"       est {estimates[entry.path] / 1024:.1f} GB  group {entry.group or '-'}  "
                    f"needs {_needs_text(entry.needs is not None, needs[entry.path], index)}"
                )
            cap = "off" if no_memory_cap or not api.memory_cap_available() else "on"
            budget = api.budget_mb(memory_gb) / 1024
            typer.echo(f"memory {memory_gb:g} GB (budget {budget:.1f} GB), jobs {jobs}, kernel cap {cap}")
            return

        started = time.monotonic()
        steps = api.run_refresh(
            plan,
            timeout=step_timeout * 60,
            jobs=jobs,
            memory_gb=memory_gb,
            memory_cap=not no_memory_cap,
            cadence=cadence,
        )
        wall = time.monotonic() - started
        failed = [step for step in steps if step.returncode != 0]
        typer.echo(f"\nRefresh finished: {len(steps) - len(failed)} ok, {len(failed)} failed")
        for step in steps:
            state = "ok" if step.returncode == 0 else ("OOM" if step.oom else f"FAILED ({step.returncode})")
            peak = f"{step.maxrss_mb / 1024:>5.1f} GB" if step.maxrss_mb is not None else "    - GB"
            typer.echo(f"  {state:<12} {step.seconds:>7.0f}s  {peak}  {step.path}")
        total = sum(step.seconds for step in steps)
        typer.echo(f"wall {wall:.0f}s (sum of steps {total:.0f}s, {total / wall if wall else 0:.1f}x)")
        if failed:
            raise typer.Exit(code=1)


def _short_name(path: str) -> str:
    return path.rsplit("/", 1)[-1].removesuffix(".py")


def _needs_text(declared: bool, resolved: tuple[str, ...], index: int) -> str:
    """Resolved in-plan dependencies; undeclared ``needs`` reads as every earlier step."""
    if not declared:
        return f"undeclared (all {index - 1} earlier)" if resolved else "undeclared (first)"
    return ", ".join(_short_name(path) for path in resolved) or "-"
