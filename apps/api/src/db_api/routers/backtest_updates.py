"""Updated backtests for the Backtesting page: read curves and start one version's update.

USAGE::

    GET  /api/backtest-updates/{family}              # {version: {backtest_run_at, updatable}}
    GET  /api/backtest-updates/{family}/{version}    # updated curves per preset + the last job
    POST /api/backtest-updates/{family}/{version}    # rerun every preset on the newest inputs

The job runs in the background (``strategies.backtest_updates``) and writes beside the
published backtest under ``research/strategies/<family>/<version>/updated/``; the published
record is never touched.
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
import re
from typing import Any

from fastapi import APIRouter, HTTPException

from strategies import backtest_updates

from ..config import settings

router = APIRouter()
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


@router.get("/{family}")
def list_family(family: str) -> dict[str, dict[str, Any]]:
    _check(family)
    dates = backtest_updates.backtest_run_dates(family)
    updatable = {version for _, version in backtest_updates.reruns(family)}
    return {version: dict(backtest_run_at=dates.get(version), updatable=version in updatable)
            for version in sorted(set(dates) | updatable)}


@router.get("/{family}/{version}")
def get_version(family: str, version: str) -> dict[str, Any]:
    _check(family, version)
    return backtest_updates.load_view(settings.db_root, family, version)


@router.post("/{family}/{version}", status_code=202)
def start_update(family: str, version: str) -> dict[str, Any]:
    _check(family, version)
    try:
        return backtest_updates.start_update(settings.db_root, family, version)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _check(*names: str) -> None:
    if not all(_NAME.match(name) and ".." not in name for name in names):
        raise HTTPException(status_code=400, detail="invalid version path")
