#!/usr/bin/env python3
"""Manage the background DB API and React development servers.

Set VIZ_API_URL to point the web app at an existing DB API (e.g. one on another
machine) instead of starting a local one.

USAGE:
    uv run python apps/viz/scripts/dev.py start
    VIZ_API_URL=https://host.example uv run python apps/viz/scripts/dev.py start
    uv run python apps/viz/scripts/dev.py stop
"""

# --------------------------------------------------------------------------- #
# Imports
# --------------------------------------------------------------------------- #

import argparse
import fcntl
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------- #
# Paths and defaults
# --------------------------------------------------------------------------- #

REPO_ROOT = Path(__file__).resolve().parents[3]
VIZ_ROOT = REPO_ROOT / "apps" / "viz"
DB_API_ROOT = REPO_ROOT / "apps" / "api"
WEB_ROOT = VIZ_ROOT / "web"
EXTENSIONS_ROOT = VIZ_ROOT / "extensions"
STRATEGIES_SRC_ROOT = REPO_ROOT / "packages" / "strategies" / "src"
STRATEGY_EXTENSIONS_ROOT = REPO_ROOT / "packages" / "strategies" / "extensions"
STATE_PATH = VIZ_ROOT / ".dev-state.json"
LOCK_PATH = VIZ_ROOT / ".dev-state.lock"
API_LOG = VIZ_ROOT / "api.log"
WEB_LOG = VIZ_ROOT / "web.log"
DEFAULT_API_PORT = 8014
DEFAULT_WEB_PORT = 5174
LOCAL_HOST = "quant-factory.localhost"


def _optional_control() -> dict[str, Any] | None:
    """Return the single installed development control descriptor, if any."""
    if not EXTENSIONS_ROOT.is_dir():
        return None
    descriptors = sorted(EXTENSIONS_ROOT.glob("*/development.json"))
    if not descriptors:
        return None
    if len(descriptors) > 1:
        raise RuntimeError("Only one Viz development control is supported")
    descriptor = descriptors[0]
    raw = json.loads(descriptor.read_text(encoding="utf-8"))
    required = {"label", "entrypoint", "port_env", "url_env", "default_port", "marker", "log"}
    if not isinstance(raw, dict) or set(raw) != required:
        raise RuntimeError(f"Malformed Viz development descriptor: {descriptor}")
    entrypoint = descriptor.parent / str(raw["entrypoint"])
    if not entrypoint.is_file():
        raise RuntimeError(f"Viz development entrypoint is missing: {entrypoint}")
    return {**raw, "entrypoint": entrypoint, "log_path": VIZ_ROOT / str(raw["log"])}


# --------------------------------------------------------------------------- #
# State and process helpers
# --------------------------------------------------------------------------- #


def _read_state() -> dict[str, Any] | None:
    if not STATE_PATH.exists():
        return None
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return state if isinstance(state, dict) else None


def _write_state(state: dict[str, Any]) -> None:
    temporary = STATE_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    temporary.replace(STATE_PATH)


def _pid_command(pid: int) -> str:
    result = subprocess.run(
        ["ps", "-p", str(pid), "-o", "command="],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _service_is_owned(service: dict[str, Any]) -> bool:
    pid = service.get("pid")
    marker = service.get("marker")
    return isinstance(pid, int) and isinstance(marker, str) and marker in _pid_command(pid)


def _process_group_exists(process_group: int) -> bool:
    try:
        os.killpg(process_group, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _url_ready(url: str, timeout: float = 0.5) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310 - localhost only
            return response.status < 500
    except (OSError, urllib.error.URLError):
        return False


def _readiness_urls(api_url: str, web_port: int, control_port: int | None) -> list[str]:
    urls = [f"{api_url}/health", f"http://127.0.0.1:{web_port}/"]
    if control_port is not None:
        urls.append(f"http://127.0.0.1:{control_port}/health")
    return urls


def _state_is_ready(state: dict[str, Any]) -> bool:
    api = state.get("api")
    web = state.get("web")
    control = state.get("control")
    if not isinstance(api, dict) or not isinstance(web, dict):
        return False
    remote_url = (os.environ.get("VIZ_API_URL") or "").rstrip("/")
    if (api.get("url") != remote_url) if remote_url else api.get("remote"):
        return False  # running against a different API than this start asks for
    # A remote API is not ours to own; only the processes this script spawned are checked.
    services = ([] if remote_url else [api]) + [web] + ([control] if isinstance(control, dict) else [])
    if not all(isinstance(service.get("port"), int) for service in services):
        return False
    if not all(_service_is_owned(service) for service in services):
        return False
    control_port = control["port"] if isinstance(control, dict) else None
    urls = _readiness_urls(_api_url(api), web["port"], control_port)
    return all(_url_ready(url, timeout=3.0) for url in urls)


def _api_url(api: dict[str, Any]) -> str:
    return str(api["url"]) if api.get("remote") else f"http://127.0.0.1:{api['port']}"


def _stop_service(service: dict[str, Any]) -> None:
    if not _service_is_owned(service):
        return
    pid = service["pid"]
    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    for _ in range(20):
        if not _process_group_exists(pid):
            return
        time.sleep(0.1)
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _stop_from_state(state: dict[str, Any]) -> None:
    for name in ("web", "api", "control"):
        service = state.get(name)
        if isinstance(service, dict):
            _stop_service(service)
    STATE_PATH.unlink(missing_ok=True)


# --------------------------------------------------------------------------- #
# Port and launch helpers
# --------------------------------------------------------------------------- #


def _preferred_port(variable: str, default: int) -> int:
    raw = os.environ.get(variable)
    if raw is None:
        return default
    try:
        port = int(raw)
    except ValueError as error:
        raise RuntimeError(f"{variable} must be an integer, got {raw!r}") from error
    if not 1 <= port <= 65535:
        raise RuntimeError(f"{variable} must be between 1 and 65535")
    return port


def _port_is_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as candidate:
        candidate.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            candidate.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def _next_open_port(preferred: int, *, excluded: set[int] | None = None) -> int:
    excluded_ports = excluded or set()
    for port in range(preferred, min(preferred + 200, 65536)):
        if port not in excluded_ports and _port_is_available(port):
            return port
    raise RuntimeError(f"No open port found in {preferred}-{min(preferred + 199, 65535)}")


def _api_environment() -> dict[str, str]:
    environment = os.environ.copy()
    source_path = str(DB_API_ROOT / "src")
    existing = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = f"{source_path}:{existing}" if existing else source_path
    return environment


def _ensure_web_dependencies() -> None:
    if (WEB_ROOT / "node_modules").is_dir():
        return
    print("Installing viz web dependencies with pnpm...")
    subprocess.run(["pnpm", "install", "--frozen-lockfile"], cwd=WEB_ROOT, check=True)


def _spawn(command: list[str], *, cwd: Path, environment: dict[str, str], log_path: Path) -> int:
    with log_path.open("ab") as log:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    return process.pid


def _spawn_api(port: int) -> int:
    return _spawn(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "db_api.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--reload",
            "--reload-dir",
            str(DB_API_ROOT / "src"),
            "--reload-dir",
            str(STRATEGIES_SRC_ROOT),
            "--reload-dir",
            str(STRATEGY_EXTENSIONS_ROOT),
            "--reload-include",
            "*.toml",
        ],
        cwd=DB_API_ROOT,
        environment=_api_environment(),
        log_path=API_LOG,
    )


def _wait_until_ready(api_url: str, web_port: int, control_port: int | None) -> bool:
    urls = _readiness_urls(api_url, web_port, control_port)
    for _ in range(80):
        if all(_url_ready(url, timeout=3.0) for url in urls):
            return True
        time.sleep(0.5)
    return False


def _print_urls(state: dict[str, Any], prefix: str) -> None:
    print(prefix)
    web_url = f"http://{LOCAL_HOST}:{state['web']['port']}"
    print(f"Web: {web_url}")
    if os.environ.get("DEV_OPEN", "0") == "1":
        webbrowser.open(web_url)
    print(f"Web: http://127.0.0.1:{state['web']['port']}")
    print(f"API: {_api_url(state['api'])}")
    control = state.get("control")
    logs = [WEB_LOG] if state["api"].get("remote") else [API_LOG, WEB_LOG]
    if isinstance(control, dict):
        print(f"{control['label']}: http://127.0.0.1:{control['port']}")
        logs.append(Path(control["log_path"]))
    print(f"Logs: {', '.join(map(str, logs))}")


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #


def start() -> None:
    """Start or reuse the owned development stack."""
    state = _read_state()
    if state and _state_is_ready(state):
        _print_urls(state, "Viz is already running.")
        return
    if state:
        print("Removing stale or partial viz stack...")
        _stop_from_state(state)

    _ensure_web_dependencies()
    control_config = _optional_control()
    remote_url = (os.environ.get("VIZ_API_URL") or "").rstrip("/")
    if remote_url and not _url_ready(f"{remote_url}/health", timeout=5.0):
        raise RuntimeError(f"VIZ_API_URL {remote_url} is not answering /health")
    api_port = None if remote_url else _next_open_port(_preferred_port("VIZ_API_PORT", DEFAULT_API_PORT))
    control_port = None
    if control_config:
        control_port = _next_open_port(
            _preferred_port(str(control_config["port_env"]), int(control_config["default_port"])),
            excluded={api_port} if api_port else set(),
        )
    web_port = _next_open_port(
        _preferred_port("VIZ_WEB_PORT", DEFAULT_WEB_PORT),
        excluded={port for port in (api_port, control_port) if port is not None},
    )
    if api_port is None:
        api_url, api_state = remote_url, {"url": remote_url, "remote": True}
    else:
        api_url = f"http://127.0.0.1:{api_port}"
        api_state = {"pid": _spawn_api(api_port), "port": api_port, "marker": "uvicorn"}
    control_pid = None
    if control_config and control_port is not None:
        control_pid = _spawn(
            [sys.executable, str(control_config["entrypoint"]), "--port", str(control_port)],
            cwd=REPO_ROOT,
            environment=os.environ.copy(),
            log_path=Path(control_config["log_path"]),
        )
    web_environment = os.environ.copy()
    web_environment["VIZ_API_URL"] = api_url
    if control_config and control_port is not None:
        web_environment[str(control_config["url_env"])] = f"http://127.0.0.1:{control_port}"
    web_pid = _spawn(
        ["pnpm", "exec", "vite", "--host", "127.0.0.1", "--port", str(web_port), "--strictPort"],
        cwd=WEB_ROOT,
        environment=web_environment,
        log_path=WEB_LOG,
    )
    state = {
        "started_at": time.time(),
        "api": api_state,
        "web": {"pid": web_pid, "port": web_port, "marker": "pnpm"},
    }
    if control_config and control_port is not None and control_pid is not None:
        state["control"] = {
            "pid": control_pid,
            "port": control_port,
            "marker": control_config["marker"],
            "label": control_config["label"],
            "log_path": str(control_config["log_path"]),
        }
    _write_state(state)

    if not _wait_until_ready(api_url, web_port, control_port):
        _stop_from_state(state)
        print("Viz failed to start. Recent logs:", file=sys.stderr)
        log_paths = [WEB_LOG] if remote_url else [API_LOG, WEB_LOG]
        if control_config:
            log_paths.append(Path(control_config["log_path"]))
        for path in log_paths:
            print(f"--- {path} ---", file=sys.stderr)
            if path.exists():
                print("".join(path.read_text(errors="replace").splitlines(keepends=True)[-60:]), file=sys.stderr)
        raise RuntimeError("development stack did not become ready")
    _print_urls(state, "Viz is ready.")


def stop() -> None:
    """Stop only the development processes recorded in the state file."""
    state = _read_state()
    if not state:
        STATE_PATH.unlink(missing_ok=True)
        print("Viz is already stopped.")
        return
    _stop_from_state(state)
    print("Viz stopped.")


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def main() -> int:
    """Run a lifecycle command under an inter-process lock."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", choices=("start", "stop"), default="start")
    arguments = parser.parse_args()
    try:
        with LOCK_PATH.open("w", encoding="utf-8") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if arguments.command == "start":
                start()
            else:
                stop()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
