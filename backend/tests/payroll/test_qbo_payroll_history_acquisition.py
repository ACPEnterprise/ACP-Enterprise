from app.payroll.qbo_payroll_history_acquisition import (
    PAYROLL_EXPORT_REPORTS,
    PayrollSourceCapability,
    acquisition_plan,
    classify_payroll_history,
)


def test_accounting_catalog_never_claims_detailed_payroll_history() -> None:
    rows = {
        row.family: row
        for row in classify_payroll_history(
            entity_counts={
                "employee": 9,
                "time_activity": 42,
                "journal_entry": 12,
                "tax_payment": 3,
                "account": 80,
            },
            sealed_manifest_available=True,
        )
    }
    assert (
        rows["employee_identity"].classification
        is PayrollSourceCapability.EXISTING_SEALED_EVIDENCE
    )
    assert rows["employee_identity"].accounting_api_support == ("employee",)
    assert (
        rows["payroll_runs_periods_pay_dates"].classification
        is PayrollSourceCapability.EXTERNAL_EXPORT_REQUIRED
    )
    assert (
        rows["employee_ytd"].classification
        is PayrollSourceCapability.EXTERNAL_EXPORT_REQUIRED
    )
    assert (
        rows["post_qbo_bridge_and_future_final_checks"].classification
        is PayrollSourceCapability.MANUAL_EVIDENCE_REQUIRED
    )


def test_unmounted_snapshot_is_api_capability_not_acquired_evidence() -> None:
    rows = classify_payroll_history(entity_counts={}, sealed_manifest_available=False)
    identity = next(row for row in rows if row.family == "employee_identity")
    assert identity.classification is PayrollSourceCapability.API_AVAILABLE
    assert identity.accounting_api_support == ()


def test_plan_names_exact_exports_and_keeps_cutoff_unavailable() -> None:
    packet = acquisition_plan(
        entity_counts={"employee": 9},
        source_manifest_sha256=None,
        acquisition_state="SEALED_SNAPSHOT_UNAVAILABLE",
    )
    assert tuple(packet["required_exports"]) == PAYROLL_EXPORT_REPORTS
    assert (
        packet["last_qbo_payroll_cutoff"]
        == "UNAVAILABLE_UNTIL_PAYROLL_DETAILS_AND_PAYCHECK_LIST_ARE_SEALED"
    )
    assert (
        packet["bridge_periods"]
        == "UNAVAILABLE_UNTIL_LAST_QBO_PAYROLL_CUTOFF_IS_PROVEN"
    )
    assert packet["missing_values_are_zero"] is False
    assert packet["payroll_executed"] is False
    assert len(str(packet["packet_digest"])) == 64


def test_plan_is_replay_deterministic() -> None:
    arguments = {
        "entity_counts": {"employee": 9, "journal_entry": 12},
        "source_manifest_sha256": "a" * 64,
        "acquisition_state": "SEALED",
    }
    assert acquisition_plan(**arguments) == acquisition_plan(**arguments)
