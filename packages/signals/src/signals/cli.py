"""Package CLI for the signals control plane."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from signals.api import (
    SignalsApiError,
    list_catalog,
    publish_catalog,
    validate_catalog,
)
from signals.api import (
    smoke_catalog as smoke_signals,
)

app = typer.Typer(
    name="qf-signals",
    help="Signal catalog validation and smoke commands.",
    no_args_is_help=True,
)
console = Console()


@app.command("list")
def list_command(
    include_planned: bool = typer.Option(
        False,
        "--include-planned/--active-only",
        help="Include planned signals in output.",
    ),
) -> None:
    """List registry-derived signal catalog entries."""
    table = Table(show_header=True, header_style="bold")
    table.add_column("Signal", style="cyan")
    table.add_column("Status")
    table.add_column("Default")
    table.add_column("Output")
    table.add_column("Presets", style="green")
    table.add_column("Runner")

    for row in list_catalog(include_planned=include_planned):
        table.add_row(
            row["signal_type"],
            row["status"],
            row.get("default_preset", ""),
            row["output_type"],
            ",".join(row["presets"]),
            row["runner_module"],
        )

    console.print(table)


@app.command("validate")
def validate_command() -> None:
    """Validate catalog metadata, docs, presets, imports, and runtime registration."""
    result = validate_catalog()

    for row in result.info:
        console.print(f"[dim]{row}[/dim]")

    if result.warnings:
        console.print(f"[yellow]Warnings ({len(result.warnings)}):[/]")
        for warning in result.warnings:
            console.print(f"  - {warning}")

    if result.errors:
        console.print(f"[red]Errors ({len(result.errors)}):[/]")
        for error in result.errors:
            console.print(f"  - {error}")
        raise typer.Exit(code=1)

    console.print("[green]Signal catalog validation passed.[/]")


@app.command("smoke")
def smoke_command(
    signal_type: str | None = typer.Argument(
        None,
        help="Optional single signal_type to smoke instead of the full active catalog.",
    ),
) -> None:
    """Run default presets with ``save=False`` for the active signal catalog."""
    report = smoke_signals(signal_type=signal_type)

    for row in report.info:
        console.print(f"[dim]{row}[/dim]")

    if report.failed:
        console.print(f"[red]Smoke failures ({len(report.failed)}):[/]")
        for name, error in sorted(report.failed.items()):
            console.print(f"  - {name}: {error}")
        raise typer.Exit(code=1)

    console.print(f"[green]Smoke passed for {len(report.passed)} signal(s).[/]")


@app.command("publish")
def publish_command(
    signal_type: list[str] = typer.Option(  # noqa: B008 - typer option default
        [],
        "--signal-type",
        help="Signal type to publish; repeatable. Default: every active catalog entry.",
    ),
    preset: str | None = typer.Option(
        None,
        "--preset",
        help="Preset name to publish; valid only with exactly one --signal-type.",
    ),
    all_presets: bool = typer.Option(
        False,
        "--all-presets",
        help="Publish every preset file in each selected family's presets_dir.",
    ),
    db_root: Path | None = typer.Option(
        None,
        "--db-root",
        help="Persistence root; defaults to QUANT_DB_ROOT.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Run with save=False and write no ledger.",
    ),
    fail_fast: bool = typer.Option(
        False,
        "--fail-fast",
        help="Stop at the first failing runner instead of continuing.",
    ),
) -> None:
    """Run active signal families with ``save=True`` and append a publish ledger."""
    try:
        report = publish_catalog(
            signal_types=signal_type,
            preset=preset,
            all_presets=all_presets,
            db_root=db_root,
            dry_run=dry_run,
            fail_fast=fail_fast,
        )
    except SignalsApiError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(code=2) from exc

    if report.errors:
        console.print(f"[red]Publish failures ({len(report.errors)}):[/]")
        for record in report.errors:
            console.print(f"  - {record['signal_type']}/{record['preset']}: {record['error']}")
        raise typer.Exit(code=1)


def main() -> None:
    app()
