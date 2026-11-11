"""Verify the optional Signals extension boundary.

USAGE: ``uv run --frozen pytest packages/signals/tests/test_extension_loading.py -q``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from signals import SignalRegistry

# --------------------------------------------------------------------------- #
# Zero-extension core
# --------------------------------------------------------------------------- #


def test_core_imports_registry_validation_and_cli_work_without_extensions(tmp_path: Path) -> None:
    """An extracted core source tree remains useful without an overlay."""
    source_root = tmp_path / "src"
    shutil.copytree(Path(__file__).resolve().parents[1] / "src" / "signals", source_root / "signals")
    script = """
import signals
import signals.api
from signals import SignalRegistry, list_signals, validate_signal_catalog
from signals.cli import app
from typer.testing import CliRunner

assert list_signals(include_planned=True) == []
assert SignalRegistry.list() == []
assert validate_signal_catalog().valid
try:
    SignalRegistry.get("missing")
except KeyError:
    pass
else:
    raise AssertionError("missing extension did not return the registry's not-found error")
assert CliRunner().invoke(app, ["--help"]).exit_code == 0
assert CliRunner().invoke(app, ["list"]).exit_code == 0
assert CliRunner().invoke(app, ["validate"]).exit_code == 0
"""
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(source_root)
    subprocess.run([sys.executable, "-c", script], cwd=tmp_path, env=environment, check=True)


# --------------------------------------------------------------------------- #
# Registry duplicate safety
# --------------------------------------------------------------------------- #


def test_signal_registration_is_idempotent_for_the_same_runner() -> None:
    """Registering one runner twice preserves the existing idempotent path."""
    signal_type = "extension-loading-idempotent"

    class DemoRunner:
        pass

    SignalRegistry.register(signal_type)(DemoRunner)
    SignalRegistry.register(signal_type)(DemoRunner)
    SignalRegistry.unregister(signal_type)


def test_signal_registration_rejects_duplicate_family() -> None:
    """A second runner cannot silently replace a registered signal ID."""
    import pytest

    signal_type = "extension-loading-duplicate"

    class FirstRunner:
        pass

    class SecondRunner:
        pass

    SignalRegistry.register(signal_type)(FirstRunner)
    try:
        with pytest.raises(ValueError, match="already registered"):
            SignalRegistry.register(signal_type)(SecondRunner)
    finally:
        SignalRegistry.unregister(signal_type)
