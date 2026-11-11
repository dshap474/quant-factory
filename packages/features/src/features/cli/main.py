"""Package CLI for the features control plane."""

from __future__ import annotations

import click
import typer
from rich.console import Console
from rich.table import Table

from features.api import (
    list_feature_catalog,
    publish_feature_category,
    smoke_catalog,
    validate_catalog,
)

app = typer.Typer(
    name="qf-features",
    help="Feature catalog and pipeline commands.",
    no_args_is_help=True,
)
console = Console()


@app.command("list")
def list_command() -> None:
    """List publishable feature families."""
    table = Table(show_header=True, header_style="bold")
    table.add_column("Category", style="cyan")
    table.add_column("Resolutions", style="green")
    table.add_column("Asset")
    table.add_column("Runner")

    for row in list_feature_catalog():
        table.add_row(
            row["category"],
            ",".join(row["resolutions"]),
            "yes" if row["asset_column"] else "no",
            f"{row['runner_module']}.{row['runner_class']}",
        )

    console.print(table)


@app.command("validate")
def validate_command() -> None:
    """Validate explicit publishable family imports and full panels."""
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

    console.print("[green]Feature catalog validation passed.[/]")


@app.command("smoke")
def smoke_command(
    category: str | None = typer.Argument(
        None,
        help="Optional single category to smoke instead of the default active catalog.",
    ),
    execute: bool = typer.Option(
        False,
        "--execute",
        help="Run feature families instead of only instantiating their full panels.",
    ),
) -> None:
    """Instantiate full panels, optionally executing ``run(save=False)``."""
    report = smoke_catalog(
        category=category,
        execute=execute,
    )

    for row in report.info:
        console.print(f"[dim]{row}[/dim]")

    if report.failed:
        console.print(f"[red]Smoke failures ({len(report.failed)}):[/]")
        for name, error in sorted(report.failed.items()):
            console.print(f"  - {name}: {error}")
        raise typer.Exit(code=1)

    console.print(f"[green]Smoke passed for {len(report.passed)} feature family(s).[/]")


@app.command("publish")
def publish_command(
    category: str = typer.Argument(..., help="Publishable feature category."),
    preset: str | None = typer.Option(
        None,
        "--preset",
        help="Optional curated preset. Omit to publish the full panel.",
    ),
    resolution: str | None = typer.Option(
        None,
        "--resolution",
        help="Optional resolution override when the family declares multiple resolutions.",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Overwrite the target version if the underlying store resolves to an existing version.",
    ),
) -> None:
    """Run one published feature family and persist it to ``db/features``."""
    try:
        result = publish_feature_category(
            category=category,
            preset=preset,
            resolution=resolution,
            force=force,
        )
    except Exception as exc:
        typer.echo(f"feature publish failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    console.print(result.summary())


def main(argv: list[str] | None = None) -> int:
    """Run the CLI."""
    try:
        result = app(prog_name="qf-features", args=argv, standalone_mode=False)
    except typer.Exit as exc:
        return int(exc.exit_code if exc.exit_code is not None else 1)
    except click.ClickException as exc:
        exc.show()
        return int(exc.exit_code)
    except SystemExit as exc:  # pragma: no cover
        code = exc.code
        return int(code) if isinstance(code, int) else 1
    if isinstance(result, int):
        return result
    return 0
