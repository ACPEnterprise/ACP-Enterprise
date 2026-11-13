from __future__ import annotations

import pytest

from app.simulation.phase1 import SimulationInvariantError, run_phase1


def test_phase1_passes_with_zero_variance_and_complete_lifecycle() -> None:
    receipt = run_phase1(generated_at="2026-11-13T00:00:00+00:00")
    assert receipt["status"] == "PASS"
    assert receipt["accounting"]["unexplained_variance"] == "0.00"
    assert all(receipt["assertions"].values())
    assert receipt["assertions"]["company_isolation_preserved"]


def test_phase1_receipt_digest_is_stable() -> None:
    first = run_phase1(generated_at="2026-11-13T00:00:00+00:00")
    second = run_phase1(generated_at="2026-11-13T00:00:00+00:00")
    assert first["receipt_digest"] == second["receipt_digest"]
    assert first["operations"] == second["operations"]


def test_phase1_is_explicitly_synthetic_and_does_not_use_live_targets() -> None:
    receipt = run_phase1(generated_at="2026-11-13T00:00:00+00:00")
    assert receipt["mode"] == "synthetic_isolated"
    assert receipt["company_id"] == "sim-company-0001"
    assert not any("production" in path.lower() for path in receipt["service_paths"].values())
