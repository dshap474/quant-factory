"""A9 controlled mutation-strength checks against frozen audit tests.

Purpose: prove named audit regressions fail when one critical execution rule is
deliberately corrupted in an isolated source copy.

USAGE:
    uv run --project packages/platform/backtest pytest \
      packages/platform/backtest/tests/audit/test_a9_mutation_strength.py -v
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

# --------------------------------------------------------------------------- #
# Mutation catalog
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Mutant:
    """One source edit and the existing test required to kill it."""

    name: str
    package: str
    relative_file: str
    original: str
    replacement: str
    test_node: str


MUTANTS = (
    Mutant(
        "omit-contract-multiplier",
        "execution",
        "execution/sizing.py",
        "desired_notional / (reference.price * spec.multiplier)",
        "desired_notional / reference.price",
        "packages/platform/backtest/tests/audit/test_a2_policy_multiplier.py::test_s30_multiplier_applies_once_to_every_economic_field",
    ),
    Mutant(
        "reverse-funding-sign",
        "execution",
        "execution/accounting.py",
        "return -qty * mark * mult * rate_d",
        "return qty * mark * mult * rate_d",
        "packages/platform/backtest/tests/audit/test_a1_funding.py::test_s15_s17_funding_sign_oracle",
    ),
    Mutant(
        "double-apply-fee",
        "backtest",
        "backtest/projection/linear_perpetual.py",
        "self._ledger.cash = apply_fee_to_cash(self._ledger.cash, fill.fee)\n",
        "self._ledger.cash = apply_fee_to_cash(self._ledger.cash, fill.fee)\n"
        "        self._ledger.cash = apply_fee_to_cash(self._ledger.cash, fill.fee)\n",
        "packages/platform/backtest/tests/audit/test_a2_reporting.py::test_s34_flat_entry_decomposes_exact_cost_and_net_return",
    ),
    Mutant(
        "reverse-event-order",
        "backtest",
        "backtest/engines/nautilus/strategy.py",
        "            for settlement in rt.funding_by_time.get(ts, ()):\n"
        "                rt.projection.apply_funding(settlement)\n\n"
        "            if ts in rt.targets_by_earliest:\n"
        "                self._reconcile_positions(ts)\n"
        "                for target in rt.targets_by_earliest[ts]:\n"
        "                    self._size_and_plan(target, as_of=ts)\n",
        "            if ts in rt.targets_by_earliest:\n"
        "                self._reconcile_positions(ts)\n"
        "                for target in rt.targets_by_earliest[ts]:\n"
        "                    self._size_and_plan(target, as_of=ts)\n\n"
        "            for settlement in rt.funding_by_time.get(ts, ()):\n"
        "                rt.projection.apply_funding(settlement)\n",
        "packages/platform/backtest/tests/audit/test_a1_funding.py::test_s19_funding_precedes_same_bar_sizing_and_fill",
    ),
    Mutant(
        "reject-exact-minimum",
        "execution",
        "execution/sizing.py",
        "if absolute_quantity < spec.min_quantity:",
        "if absolute_quantity <= spec.min_quantity:",
        "packages/platform/backtest/tests/audit/test_a7_numeric_integrity.py::test_b06_quantity_limits_accept_exact_boundaries",
    ),
    Mutant(
        "omit-execution-fingerprint-fact",
        "backtest",
        "backtest/preparation/fingerprint.py",
        '            "execution": {\n'
        '                "mode": weights.execution.mode.value,\n'
        '                "lag_bars": weights.execution.lag_bars,\n'
        '                "timestamp_semantics": weights.execution.timestamp_semantics,\n'
        "            },",
        '            "execution": {},',
        "packages/platform/backtest/tests/audit/test_a7_numeric_integrity.py::test_b11_weights_fingerprint_covers_all_economic_and_timing_facts",
    ),
    Mutant(
        "accept-copied-weights-hash",
        "backtest",
        "backtest/connectors.py",
        "if prepared_execution_fingerprint(prepared_execution) != prepared_execution.prepared_payload_sha256:",
        "if False and prepared_execution_fingerprint(prepared_execution) != prepared_execution.prepared_payload_sha256:",
        "packages/platform/backtest/tests/audit/test_a7_numeric_integrity.py::test_b07_copied_weights_fingerprint_cannot_authorize_opposite_targets",
    ),
    Mutant(
        "drop-terminal-outcome",
        "backtest",
        "backtest/engines/nautilus/strategy.py",
        "return tuple(outcomes)\n",
        "return tuple(outcomes[:-1])\n",
        "packages/platform/backtest/tests/audit/test_a2_policy_multiplier.py::test_s31_buy_and_sell_iocs_have_exact_terminal_fill_coverage",
    ),
    Mutant(
        "skip-engine-end",
        "backtest",
        "backtest/engines/nautilus/runtime.py",
        'for stage in ("end", "dispose"):',
        'for stage in ("dispose",):',
        "packages/platform/backtest/tests/audit/test_a9_lifecycle_faults.py::test_d01_cleanup_failure_reports_stage[end]",
    ),
    Mutant(
        "accept-duplicate-fill-id",
        "execution",
        "execution/accounting.py",
        'require_unique_ids((f.fill_id for f in fills), "fill_id")',
        "return",
        "packages/execution/tests/test_accounting.py::test_duplicate_fill_ids_rejected",
    ),
    Mutant(
        "resting-buy-boundary-exclusive",
        "backtest",
        "backtest/resting_limit/matcher.py",
        "return bar.low <= threshold if order.quantity > 0 else bar.high >= threshold",
        "return bar.low < threshold if order.quantity > 0 else bar.high >= threshold",
        "packages/platform/backtest/tests/unit/test_resting_limit.py::test_exact_buy_boundary_fills_at_limit_after_activation_bar",
    ),
    Mutant(
        "resting-fill-at-open",
        "backtest",
        "backtest/resting_limit/matcher.py",
        "price=order.limit_price,",
        "price=bar.open,",
        "packages/platform/backtest/tests/unit/test_resting_limit.py::test_gap_through_fills_at_limit_and_charges_taker_fee",
    ),
    Mutant(
        "resting-activation-bar-eligible",
        "backtest",
        "backtest/resting_limit/matcher.py",
        "order.activate_at < timestamp <= order.expires_at",
        "order.activate_at <= timestamp <= order.expires_at",
        "packages/platform/backtest/tests/unit/test_resting_limit.py::test_activation_candle_touch_is_ignored",
    ),
)


# --------------------------------------------------------------------------- #
# D08: controlled mutants
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("mutant", MUTANTS, ids=lambda mutant: mutant.name)
def test_d08_frozen_test_kills_controlled_mutant(mutant: Mutant, tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[5]
    source_roots: dict[str, Path] = {}
    package_sources = {
        "execution": project_root / "packages/execution/src",
        "backtest": project_root / "packages/platform/backtest/src",
    }
    for package, source in package_sources.items():
        destination = tmp_path / package / "src"
        shutil.copytree(source, destination)
        source_roots[package] = destination

    mutated_file = source_roots[mutant.package] / mutant.relative_file
    source_text = mutated_file.read_text()
    assert source_text.count(mutant.original) == 1, mutant.name
    mutated_file.write_text(source_text.replace(mutant.original, mutant.replacement, 1))

    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join(
        (
            str(source_roots["backtest"]),
            str(source_roots["execution"]),
            str(project_root / "packages/platform/backtest/tests"),
        )
    )
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", mutant.test_node],
        cwd=project_root,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 1, (
        f"mutant was not killed by one collected test: {mutant.name}\n"
        f"pytest exit={completed.returncode}\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
    )
