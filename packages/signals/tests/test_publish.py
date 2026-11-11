"""Verify registry-driven publication against a temporary db root.

Every test here registers a fake family and writes only under ``tmp_path``; the
real ``db/`` and the real extension families are never touched.

USAGE: ``uv run pytest packages/signals/tests/test_publish.py -q``.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import polars as pl
import pytest
from signals.publish import LEDGER_FILENAME, RECORD_FIELDS, publish_catalog, select_targets

from signals import PredictionStore, SignalRegistry, SignalRunConfig, SignalRunner

# --------------------------------------------------------------------------- #
# Fake family fixtures
# --------------------------------------------------------------------------- #

ACTIVE_TYPE = "publish-fake-active"
PLANNED_TYPE = "publish-fake-planned"
PRESETS = {"default": "publish-fake-active-default", "alternate": "publish-fake-active-alternate"}


class FakeRunner(SignalRunner):
    """Deterministic two-row runner used only by these tests."""

    fail_presets: set[str] = set()

    def __init__(self, preset: str, *, save: bool, db_root: Path | None) -> None:
        super().__init__(
            SignalRunConfig(
                signal_id=PRESETS[preset],
                signal_type=ACTIVE_TYPE,
                save=save,
                db_root=db_root or Path("/nonexistent"),
            )
        )
        self.preset = preset

    @classmethod
    def from_preset(cls, name: str, save: bool = True, db_root: Path | None = None) -> "FakeRunner":
        if name not in PRESETS:
            raise KeyError(f"unknown preset: {name}")
        return cls(name, save=save, db_root=db_root)

    def load_data(self) -> pl.DataFrame:
        if self.preset in FakeRunner.fail_presets:
            raise RuntimeError("input panel missing")
        return pl.DataFrame({"timestamp": [1, 2]})

    def compute(self, data: pl.DataFrame) -> pl.DataFrame:
        del data
        return pl.DataFrame(
            {
                "timestamp": [datetime(2026, 1, 1), datetime(2026, 1, 2)],
                "prediction": [0.25, 0.75],
            }
        )

    def get_config_dict(self) -> dict[str, Any]:
        return {"preset": self.preset, "signal_type": ACTIVE_TYPE}


@pytest.fixture
def fake_catalog(monkeypatch: pytest.MonkeyPatch):
    """Register one active and one planned fake family, isolated from discovery."""
    from signals import publish as publish_module

    entries = {
        ACTIVE_TYPE: {"status": "active", "presets_dir": "extensions/lib/publish-fake-active/presets"},
        PLANNED_TYPE: {"status": "planned", "presets_dir": "extensions/lib/publish-fake-planned/presets"},
    }

    def fake_iter_signal_entries(*, include_planned: bool = True) -> list[tuple[str, dict[str, Any]]]:
        items = sorted(entries.items())
        if include_planned:
            return items
        return [(name, info) for name, info in items if info["status"] == "active"]

    monkeypatch.setattr(publish_module, "iter_signal_entries", fake_iter_signal_entries)
    monkeypatch.setattr(
        publish_module, "get_presets_for_signal", lambda name: sorted(PRESETS) if name == ACTIVE_TYPE else []
    )
    monkeypatch.setattr(publish_module, "get_default_preset", lambda name: "default" if name == ACTIVE_TYPE else None)
    monkeypatch.setattr(publish_module, "import_active_runner_modules", lambda **_: [ACTIVE_TYPE])

    FakeRunner.fail_presets = set()
    SignalRegistry.register(ACTIVE_TYPE, presets_dir="extensions/lib/publish-fake-active/presets")(FakeRunner)
    try:
        yield entries
    finally:
        SignalRegistry.unregister(ACTIVE_TYPE)
        FakeRunner.fail_presets = set()


def _ledger_lines(db_root: Path) -> list[dict[str, Any]]:
    path = db_root / "signals" / LEDGER_FILENAME
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# --------------------------------------------------------------------------- #
# Selection
# --------------------------------------------------------------------------- #


def test_default_selection_is_every_active_catalog_entry(fake_catalog) -> None:
    assert select_targets() == [(ACTIVE_TYPE, "default", None)]


def test_all_presets_selects_every_preset_file(fake_catalog) -> None:
    assert select_targets(all_presets=True) == [
        (ACTIVE_TYPE, "alternate", None),
        (ACTIVE_TYPE, "default", None),
    ]


def test_explicit_preset_requires_exactly_one_signal_type(fake_catalog) -> None:
    with pytest.raises(ValueError, match="exactly one --signal-type"):
        select_targets(preset="alternate")
    with pytest.raises(ValueError, match="mutually exclusive"):
        select_targets(signal_types=[ACTIVE_TYPE], preset="alternate", all_presets=True)

    assert select_targets(signal_types=[ACTIVE_TYPE], preset="alternate") == [(ACTIVE_TYPE, "alternate", None)]


def test_unknown_or_planned_signal_type_is_a_recorded_selection_error(fake_catalog) -> None:
    targets = select_targets(signal_types=[PLANNED_TYPE, "no-such-signal"])
    assert [target[1] for target in targets] == [None, None]
    assert all("not found in the active catalog" in str(target[2]) for target in targets)


# --------------------------------------------------------------------------- #
# Publication and ledger
# --------------------------------------------------------------------------- #


def test_publish_writes_history_and_one_ledger_line(fake_catalog, tmp_path: Path, capsys) -> None:
    db_root = tmp_path / "db"

    report = publish_catalog(db_root=db_root)

    assert report.exit_code == 0
    assert len(report.ok) == 1
    record = report.records[0]
    assert set(record) == set(RECORD_FIELDS)
    assert record["status"] == "ok"
    assert record["signal_type"] == ACTIVE_TYPE
    assert record["preset"] == "default"
    assert record["signal_id"] == PRESETS["default"]
    assert record["rows"] == 2
    assert record["rows_before"] == 0
    assert record["rows_after"] == 2
    assert record["first_timestamp"].startswith("2026-01-01")
    assert record["last_timestamp"].startswith("2026-01-02")
    assert record["run_id"]
    assert record["error"] is None
    assert isinstance(record["duration_s"], float)

    assert _ledger_lines(db_root) == [record]
    assert json.loads(capsys.readouterr().out.splitlines()[-2]) == record

    store = PredictionStore(db_root / "signals")
    assert store.list_signals() == [PRESETS["default"]]


def test_rows_before_and_after_show_what_a_republish_added(fake_catalog, tmp_path: Path) -> None:
    db_root = tmp_path / "db"
    publish_catalog(db_root=db_root)

    report = publish_catalog(db_root=db_root)

    record = report.records[0]
    assert (record["rows_before"], record["rows_after"]) == (2, 2)
    assert len(_ledger_lines(db_root)) == 2


def test_dry_run_writes_nothing(fake_catalog, tmp_path: Path) -> None:
    db_root = tmp_path / "db"

    report = publish_catalog(db_root=db_root, dry_run=True)

    assert report.exit_code == 0
    assert report.records[0]["run_id"] is None
    assert report.records[0]["rows"] == 2
    assert not db_root.exists()


def test_error_continues_to_the_next_runner_and_exits_nonzero(fake_catalog, tmp_path: Path) -> None:
    db_root = tmp_path / "db"
    FakeRunner.fail_presets = {"alternate"}

    report = publish_catalog(db_root=db_root, all_presets=True)

    assert report.exit_code == 1
    assert [record["preset"] for record in report.records] == ["alternate", "default"]
    assert [record["status"] for record in report.records] == ["error", "ok"]
    assert "input panel missing" in report.records[0]["error"]
    # The failure is in the ledger too, so the operator sees it without the console.
    assert [line["status"] for line in _ledger_lines(db_root)] == ["error", "ok"]


def test_fail_fast_stops_at_the_first_failure(fake_catalog, tmp_path: Path) -> None:
    db_root = tmp_path / "db"
    FakeRunner.fail_presets = {"alternate"}

    report = publish_catalog(db_root=db_root, all_presets=True, fail_fast=True)

    assert report.exit_code == 1
    assert [record["preset"] for record in report.records] == ["alternate"]


def test_ledger_file_does_not_break_signal_listing(fake_catalog, tmp_path: Path) -> None:
    """A plain file beside the signal directories must stay invisible to listing."""
    db_root = tmp_path / "db"
    publish_catalog(db_root=db_root)
    (db_root / "signals" / "SCHEMA.yaml").write_text("stray: file\n", encoding="utf-8")

    store = PredictionStore(db_root / "signals")

    assert (db_root / "signals" / LEDGER_FILENAME).is_file()
    assert store.list_signals() == [PRESETS["default"]]
