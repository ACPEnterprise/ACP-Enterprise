import hashlib
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

from app.business_economics.findings import FindingState
from app.business_economics.launch_evidence_readiness import (
    LaborEvidenceClass,
    LaunchDomain,
    LaunchReadinessState,
    PayrollPrerequisite,
    PrerequisiteState,
    SourcePopulationState,
    build_launch_evidence_readiness,
)
from app.business_economics.measurement_contract import (
    MeasurementComponent,
    MeasurementEvidenceInput,
)
from app.business_economics.source_conformance import EvidenceConfidence
from app.operational_measurement.labor_evidence import (
    EmployeeJobLink,
    IntervalKind,
    LaborInterval,
    ProvenanceRef,
    compose_labor_evidence,
)

NOW = datetime(2026, 9, 12, tzinfo=timezone.utc)


def labor(*, worked: bool = True):
    company, branch, employee, job, appointment = (uuid4() for _ in range(5))
    ref = ProvenanceRef("accepted_source", "record", "revision-1", "a" * 64)
    link = EmployeeJobLink(company, branch, employee, job, appointment, ref)
    values = [
        LaborInterval(
            company,
            branch,
            employee,
            IntervalKind.SCHEDULED,
            NOW,
            NOW + timedelta(hours=4),
            ref,
            job,
            appointment,
        ),
        LaborInterval(
            company,
            None,
            employee,
            IntervalKind.PAID,
            NOW,
            NOW + timedelta(hours=8),
            ref,
        ),
    ]
    if worked:
        values.append(
            LaborInterval(
                company,
                branch,
                employee,
                IntervalKind.WORKED,
                NOW,
                NOW + timedelta(hours=3),
                ref,
                job,
                appointment,
            )
        )
    return compose_labor_evidence(
        company_id=company, links=(link,), intervals=tuple(values)
    )


def measurement(company, component, *, identity="one", accepted=True, value=Decimal(1)):
    value_digest = hashlib.sha256(identity.encode()).hexdigest()
    return MeasurementEvidenceInput(
        f"input-{identity}",
        "job-1",
        "job:1",
        component,
        "accepted_domain",
        FindingState.READY,
        EvidenceConfidence.AVAILABLE,
        value,
        "USD",
        None,
        date(2026, 9, 12),
        NOW,
        accepted,
        (),
        "b" * 64,
        value_digest,
        "d" * 64,
        company_id=company,
    )


def prerequisites():
    names = (
        "compensation_effective_date",
        "employee_rate",
        "accepted_paid_time",
        "overtime_applicability",
        "payroll_period_identity",
        "revision_correction_state",
        "jurisdiction_and_tax_tables",
        "deduction_elections_where_relevant",
    )
    return tuple(
        PayrollPrerequisite(name, PrerequisiteState.AVAILABLE, "payroll", f"e-{name}")
        for name in names
    )


def by_domain(packet):
    return {item.domain: item for item in packet.domains}


def test_scheduled_only_is_not_job_labor_and_missing_costs_are_absent_not_zero():
    packet = build_launch_evidence_readiness(
        labor=labor(worked=False),
        evidence=(),
        payroll_prerequisites=(),
        source_population_state=SourcePopulationState.CONTRACT_VALIDATED,
    )
    assert (
        packet.labor_attribution[0].classification is LaborEvidenceClass.SCHEDULED_ONLY
    )
    assert packet.labor_attribution[0].worked_minutes is None
    assert (
        by_domain(packet)[LaunchDomain.DIRECT_MATERIAL].state
        is LaunchReadinessState.ABSENT
    )
    assert (
        by_domain(packet)[LaunchDomain.OVERHEAD].smallest_blocker
        == "approved_overhead_allocation_authority_absent"
    )


def test_job_actual_and_payroll_prerequisites_are_explicit():
    source = labor()
    packet = build_launch_evidence_readiness(
        labor=source,
        evidence=(measurement(source.company_id, MeasurementComponent.DIRECT_LABOR),),
        payroll_prerequisites=prerequisites(),
        source_population_state=SourcePopulationState.SOURCE_PARTIAL,
    )
    assert (
        packet.labor_attribution[0].classification
        is LaborEvidenceClass.JOB_ATTRIBUTABLE
    )
    assert (
        by_domain(packet)[LaunchDomain.DIRECT_LABOR].state
        is LaunchReadinessState.AVAILABLE
    )
    assert (
        by_domain(packet)[LaunchDomain.PAYROLL].state is LaunchReadinessState.AVAILABLE
    )


def test_hcp_qbo_same_event_values_conflict_instead_of_double_counting():
    source = labor()
    first = measurement(
        source.company_id, MeasurementComponent.REVENUE_EARNED_VALUE, identity="aaa"
    )
    second = measurement(
        source.company_id, MeasurementComponent.REVENUE_EARNED_VALUE, identity="ccc"
    )
    packet = build_launch_evidence_readiness(
        labor=source,
        evidence=(first, second),
        payroll_prerequisites=prerequisites(),
        source_population_state=SourcePopulationState.SOURCE_CURRENT,
    )
    revenue = by_domain(packet)[LaunchDomain.REVENUE]
    assert revenue.state is LaunchReadinessState.CONFLICTING
    assert (
        revenue.smallest_blocker
        == "same_reconciliation_component_has_conflicting_values"
    )


def test_missing_payroll_input_is_partial_not_zero():
    source = labor()
    partial = tuple(
        item for item in prerequisites() if item.name != "employee_rate"
    ) + (
        PayrollPrerequisite(
            "employee_rate", PrerequisiteState.ABSENT, None, None, "rate_missing"
        ),
    )
    packet = build_launch_evidence_readiness(
        labor=source,
        evidence=(),
        payroll_prerequisites=partial,
        source_population_state=SourcePopulationState.SOURCE_MISSING,
    )
    payroll = by_domain(packet)[LaunchDomain.PAYROLL]
    assert payroll.state is LaunchReadinessState.PARTIAL
    assert payroll.smallest_blocker == "rate_missing"
