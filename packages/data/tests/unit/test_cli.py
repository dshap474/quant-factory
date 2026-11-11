"""Unit tests for the Typer CLI."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import data.api as data_api
from data.cli import api, app
from data.platform.errors import DatasetContractError
from data.platform.schema import ValidationResult
from typer.testing import CliRunner

runner = CliRunner()
STABLE_COMMANDS = ["schema-validate", "surface-validate", "surface-status", "dataset"]


def _spec_json() -> str:
    return """
    {
      "dataset_id": "example.market.sync",
      "family": "example_raw",
      "kind": "data/raw",
      "target": "canonical_data_raw",
      "product_type": "futures",
      "exchange": "example_venue",
      "resolution": "1h",
      "start_time": "2024-01-01T00:00:00Z",
      "end_time": "2024-01-02T00:00:00Z"
    }
    """


def test_cli_module_uses_canonical_api_module():
    assert api is data_api


def test_cli_help_smoke():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command_name in STABLE_COMMANDS:
        assert command_name in result.stdout


def test_schema_validate_help_smoke():
    result = runner.invoke(app, ["schema-validate", "--help"])
    assert result.exit_code == 0
    assert "--mode" in result.stdout
    assert "--layer" in result.stdout
    assert "--db-root" in result.stdout
    assert "--generate" in result.stdout


def test_surface_validate_passes() -> None:
    with patch("data.cli.api.validate_data_operational_surface", return_value=ValidationResult(valid=True)):
        result = runner.invoke(app, ["surface-validate"])

    assert result.exit_code == 0
    assert "Valid: True" in result.stdout


def test_surface_validate_exception_exits_nonzero() -> None:
    with patch("data.cli.api.validate_data_operational_surface", side_effect=RuntimeError("boom")):
        result = runner.invoke(app, ["surface-validate"])

    assert result.exit_code == 1
    assert "Surface validation failed" in result.stderr


def _surface_statuses() -> list:
    from datetime import datetime, timedelta, timezone

    from data.api import SurfaceStatus

    return [
        SurfaceStatus(
            script="pipelines/raw/1d/missing/b.py",
            contract="control_plane",
            cadence="daily",
            surface="db/data/raw/1d/missing",
            parquet_files=0,
            total_bytes=0,
            latest_write=None,
        ),
        SurfaceStatus(
            script="pipelines/raw/1d/fresh/a.py",
            contract="control_plane",
            cadence="daily",
            surface="db/data/raw/1d/fresh",
            parquet_files=3,
            total_bytes=2048,
            latest_write=datetime.now(timezone.utc) - timedelta(days=1),
        ),
        SurfaceStatus(
            script="pipelines/raw/1d/dormant/c.py",
            contract="control_plane",
            cadence="on_demand",
            surface="db/data/raw/1d/dormant",
            parquet_files=0,
            total_bytes=0,
            latest_write=None,
        ),
    ]


def test_surface_status_table_output() -> None:
    with patch("data.cli.api.collect_data_surface_status", return_value=_surface_statuses()):
        result = runner.invoke(app, ["surface-status"])

    assert result.exit_code == 0
    assert "STALE" in result.stdout
    assert "pipelines/raw/1d/fresh/a.py" in result.stdout
    assert "on_demand" in result.stdout


def test_surface_status_json_output() -> None:
    import json

    with patch("data.cli.api.collect_data_surface_status", return_value=_surface_statuses()):
        result = runner.invoke(app, ["surface-status", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload[0]["script"] == "pipelines/raw/1d/missing/b.py"
    assert payload[0]["latest_write"] is None
    assert payload[0]["stale"] is True
    assert payload[1]["parquet_files"] == 3
    assert payload[1]["stale"] is False
    assert payload[2]["cadence"] == "on_demand"
    assert payload[2]["stale"] is False


def test_surface_status_check_exits_nonzero_on_stale_routine_pipeline() -> None:
    with patch("data.cli.api.collect_data_surface_status", return_value=_surface_statuses()):
        result = runner.invoke(app, ["surface-status", "--check"])

    assert result.exit_code == 1
    assert "pipelines/raw/1d/missing/b.py" in result.stderr
    assert "pipelines/raw/1d/dormant/c.py" not in result.stderr


def test_surface_status_check_passes_when_routine_pipelines_fresh() -> None:
    statuses = [status for status in _surface_statuses() if status.cadence != "daily" or status.latest_write]
    with patch("data.cli.api.collect_data_surface_status", return_value=statuses):
        result = runner.invoke(app, ["surface-status", "--check"])

    assert result.exit_code == 0


def test_surface_status_check_exits_nonzero_on_quality_issue() -> None:
    from dataclasses import replace

    statuses = [status for status in _surface_statuses() if status.cadence != "daily" or status.latest_write]
    statuses[0] = replace(statuses[0], issues=("close <= 0 (min 0) in data/raw/1d/fresh/data.parquet",))
    with patch("data.cli.api.collect_data_surface_status", return_value=statuses):
        result = runner.invoke(app, ["surface-status", "--check"])

    assert result.exit_code == 1
    assert "failed a quality check" in result.stderr
    assert "close <= 0" in result.stderr


def test_schema_validate_passes_all_options(tmp_path: Path):
    with patch("data.cli.api.validate_schema", return_value=ValidationResult(valid=True)) as mock_validate:
        result = runner.invoke(
            app,
            ["schema-validate", "--mode", "repair", "--layer", "data/raw", "--db-root", str(tmp_path)],
        )

    assert result.exit_code == 0
    assert "Valid: True" in result.stdout
    mock_validate.assert_called_once_with(mode="repair", layer="data/raw", db_root=tmp_path)


def test_schema_validate_generate_uses_package_api(tmp_path: Path):
    with patch("data.cli.api.generate_schema_files") as mock_generate:
        result = runner.invoke(app, ["schema-validate", "--generate", "--db-root", str(tmp_path)])

    assert result.exit_code == 0
    assert "Generated master and layer SCHEMA.yaml files." in result.stdout
    mock_generate.assert_called_once_with(db_root=tmp_path)


def test_schema_validate_generate_rejects_layer(tmp_path: Path):
    with patch("data.cli.api.generate_schema_files") as mock_generate:
        result = runner.invoke(
            app,
            ["schema-validate", "--generate", "--layer", "data/raw", "--db-root", str(tmp_path)],
        )

    assert result.exit_code == 2
    assert "--generate cannot be combined with --layer" in result.stderr
    mock_generate.assert_not_called()


def test_schema_validate_invalid_exits_nonzero():
    with patch("data.cli.api.validate_schema", return_value=ValidationResult(valid=False, errors=["boom"])):
        result = runner.invoke(app, ["schema-validate", "--mode", "strict"])

    assert result.exit_code == 1
    assert "Valid: False" in result.stdout


def test_schema_validate_exception_exits_nonzero():
    with patch("data.cli.api.validate_schema", side_effect=RuntimeError("boom")):
        result = runner.invoke(app, ["schema-validate"])

    assert result.exit_code == 1
    assert "Schema validation failed" in result.stderr


def test_dataset_help_smoke():
    result = runner.invoke(app, ["dataset", "--help"])
    assert result.exit_code == 0
    for command in ["ingest", "sync", "materialize", "validate", "status", "reconcile"]:
        assert command in result.stdout


def test_dataset_ingest_help_smoke():
    result = runner.invoke(app, ["dataset", "ingest", "--help"])
    assert result.exit_code == 0
    assert "--spec-file" in result.stdout
    assert "--spec-json" in result.stdout
    assert "--json" in result.stdout


def test_dataset_ingest_passes_spec_and_renders_json(sample_ingest_result):
    with patch("data.cli.api.ingest_dataset", return_value=sample_ingest_result) as mock_ingest:
        result = runner.invoke(app, ["dataset", "ingest", "--spec-json", _spec_json(), "--json"])

    assert result.exit_code == 0
    assert '"dataset_id": "example.market.sync"' in result.stdout
    mock_ingest.assert_called_once()
    assert mock_ingest.call_args.args[0].dataset_id == "example.market.sync"


def test_dataset_validate_passes_mode(sample_ingest_result):
    with patch("data.cli.api.validate_dataset", return_value=sample_ingest_result) as mock_validate:
        result = runner.invoke(
            app,
            ["dataset", "validate", "--spec-json", _spec_json(), "--mode", "strict"],
        )

    assert result.exit_code == 0
    assert "Status: success" in result.stdout
    mock_validate.assert_called_once()
    assert mock_validate.call_args.args[0].family == "example_raw"
    assert mock_validate.call_args.kwargs["mode"] == "strict"


def test_dataset_status_reads_spec_file(sample_ingest_result, tmp_path: Path):
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(_spec_json(), encoding="utf-8")

    with patch("data.cli.api.get_dataset_status", return_value=sample_ingest_result) as mock_status:
        result = runner.invoke(app, ["dataset", "status", "--spec-file", str(spec_path)])

    assert result.exit_code == 0
    assert "Dataset: example.market.sync" in result.stdout
    mock_status.assert_called_once()


def test_dataset_command_maps_data_package_errors_to_exit_1():
    with patch("data.cli.api.sync_dataset", side_effect=DatasetContractError("bad spec")):
        result = runner.invoke(app, ["dataset", "sync", "--spec-json", _spec_json()])

    assert result.exit_code == 1
    assert "dataset_contract_error" in result.stderr


def test_dataset_requires_exactly_one_spec_source():
    result = runner.invoke(app, ["dataset", "sync", "--json"])
    assert result.exit_code != 0
    combined_output = f"{result.stdout}\n{result.stderr}"
    assert "--spec-file" in combined_output or "--spec-json" in combined_output
