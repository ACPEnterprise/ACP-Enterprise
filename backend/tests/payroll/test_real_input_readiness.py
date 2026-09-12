from app.business_economics.launch_evidence_readiness import (
    CONTRACT_VERSION as ECO_VERSION,
)
from app.business_economics.launch_evidence_readiness import (
    SourcePopulationState,
)
from app.payroll.real_input_readiness import (
    CalculationReadiness,
    EmployeePayrollEvidence,
    EmployeePayrollStatus,
    EvidenceValueState,
    PayrollEvidenceField,
    build_payroll_readiness_packet,
)


def field(key, state=EvidenceValueState.AVAILABLE):
    available = state in {
        EvidenceValueState.AVAILABLE,
        EvidenceValueState.AUTHORITATIVE_ZERO,
    }
    return PayrollEvidenceField(
        key,
        state,
        "authority" if available else None,
        "record" if available else None,
        "v1" if available else None,
        "2026-09-12" if available else None,
        "a" * 64 if available else None,
    )


def all_fields():
    keys = (
        "compensation_basis",
        "compensation_rate",
        "compensation_effective_date",
        "compensation_revision_state",
        "accepted_paid_time",
        "accepted_job_specific_time",
        "timecard_status",
        "time_correction_revision",
        "overtime_applicability",
        "payroll_period_assignment",
        "w4_filing_status",
        "w4_step_2",
        "w4_step_3",
        "w4_step_4a",
        "w4_step_4b",
        "w4_step_4c",
        "work_jurisdiction",
        "residence_jurisdiction",
        "state_local_withholding_configuration",
        "unemployment_workforce_jurisdiction",
        "deduction_configuration",
        "deduction_tax_treatment",
        "deduction_effective_date",
        "deduction_limits",
        "social_security_wages_ytd",
        "social_security_tax_ytd",
        "medicare_wages_ytd",
        "medicare_tax_ytd",
        "additional_medicare_prerequisites",
        "federal_withholding_ytd",
        "prior_payroll_coverage",
        "federal_tax_table",
        "state_local_tax_table",
        "tax_table_source_version",
        "tax_table_effective_date",
    )
    return tuple(field(key) for key in keys)


def employee(fields, *, active=True):
    return EmployeePayrollEvidence(
        "employee-1", "company-1", "branch-1", active, "hourly", fields
    )


def test_complete_inputs_are_ready_but_checklist_requires_independent_reference():
    packet = build_payroll_readiness_packet(
        employees=(employee(all_fields()),),
        source_population_state=SourcePopulationState.SOURCE_CURRENT,
        independently_accepted_reference_reconciled=False,
    )
    assert packet.governing_eco_contract_version == ECO_VERSION
    assert packet.employees[0].status is EmployeePayrollStatus.PAYROLL_READY
    assert packet.employees[0].calculation_readiness == (
        CalculationReadiness.INPUT_READY,
    )
    assert packet.checklist_6_calculation_ready is False


def test_authoritative_zero_is_present_and_missing_is_an_exact_blocker():
    values = tuple(
        field(item.key, EvidenceValueState.AUTHORITATIVE_ZERO)
        if item.key == "w4_step_3"
        else item
        for item in all_fields()
        if item.key != "social_security_wages_ytd"
    )
    packet = build_payroll_readiness_packet(
        employees=(employee(values),),
        source_population_state=SourcePopulationState.SOURCE_CURRENT,
        independently_accepted_reference_reconciled=True,
    )
    result = packet.employees[0]
    assert result.status is EmployeePayrollStatus.BLOCKED_FOR_PAYROLL
    assert result.exact_blockers == ("missing social_security_wages_ytd",)
    assert CalculationReadiness.YTD_NOT_READY in result.calculation_readiness


def test_conflict_and_inactive_employee_handling_are_deterministic():
    values = tuple(
        field(item.key, EvidenceValueState.CONFLICTING)
        if item.key == "compensation_rate"
        else item
        for item in all_fields()
    )
    packet = build_payroll_readiness_packet(
        employees=(employee(values), employee(all_fields(), active=False)),
        source_population_state=SourcePopulationState.SOURCE_CURRENT,
        independently_accepted_reference_reconciled=True,
    )
    assert packet.total_active_employees_evaluated == 1
    assert (
        packet.employees[0].calculation_readiness[0] is CalculationReadiness.CONFLICTING
    )
    assert "conflicting compensation_rate" in packet.employees[0].exact_blockers


def test_not_applicable_is_explicit_evidence_not_missing():
    values = tuple(
        field(item.key, EvidenceValueState.NOT_APPLICABLE)
        if item.key.startswith("deduction_")
        else item
        for item in all_fields()
    )
    packet = build_payroll_readiness_packet(
        employees=(employee(values),),
        source_population_state=SourcePopulationState.SOURCE_CURRENT,
        independently_accepted_reference_reconciled=True,
    )
    assert packet.employees[0].status is EmployeePayrollStatus.PAYROLL_READY
    assert packet.deduction_readiness == "READY"


def test_missing_real_population_has_unknown_counts_not_false_zero():
    packet = build_payroll_readiness_packet(
        employees=(),
        source_population_state=SourcePopulationState.SOURCE_MISSING,
        independently_accepted_reference_reconciled=False,
    )
    assert packet.total_active_employees_evaluated is None
    assert packet.payroll_ready_count is None
    assert packet.blocked_for_payroll_count is None
    assert (
        packet.population_blocker
        == "authorized_real_active_employee_population_unavailable"
    )
    assert packet.checklist_6_calculation_ready is False


def test_not_applicable_cannot_waive_required_w4_evidence():
    values = tuple(
        field(item.key, EvidenceValueState.NOT_APPLICABLE)
        if item.key == "w4_step_2"
        else item
        for item in all_fields()
    )
    packet = build_payroll_readiness_packet(
        employees=(employee(values),),
        source_population_state=SourcePopulationState.SOURCE_CURRENT,
        independently_accepted_reference_reconciled=True,
    )
    assert packet.employees[0].status is EmployeePayrollStatus.BLOCKED_FOR_PAYROLL
    assert "missing w4_step_2" in packet.employees[0].exact_blockers
