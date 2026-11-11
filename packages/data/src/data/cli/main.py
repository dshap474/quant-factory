"""Typer CLI surface for the data package."""

from __future__ import annotations

import typer

from .commands.dataset import register as register_dataset
from .commands.schema import register as register_schema
from .commands.surface import register as register_surface

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="qf-data commands for canonical dataset control-plane operations.",
)

register_schema(app)
register_surface(app)
register_dataset(app)


def main() -> None:
    """Run the Typer CLI app."""
    app()
