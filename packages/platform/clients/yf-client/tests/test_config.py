"""Verify yf-client configuration remains read-only until an export occurs.

USAGE: ``uv run pytest packages/platform/clients/yf-client/tests/test_config.py -q``.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# --------------------------------------------------------------------------- #
# Import behavior
# --------------------------------------------------------------------------- #


def test_package_import_does_not_create_exports_directory(tmp_path: Path) -> None:
    subprocess.run(
        [sys.executable, "-c", "import yf_client"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )

    assert not (tmp_path / "exports").exists()
