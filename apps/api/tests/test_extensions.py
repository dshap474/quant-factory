"""Contract tests for optional DB API extension discovery.

USAGE: ``uv run pytest apps/api/tests/test_extensions.py -q``
"""

from pathlib import Path

import pytest
from db_api.extensions import ExtensionError
from db_api.main import create_app
from fastapi.testclient import TestClient

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _write_extension(root: Path, name: str, route: str) -> None:
    extension = root / name
    extension.mkdir(parents=True)
    (extension / "extension.py").write_text(
        "\n".join(
            (
                "from fastapi import FastAPI",
                "def endpoint(): return {'extension': True}",
                "def register(app: FastAPI):",
                f"    app.add_api_route('{route}', endpoint, methods=['GET'])",
            )
        ),
        encoding="utf-8",
    )


# --------------------------------------------------------------------------- #
# Contracts
# --------------------------------------------------------------------------- #


def test_missing_extension_root_is_a_valid_public_app(tmp_path: Path) -> None:
    app = create_app(extension_root=tmp_path / "missing")

    assert app.state.loaded_extensions == ()
    assert TestClient(app).get("/health").status_code == 200


def test_extensions_load_in_deterministic_order_and_ignore_private_directories(tmp_path: Path) -> None:
    _write_extension(tmp_path, "z-last", "/z")
    _write_extension(tmp_path, "a-first", "/a")
    (tmp_path / "_archive").mkdir()

    app = create_app(extension_root=tmp_path)

    assert app.state.loaded_extensions == ("a-first", "z-last")
    assert TestClient(app).get("/a").status_code == 200


def test_installed_extension_without_entrypoint_fails_loudly(tmp_path: Path) -> None:
    (tmp_path / "broken").mkdir()

    with pytest.raises(ExtensionError, match="missing extension.py"):
        create_app(extension_root=tmp_path)


def test_duplicate_method_path_registration_is_rejected(tmp_path: Path) -> None:
    _write_extension(tmp_path, "duplicate", "/health")

    with pytest.raises(ExtensionError, match="duplicates route GET /health"):
        create_app(extension_root=tmp_path)
