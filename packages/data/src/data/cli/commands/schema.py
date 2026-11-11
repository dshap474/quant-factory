"""Schema validation commands for the data CLI."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Annotated

import typer

import data.api as api


class SchemaMode(str, Enum):
    strict = "strict"
    repair = "repair"
    warn = "warn"


def register(app: typer.Typer) -> None:
    @app.command("schema-validate")
    def schema_validate(
        mode: Annotated[SchemaMode, typer.Option("--mode", help="Validation mode.")] = SchemaMode.warn,
        layer: Annotated[str | None, typer.Option("--layer", help="Optional single layer to validate.")] = None,
        db_root: Annotated[Path | None, typer.Option("--db-root", help="Optional db root override.")] = None,
        generate: Annotated[
            bool,
            typer.Option("--generate", help="Generate master and layer SCHEMA.yaml files before exiting."),
        ] = False,
    ) -> None:
        """Validate datasets against schema contracts."""
        if generate and layer is not None:
            typer.echo("--generate cannot be combined with --layer", err=True)
            raise typer.Exit(code=2)

        try:
            if generate:
                api.generate_schema_files(db_root=db_root)
                typer.echo("Generated master and layer SCHEMA.yaml files.")
                return
            result = api.validate_schema(mode=mode.value, layer=layer, db_root=db_root)
        except Exception as exc:
            action = "generation" if generate else "validation"
            typer.echo(f"Schema {action} failed: {exc}", err=True)
            raise typer.Exit(code=1) from exc

        typer.echo(str(result))
        if not result.valid:
            raise typer.Exit(code=1)
