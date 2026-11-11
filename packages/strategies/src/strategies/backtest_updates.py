"""Updated backtests: rerun one version on the newest inputs, beside its published backtest.

USAGE: start_update(db_root, "<family>", "v002")   # background job, every preset
       view = load_view(db_root, "<family>", "v002")
       dates = backtest_run_dates("<family>")      # {"v002": "2024-01-01T00:00:00Z", ...}
       python -m strategies.backtest_updates <db_root> <family> <version> [--here]   # what the job runs

A version can be updated when its directory holds ``rerun.py`` with ``PRESETS`` (its tradable
arms) and ``build(preset)``, a ``StrategyRunner`` for that arm on the newest complete inputs.
The job runs each preset (an event-driven runner through ``run_nav()``) and writes its daily
NAV to ``research/strategies/<family>/<version>/updated/<preset>.parquet`` with a
``<preset>.json`` status; ``job.json`` and ``job.log`` record the last job. A version with a
recorded commit (``checkout.recorded_commit``) always runs on that commit (``checkout.rerun``); one
without runs in this checkout. The published backtest (``surface.json`` and its run) is never touched.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Layout
# --------------------------------------------------------------------------- #
import importlib.util
import json
import os
import subprocess
import sys
import tomllib
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import polars as pl

from . import checkout
from .paths import FAMILIES_ROOT
from .runner import StrategyRunner


def updated_dir(db_root: Path, family: str, version: str) -> Path:
    return Path(db_root) / "research" / "strategies" / family / version / "updated"


def backtest_run_dates(family: str) -> dict[str, str]:
    """``{version: backtest_run_at}`` for every version whose ``VERSION.toml`` records it."""
    dates: dict[str, str] = {}
    for path in (FAMILIES_ROOT / family / "optimization").glob("**/VERSION.toml"):
        if ".dev" not in path.parts and (at := tomllib.loads(path.read_text()).get("backtest_run_at")):
            dates.setdefault(path.parent.name, at)
    return dict(sorted(dates.items()))


def reruns(family: str | None = None) -> dict[tuple[str, str], Path]:
    """``{(family, version): rerun.py}`` for every updatable version, optionally of one family."""
    found = {(path.relative_to(FAMILIES_ROOT).parts[0], path.parent.name): path
             for path in FAMILIES_ROOT.glob(f"{family or '*'}/optimization/**/rerun.py")
             if ".dev" not in path.parts}
    return dict(sorted(found.items()))


def load_rerun(family: str, version: str) -> ModuleType:
    """The version's ``rerun.py``, under a module name unique to the family and version."""
    path = reruns(family).get((family, version))
    if path is None:
        raise ValueError(f"{family} {version} has no rerun.py; it cannot be rerun")
    name = f"strategies_rerun_{family.replace('-', '_')}_{version}"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            del sys.modules[name]
            raise
    return sys.modules[name]


def targets(family: str | None = None, version: str | None = None) -> list[tuple[str, str, str]]:
    """Every ``(family, version, preset)`` a ``rerun.py`` offers, optionally narrowed."""
    return [(f, v, p) for f, v in reruns(family) if version in (None, v)
            for p in load_rerun(f, v).PRESETS]


# --------------------------------------------------------------------------- #
# Update: the version's own backtest through the newest inputs
# --------------------------------------------------------------------------- #
def daily_nav(account: pl.DataFrame) -> pl.DataFrame:
    """One row per UTC day: closing NAV."""
    return account.group_by(pl.col("timestamp").dt.truncate("1d")).agg(pl.col("nav").last()).sort("timestamp")


def _write_atomic(path: Path, write) -> None:
    temporary = path.with_suffix(".tmp")
    write(temporary)
    temporary.replace(path)


def update_preset(db_root: Path, family: str, version: str, preset: str) -> dict[str, Any]:
    rerun = load_rerun(family, version)
    if preset not in rerun.PRESETS:
        raise ValueError(f"{family} {version} has no preset {preset!r}; it has {list(rerun.PRESETS)}")
    runner: StrategyRunner = rerun.build(preset)
    if runner.event_driven:  # the family's own execution and accounting
        account = runner.run_nav()
    elif runner.account_aware:
        runner.run()
        account = runner.last_intent_result.account
    else:  # a weight-history backtest's equity, stamped with its weight rows
        result = runner.run()
        equity = result.backtest.to_dataframe().rename({"equity": "nav"})
        stamps = result.effective_weights.weights["timestamp"].tail(equity.height)
        account = equity.with_columns(stamps.alias("timestamp"))
    nav = daily_nav(account)
    folder = updated_dir(db_root, family, version)
    folder.mkdir(parents=True, exist_ok=True)
    status = dict(preset=preset, refreshed_at=datetime.now(UTC).isoformat(),
                  inputs_end=nav["timestamp"].max().isoformat(), nav=float(nav["nav"][-1]))
    _write_atomic(folder / f"{preset}.parquet", nav.write_parquet)
    _write_atomic(folder / f"{preset}.json", lambda p: p.write_text(json.dumps(status, indent=2) + "\n"))
    return status


def update_version(db_root: Path, family: str, version: str, *, here: bool = False) -> None:
    """Update every preset, on the version's recorded commit when it has one (``here``: in this checkout)."""
    if not here and (commit := checkout.recorded_commit(family, version)):
        _update_on_commit(db_root, family, version, commit)
        return
    presets = load_rerun(family, version).PRESETS
    if not presets:
        raise ValueError(f"{family} {version} rerun.py lists no presets; it cannot be rebuilt on newer inputs")
    for preset in presets:
        print(f"{family} {version} {preset}: {update_preset(db_root, family, version, preset)}", flush=True)


def _update_on_commit(db_root: Path, family: str, version: str, commit: str) -> None:
    command = ["python", "-m", "strategies.backtest_updates", str(db_root), family, version, "--here"]
    if checkout.rerun(family, version, command) != 0:
        raise RuntimeError(f"{family} {version} failed on its own commit {commit}")


# --------------------------------------------------------------------------- #
# Job: one background update per version
# --------------------------------------------------------------------------- #
def _alive(pid: int | None) -> bool:
    if pid is None:
        return True  # just launched; start_update records the pid next
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    stat = Path(f"/proc/{pid}/stat")  # an unreaped child of the API is a zombie, not a live job
    return not (stat.is_file() and stat.read_text().rsplit(")", 1)[-1].split()[0] == "Z")


def job_status(db_root: Path, family: str, version: str) -> dict[str, Any] | None:
    path = updated_dir(db_root, family, version) / "job.json"
    if not path.is_file():
        return None
    job = json.loads(path.read_text())
    if job["state"] == "running" and not _alive(job.get("pid")):
        job |= dict(state="failed", error="the job stopped without reporting; see job.log")
    return job


def _write_job(db_root: Path, family: str, version: str, **job: Any) -> None:
    folder = updated_dir(db_root, family, version)
    folder.mkdir(parents=True, exist_ok=True)
    _write_atomic(folder / "job.json", lambda p: p.write_text(json.dumps(job, indent=2) + "\n"))


def start_update(db_root: Path, family: str, version: str) -> dict[str, Any]:
    """Start the background job; raises ``LookupError`` without ``rerun.py``, ``RuntimeError`` while one runs."""
    if (family, version) not in reruns(family):
        raise LookupError(f"{family} {version} has no rerun.py; it cannot be updated")
    current = job_status(db_root, family, version)
    if current and current["state"] == "running":
        raise RuntimeError(f"{family} {version} is already updating")
    started = datetime.now(UTC).isoformat()
    _write_job(db_root, family, version, state="running", started_at=started)
    with (updated_dir(db_root, family, version) / "job.log").open("w") as log:
        child = subprocess.Popen([sys.executable, "-m", "strategies.backtest_updates", str(db_root), family, version],
                                 stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True,
                                 env=checkout.SINGLE_THREAD | dict(os.environ))
    job = job_status(db_root, family, version)
    if job and job["state"] == "running" and "pid" not in job:  # unless the job already finished
        _write_job(db_root, family, version, state="running", started_at=started, pid=child.pid)
    return job_status(db_root, family, version)


# --------------------------------------------------------------------------- #
# View: everything the Backtesting page draws for one version
# --------------------------------------------------------------------------- #
def load_view(db_root: Path, family: str, version: str) -> dict[str, Any]:
    folder = updated_dir(db_root, family, version)
    presets = []
    for path in sorted(folder.glob("*.parquet")):
        nav = pl.read_parquet(path)
        presets.append(dict(**json.loads(path.with_suffix(".json").read_text()),
                            series=[dict(timestamp=t.isoformat(), nav=v) for t, v in nav.iter_rows()]))
    return dict(family=family, version=version, updatable=(family, version) in reruns(family),
                job=job_status(db_root, family, version), presets=presets)


# --------------------------------------------------------------------------- #
# Entry point: the job ``start_update`` launches
# --------------------------------------------------------------------------- #
def main(argv: list[str]) -> int:
    db_root, family, version = Path(argv[0]), argv[1], argv[2]
    here = "--here" in argv[3:]
    started = (job_status(db_root, family, version) or {}).get("started_at", datetime.now(UTC).isoformat())
    try:
        update_version(db_root, family, version, here=here)
    except Exception as exc:
        if not here:
            _write_job(db_root, family, version, state="failed", started_at=started,
                       finished_at=datetime.now(UTC).isoformat(), error=f"{type(exc).__name__}: {exc}")
        raise
    if not here:
        _write_job(db_root, family, version, state="done", started_at=started,
                   finished_at=datetime.now(UTC).isoformat())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
