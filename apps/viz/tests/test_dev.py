"""Verify optional Viz extensions and direct local development URLs.

USAGE: ``uv run pytest apps/viz/tests/test_dev.py -q``.
"""

# --------------------------------------------------------------------------- #
# Imports
# --------------------------------------------------------------------------- #

from pathlib import Path

import pytest
from apps.viz.scripts import dev

# --------------------------------------------------------------------------- #
# Extension discovery
# --------------------------------------------------------------------------- #


def test_missing_extension_root_has_no_optional_control(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(dev, "EXTENSIONS_ROOT", tmp_path / "missing")

    assert dev._optional_control() is None


def test_malformed_optional_control_fails_loudly(monkeypatch, tmp_path: Path) -> None:
    extension = tmp_path / "installed"
    extension.mkdir()
    (extension / "development.json").write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(dev, "EXTENSIONS_ROOT", tmp_path)

    try:
        dev._optional_control()
    except RuntimeError as error:
        assert "Malformed Viz development descriptor" in str(error)
    else:
        raise AssertionError("malformed descriptor was accepted")


# --------------------------------------------------------------------------- #
# Direct local development URL
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("dev_open", [None, "0", "1"])
def test_browser_opens_named_url_only_when_requested(monkeypatch, capsys, dev_open) -> None:
    opened = []
    if dev_open is None:
        monkeypatch.delenv("DEV_OPEN", raising=False)
    else:
        monkeypatch.setenv("DEV_OPEN", dev_open)
    monkeypatch.setattr(dev.webbrowser, "open", opened.append)
    state = {"web": {"port": 5175}, "api": {"port": 8014}}

    dev._print_urls(state, "Viz is ready.")

    assert opened == (["http://quant-factory.localhost:5175"] if dev_open == "1" else [])
    assert "Web: http://quant-factory.localhost:5175" in capsys.readouterr().out
