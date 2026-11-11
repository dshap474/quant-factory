"""Contracts for canonical DB root usage.

These tests enforce that durable storage paths are derived from QUANT_DB_ROOT,
not from cwd-relative or module-relative paths.
"""

from __future__ import annotations

import ast
import hashlib
import importlib
import importlib.util
import json
import subprocess
import textwrap
from datetime import datetime
from pathlib import Path

import polars as pl
import pytest


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _iter_python_files() -> list[Path]:
    root = _repo_root()
    tracked = subprocess.run(
        ["git", "ls-files", "-z", "--", "*.py"],
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout
    files: list[Path] = []
    for relative_path in tracked.decode().split("\0"):
        if not relative_path:
            continue
        path = root / relative_path
        if not path.is_file() or "tests" in path.parts or path.name.startswith("test_"):
            continue
        if "packages" in path.parts and "data" in path.parts and "archive" in path.parts:
            continue
        files.append(path)
    return files


def _is_path_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call):
        return False
    if isinstance(node.func, ast.Name) and node.func.id == "Path":
        return True
    if isinstance(node.func, ast.Attribute) and node.func.attr == "Path":
        return True
    return False


def _is_db_literal(value: object) -> bool:
    if not isinstance(value, str):
        return False
    return value == "db" or value.startswith("db/") or value.startswith("db\\")


def _path_call_uses_db_literal(node: ast.AST) -> bool:
    if not _is_path_call(node):
        return False
    if not node.args:
        return False
    first_arg = node.args[0]
    if isinstance(first_arg, ast.Constant):
        return _is_db_literal(first_arg.value)
    return False


def _contains_path_file_call(node: ast.AST) -> bool:
    for sub in ast.walk(node):
        if not _is_path_call(sub):
            continue
        if not sub.args:
            continue
        arg = sub.args[0]
        if isinstance(arg, ast.Name) and arg.id == "__file__":
            return True
    return False


def _binop_from_file_to_db(node: ast.AST) -> bool:
    if not isinstance(node, ast.BinOp):
        return False
    if not isinstance(node.op, ast.Div):
        return False
    if not isinstance(node.right, ast.Constant):
        return False
    if node.right.value != "db":
        return False
    return _contains_path_file_call(node.left)


def _db_path_violations(paths: list[Path], root: Path, baseline: dict) -> list[str]:
    """Keep reviewed historical bytes sealed while checking every active file."""
    violations: list[str] = []
    remaining = set(baseline)
    for path in paths:
        relative = path.relative_to(root).as_posix()
        raw = path.read_bytes()
        source = textwrap.dedent(raw.decode())
        try:
            tree = ast.parse(source, filename=str(path))
        except SyntaxError as exc:
            pytest.fail(f"Failed to parse {path}: {exc}")

        patterns: list[str] = []
        for node in ast.walk(tree):
            if _path_call_uses_db_literal(node):
                patterns.append(f"{path}: Path('db...') literal")
            elif _binop_from_file_to_db(node):
                patterns.append(f"{path}: Path(__file__...)/'db' pattern")
        if relative in baseline:
            remaining.remove(relative)
            record = baseline[relative]
            if not record.get("reason") or hashlib.sha256(raw).hexdigest() != record.get("sha256"):
                violations.append(f"{path}: historical baseline changed or lacks rationale")
            if not patterns:
                violations.append(f"{path}: stale historical baseline entry")
        else:
            violations.extend(patterns)
    violations.extend(f"{path}: missing historical baseline file" for path in sorted(remaining))
    return violations


def test_no_relative_db_paths_in_codebase() -> None:
    """Disallow relative paths except exact, reviewed immutable research files."""
    # The baseline pins only extension files, so a checkout without extensions ships none.
    baseline_path = Path(__file__).with_name("db_root_historical_baseline.json")
    baseline = json.loads(baseline_path.read_text()) if baseline_path.exists() else {}
    violations = _db_path_violations(_iter_python_files(), _repo_root(), baseline)

    assert not violations, "Disallowed db path patterns found:\n" + "\n".join(violations)


def test_historical_baseline_is_exact_and_does_not_exempt_new_code(tmp_path: Path) -> None:
    """Edits, deleted pins, stale pins, and new sibling scripts must fail."""
    old = tmp_path / "old.py"
    old.write_text("from pathlib import Path\nROOT = Path('db/archive')\n")
    baseline = {"old.py": {"sha256": hashlib.sha256(old.read_bytes()).hexdigest(), "reason": "sealed"}}
    assert not _db_path_violations([old], tmp_path, baseline)
    new = tmp_path / "new.py"
    new.write_bytes(old.read_bytes())
    assert _db_path_violations([old, new], tmp_path, baseline)
    old.write_text(old.read_text() + "# altered\n")
    assert _db_path_violations([old], tmp_path, baseline)
    assert _db_path_violations([], tmp_path, baseline)
    old.write_text("ROOT = None\n")
    baseline["old.py"]["sha256"] = hashlib.sha256(old.read_bytes()).hexdigest()
    assert _db_path_violations([old], tmp_path, baseline)


def test_default_db_root_configs_use_quant_db_root() -> None:
    """Default db_root values must match QUANT_DB_ROOT."""
    from config import QUANT_DB_ROOT

    from signals import SignalRunConfig
    from strategies import StrategyRunConfig

    strategy_cfg = StrategyRunConfig(strategy_id="test_strategy", save=False)
    signal_cfg = SignalRunConfig(signal_id="test_signal", save=False)

    assert strategy_cfg.db_root == QUANT_DB_ROOT
    assert signal_cfg.db_root == QUANT_DB_ROOT


def test_feature_store_persists_under_features_subtree(tmp_path: Path) -> None:
    """FeatureStore durable writes stay under <db_root>/features/..."""
    module = importlib.import_module("data.platform.storage.feature_store")
    FeatureStore = module.FeatureStore
    FeatureStoreConfig = module.FeatureStoreConfig

    store = FeatureStore(
        FeatureStoreConfig(
            db_root=tmp_path,
            require_asset_column=False,
        )
    )
    data = pl.DataFrame(
        {
            "timestamp": [datetime(2024, 1, 1)],
            "value": [1.0],
        }
    )

    version = store.write(
        data=data,
        resolution="1d",
        category="macro/example",
        description="contract test",
        force=True,
    )

    assert version.path == tmp_path / "features" / "1d" / "macro" / "example"
    assert version.data_path == version.path / "data.parquet"
    assert version.meta_path == version.path / "meta.yaml"


def test_prediction_store_persists_under_signals_subtree(tmp_path: Path) -> None:
    """PredictionStore durable writes stay under <db_root>/signals/..."""
    from signals import PredictionStore

    store = PredictionStore(tmp_path / "signals")
    predictions = pl.DataFrame(
        {
            "timestamp": [datetime(2024, 1, 1)],
            "prediction": [0.25],
        }
    )

    path = store.save(predictions, "btc_test_signal")

    assert path == tmp_path / "signals" / "btc_test_signal" / "predictions.parquet"
    assert (path.parent / "latest.json").exists()
    assert (path.parent / "index.json").exists()


def test_backtest_output_writes_only_into_its_run_dir(tmp_path: Path) -> None:
    """BacktestOutput writes into the run dir it is given; the runner owns the layout."""
    from strategies import BacktestOutput

    output = BacktestOutput(
        strategy_id="test_strategy",
        run_id="run-test-001",
        equity=pl.DataFrame(
            {
                "timestamp": [datetime(2024, 1, 1)],
                "equity": [1.0],
            }
        ),
        metrics={"sharpe": 1.0},
    )

    run_dir = tmp_path / "research" / "strategies" / "xs-test" / "v001" / "test_strategy" / "run-test-001"

    assert output.save(run_dir) == run_dir
    assert sorted(p.name for p in tmp_path.rglob("*") if p.is_file()) == ["backtest.parquet", "meta.json"]
