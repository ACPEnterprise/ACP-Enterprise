from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.accounting.posting.contracts import PostingFact
from app.jobs.query_types import JobDetail
from app.qbo_source.economics_evidence import (
    EconomicsEvidenceCategory,
    QboEconomicsAssertion,
)

from .findings import FindingState
from .measurement_contract import MeasurementComponent, MeasurementEvidenceInput
from .source_adapters import PublicOperationalEvidence
from .source_conformance import EvidenceConfidence

MEASUREMENT_ADAPTER_DEFINITION_VERSION = "eco.measurement.adapters.v1"
_SHA256 = re.compile(r"^[a-f0-9]{64}$")


@dataclass(frozen=True, slots=True)
class MeasurementAdapterContext:
    company_id: UUID
    branch_id: UUID | None
    subject_id: str
    reconciliation_key: str
    package_digest: str
    as_of: datetime

    def __post_init__(self) -> None:
        if not self.subject_id or not self.reconciliation_key:
            raise ValueError(
                "explicit subject and reconciliation identity are required"
            )
        if not _SHA256.fullmatch(self.package_digest):
            raise ValueError("adapter package digest is required")


def adapt_job_detail(
    job: JobDetail, context: MeasurementAdapterContext
) -> tuple[MeasurementEvidenceInput, ...]:
    """Adapt accepted ACP Job identity/lifecycle without inferring relationships."""

    _require_scope(job.company_id, job.branch_id, context)
    if context.subject_id != str(job.id):
        raise ValueError("Job subject identity does not match adapter context")
    canonical = {
        "id": str(job.id),
        "job_number": job.job_number,
        "company_id": str(job.company_id),
        "branch_id": str(job.branch_id),
        "status": job.status.value,
        "version": job.concurrency_version,
        "activated_at": job.activated_at.isoformat() if job.activated_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "cancelled_at": job.cancelled_at.isoformat() if job.cancelled_at else None,
        "job_type_code": job.job_type_code,
        "updated_at": job.updated_at.isoformat(),
    }
    value_digest = _digest(canonical)
    result = [
        _job_input(
            job=job,
            context=context,
            input_id=f"eco-job-context:{job.id}:{job.concurrency_version}",
            component=MeasurementComponent.JOB_CONTEXT,
            limitations=("identity_and_lifecycle_context_only",),
            evidence_digest=value_digest,
        )
    ]
    if job.job_type_code:
        service_digest = _digest(
            {"job_id": str(job.id), "job_type_code": job.job_type_code}
        )
        result.append(
            _job_input(
                job=job,
                context=context,
                input_id=f"eco-service-line:{job.id}:{job.concurrency_version}",
                component=MeasurementComponent.SERVICE_LINE_ATTRIBUTION,
                limitations=("explicit_job_type_code_only",),
                evidence_digest=service_digest,
            )
        )
    return tuple(result)


def _job_input(
    *,
    job: JobDetail,
    context: MeasurementAdapterContext,
    input_id: str,
    component: MeasurementComponent,
    limitations: tuple[str, ...],
    evidence_digest: str,
) -> MeasurementEvidenceInput:
    return MeasurementEvidenceInput(
        input_id=input_id,
        subject_id=context.subject_id,
        reconciliation_key=context.reconciliation_key,
        component=component,
        source_authority="acp_job_domain_accepted",
        evidence_state=FindingState.READY,
        confidence=EvidenceConfidence.AVAILABLE,
        source_value=None,
        currency=None,
        unit=None,
        effective_date=job.completed_at.date() if job.completed_at else None,
        as_of=context.as_of,
        accepted_for_measurement=True,
        limitations=limitations,
        evidence_digest=evidence_digest,
        value_digest=evidence_digest,
        package_digest=context.package_digest,
        company_id=context.company_id,
        branch_id=context.branch_id,
    )


def adapt_accounting_posting_fact(
    fact: PostingFact, context: MeasurementAdapterContext
) -> MeasurementEvidenceInput:
    """Adapt accepted posting evidence without interpreting its economic category."""

    _require_scope(fact.company_id, fact.branch_id, context)
    if not _SHA256.fullmatch(fact.evidence_digest):
        raise ValueError("PostingFact evidence digest is invalid")
    return MeasurementEvidenceInput(
        input_id=f"eco-posting:{fact.source_identity}",
        subject_id=context.subject_id,
        reconciliation_key=context.reconciliation_key,
        component=MeasurementComponent.ACCOUNTING_RECONCILIATION,
        source_authority="acp_accounting_posting_fact_accepted",
        evidence_state=FindingState.READY,
        confidence=EvidenceConfidence.AVAILABLE,
        source_value=None,
        currency=fact.currency,
        unit=None,
        effective_date=fact.effective_date,
        as_of=context.as_of,
        accepted_for_measurement=True,
        limitations=(
            "posting_fact_does_not_select_revenue_or_cost_policy",
            "posting_components_not_reclassified",
        ),
        evidence_digest=fact.evidence_digest,
        value_digest=fact.canonical_digest(),
        package_digest=context.package_digest,
        company_id=context.company_id,
        branch_id=context.branch_id,
    )


def adapt_public_operational_measurement(
    evidence: PublicOperationalEvidence,
    *,
    component: MeasurementComponent,
    context: MeasurementAdapterContext,
) -> MeasurementEvidenceInput:
    """Adapt public provider-neutral evidence without inferring its acceptance."""

    if evidence.semantic_key != context.reconciliation_key:
        raise ValueError("public evidence reconciliation identity does not match")
    state = {
        EvidenceConfidence.AVAILABLE: FindingState.PARTIAL,
        EvidenceConfidence.PARTIAL: FindingState.PARTIAL,
        EvidenceConfidence.UNKNOWN: FindingState.UNKNOWN,
        EvidenceConfidence.CONFLICTING: FindingState.CONFLICTING,
    }[evidence.confidence]
    return MeasurementEvidenceInput(
        input_id=f"eco-public:{evidence.assertion_id}",
        subject_id=context.subject_id,
        reconciliation_key=context.reconciliation_key,
        component=component,
        source_authority=evidence.source_authority,
        evidence_state=state,
        confidence=evidence.confidence,
        source_value=None,
        currency=None,
        unit=None,
        effective_date=None,
        as_of=context.as_of,
        accepted_for_measurement=False,
        limitations=tuple(
            sorted(
                (
                    *evidence.limitations,
                    "public_contract_does_not_assert_measurement_acceptance",
                )
            )
        ),
        evidence_digest=evidence.evidence_digest,
        value_digest=evidence.value_digest,
        package_digest=evidence.package_digest,
        company_id=context.company_id,
        branch_id=context.branch_id,
    )


def adapt_qbo_source_reported_measurement(
    evidence: QboEconomicsAssertion,
    *,
    context: MeasurementAdapterContext,
) -> MeasurementEvidenceInput:
    """Retain QBO provenance while refusing economic acceptance or value promotion."""

    components = {
        EconomicsEvidenceCategory.REVENUE_ASSERTION: MeasurementComponent.REVENUE_EARNED_VALUE,
        EconomicsEvidenceCategory.SETTLEMENT_ASSERTION: MeasurementComponent.SETTLEMENT,
        EconomicsEvidenceCategory.PROCUREMENT_ASSERTION: MeasurementComponent.DIRECT_MATERIAL,
    }
    component = components.get(evidence.category)
    if component is None:
        raise ValueError("QBO assertion has no supported measurement component")
    if evidence.source_authority != "quickbooks_online_source_reported":
        raise ValueError("QBO source-reported authority is required")
    return MeasurementEvidenceInput(
        input_id=f"eco-qbo-measurement:{evidence.assertion_id}",
        subject_id=context.subject_id,
        reconciliation_key=context.reconciliation_key,
        component=component,
        source_authority=evidence.source_authority,
        evidence_state=FindingState.PARTIAL,
        confidence=EvidenceConfidence.PARTIAL,
        source_value=None,
        currency=None,
        unit=None,
        effective_date=None,
        as_of=context.as_of,
        accepted_for_measurement=False,
        limitations=tuple(
            sorted(
                (
                    *evidence.limitations,
                    "qbo_source_value_not_promoted",
                    "finance_acceptance_required",
                )
            )
        ),
        evidence_digest=evidence.raw_sha256,
        value_digest=evidence.source_envelope_sha256,
        package_digest=evidence.source_manifest_sha256,
        company_id=context.company_id,
        branch_id=context.branch_id,
    )


def _require_scope(
    company_id: UUID, branch_id: UUID | None, context: MeasurementAdapterContext
) -> None:
    if company_id != context.company_id:
        raise ValueError("company isolation violation")
    if branch_id != context.branch_id:
        raise ValueError("branch isolation violation")


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
