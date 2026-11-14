from __future__ import annotations

from app.simulation.phase1 import (
    ACCOUNTING_REGRESSION_SCENARIOS,
    run_accounting_lifecycle,
    run_accounting_regression_scenarios,
    run_phase1,
)


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
    assert not any(
        "production" in path.lower() for path in receipt["service_paths"].values()
    )


def test_accounting_regressions_cover_all_real_defect_classes() -> None:
    result = run_accounting_regression_scenarios()
    assert result["status"] == "PASS"
    assert len(result["scenarios"]) == len(ACCOUNTING_REGRESSION_SCENARIOS) == 11
    assert all(
        row["synthetic_only"] and row["status"] == "PASS" for row in result["scenarios"]
    )
    assert all(not row["native_books_affected"] for row in result["scenarios"])
    assert all(row["unexplained_variance"] == "0.00" for row in result["scenarios"])


def test_accounting_operational_independence_lifecycle() -> None:
    result = run_accounting_lifecycle()
    assert result["status"] == "PASS"
    assert result["scenario_count"] == 12
    assert result["unexplained_variance"] == "0.00"
    assert result["orphan_records"] == result["duplicate_records"] == 0
    assert result["unauthorized_operations_rejected"] == 1
    assert all(result["assertions"].values())
