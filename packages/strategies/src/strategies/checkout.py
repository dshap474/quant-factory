"""Rerun a version on the code it ran: a scratch Git worktree at its recorded commit.

USAGE: qf-strategies rerun <family> v001 -- python -m pytest packages/strategies/extensions/lib/<family>
       code = rerun("<family>", "v001", ["python", "-m", "pytest"])   # the command's exit code

The commit is the version's ``VERSION.toml`` ``src_commit``; versions recorded before that field use
``default_commit`` from the family's ``optimization/RERUN.toml``. Git-ignored data the old code reads is
linked in from this checkout: ``db/`` plus the ``links`` that file lists. The command runs from the
worktree root through ``uv run --locked``, so it gets that commit's dependencies. The links are removed
before the worktree, so cleanup never reaches the linked data. The command also gets single-thread
BLAS and OpenMP (``SINGLE_THREAD``, unless already set): research accounts are recorded that way, and a
thread count fixed before Python starts is the only one that reproduces them bit for bit.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Imports
# --------------------------------------------------------------------------- #
import os
import shutil
import subprocess
import tempfile
import tomllib
from pathlib import Path

from .paths import FAMILIES_ROOT, STRATEGIES_ROOT
from .records import version_dir

REPO_ROOT = STRATEGIES_ROOT.parents[1]
# Read by OpenBLAS and OpenMP when they load; setting a limit later in the process gives other last digits.
SINGLE_THREAD = {"OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"}


# --------------------------------------------------------------------------- #
# What to check out
# --------------------------------------------------------------------------- #
def family_config(family: str) -> dict:
    """The family's ``optimization/RERUN.toml``, or ``{}``."""
    path = FAMILIES_ROOT / family / "optimization" / "RERUN.toml"
    return tomllib.loads(path.read_text()) if path.is_file() else {}


def recorded_commit(family: str, version: str) -> str | None:
    """The commit ``version`` ran on: its ``src_commit``, else the family's ``default_commit``, else None."""
    folder = version_dir(family, version)
    commit = folder and tomllib.loads((folder / "VERSION.toml").read_text()).get("src_commit")
    return commit or family_config(family).get("default_commit")


def commit_for(family: str, version: str) -> str:
    """``recorded_commit``, raising when there is none."""
    commit = recorded_commit(family, version)
    if not commit:
        raise ValueError(f"{family} {version} records no src_commit and {family} has no RERUN.toml default_commit")
    return commit


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def rerun(family: str, version: str, command: list[str]) -> int:
    """Run ``command`` in a scratch worktree at the version's commit."""
    commit = commit_for(family, version)
    links = ["db", *family_config(family).get("links", [])]
    # uv cannot hardlink from its cache into /tmp (another filesystem); copy quietly instead.
    env = SINGLE_THREAD | {key: value for key, value in os.environ.items() if key != "VIRTUAL_ENV"} | {"UV_LINK_MODE": "copy"}
    with tempfile.TemporaryDirectory(prefix=f"{family}-{version}-") as scratch:
        tree = Path(scratch) / "checkout"
        subprocess.run(["git", "-C", str(REPO_ROOT), "worktree", "add", "--detach", str(tree), commit], check=True)
        made: list[Path] = []
        try:
            for name in links:
                link = tree / name
                if link.is_dir():  # tracked files under an ignored data root
                    shutil.rmtree(link)
                link.parent.mkdir(parents=True, exist_ok=True)
                link.symlink_to(REPO_ROOT / name, target_is_directory=True)
                made.append(link)
            return subprocess.run(["uv", "run", "--locked", *command], cwd=tree, env=env).returncode
        finally:
            for link in made:
                link.unlink()
            subprocess.run(["git", "-C", str(REPO_ROOT), "worktree", "remove", "--force", str(tree)], check=True)
