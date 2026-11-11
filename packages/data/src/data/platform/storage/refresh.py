"""Run registered pipelines that declare a routine ``refresh`` command: raw, then corrected, then derived.

USAGE: ``refresh_plan(cadence="daily")`` lists the steps; ``run_refresh(plan, jobs=6)`` runs them.
``step_estimates(plan, db_root)`` and ``resolve_needs(plan)`` show what the scheduler will use.
``run_refresh(plan, memory_gb=10)`` holds the whole run to 10 GB (default ``default_memory_gb()``).

Each step runs ``run-local -- <python> <pipeline> <refresh args>`` from the repository root (bare
``<python> <pipeline> ...`` with credentials from the environment when the ``run-local`` wrapper is
absent), in its own process group so a step past its timeout is killed with everything it started.
Independent steps run at the same time: a step starts once every step it ``needs`` has finished
(pass or fail; undeclared ``needs`` waits for every earlier step), at most ``jobs`` at once, within a
memory budget sized from each step's history, and never next to a running step of the same
``group``. ``jobs=1`` runs the plan in order, one step at a time.

Memory: one number, ``memory_gb`` (N), sets everything. The scheduler budget (sum of running step
estimates) is 0.9 N; each step's cap stays within the budget and reaches the step as
``QF_STEP_MEMORY_MB`` (``duckdb_runtime.duckdb_connect`` sizes DuckDB from it). On Linux
with a systemd user manager the kernel enforces it: every step runs in a transient scope
(``MemoryMax`` = its cap, ``OOMPolicy=kill``) inside ``qf-refresh.slice``, whose runtime limits are
set at the start of each run to ``MemoryMax`` N and no swap, so the run as a whole never exceeds N
even when an estimate is wrong: the kernel kills the largest process in the slice, which may be another step. No ``MemoryHigh``:
without swap it does not stop a step, it throttles it to a standstill (observed: stuck just
under the limit until killed by hand), which would hang the step until its timeout. When the runner itself runs in a user service,
each scope is bound to that service (``BindsTo``) so stopping the service stops the steps even if
the runner is killed outright.
SIGTERM/SIGHUP/Ctrl-C to the runner stop every running step (SIGTERM, 30 s, then SIGKILL).

Files under ``db/data/`` (written only here): ``refresh-log.json`` (stamp per ok step, read by
``surface-status``), ``refresh-steps.jsonl`` (one line per finished step: wall seconds, peak memory,
estimate, cap; sizes the next run's estimates), ``refresh-status.json`` (live run status, rewritten on
every change and at least every 15 s) and ``refresh-logs/<run_id>/<slug>.log`` (each step's
stdout+stderr; not rotated).
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import signal
import socket
import statistics
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Any

from config import QUANT_DB_ROOT

from data.extensions import DATA_PACKAGE_ROOT, EXTENSIONS_ROOT

from .duckdb_runtime import STEP_MEMORY_ENV
from .operator_surface_registry import OPERATOR_SCRIPTS, OperatorScript
from .parquet_runtime import write_text_atomic

# --------------------------------------------------------------------------- #
# Constants and paths
# --------------------------------------------------------------------------- #

REPO_ROOT = DATA_PACKAGE_ROOT.parents[1]
# A platform package may ship a credential wrapper at ``scripts/run-local``; steps run through it.
RUN_LOCAL = next(iter(sorted((REPO_ROOT / "packages" / "platform").glob("*/scripts/run-local"))), None)
LAYER_ORDER = ("raw", "corrected", "derived")
STEP_TIMEOUT_SECONDS = 2 * 60 * 60
TIMEOUT_RETURNCODE = 124  # GNU timeout's convention
DEFAULT_JOBS = 6
STEP_POLARS_THREADS = 8  # Polars buffers per thread: 32 used twice the memory of 8 for the same wall time
DEFAULT_ESTIMATE_MB = 3072.0  # most steps peak under 3 GB; above 6 GB, two unknown steps could never overlap
DEFAULT_MEMORY_GB = 10.0
MEMORY_GB_ENV = "QF_REFRESH_MEMORY_GB"
REFRESH_SLICE = "qf-refresh.slice"
BUDGET_FRACTION = 0.9  # scheduler budget as a share of N; the rest is headroom for estimate misses
HISTORY_RECORDS = 5
POLL_SECONDS = 0.2
HEARTBEAT_SECONDS = 15.0
FAILURE_TAIL_LINES = 40
KILL_GRACE_SECONDS = 30.0
_OOM_RETURNCODES = (-signal.SIGKILL, 128 + signal.SIGKILL)


def refresh_log_path(db_root: Path) -> Path:
    return db_root / "data" / "refresh-log.json"


def refresh_steps_path(db_root: Path) -> Path:
    return db_root / "data" / "refresh-steps.jsonl"


def refresh_status_path(db_root: Path) -> Path:
    return db_root / "data" / "refresh-status.json"


def step_log_name(run_id: str, path: str) -> str:
    """``refresh-logs/<run_id>/<slug>.log``, relative to ``db/data``; slug = path, ``/`` → ``__``, no ``.py``."""
    return f"refresh-logs/{run_id}/{path.removesuffix('.py').replace('/', '__')}.log"


def read_refresh_log(db_root: Path) -> dict[str, datetime]:
    """Pipeline path -> time of its last successful ``refresh`` step."""
    path = refresh_log_path(db_root)
    if not path.is_file():
        return {}
    return {script: datetime.fromisoformat(stamp) for script, stamp in json.loads(path.read_text()).items()}


@dataclass(frozen=True, slots=True)
class RefreshStep:
    """One finished refresh step."""

    path: str
    returncode: int
    seconds: float
    maxrss_mb: float | None = None
    """Peak memory in MB: the largest of the step's anonymous memory across all its processes
    (cgroup ``memory.stat``, sampled every poll) and its largest single process (``ru_maxrss``)."""
    oom: bool = False


# --------------------------------------------------------------------------- #
# Plan
# --------------------------------------------------------------------------- #


def refresh_plan(
    *,
    resolution: str | None = None,
    cadence: str | None = None,
    match: str | None = None,
    scripts: tuple[OperatorScript, ...] = OPERATOR_SCRIPTS,
) -> list[OperatorScript]:
    """Pipelines with a ``refresh`` command (one resolution, or all): raw, corrected, then derived, in registry order."""
    selected = [
        entry
        for entry in scripts
        if entry.root == "pipelines"
        and entry.refresh is not None
        and (resolution is None or entry.path.split("/")[1:2] == [resolution])
        and (cadence is None or entry.cadence == cadence)
        and (match is None or match in entry.path)
    ]
    return sorted(selected, key=lambda entry: LAYER_ORDER.index(entry.path.split("/")[0]))


def refresh_command(entry: OperatorScript) -> list[str]:
    """The argv for one step."""
    script = EXTENSIONS_ROOT / "pipelines" / entry.path
    wrapper = [str(RUN_LOCAL), "--"] if RUN_LOCAL is not None and RUN_LOCAL.is_file() else []
    return [*wrapper, sys.executable, str(script), *shlex.split(entry.refresh or "")]


def resolve_needs(plan: list[OperatorScript]) -> dict[str, tuple[str, ...]]:
    """Path -> the in-plan steps it waits for; raises ``ValueError`` on a cycle.

    ``needs=None`` waits for every earlier step in plan order, ``()`` for none; a ``needs`` path that
    is not in this plan (other cadence, filtered out) is ignored.
    """
    in_plan = {entry.path for entry in plan}
    resolved: dict[str, tuple[str, ...]] = {}
    for index, entry in enumerate(plan):
        if entry.needs is None:
            resolved[entry.path] = tuple(earlier.path for earlier in plan[:index])
        else:
            resolved[entry.path] = tuple(need for need in entry.needs if need in in_plan)

    done: set[str] = set()
    for root in resolved:
        if root in done:
            continue
        on_path: list[str] = [root]
        stack = [iter(resolved[root])]
        while stack:
            need = next(stack[-1], None)
            if need is None:
                stack.pop()
                done.add(on_path.pop())
            elif need in on_path:
                cycle = [*on_path[on_path.index(need) :], need]
                raise ValueError(f"refresh dependency cycle: {' -> '.join(cycle)}")
            elif need not in done:
                on_path.append(need)
                stack.append(iter(resolved[need]))
    return resolved


# --------------------------------------------------------------------------- #
# Estimates and budget
# --------------------------------------------------------------------------- #


def _read_step_history(db_root: Path) -> dict[tuple[str, str | None], list[dict[str, Any]]]:
    """``(path, refresh args)`` -> its ``refresh-steps.jsonl`` records, oldest first."""
    path = refresh_steps_path(db_root)
    history: dict[tuple[str, str | None], list[dict[str, Any]]] = {}
    if not path.is_file():
        return history
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, dict) and "path" in record:
                history.setdefault((record["path"], record.get("refresh")), []).append(record)
    return history


def _estimate_mb(records: list[dict[str, Any]]) -> float:
    # Failed runs count: their peak is real. Records without a run_id predate the memory cap and the step
    # fixes that came with it, so they only stand in until a step has a current measurement.
    usable = ([r for r in records if r.get("run_id")] or records)[-HISTORY_RECORDS:]
    peaks = [float(r["maxrss_mb"]) for r in usable if r.get("maxrss_mb") is not None]
    return round(max(peaks) * 1.25 + 512, 1) if peaks else DEFAULT_ESTIMATE_MB


def _median_seconds(records: list[dict[str, Any]]) -> float:
    seconds = [float(r["seconds"]) for r in records if r.get("returncode") == 0 and r.get("seconds") is not None]
    return statistics.median(seconds[-HISTORY_RECORDS:]) if seconds else 0.0


def step_estimates(plan: list[OperatorScript], db_root: Path = QUANT_DB_ROOT) -> dict[str, float]:
    """Path -> memory estimate in MB: last 5 peaks of the same args, ``max * 1.25 + 512``; else ``DEFAULT_ESTIMATE_MB``."""
    history = _read_step_history(db_root)
    return {entry.path: _estimate_mb(history.get((entry.path, entry.refresh), [])) for entry in plan}


def default_memory_gb() -> float:
    """The run's memory limit in GB: ``QF_REFRESH_MEMORY_GB`` when set, else ``DEFAULT_MEMORY_GB``."""
    value = os.environ.get(MEMORY_GB_ENV, "").strip()
    return float(value) if value else DEFAULT_MEMORY_GB


def budget_mb(memory_gb: float) -> float:
    """The scheduler budget for a run limited to ``memory_gb``: ``0.9 N`` in MB."""
    return round(memory_gb * 1024 * BUDGET_FRACTION, 1)


def memory_cap_available() -> bool:
    """Linux with ``systemd-run`` and a reachable user manager (``degraded`` counts: it exits 1 but runs scopes)."""
    if not sys.platform.startswith("linux") or shutil.which("systemd-run") is None:
        return False
    try:
        result = subprocess.run(
            ["systemctl", "--user", "is-system-running"], capture_output=True, text=True, timeout=10, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.stdout.strip() in {"running", "degraded"}


def _cap_mb(estimate_mb: float, budget_mb: float) -> float:
    if estimate_mb == DEFAULT_ESTIMATE_MB:  # no history: the default says nothing about what it needs
        return max(estimate_mb, budget_mb)
    # never below the estimate, so a step admitted alone above the budget is not killed for it
    return round(max(estimate_mb, min(budget_mb, max(2 * estimate_mb, estimate_mb + 4096))), 1)


def _set_slice_limit(limit_mb: float) -> None:
    """Set ``qf-refresh.slice``'s runtime limits (gone on reboot, so set every run): ``MemoryMax`` N, no swap."""
    subprocess.run(
        [
            "systemctl", "--user", "set-property", "--runtime", REFRESH_SLICE,
            f"MemoryMax={int(limit_mb)}M", "MemoryHigh=infinity", "MemorySwapMax=0",
        ],
        check=True, capture_output=True, timeout=30,
    )  # fmt: skip


def _capped(command: list[str], cap_mb: float, bind_unit: str | None = None) -> list[str]:
    # OOMPolicy=kill: the kernel OOM kills the whole scope, so the step's own pid exits -9 even under
    # a credential wrapper (which otherwise turns its child's SIGKILL into exit 255).
    scope = ["systemd-run", "--user", "--scope", "--quiet", "--collect", f"--slice={REFRESH_SLICE}"]
    props = ["-p", f"MemoryMax={int(cap_mb)}M", "-p", "MemorySwapMax=0", "-p", "OOMPolicy=kill"]
    if bind_unit is not None:
        # No After=: the service is a oneshot still activating while it runs steps, so ordering a
        # step after it would hold the step's start job until the service finishes: a deadlock.
        props += ["-p", f"BindsTo={bind_unit}"]
    return [*scope, *props, "--", *command]


def _own_cgroup() -> str | None:
    """This process's cgroup v2 path (``/user.slice/...``), or ``None`` off Linux."""
    try:
        text = Path("/proc/self/cgroup").read_text()
    except OSError:
        return None
    return next((line[3:] for line in text.splitlines() if line.startswith("0::")), None)


def _user_service_unit(cgroup: str | None) -> str | None:
    """The user-manager ``.service`` this process runs in (its own cgroup leaf), else ``None``."""
    parts = (cgroup or "").strip("/").split("/")
    in_user_manager = any(part.startswith("user@") and part.endswith(".service") for part in parts[:-1])
    return parts[-1] if in_user_manager and parts[-1].endswith(".service") else None


def _scope_cgroup(pid: int, own: str | None) -> str | None:
    """The step's scope cgroup once ``systemd-run`` has moved itself there; ``None`` until then."""
    try:
        text = Path(f"/proc/{pid}/cgroup").read_text()
    except OSError:
        return None
    cgroup = next((line[3:] for line in text.splitlines() if line.startswith("0::")), None)
    return cgroup if cgroup and cgroup != own and cgroup.endswith(".scope") else None


def _anon_mb(cgroup: str) -> float | None:
    """Anonymous memory of every process in the scope (``memory.stat`` ``anon``), MB; ``None`` once removed.

    Not ``memory.peak``: that counts page cache, which a step reading large parquet fills up to its cap
    though the kernel reclaims it freely, so estimates built on it would ratchet up run after run.
    """
    try:
        with Path("/sys/fs/cgroup", cgroup.lstrip("/"), "memory.stat").open() as handle:
            for line in handle:
                if line.startswith("anon "):
                    return round(int(line.split()[1]) / (1024 * 1024), 1)
    except OSError:
        return None
    return None


def _oom_kills(cgroup: str) -> int | None:
    """``oom_kill`` from the scope's ``memory.events``; ``None`` once systemd has removed the scope."""
    try:
        text = Path("/sys/fs/cgroup", cgroup.lstrip("/"), "memory.events").read_text()
    except OSError:
        return None
    fields = dict(line.split(" ", 1) for line in text.splitlines() if " " in line)
    return int(fields.get("oom_kill", "0"))


# --------------------------------------------------------------------------- #
# Run
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class _Step:
    """Scheduler state of one plan step."""

    index: int
    entry: OperatorScript
    needs: tuple[str, ...]
    estimate_mb: float
    median_seconds: float
    log: str
    cap_mb: float | None = None
    state: str = "pending"
    ready_at: float | None = None
    queued_at: str | None = None
    started: float = 0.0
    started_at: str | None = None
    finished_at: str | None = None
    deadline: float = 0.0
    kill_at: float | None = None
    """Set once the step timed out and got SIGTERM: SIGKILL its group at this monotonic time."""
    cgroup: str | None = None
    oom_kills: int = 0
    anon_mb: float = 0.0
    """Current anonymous memory of the step's scope (0 until seen, and off Linux)."""
    anon_peak_mb: float = 0.0
    process: subprocess.Popen[bytes] | None = None
    handle: IO[bytes] | None = None
    result: RefreshStep | None = None
    queued_seconds: float | None = None

    def status(self) -> dict[str, Any]:
        result = self.result
        return {
            "path": self.entry.path,
            "refresh": self.entry.refresh,
            "layer": self.entry.path.split("/")[0],
            "group": self.entry.group,
            "needs": list(self.needs),
            "state": self.state,
            "estimate_mb": self.estimate_mb,
            "cap_mb": self.cap_mb,
            "queued_at": self.queued_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "seconds": round(result.seconds, 1) if result else None,
            "maxrss_mb": result.maxrss_mb if result else None,
            "returncode": result.returncode if result else None,
            "log": self.log,
        }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _gb(mb: float | None) -> str:
    return f"{mb / 1024:.1f} GB" if mb is not None else "- GB"


def run_refresh(
    plan: list[OperatorScript],
    *,
    db_root: Path = QUANT_DB_ROOT,
    timeout: float = STEP_TIMEOUT_SECONDS,
    jobs: int = DEFAULT_JOBS,
    memory_gb: float | None = None,
    memory_cap: bool = True,
    cadence: str | None = None,
) -> list[RefreshStep]:
    """Run the plan within ``jobs`` and ``memory_gb`` (default ``default_memory_gb()``), continuing past
    failures; results in plan order."""
    jobs = max(1, jobs)
    memory_gb = default_memory_gb() if memory_gb is None else float(memory_gb)
    if memory_gb <= 0:
        raise ValueError(f"memory limit must be > 0 GB, got {memory_gb}")
    limit = round(memory_gb * 1024, 1)
    budget = budget_mb(memory_gb)
    capped = memory_cap and memory_cap_available()
    if capped:
        _set_slice_limit(limit)
    own_cgroup = _own_cgroup() if capped else None
    bind_unit = _user_service_unit(own_cgroup)
    needs = resolve_needs(plan)
    history = _read_step_history(db_root)
    started_dt = datetime.now(timezone.utc)
    run_started = started_dt.isoformat()
    run_id = started_dt.strftime("%Y%m%dT%H%M%SZ")
    cadences = {entry.cadence for entry in plan}
    run_cadence = cadence or (next(iter(cadences)) if len(cadences) == 1 else None)
    steps = [
        _Step(
            index=index,
            entry=entry,
            needs=needs[entry.path],
            estimate_mb=_estimate_mb(history.get((entry.path, entry.refresh), [])),
            median_seconds=_median_seconds(history.get((entry.path, entry.refresh), [])),
            log=step_log_name(run_id, entry.path),
        )
        for index, entry in enumerate(plan, start=1)
    ]
    data_dir = db_root / "data"
    (data_dir / "refresh-logs" / run_id).mkdir(parents=True, exist_ok=True)
    run: dict[str, Any] = {
        "run_id": run_id,
        "run_started": run_started,
        "cadence": run_cadence,
        "state": "running",
        "jobs": jobs,
        "limit_mb": limit,
        "budget_mb": budget,
        "memory_cap": capped,
        "peak_mb": 0.0,
    }
    print(
        f"refresh {run_id}: {len(plan)} steps, jobs {jobs}, memory {_gb(limit)} (budget {_gb(budget)}), "
        f"kernel cap {'on' if capped else 'off'}, logs {data_dir / 'refresh-logs' / run_id}",
        flush=True,
    )

    def write_status() -> None:
        payload = {
            **run,
            "updated_at": _now(),
            "finished_at": run.get("finished_at"),
            "pid": os.getpid(),
            "host": socket.gethostname(),
            "steps": [step.status() for step in steps],
        }
        write_text_atomic(json.dumps(payload, indent=2) + "\n", refresh_status_path(db_root))

    running: list[_Step] = []
    finished: set[str] = set()
    previous_handlers = _raise_on_stop_signals()
    try:
        write_status()
        last_status = time.monotonic()
        while len(finished) < len(steps):
            changed = False
            run["peak_mb"] = max(run["peak_mb"], round(sum(step.anon_mb for step in running), 1))
            for step in list(running):
                if _poll(step, timeout, own_cgroup):
                    running.remove(step)
                    finished.add(step.entry.path)
                    _finish(step, db_root, run, len(steps))
                    changed = True
            now = time.monotonic()
            for step in steps:
                if step.state == "pending" and step.ready_at is None and all(n in finished for n in step.needs):
                    step.ready_at, step.queued_at = now, _now()
            for step in _admissible(steps, running, jobs=jobs, budget_mb=budget):
                step.cap_mb = _cap_mb(step.estimate_mb, budget)
                _start(step, data_dir, timeout, running, bind_unit, capped=capped)
                in_use = sum(s.estimate_mb for s in running)
                print(
                    f"[{step.index}/{len(steps)}] start  {step.entry.path} (est {_gb(step.estimate_mb)}, "
                    f"{len(running)} running, {in_use / 1024:.1f}/{budget / 1024:.1f} GB)",
                    flush=True,
                )
                changed = True
            if changed or time.monotonic() - last_status >= HEARTBEAT_SECONDS:
                write_status()
                last_status = time.monotonic()
            if not changed:
                time.sleep(POLL_SECONDS)
    except BaseException:
        for sig in previous_handlers:
            signal.signal(sig, signal.SIG_IGN)  # a second Ctrl-C/SIGTERM must not cut the cleanup short
        _stop_all(running)
        for step in steps:
            if step.handle is not None and not step.handle.closed:
                step.handle.close()
            if step.state == "running":
                step.state, step.finished_at = "failed", _now()
        run["state"], run["finished_at"] = "finished", _now()
        write_status()
        raise
    finally:
        for sig, handler in previous_handlers.items():
            signal.signal(sig, handler)
    run["state"], run["finished_at"] = "finished", _now()
    write_status()
    return [step.result for step in steps if step.result is not None]


def _admissible(steps: list[_Step], running: list[_Step], *, jobs: int, budget_mb: float) -> list[_Step]:
    """Ready steps to start now: longest median first (plan order with ``jobs=1``), within jobs/budget/groups."""
    ready = [step for step in steps if step.state == "pending" and step.ready_at is not None]
    if jobs > 1:
        ready.sort(key=lambda step: (-step.median_seconds, step.index))
    chosen: list[_Step] = []
    count = len(running)
    in_use = sum(step.estimate_mb for step in running)
    groups = {step.entry.group for step in running if step.entry.group is not None}
    for step in ready:
        if count >= jobs:
            break
        if count > 0:  # nothing running: the first ready step starts, even above the budget
            if step.entry.group is not None and step.entry.group in groups:
                continue  # blocked by its group: a lower-ranked step may go instead
            if in_use + step.estimate_mb > budget_mb:
                break  # head-of-queue reservation: smaller steps must not starve the top-ranked one
        chosen.append(step)
        count += 1
        in_use += step.estimate_mb
        if step.entry.group is not None:
            groups.add(step.entry.group)
    return chosen


def _start(
    step: _Step, data_dir: Path, timeout: float, running: list[_Step], bind_unit: str | None, *, capped: bool
) -> None:
    """Launch one step and add it to ``running``; it is ``running`` only once ``Popen`` succeeded.

    The step always gets its cap as ``QF_STEP_MEMORY_MB``; with ``capped`` the kernel also enforces it.
    """
    assert step.cap_mb is not None
    command = refresh_command(step.entry)
    if capped:
        command = _capped(command, step.cap_mb, bind_unit)
    handle = (data_dir / step.log).open("ab")
    try:
        handle.write(f"$ {shlex.join(command)}\n".encode())
        handle.flush()
        process = subprocess.Popen(
            command,
            cwd=REPO_ROOT,
            start_new_session=True,
            stdout=handle,
            stderr=subprocess.STDOUT,
            env={
                "POLARS_MAX_THREADS": str(STEP_POLARS_THREADS),  # an exported value wins
                **os.environ,
                "PYTHONUNBUFFERED": "1",
                STEP_MEMORY_ENV: str(int(step.cap_mb)),
            },
        )
    except BaseException:
        handle.close()
        raise
    step.process, step.handle = process, handle
    step.state = "running"
    running.append(step)
    step.started = time.monotonic()
    step.started_at = _now()
    step.queued_seconds = round(step.started - (step.ready_at or step.started), 1)
    step.deadline = step.started + timeout


def _poll(step: _Step, timeout: float, own_cgroup: str | None) -> bool:
    """Reap, time out or escalate one running step without blocking; ``True`` once it has a result.

    A step past its timeout gets SIGTERM on its group and ``KILL_GRACE_SECONDS`` before SIGKILL; it is
    recorded (returncode 124) when reaped. OOM = exit by SIGKILL (the scope's ``OOMPolicy=kill``) or a
    non-zero ``oom_kill`` seen in the scope's ``memory.events`` (best effort: systemd removes the
    scope within milliseconds of the kill, so the 0.2 s poll often misses it).
    """
    process = step.process
    assert process is not None
    if own_cgroup is not None:
        if step.cgroup is None:
            step.cgroup = _scope_cgroup(process.pid, own_cgroup)
        if step.cgroup is not None:
            step.oom_kills = max(step.oom_kills, _oom_kills(step.cgroup) or 0)
            step.anon_mb = _anon_mb(step.cgroup) or step.anon_mb
            step.anon_peak_mb = max(step.anon_peak_mb, step.anon_mb)
    pid, status, usage = os.wait4(process.pid, os.WNOHANG)
    now = time.monotonic()
    if not pid:
        if step.kill_at is None and now >= step.deadline:
            _signal_group(process, signal.SIGTERM)
            step.kill_at = now + KILL_GRACE_SECONDS
            if step.handle is not None:
                step.handle.write(f"\ntimed out after {timeout:.0f}s; SIGTERM sent\n".encode())
                step.handle.flush()
        elif step.kill_at is not None and now >= step.kill_at:
            _signal_group(process, signal.SIGKILL)
            step.kill_at = float("inf")  # SIGKILL once; keep polling until reaped
        return False
    seconds = now - step.started
    process.returncode = returncode = os.waitstatus_to_exitcode(status)
    if step.kill_at is not None:
        step.result = RefreshStep(step.entry.path, TIMEOUT_RETURNCODE, seconds, None)
        step.state = "timeout"
    else:
        maxrss = max(_maxrss_mb(usage.ru_maxrss), step.anon_peak_mb)
        if step.cgroup is not None:
            step.oom_kills = max(step.oom_kills, _oom_kills(step.cgroup) or 0)
        oom = returncode != 0 and (returncode in _OOM_RETURNCODES or step.oom_kills > 0)
        if oom and own_cgroup is not None:
            maxrss = step.cap_mb
        step.result = RefreshStep(step.entry.path, returncode, seconds, maxrss, oom)
        step.state = "ok" if returncode == 0 else ("oom" if oom else "failed")
    if step.handle is not None:
        step.handle.close()
    step.finished_at = _now()
    step.anon_mb = 0.0
    return True


_STOP_SIGNALS = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)


class RefreshStopped(KeyboardInterrupt):
    """The runner got SIGTERM or SIGHUP; raised from the signal handler like Ctrl-C's ``KeyboardInterrupt``."""


def _raise_on_stop_signals() -> dict[int, Any]:
    """Make SIGTERM/SIGHUP raise ``RefreshStopped``; the previous handlers, to restore (none off the main thread)."""
    if threading.current_thread() is not threading.main_thread():
        return {}

    def handler(signum: int, _frame: object) -> None:
        raise RefreshStopped(f"refresh stopped by {signal.Signals(signum).name}")

    previous: dict[int, Any] = {sig: signal.getsignal(sig) for sig in _STOP_SIGNALS}
    signal.signal(signal.SIGTERM, handler)
    signal.signal(signal.SIGHUP, handler)
    return previous


def _stop_all(running: list[_Step]) -> None:
    """SIGTERM every running step's group, wait on all against one shared deadline, then SIGKILL the rest."""
    alive = [step.process for step in running if step.process is not None and step.process.returncode is None]
    for process in alive:
        _signal_group(process, signal.SIGTERM)
    deadline = time.monotonic() + KILL_GRACE_SECONDS
    while alive and time.monotonic() < deadline:
        alive = [process for process in alive if not _reaped(process)]
        if alive:
            time.sleep(POLL_SECONDS)
    for process in alive:
        _signal_group(process, signal.SIGKILL)
    for process in alive:
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass  # stuck in the kernel; the scope (BindsTo) or the OS has the last word


def _reaped(process: subprocess.Popen[bytes]) -> bool:
    try:
        pid, status = os.waitpid(process.pid, os.WNOHANG)
    except ChildProcessError:
        return True
    if pid:
        process.returncode = os.waitstatus_to_exitcode(status)
    return bool(pid)


def _signal_group(process: subprocess.Popen[bytes], sig: signal.Signals) -> None:
    try:
        os.killpg(process.pid, sig)
    except (ProcessLookupError, PermissionError):
        pass


def _finish(step: _Step, db_root: Path, run: dict[str, Any], total: int) -> None:
    result = step.result
    assert result is not None
    print(
        f"[{step.index}/{total}] {step.state:<6} {step.entry.path}  {result.seconds:.0f}s {_gb(result.maxrss_mb)}",
        flush=True,
    )
    if step.state != "ok":
        log_path = db_root / "data" / step.log
        with log_path.open(encoding="utf-8", errors="replace") as handle:
            tail = deque(handle, maxlen=FAILURE_TAIL_LINES)
        print("".join(f"    | {line}" for line in tail).rstrip(), flush=True)
    _append_step_record(
        db_root,
        run["run_started"],
        step.started_at or "",
        step.entry,
        result,
        run_id=run["run_id"],
        estimate_mb=step.estimate_mb,
        cap_mb=step.cap_mb,
        queued_seconds=step.queued_seconds,
        log=step.log,
        jobs=run["jobs"],
        limit_mb=run["limit_mb"],
        budget_mb=run["budget_mb"],
    )
    if result.returncode == 0:
        _stamp_refresh_log(db_root, step.entry.path)


def _run_step(command: list[str], *, timeout: float) -> int:
    """Run one step in a new process group; on timeout or Ctrl-C kill the whole group."""
    return _run_step_measured(command, timeout=timeout)[0]


def _run_step_measured(command: list[str], *, timeout: float) -> tuple[int, float | None]:
    """``_run_step`` plus the peak RSS in MB of the step's largest process (``wait4`` rusage).

    ``ru_maxrss`` covers the child and every descendant it reaped, so a ``run-local`` wrapper still
    reports the pipeline's own peak. It is the largest single process, not the sum of the group.
    """
    process = subprocess.Popen(command, cwd=REPO_ROOT, start_new_session=True)
    deadline = time.monotonic() + timeout
    try:
        while True:
            pid, status, usage = os.wait4(process.pid, os.WNOHANG)
            if pid:
                process.returncode = os.waitstatus_to_exitcode(status)
                return process.returncode, _maxrss_mb(usage.ru_maxrss)
            if time.monotonic() >= deadline:
                _kill_group(process)
                return TIMEOUT_RETURNCODE, None
            time.sleep(POLL_SECONDS)
    except BaseException:
        _kill_group(process)
        raise


def _maxrss_mb(ru_maxrss: int) -> float:
    """``ru_maxrss`` is KiB on Linux and bytes on macOS."""
    return round(ru_maxrss / (1024 * 1024 if sys.platform == "darwin" else 1024), 1)


def _append_step_record(
    db_root: Path,
    run_started: str,
    started_at: str,
    entry: OperatorScript,
    step: RefreshStep,
    **extra: Any,
) -> None:
    record = {
        "run_started": run_started,
        "started_at": started_at,
        "path": step.path,
        "cadence": entry.cadence,
        "refresh": entry.refresh,
        "returncode": step.returncode,
        "seconds": round(step.seconds, 1),
        "maxrss_mb": step.maxrss_mb,
        "oom": step.oom,
        **extra,
    }
    path = refresh_steps_path(db_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")


def _kill_group(process: subprocess.Popen[bytes]) -> None:
    for sig, grace in ((signal.SIGTERM, 30), (signal.SIGKILL, None)):
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            return
        try:
            process.wait(timeout=grace)
            return
        except subprocess.TimeoutExpired:
            continue


def _stamp_refresh_log(db_root: Path, script: str) -> None:
    log = {name: stamp.isoformat() for name, stamp in read_refresh_log(db_root).items()}
    log[script] = datetime.now(timezone.utc).isoformat()
    write_text_atomic(json.dumps(dict(sorted(log.items())), indent=2) + "\n", refresh_log_path(db_root))


__all__ = [
    "DEFAULT_ESTIMATE_MB",
    "DEFAULT_JOBS",
    "DEFAULT_MEMORY_GB",
    "STEP_MEMORY_ENV",
    "STEP_TIMEOUT_SECONDS",
    "RefreshStep",
    "RefreshStopped",
    "budget_mb",
    "default_memory_gb",
    "memory_cap_available",
    "read_refresh_log",
    "refresh_command",
    "refresh_plan",
    "refresh_status_path",
    "resolve_needs",
    "run_refresh",
    "step_estimates",
    "step_log_name",
]
