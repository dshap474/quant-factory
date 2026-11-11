"""Package CLI for the strategies control plane.

USAGE: ``qf-strategies align family`` checks the selected preset and version.
       ``qf-strategies rerun family v002 -- python -m pytest packages/strategies/extensions/lib/family`` runs a command on the commit a version ran.
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from . import api, checkout

# --------------------------------------------------------------------------- #
# CLI application
# --------------------------------------------------------------------------- #

app = typer.Typer(
    name="qf-strategies",
    help="Strategy registry validation, presets, and versioned-run commands.",
    no_args_is_help=True,
)
console = Console()


# --------------------------------------------------------------------------- #
# Operator commands
# --------------------------------------------------------------------------- #


@app.command("list")
def list_command(
    include_planned: bool = typer.Option(
        False,
        "--include-planned/--active-only",
        help="Include planned strategies in output.",
    ),
) -> None:
    """List strategy registry entries."""
    table = Table(show_header=True, header_style="bold")
    table.add_column("Strategy", style="cyan")
    table.add_column("Status")
    table.add_column("Default")
    table.add_column("Output")
    table.add_column("Presets", style="green")
    table.add_column("Runner")

    for row in api.list_catalog(include_planned=include_planned):
        table.add_row(
            row["strategy_type"],
            row["status"],
            row.get("default_preset", ""),
            row["output_type"],
            ",".join(row["presets"]),
            row["runner_module"],
        )

    console.print(table)


@app.command("validate")
def validate_command() -> None:
    """Validate registry-derived catalog, docs, presets, imports, and runtime registration."""
    result = api.validate_catalog()

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

    console.print("[green]Strategy catalog validation passed.[/]")


@app.command("align")
def align_command(
    strategy_type: str | None = typer.Argument(
        None,
        help="Optional single strategy_type to validate instead of the full active catalog.",
    ),
    include_planned: bool = typer.Option(
        False,
        "--include-planned/--active-only",
        help="Include planned strategies in alignment validation.",
    ),
) -> None:
    """Validate registered preset and selected memory-version alignment."""
    result = api.validate_alignment(strategy_type, include_planned=include_planned)

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

    console.print("[green]Strategy alignment validation passed.[/]")


@app.command("check")
def check_command() -> None:
    """Alias for validate command."""
    validate_command()


@app.command("smoke")
def smoke_command(
    strategy_type: str | None = typer.Argument(
        None,
        help="Optional single strategy_type to smoke instead of the full active catalog.",
    ),
    execute: bool = typer.Option(
        False,
        "--execute",
        help="Run each default preset instead of only instantiating from_preset().",
    ),
) -> None:
    """Run preset smoke for the active strategy catalog."""
    report = api.smoke(family=strategy_type, execute=execute)

    for row in report.info:
        console.print(f"[dim]{row}[/dim]")

    if report.failed:
        console.print(f"[red]Smoke failures ({len(report.failed)}):[/]")
        for name, error in sorted(report.failed.items()):
            console.print(f"  - {name}: {error}")
        raise typer.Exit(code=1)

    console.print(f"[green]Smoke passed for {len(report.passed)} strategy(s).[/]")


@app.command("families")
def families_command(
    include_planned: bool = typer.Option(
        False,
        "--include-planned/--active-only",
        help="Include planned strategy families.",
    ),
) -> None:
    """List strategy families."""
    for family in api.list_families(include_planned=include_planned):
        console.print(family)


@app.command("presets")
def presets_command(
    family: str = typer.Argument(..., help="Strategy family"),
) -> None:
    """List package-level runnable presets for a family."""
    presets = api.list_presets(family)
    active = api.get_active_preset(family)
    for preset in presets:
        marker = " *" if preset == active else ""
        console.print(f"{preset}{marker}")


@app.command("run")
def run_command(
    family: str = typer.Argument(..., help="Strategy family"),
    preset: str | None = typer.Option(None, "--preset", help="Override preset name"),
    memory_version: str = typer.Option(..., "--memory-version", help="Hard strategy memory version (vNNN)"),
) -> None:
    """Run a strategy family and save the run under the version's research directory."""
    handle = api.run(family, preset=preset, memory_version=memory_version, save=True)
    console.print(
        f"[green]Run complete[/] family={handle.strategy_type} version={handle.memory_version} preset={handle.preset} "
        f"run_id={handle.run_id} run_dir={handle.run_dir}"
    )


@app.command("finalize")
def finalize_command(
    family: str = typer.Argument(..., help="Strategy family"),
    memory_version: str = typer.Option(..., "--memory-version", help="Hard strategy memory version (vNNN)"),
    run_id: str = typer.Option(..., "--run-id", help="Operator-chosen saved run to promote"),
) -> None:
    """Promote one saved run into the version's canonical final artifact."""
    handle = api.finalize(family, memory_version=memory_version, run_id=run_id)
    console.print(
        f"[green]Finalize complete[/] family={handle.strategy_type} version={handle.memory_version} "
        f"run_id={handle.run_id} final_dir={handle.run_dir}"
    )


# --------------------------------------------------------------------------- #
# Rerun on a recorded commit
# --------------------------------------------------------------------------- #

@app.command("rerun")
def rerun_command(
    family: str = typer.Argument(..., help="Strategy family"),
    memory_version: str = typer.Argument(..., help="Strategy version (vNNN)"),
    command: list[str] = typer.Argument(..., help="Command to run after --"),
) -> None:
    """Run a version on the code it ran, in a scratch worktree at its recorded commit."""
    raise typer.Exit(checkout.rerun(family, memory_version, command))


def main() -> None:
    app()
