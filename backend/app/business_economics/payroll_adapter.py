"""Admit authoritative Payroll reporting into Economics measurement evidence."""

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from decimal import Decimal
from uuid import UUID

from app.payroll.reporting import PayrollReportingResult, ReportingState

from .findings import FindingState, SubjectKind
from .measurement_contract import MeasurementComponent, MeasurementEvidenceInput
from .source_conformance import EvidenceConfidence

PAYROLL_ECONOMICS_ADAPTER_VERSION = "eco.payroll-reporting-adapter.v1"
PAYROLL_REPORTING_AUTHORITY = "accepted_payroll_reporting"


class PayrollEconomicsAdmissionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class LaborAttributionAuthority:
    authority_id: str
    authority_digest: str
    company_id: UUID
    branch_id: UUID | None
    subject_id: str
    subject_kind: SubjectKind
    reconciliation_key: str
    direct_labor: Decimal
    labor_burden: Decimal
    currency: str
    effective_date: date
    approved: bool
    compensation_allocation_family: str
    compensation_allocation_method: str
    compensation_policy_digest: str
    burden_allocation_method: str
    burden_policy_digest: str


def adapt_payroll_reporting(
    *, report: PayrollReportingResult, attribution: LaborAttributionAuthority
) -> tuple[MeasurementEvidenceInput, MeasurementEvidenceInput]:
    if report.state is not ReportingState.AUTHORITATIVE or report.totals is None:
        raise PayrollEconomicsAdmissionError(
            "authoritative Payroll reporting is required"
        )
    if attribution.company_id != report.company_id or not attribution.approved:
        raise PayrollEconomicsAdmissionError(
            "approved Company labor attribution is required"
        )
    if attribution.subject_kind is not SubjectKind.JOB:
        raise PayrollEconomicsAdmissionError(
            "Job labor Economics requires exact Job subject authority"
        )
    if attribution.compensation_allocation_family not in {
        "overtime_premium_allocation",
        "salary_job_allocation",
        "direct_labor_measurement",
    }:
        raise PayrollEconomicsAdmissionError(
            "certified compensation allocation family is required"
        )
    if (
        not attribution.compensation_allocation_method
        or not attribution.burden_allocation_method
    ):
        raise PayrollEconomicsAdmissionError("certified allocation method is required")
    if (
        len(attribution.compensation_policy_digest) != 64
        or len(attribution.burden_policy_digest) != 64
    ):
        raise PayrollEconomicsAdmissionError("certified policy digests are required")
    if not report.period.start <= attribution.effective_date <= report.period.end:
        raise PayrollEconomicsAdmissionError(
            "allocation effective date is outside Payroll reporting period"
        )
    if report.currency != attribution.currency:
        raise PayrollEconomicsAdmissionError("Payroll Economics currency mismatch")
    if attribution.direct_labor < 0 or attribution.labor_burden < 0:
        raise PayrollEconomicsAdmissionError(
            "Payroll Economics attribution cannot be negative"
        )
    if (
        attribution.direct_labor > report.totals.gross
        or attribution.labor_burden > report.totals.employer_taxes_contributions
    ):
        raise PayrollEconomicsAdmissionError(
            "Payroll attribution exceeds authoritative reporting totals"
        )
    direct = _measurement(
        report,
        attribution,
        MeasurementComponent.DIRECT_LABOR,
        "direct_labor",
        attribution.direct_labor,
    )
    burden = _measurement(
        report,
        attribution,
        MeasurementComponent.LABOR_BURDEN,
        "labor_burden",
        attribution.labor_burden,
    )
    return direct, burden


def _measurement(
    report: PayrollReportingResult,
    attribution: LaborAttributionAuthority,
    component: MeasurementComponent,
    component_name: str,
    amount: Decimal,
) -> MeasurementEvidenceInput:
    return MeasurementEvidenceInput(
        input_id=f"payroll-{component_name.replace('_', '-')}:{report.report_digest}:{attribution.authority_id}",
        subject_id=attribution.subject_id,
        reconciliation_key=attribution.reconciliation_key,
        component=component,
        source_authority=PAYROLL_REPORTING_AUTHORITY,
        evidence_state=FindingState.READY,
        confidence=EvidenceConfidence.AVAILABLE,
        source_value=amount,
        currency=attribution.currency,
        unit=None,
        effective_date=attribution.effective_date,
        as_of=datetime.combine(report.period.end, time.min, tzinfo=timezone.utc),
        accepted_for_measurement=True,
        limitations=(
            "Attribution is limited to explicitly approved labor allocation authority.",
            f"Compensation allocation: {attribution.compensation_allocation_family}/{attribution.compensation_allocation_method}.",
            f"Employer burden allocation: {attribution.burden_allocation_method}.",
        ),
        evidence_digest=_authority_lineage_digest(attribution),
        value_digest=_value_digest(
            report.report_digest, attribution.authority_digest, component_name, amount
        ),
        package_digest=report.report_digest,
        definition_version="eco.measurement.inputs.v1",
        company_id=report.company_id,
        branch_id=attribution.branch_id,
    )


def _value_digest(
    report_digest: str, authority_digest: str, component: str, amount: Decimal
) -> str:
    import hashlib

    return hashlib.sha256(
        f"{PAYROLL_ECONOMICS_ADAPTER_VERSION}:{report_digest}:{authority_digest}:{component}:{amount}".encode()
    ).hexdigest()


def _authority_lineage_digest(attribution: LaborAttributionAuthority) -> str:
    import hashlib

    lineage = (
        f"{attribution.authority_digest}:"
        f"{attribution.compensation_policy_digest}:"
        f"{attribution.burden_policy_digest}:"
        f"{attribution.compensation_allocation_method}:"
        f"{attribution.burden_allocation_method}"
    )
    return hashlib.sha256(lineage.encode()).hexdigest()
