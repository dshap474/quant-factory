"""CLI tests for the slim feature control plane."""

from __future__ import annotations

import features.cli.main as cli_module
from features.cli.main import app, main
from typer.testing import CliRunner


def test_publish_command_calls_explicit_publish_surface(monkeypatch) -> None:
    runner = CliRunner()
    captured: dict[str, object] = {}

    class FakeResult:
        def summary(self) -> str:
            return "published"

    def fake_publish_feature_category(*, category: str, preset: str | None, resolution: str | None, force: bool):
        captured["category"] = category
        captured["preset"] = preset
        captured["resolution"] = resolution
        captured["force"] = force
        return FakeResult()

    monkeypatch.setattr(cli_module, "publish_feature_category", fake_publish_feature_category)

    result = runner.invoke(
        app,
        ["publish", "example/category", "--preset", "default", "--resolution", "1d", "--force"],
    )

    assert result.exit_code == 0
    assert captured == {
        "category": "example/category",
        "preset": "default",
        "resolution": "1d",
        "force": True,
    }
    assert "published" in result.output


def test_validate_command_uses_api_surface(monkeypatch) -> None:
    runner = CliRunner()

    class FakeValidation:
        info = ["ok"]
        warnings = []
        errors = []

    monkeypatch.setattr(cli_module, "validate_catalog", lambda: FakeValidation())

    result = runner.invoke(app, ["validate"])

    assert result.exit_code == 0
    assert "Feature catalog validation passed." in result.output


def test_smoke_command_uses_api_surface(monkeypatch) -> None:
    runner = CliRunner()
    captured: dict[str, object] = {}

    class FakeReport:
        info = ["ok"]
        failed = {}
        passed = ["example/category"]

    def fake_smoke_catalog(*, category: str | None, execute: bool):
        captured["category"] = category
        captured["execute"] = execute
        return FakeReport()

    monkeypatch.setattr(cli_module, "smoke_catalog", fake_smoke_catalog)

    result = runner.invoke(app, ["smoke", "example/category", "--execute"])

    assert result.exit_code == 0
    assert captured == {
        "category": "example/category",
        "execute": True,
    }
    assert "Smoke passed for 1 feature family(s)." in result.output


def test_main_publish_surface_calls_typer_app(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_app(*, prog_name: str, args, standalone_mode: bool):
        captured["prog_name"] = prog_name
        captured["args"] = args
        captured["standalone_mode"] = standalone_mode

    monkeypatch.setattr(cli_module, "app", fake_app)

    exit_code = main(["publish", "example/category"])

    assert exit_code == 0
    assert captured == {
        "prog_name": "qf-features",
        "args": ["publish", "example/category"],
        "standalone_mode": False,
    }


def test_removed_pipeline_command_is_not_exposed() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["pipeline"])

    assert result.exit_code != 0
    assert "No such command" in result.output
