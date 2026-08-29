from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from app.business_economics.findings import SubjectKind
from app.business_economics.measurement_contract import MeasurementComponent
from app.business_economics.payroll_adapter import (
    LaborAttributionAuthority,
    PayrollEconomicsAdmissionError,
    adapt_payroll_reporting,
)
from app.payroll.reporting import (
    HistoryCoverageEvidence,
    PayrollReportingEngine,
    PayrollReportingSource,
    ReportingPeriod,
    ReportingPeriodKind,
)

COMPANY, EMPLOYEE = uuid4(), uuid4()


def report():
    period = ReportingPeriod(
        "2026-Q1", ReportingPeriodKind.QUARTER, date(2026, 1, 1), date(2026, 3, 31)
    )
    source = PayrollReportingSource(
        "payroll-source",
        "a" * 64,
        COMPANY,
        EMPLOYEE,
        uuid4(),
        date(2026, 1, 15),
        "USD",
        Decimal("1000.00"),
        Decimal("150.00"),
        Decimal("90.00"),
        Decimal("50.00"),
        Decimal("800.00"),
        True,
        True,
    )
    coverage = HistoryCoverageEvidence(
        "coverage",
        "b" * 64,
        COMPANY,
        period.start,
        period.end,
        True,
        True,
        "native_acp_history",
    )
    return PayrollReportingEngine().compose(
        company_id=COMPANY, period=period, sources=(source,), coverage=coverage
    )


def attribution(**overrides):
    values = {
        "authority_id": "allocation-v1",
        "authority_digest": "c" * 64,
        "company_id": COMPANY,
        "branch_id": uuid4(),
        "subject_id": str(uuid4()),
        "subject_kind": SubjectKind.JOB,
        "reconciliation_key": "job-labor-2026-q1",
        "direct_labor": Decimal("600.00"),
        "labor_burden": Decimal("54.00"),
        "currency": "USD",
        "effective_date": date(2026, 1, 15),
        "approved": True,
    }
    values.update(overrides)
    return LaborAttributionAuthority(**values)


def test_payroll_reporting_adapts_to_measured_labor_with_provenance() -> None:
    direct, burden = adapt_payroll_reporting(report=report(), attribution=attribution())
    assert (
        direct.component is MeasurementComponent.DIRECT_LABOR
        and direct.source_value == Decimal("600.00")
    )
    assert (
        burden.component is MeasurementComponent.LABOR_BURDEN
        and burden.source_value == Decimal("54.00")
    )
    assert (
        direct.package_digest == report().report_digest
        and direct.accepted_for_measurement
    )


def test_attribution_is_required_and_cannot_exceed_payroll_truth() -> None:
    with pytest.raises(PayrollEconomicsAdmissionError, match="approved"):
        adapt_payroll_reporting(
            report=report(), attribution=attribution(approved=False)
        )
    with pytest.raises(PayrollEconomicsAdmissionError, match="exceeds"):
        adapt_payroll_reporting(
            report=report(), attribution=attribution(direct_labor=Decimal("1000.01"))
        )
    with pytest.raises(PayrollEconomicsAdmissionError, match="Company"):
        adapt_payroll_reporting(
            report=report(), attribution=attribution(company_id=uuid4())
        )
