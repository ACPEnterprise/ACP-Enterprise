from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

import pytest

from app.accounting.posting.contracts import PostingFact
from app.business_economics.findings import FindingState, SubjectKind
from app.business_economics.measurement_adapters import (
    MeasurementAdapterContext,
    adapt_accounting_posting_fact,
    adapt_job_detail,
    adapt_public_operational_measurement,
    adapt_qbo_source_reported_measurement,
)
from app.business_economics.measurement_contract import (
    MeasurementComponent,
    MeasurementGateState,
    evaluate_contribution_measurement_gate,
)
from app.business_economics.source_adapters import PublicOperationalEvidence
from app.business_economics.source_conformance import (
    EconomicComponent,
    EvidenceConfidence,
)
from app.jobs.query_types import (
    JobCustomerSummary,
    JobDetail,
    JobServiceLocationSummary,
)
from app.jobs.types import JobPriority, JobStatus
from app.qbo_source.economics_evidence import (
    EconomicsEvidenceCategory,
    EconomicsEvidenceState,
    QboEconomicsAssertion,
)

NOW = datetime(2026, 8, 27, tzinfo=timezone.utc)
COMPANY = UUID("00000000-0000-0000-0000-000000000001")
BRANCH = UUID("00000000-0000-0000-0000-000000000002")
JOB = UUID("00000000-0000-0000-0000-000000000003")


def _context(**changes) -> MeasurementAdapterContext:
    values = {
        "company_id": COMPANY,
        "branch_id": BRANCH,
        "subject_id": str(JOB),
        "reconciliation_key": "job:synthetic",
        "package_digest": "f" * 64,
        "as_of": NOW,
    }
    values.update(changes)
    return MeasurementAdapterContext(**values)


def _job() -> JobDetail:
    return JobDetail(
        id=JOB,
        job_number="J-SYNTHETIC",
        company_id=COMPANY,
        branch_id=BRANCH,
        customer_id=UUID("00000000-0000-0000-0000-000000000004"),
        service_location_id=UUID("00000000-0000-0000-0000-000000000005"),
        status=JobStatus.COMPLETED,
        concurrency_version=3,
        activated_at=NOW,
        started_at=NOW,
        paused_at=None,
        pause_reason_code=None,
        completed_at=NOW,
        completed_by_user_id=None,
        cancelled_at=None,
        cancelled_by_user_id=None,
        cancellation_reason_code=None,
        created_at=NOW,
        created_by_user_id=None,
        updated_at=NOW,
        updated_by_user_id=None,
        job_type_code="repair",
        priority=JobPriority.NORMAL,
        customer_reported_problem=None,
        internal_description=None,
        customer=JobCustomerSummary(
            id=UUID("00000000-0000-0000-0000-000000000004"),
            customer_number="C-SYNTHETIC",
            display_name="Synthetic Customer",
        ),
        service_location=JobServiceLocationSummary(
            id=UUID("00000000-0000-0000-0000-000000000005"),
            nickname=None,
            address_line_1="Synthetic",
            address_line_2=None,
            city="Synthetic",
            state="ST",
            postal_code="00000",
            country="US",
        ),
        appointments=(),
    )


def test_job_adapter_is_deterministic_and_preserves_explicit_service_line() -> None:
    first = adapt_job_detail(_job(), _context())
    second = adapt_job_detail(_job(), _context())
    assert first == second
    assert {item.component for item in first} == {
        MeasurementComponent.JOB_CONTEXT,
        MeasurementComponent.SERVICE_LINE_ATTRIBUTION,
    }
    assert all(item.accepted_for_measurement for item in first)
    assert all(item.source_value is None for item in first)


def test_job_adapter_enforces_company_branch_and_subject_identity() -> None:
    with pytest.raises(ValueError, match="company isolation"):
        adapt_job_detail(
            _job(), _context(company_id=UUID("00000000-0000-0000-0000-000000000099"))
        )
    with pytest.raises(ValueError, match="branch isolation"):
        adapt_job_detail(_job(), _context(branch_id=None))
    with pytest.raises(ValueError, match="subject identity"):
        adapt_job_detail(_job(), _context(subject_id="another-job"))


def test_accounting_posting_adapter_preserves_fact_without_reclassification() -> None:
    fact = PostingFact(
        schema_version="1",
        company_id=COMPANY,
        branch_id=BRANCH,
        source_event_id=UUID("00000000-0000-0000-0000-000000000006"),
        source_type="invoice",
        source_id=UUID("00000000-0000-0000-0000-000000000007"),
        event_type="invoice_posted",
        effective_date=date(2026, 8, 25),
        occurred_at=NOW,
        currency="USD",
        components={"receivable": Decimal(10)},
        evidence_digest="a" * 64,
    )
    adapted = adapt_accounting_posting_fact(fact, _context())
    assert adapted.component is MeasurementComponent.ACCOUNTING_RECONCILIATION
    assert adapted.source_value is None
    assert adapted.accepted_for_measurement
    assert "posting_components_not_reclassified" in adapted.limitations


def test_public_hcp_shaped_contract_is_unaccepted_without_explicit_acceptance_contract() -> (
    None
):
    public = PublicOperationalEvidence(
        assertion_id="hcp-job",
        source_system="housecall_pro",
        source_authority="hcp_authoritative_operational_source",
        component=EconomicComponent.DIRECT_LABOR,
        semantic_key="job:synthetic",
        value_digest="b" * 64,
        evidence_digest="c" * 64,
        package_digest="d" * 64,
        confidence=EvidenceConfidence.AVAILABLE,
    )
    adapted = adapt_public_operational_measurement(
        public, component=MeasurementComponent.DIRECT_LABOR, context=_context()
    )
    assert adapted.evidence_state is FindingState.PARTIAL
    assert not adapted.accepted_for_measurement
    assert adapted.source_value is None


def test_public_contract_reconciliation_key_cannot_be_inferred() -> None:
    public = PublicOperationalEvidence(
        assertion_id="hcp-other",
        source_system="housecall_pro",
        source_authority="hcp_authoritative_operational_source",
        component=EconomicComponent.JOB_IDENTITY,
        semantic_key="job:other",
        value_digest="b" * 64,
        evidence_digest="c" * 64,
        package_digest="d" * 64,
        confidence=EvidenceConfidence.AVAILABLE,
    )
    with pytest.raises(ValueError, match="reconciliation identity"):
        adapt_public_operational_measurement(
            public, component=MeasurementComponent.JOB_CONTEXT, context=_context()
        )


def test_qbo_adapter_preserves_partial_unaccepted_authority_and_no_value() -> None:
    qbo = QboEconomicsAssertion(
        assertion_id="qbo-invoice",
        category=EconomicsEvidenceCategory.REVENUE_ASSERTION,
        state=EconomicsEvidenceState.PARTIAL,
        source_authority="quickbooks_online_source_reported",
        acceptance_status="unreconciled_not_enterprise_accepted",
        source_manifest_sha256="a" * 64,
        source_envelope_sha256="b" * 64,
        native_entity_type="invoice",
        native_id="synthetic",
        raw_sha256="c" * 64,
        relationship_ids=(),
        reported_fields={"TotalAmt": 10},
        limitations=("source_reported_not_enterprise_accepted",),
    )
    adapted = adapt_qbo_source_reported_measurement(qbo, context=_context())
    assert adapted.source_authority == "quickbooks_online_source_reported"
    assert adapted.evidence_state is FindingState.PARTIAL
    assert not adapted.accepted_for_measurement
    assert adapted.source_value is None


def test_adapters_feed_measurement_gate_without_calculating_contribution() -> None:
    job_inputs = adapt_job_detail(_job(), _context())
    gate = evaluate_contribution_measurement_gate(
        subject_id=str(JOB),
        subject_kind=SubjectKind.JOB,
        reconciliation_key="job:synthetic",
        required_components=(
            MeasurementComponent.JOB_CONTEXT,
            MeasurementComponent.SERVICE_LINE_ATTRIBUTION,
        ),
        evidence=job_inputs,
        findings=(),
        policy_dependencies=(),
    )
    assert gate.state is MeasurementGateState.MEASURABLE
    assert not hasattr(gate, "contribution")
    assert not hasattr(gate, "profit")
