"""Prove the public Features core works without an extension overlay.

USAGE: ``uv run pytest packages/features/tests/test_zero_extensions.py -q``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

# --------------------------------------------------------------------------- #
# Zero-extension artifact smoke
# --------------------------------------------------------------------------- #

FEATURES_ROOT = Path(__file__).resolve().parents[1]


def test_core_import_api_validation_and_cli_help_without_extensions(tmp_path: Path) -> None:
    isolated_src = tmp_path / "src"
    shutil.copytree(
        FEATURES_ROOT / "src",
        isolated_src,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(isolated_src)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import features; "
                "from features.api import PUBLISHABLE_FAMILIES, list_feature_catalog, validate_catalog; "
                "from features.cli.main import main; "
                "assert PUBLISHABLE_FAMILIES == {}; "
                "assert list_feature_catalog() == []; "
                "assert validate_catalog().valid; "
                "assert main(['--help']) == 0"
            ),
        ],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
