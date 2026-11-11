"""Dataset-oriented commands for the data CLI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

import data.api as api
from data.platform.errors import DataPackageError


def _load_spec(*, spec_file: Path | None, spec_json: str | None) -> api.DatasetSpec:
    if bool(spec_file) == bool(spec_json):
        raise typer.BadParameter("Provide exactly one of --spec-file or --spec-json.")
    if spec_file is not None:
        payload = spec_file.read_text(encoding="utf-8")
    else:
        payload = spec_json or ""
    return api.DatasetSpec.model_validate_json(payload)


def _print_result(result: api.IngestResult, *, as_json: bool) -> None:
    if as_json:
        typer.echo(result.model_dump_json(indent=2))
        return

    typer.echo(f"Status: {result.status}")
    typer.echo(f"Operation: {result.operation}")
    typer.echo(f"Dataset: {result.dataset_id}")
    if result.written_artifacts:
        typer.echo(f"Wrote artifacts: {len(result.written_artifacts)}")
    if result.row_counts:
        typer.echo("Row counts:")
        typer.echo(json.dumps(result.row_counts, indent=2, sort_keys=True))
    if result.checks_passed:
        typer.echo(f"Checks: {', '.join(result.checks_passed)}")
    if result.warnings:
        typer.echo("Warnings:")
        for warning in result.warnings:
            typer.echo(f"- {warning}")
    if result.errors:
        typer.echo("Errors:")
        for error in result.errors:
            typer.echo(f"- {error}")


def _run_dataset_op(
    fn,
    *,
    spec_file: Path | None,
    spec_json: str | None,
    as_json: bool,
    mode: str | None = None,
) -> None:
    try:
        spec = _load_spec(spec_file=spec_file, spec_json=spec_json)
        result = fn(spec, mode=mode) if mode is not None else fn(spec)
    except DataPackageError as exc:
        typer.echo(f"{exc.code}: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        typer.echo(f"Dataset command failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    _print_result(result, as_json=as_json)
    if result.status == "error":
        raise typer.Exit(code=1)


def register(app: typer.Typer) -> None:
    dataset = typer.Typer(add_completion=False, no_args_is_help=True, help="Dataset-oriented canonical DB operations.")

    @dataset.command("ingest")
    def ingest(
        spec_file: Annotated[Path | None, typer.Option("--spec-file", help="Path to a DatasetSpec JSON file.")] = None,
        spec_json: Annotated[str | None, typer.Option("--spec-json", help="Inline DatasetSpec JSON payload.")] = None,
        as_json: Annotated[bool, typer.Option("--json", help="Emit structured JSON output.")] = False,
    ) -> None:
        """Ingest a dataset spec into canonical storage."""
        _run_dataset_op(api.ingest_dataset, spec_file=spec_file, spec_json=spec_json, as_json=as_json)

    @dataset.command("sync")
    def sync(
        spec_file: Annotated[Path | None, typer.Option("--spec-file", help="Path to a DatasetSpec JSON file.")] = None,
        spec_json: Annotated[str | None, typer.Option("--spec-json", help="Inline DatasetSpec JSON payload.")] = None,
        as_json: Annotated[bool, typer.Option("--json", help="Emit structured JSON output.")] = False,
    ) -> None:
        """Sync a dataset spec into canonical storage."""
        _run_dataset_op(api.sync_dataset, spec_file=spec_file, spec_json=spec_json, as_json=as_json)

    @dataset.command("materialize")
    def materialize(
        spec_file: Annotated[Path | None, typer.Option("--spec-file", help="Path to a DatasetSpec JSON file.")] = None,
        spec_json: Annotated[str | None, typer.Option("--spec-json", help="Inline DatasetSpec JSON payload.")] = None,
        as_json: Annotated[bool, typer.Option("--json", help="Emit structured JSON output.")] = False,
    ) -> None:
        """Materialize a feature dataset into canonical feature storage."""
        _run_dataset_op(api.materialize_dataset, spec_file=spec_file, spec_json=spec_json, as_json=as_json)

    @dataset.command("validate")
    def validate(
        spec_file: Annotated[Path | None, typer.Option("--spec-file", help="Path to a DatasetSpec JSON file.")] = None,
        spec_json: Annotated[str | None, typer.Option("--spec-json", help="Inline DatasetSpec JSON payload.")] = None,
        mode: Annotated[str, typer.Option("--mode", help="Validation mode: strict, repair, or warn.")] = "warn",
        as_json: Annotated[bool, typer.Option("--json", help="Emit structured JSON output.")] = False,
    ) -> None:
        """Validate a dataset target against canonical contracts."""
        _run_dataset_op(api.validate_dataset, spec_file=spec_file, spec_json=spec_json, as_json=as_json, mode=mode)

    @dataset.command("status")
    def status(
        spec_file: Annotated[Path | None, typer.Option("--spec-file", help="Path to a DatasetSpec JSON file.")] = None,
        spec_json: Annotated[str | None, typer.Option("--spec-json", help="Inline DatasetSpec JSON payload.")] = None,
        as_json: Annotated[bool, typer.Option("--json", help="Emit structured JSON output.")] = False,
    ) -> None:
        """Inspect canonical dataset status."""
        _run_dataset_op(api.get_dataset_status, spec_file=spec_file, spec_json=spec_json, as_json=as_json)

    @dataset.command("reconcile")
    def reconcile(
        spec_file: Annotated[Path | None, typer.Option("--spec-file", help="Path to a DatasetSpec JSON file.")] = None,
        spec_json: Annotated[str | None, typer.Option("--spec-json", help="Inline DatasetSpec JSON payload.")] = None,
        as_json: Annotated[bool, typer.Option("--json", help="Emit structured JSON output.")] = False,
    ) -> None:
        """Reconcile a dataset by re-running canonical sync behavior."""
        _run_dataset_op(api.reconcile_dataset, spec_file=spec_file, spec_json=spec_json, as_json=as_json)

    app.add_typer(dataset, name="dataset")
