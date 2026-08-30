"""Provider-neutral LIA readiness, safety, evidence, and tool contracts."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.payroll.permissions import PayrollPermission
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import (
    AdministrationPermission,
    AnalyticsPermission,
    CustomerPermission,
    EconomicsPolicyPermission,
    InvoicePermission,
    JobPermission,
    SchedulingPermission,
)

FOUNDATION_VERSION = "LIA.FOUNDATION.v1"
READ_ONLY_PROFILE = "LIA.READ_ONLY.v1"
PROPOSAL_NAMESPACE = UUID("99de5512-c3da-4ea4-971f-98996893d1ef")


class FrozenContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceReadiness(StrEnum):
    READY = "READY"
    PARTIAL = "PARTIAL"
    BLOCKED = "BLOCKED"


class EvidenceState(StrEnum):
    KNOWN = "KNOWN"
    PARTIAL = "PARTIAL"
    STALE = "STALE"
    CONFLICTING = "CONFLICTING"
    UNRESOLVED = "UNRESOLVED"
    UNAVAILABLE = "UNAVAILABLE"


class SupportState(StrEnum):
    SUPPORTED = "SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    CONFLICTING = "CONFLICTING"
    UNSUPPORTED = "UNSUPPORTED"
    AUTHORIZATION_DENIED = "AUTHORIZATION_DENIED"


class Sensitivity(StrEnum):
    LOW_OPERATIONAL = "LOW_SENSITIVITY_OPERATIONAL"
    INTERNAL_OPERATIONAL = "INTERNAL_OPERATIONAL"
    CUSTOMER_PROTECTED = "CUSTOMER_PROTECTED"
    FINANCIAL = "FINANCIAL"
    PAYROLL_PROTECTED = "PAYROLL_PROTECTED"
    SECURITY_ADMIN = "SECURITY_ADMIN"
    CREDENTIAL_SECRET = "CREDENTIAL_SECRET_NEVER_CONTEXT"


class QuestionIntent(StrEnum):
    EXPLAIN_SIGNAL = "EXPLAIN_SIGNAL"
    EXPLAIN_ECONOMICS = "EXPLAIN_ECONOMICS"
    BUSINESS_STATUS = "BUSINESS_STATUS"
    JOB_STATUS = "JOB_STATUS"
    CUSTOMER_OPERATIONAL = "CUSTOMER_OPERATIONAL"
    SCHEDULE_STATUS = "SCHEDULE_STATUS"
    WHY_CHANGED = "WHY_CHANGED"
    WHAT_NEEDS_ATTENTION = "WHAT_NEEDS_ATTENTION"
    COMPARE = "COMPARE"
    PREPARE_ACTION = "PREPARE_ACTION"


class OutputClass(StrEnum):
    FACTUAL_ANSWER = "FACTUAL_ANSWER"
    EXPLANATION = "EXPLANATION"
    COMPARISON = "COMPARISON"
    SUMMARY = "SUMMARY"
    RECOMMENDATION = "RECOMMENDATION"
    ACTION_PROPOSAL = "ACTION_PROPOSAL"
    CLARIFICATION_REQUIRED = "CLARIFICATION_REQUIRED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    AUTHORIZATION_DENIED = "AUTHORIZATION_DENIED"


class ActionRisk(StrEnum):
    READ_ONLY = "READ_ONLY"
    LOW_RISK_REVERSIBLE = "LOW_RISK_REVERSIBLE"
    OPERATIONAL_MUTATION = "OPERATIONAL_MUTATION"
    FINANCIAL_MUTATION = "FINANCIAL_MUTATION"
    PAYROLL = "PAYROLL"
    SECURITY_ADMIN = "SECURITY_ADMIN"
    PRODUCTION_IRREVERSIBLE = "PRODUCTION_IRREVERSIBLE"


class Reversibility(StrEnum):
    READ_ONLY = "READ_ONLY"
    REVERSIBLE = "REVERSIBLE"
    COMPENSATABLE = "COMPENSATABLE"
    IRREVERSIBLE = "IRREVERSIBLE"


class MemoryClass(StrEnum):
    CONVERSATION_HISTORY = "CONVERSATION_HISTORY"
    USER_PREFERENCE = "USER_PREFERENCE_NON_AUTHORITATIVE"
    AUTHORITATIVE_BUSINESS_FACT_REFERENCE = "AUTHORITATIVE_BUSINESS_FACT_REFERENCE"
    TEMPORARY_CONTEXT = "TEMPORARY_CONTEXT"


class ActionResultState(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CONFLICT = "CONFLICT"
    STALE = "STALE"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    AUTHORIZATION_DENIED = "AUTHORIZATION_DENIED"
    CANCELED = "CANCELED"
    UNCERTAIN = "UNCERTAIN"


class ProviderState(StrEnum):
    NOT_CONFIGURED = "NOT_CONFIGURED"
    AVAILABLE = "AVAILABLE"
    TEMPORARILY_UNAVAILABLE = "TEMPORARILY_UNAVAILABLE"
    RATE_LIMITED = "RATE_LIMITED"
    TIMEOUT = "TIMEOUT"
    UNCERTAIN = "UNCERTAIN"
    FAILED = "FAILED"


class ToolMutability(StrEnum):
    READ_ONLY = "READ_ONLY"
    PROPOSAL_ONLY = "PROPOSAL_ONLY"
    DOMAIN_EXECUTION = "DOMAIN_EXECUTION"


class PrincipalSnapshot(FrozenContract):
    user_id: UUID
    membership_id: UUID
    company_id: UUID
    authorized_branch_ids: tuple[UUID, ...]
    active_branch_id: UUID | None
    permission_codes: tuple[str, ...]
    role_codes: tuple[str, ...]
    credential_version: int
    authorization_version: int
    environment: str = "NON_PRODUCTION"
    digest: str

    @classmethod
    def capture(cls, context: AuthorizationContext) -> PrincipalSnapshot:
        canonical = {
            "user_id": str(context.user.id),
            "membership_id": str(context.membership.id),
            "company_id": str(context.company.id),
            "authorized_branch_ids": sorted(
                str(item) for item in context.authorized_branch_ids
            ),
            "active_branch_id": str(context.active_branch.id)
            if context.active_branch
            else None,
            "permission_codes": sorted(context.permission_codes),
            "role_codes": sorted(context.role_codes),
            "credential_version": context.credential_version,
            "authorization_version": context.authorization_version,
            "environment": "NON_PRODUCTION",
        }
        return cls(
            user_id=context.user.id,
            membership_id=context.membership.id,
            company_id=context.company.id,
            authorized_branch_ids=tuple(sorted(context.authorized_branch_ids)),
            active_branch_id=context.active_branch.id
            if context.active_branch
            else None,
            permission_codes=tuple(sorted(context.permission_codes)),
            role_codes=tuple(sorted(context.role_codes)),
            credential_version=context.credential_version,
            authorization_version=context.authorization_version,
            digest=_digest(canonical),
        )


class ContextBudget(FrozenContract):
    max_sources: int = Field(default=8, ge=1, le=32)
    max_evidence_items: int = Field(default=25, ge=1, le=100)
    max_history_depth: int = Field(default=10, ge=0, le=100)
    max_tool_attempts: int = Field(default=4, ge=0, le=20)
    max_time_range_days: int = Field(default=366, ge=1, le=3660)
    timeout_classification: str = "TEMPORARILY_UNAVAILABLE"


class SourceSpec(FrozenContract):
    source_id: str
    authority: str
    required_permission: str
    sensitivity: Sensitivity
    branch_scoped: bool
    max_results: int
    freshness_contract: str
    provenance_contract: str
    readiness: SourceReadiness
    blocker: str | None = None


class EvidenceEnvelope(FrozenContract):
    evidence_id: str
    source_id: str
    source_domain: str
    source_entity_type: str
    source_entity_id: UUID | None
    version_or_digest: str
    effective_at: datetime | None
    observed_at: datetime
    state: EvidenceState
    freshness: str
    confidence: str
    completeness: str
    reconciliation: str
    limitations: tuple[str, ...] = ()
    safe_summary: str
    drillback_path: str | None = None
    untrusted_content: bool = False


class ToolSpec(FrozenContract):
    tool_id: str
    version: int
    owning_domain: str
    required_permission: str
    input_schema: str
    branch_scoped: bool
    mutability: ToolMutability
    risk: ActionRisk
    reversibility: Reversibility
    idempotency_required: bool
    owner_approval_required: bool
    evidence_result_contract: str


class ActionProposalV1(FrozenContract):
    contract_version: str = "LIA_PROPOSED_ACTION.v1"
    proposal_id: UUID
    action_type: str
    owning_domain: str
    target_id: UUID
    company_id: UUID
    branch_id: UUID | None
    principal_digest: str
    evidence_references: tuple[str, ...]
    evidence_digest: str
    target_version: int | None
    reason_summary: str = Field(max_length=500)
    required_permission: str
    approval_requirement: str
    risk: ActionRisk
    reversibility: Reversibility
    idempotency_key: UUID
    expires_at: datetime
    execution_state: str = "PROPOSED_NOT_EXECUTED"

    @model_validator(mode="after")
    def prohibit_execution(self) -> ActionProposalV1:
        if self.execution_state != "PROPOSED_NOT_EXECUTED":
            raise ValueError("LIA foundation cannot represent executed authority.")
        return self

    @classmethod
    def create(
        cls,
        *,
        action_type: str,
        owning_domain: str,
        target_id: UUID,
        company_id: UUID,
        branch_id: UUID | None,
        principal_digest: str,
        evidence_references: tuple[str, ...],
        target_version: int | None,
        reason_summary: str,
        required_permission: str,
        approval_requirement: str,
        risk: ActionRisk,
        reversibility: Reversibility,
        idempotency_key: UUID,
        expires_at: datetime,
    ) -> ActionProposalV1:
        canonical = {
            "action_type": action_type,
            "owning_domain": owning_domain,
            "target_id": str(target_id),
            "company_id": str(company_id),
            "branch_id": str(branch_id) if branch_id else None,
            "principal_digest": principal_digest,
            "evidence_references": sorted(evidence_references),
            "target_version": target_version,
            "required_permission": required_permission,
            "risk": risk.value,
            "idempotency_key": str(idempotency_key),
            "expires_at": expires_at.isoformat(),
        }
        evidence_digest = _digest(canonical)
        return cls(
            proposal_id=uuid5(PROPOSAL_NAMESPACE, evidence_digest),
            action_type=action_type,
            owning_domain=owning_domain,
            target_id=target_id,
            company_id=company_id,
            branch_id=branch_id,
            principal_digest=principal_digest,
            evidence_references=tuple(sorted(evidence_references)),
            evidence_digest=evidence_digest,
            target_version=target_version,
            reason_summary=reason_summary,
            required_permission=required_permission,
            approval_requirement=approval_requirement,
            risk=risk,
            reversibility=reversibility,
            idempotency_key=idempotency_key,
            expires_at=expires_at,
        )


class ActionPreview(FrozenContract):
    proposal_id: UUID
    action_type: str
    target_id: UUID
    expected_effect: str
    evidence_references: tuple[str, ...]
    required_permission: str
    risk: ActionRisk
    reversibility: Reversibility
    approval_requirement: str
    target_version: int | None
    stale: bool
    executable: bool = False


class ActionResult(FrozenContract):
    proposal_id: UUID
    state: ActionResultState
    owning_domain_reference: UUID | None
    occurred_at: datetime
    reconciliation_reference: UUID | None = None
    retry_classification: str


class StructuredClaim(FrozenContract):
    claim_id: str
    claim_type: str
    value: str
    unit: str | None = None
    evidence_ids: tuple[str, ...]
    effective_at: datetime | None = None
    policy_reference: str | None = None


class LiaAuditEvidence(FrozenContract):
    request_id: UUID
    conversation_id: UUID | None
    principal_digest: str
    requested_source_ids: tuple[str, ...]
    requested_tool_ids: tuple[str, ...]
    result_classification: str
    proposed_action_ids: tuple[UUID, ...]
    authorization_result: str
    occurred_at: datetime
    raw_prompt_logged: bool = False
    raw_evidence_logged: bool = False
    hidden_reasoning_logged: bool = False


class LiaOperationalMetric(FrozenContract):
    metric: str
    source_or_tool_category: str | None
    classification: str
    latency_bucket: str | None
    count: int = Field(ge=0)
    contains_prompt_content: bool = False


class AnswerEvidenceContract(FrozenContract):
    output_class: OutputClass
    support_state: SupportState
    evidence_ids: tuple[str, ...]
    freshness: str
    limitations: tuple[str, ...]
    principal_digest: str
    generated_at: datetime
    claim_digest: str


class ConversationAuthority(FrozenContract):
    conversation_id: UUID
    principal_digest: str
    company_id: UUID
    authorized_branch_ids: tuple[UUID, ...]
    authorization_version: int
    created_at: datetime
    last_reauthorized_at: datetime
    lifecycle: str = "ACTIVE_REAUTHORIZE_EACH_REQUEST"
    transcript_retention: str = "NOT_CONFIGURED_NO_DURABLE_TRANSCRIPT"
    hidden_reasoning_retention: str = "PROHIBITED"

    def is_current(self, principal: PrincipalSnapshot) -> bool:
        return (
            self.principal_digest == principal.digest
            and self.authorization_version == principal.authorization_version
            and self.authorized_branch_ids == principal.authorized_branch_ids
        )


class ProviderRequest(FrozenContract):
    policy_version: str
    principal_digest: str
    visible_messages: tuple[str, ...]
    evidence: tuple[EvidenceEnvelope, ...]
    available_tools: tuple[ToolSpec, ...]
    context_budget: ContextBudget


class ProviderCandidate(FrozenContract):
    output_class: OutputClass
    visible_text: str
    evidence_ids: tuple[str, ...]
    requested_tool_id: str | None = None
    requested_tool_arguments: dict[str, object] | None = None
    provider_state: ProviderState


class EvaluationCase(FrozenContract):
    case_id: str
    intent: QuestionIntent
    permission_codes: tuple[str, ...]
    requested_sources: tuple[str, ...]
    authorized_evidence: tuple[str, ...]
    forbidden_evidence: tuple[str, ...]
    expected_tools: tuple[str, ...]
    expected_support: SupportState
    expected_output: OutputClass
    forbidden_actions: tuple[str, ...]


class FoundationReadiness(FrozenContract):
    foundation_version: str
    release_profile: str
    provider_state: ProviderState
    provider_configured: bool
    autonomous_mutation: bool
    production_mutation: bool
    source_states: dict[str, SourceReadiness]
    tool_count: int
    executable_tool_count: int
    permission_propagation: str
    conversation_retention: str
    evaluation_status: str
    blockers: tuple[str, ...]


def foundation_readiness() -> FoundationReadiness:
    return FoundationReadiness(
        foundation_version=FOUNDATION_VERSION,
        release_profile=READ_ONLY_PROFILE,
        provider_state=ProviderState.NOT_CONFIGURED,
        provider_configured=False,
        autonomous_mutation=False,
        production_mutation=False,
        source_states={item.source_id: item.readiness for item in SOURCE_REGISTRY},
        tool_count=len(TOOL_REGISTRY),
        executable_tool_count=sum(
            item.mutability is ToolMutability.DOMAIN_EXECUTION for item in TOOL_REGISTRY
        ),
        permission_propagation="REAUTHORIZE_AND_SCOPE_BEFORE_RETRIEVAL",
        conversation_retention="NOT_CONFIGURED_NO_DURABLE_TRANSCRIPT",
        evaluation_status="DETERMINISTIC_HARNESS_AVAILABLE",
        blockers=tuple(
            sorted(item.blocker for item in SOURCE_REGISTRY if item.blocker)
        ),
    )


SOURCE_REGISTRY = (
    SourceSpec(
        source_id="BEACON_INTELLIGENCE",
        authority="BEACON.INTELLIGENCE.v1",
        required_permission=AnalyticsPermission.READ,
        sensitivity=Sensitivity.INTERNAL_OPERATIONAL,
        branch_scoped=True,
        max_results=25,
        freshness_contract="BEACON_QUALITY_ENVELOPE",
        provenance_contract="BEACON_EVIDENCE_DIGEST",
        readiness=SourceReadiness.READY,
    ),
    SourceSpec(
        source_id="ECONOMICS_INTELLIGENCE",
        authority="economics.owner-intelligence.v1",
        required_permission=EconomicsPolicyPermission.MEASUREMENT_READ,
        sensitivity=Sensitivity.FINANCIAL,
        branch_scoped=True,
        max_results=20,
        freshness_contract="ECONOMICS_MEASUREMENT_PACKAGE",
        provenance_contract="ECONOMICS_RESULT_LINEAGE",
        readiness=SourceReadiness.READY,
    ),
    SourceSpec(
        source_id="CUSTOMER_OPERATIONAL",
        authority="CUSTOMER_DOMAIN",
        required_permission=CustomerPermission.READ,
        sensitivity=Sensitivity.CUSTOMER_PROTECTED,
        branch_scoped=False,
        max_results=20,
        freshness_contract="CURRENT_QUERY",
        provenance_contract="CUSTOMER_ID_VERSION",
        readiness=SourceReadiness.PARTIAL,
        blocker="Role-specific minimum necessary projection remains domain-owned.",
    ),
    SourceSpec(
        source_id="JOB_OPERATIONAL",
        authority="JOB_DOMAIN",
        required_permission=JobPermission.READ,
        sensitivity=Sensitivity.CUSTOMER_PROTECTED,
        branch_scoped=True,
        max_results=20,
        freshness_contract="CURRENT_QUERY",
        provenance_contract="JOB_ID_VERSION",
        readiness=SourceReadiness.READY,
    ),
    SourceSpec(
        source_id="SCHEDULE_CONTEXT",
        authority="SCHEDULING_DOMAIN",
        required_permission=SchedulingPermission.READ,
        sensitivity=Sensitivity.INTERNAL_OPERATIONAL,
        branch_scoped=True,
        max_results=20,
        freshness_contract="CURRENT_QUERY",
        provenance_contract="APPOINTMENT_ID_VERSION",
        readiness=SourceReadiness.READY,
    ),
    SourceSpec(
        source_id="INVOICE_STATUS",
        authority="INVOICE_DOMAIN",
        required_permission=InvoicePermission.READ,
        sensitivity=Sensitivity.FINANCIAL,
        branch_scoped=True,
        max_results=20,
        freshness_contract="CURRENT_QUERY",
        provenance_contract="INVOICE_ID_VERSION",
        readiness=SourceReadiness.READY,
    ),
    SourceSpec(
        source_id="PAYROLL_OWN_STATEMENT",
        authority="PAYROLL_DOMAIN",
        required_permission=PayrollPermission.STATEMENT_OWN_READ,
        sensitivity=Sensitivity.PAYROLL_PROTECTED,
        branch_scoped=True,
        max_results=1,
        freshness_contract="PAYROLL_STATEMENT_VERSION",
        provenance_contract="SERVER_RESOLVED_EMPLOYEE",
        readiness=SourceReadiness.READY,
    ),
    SourceSpec(
        source_id="SYSTEM_READINESS",
        authority="ACP_READINESS_REGISTRIES",
        required_permission=AdministrationPermission.COMPANY_ADMINISTER,
        sensitivity=Sensitivity.SECURITY_ADMIN,
        branch_scoped=False,
        max_results=25,
        freshness_contract="CURRENT_AUTHORITY",
        provenance_contract="REGISTRY_DIGEST",
        readiness=SourceReadiness.PARTIAL,
        blocker="Only approved bounded readiness registries may be adapted.",
    ),
)


TOOL_REGISTRY = (
    ToolSpec(
        tool_id="get_signal",
        version=1,
        owning_domain="Beacon",
        required_permission=AnalyticsPermission.READ,
        input_schema="SignalIdentityInput.v1",
        branch_scoped=True,
        mutability=ToolMutability.READ_ONLY,
        risk=ActionRisk.READ_ONLY,
        reversibility=Reversibility.READ_ONLY,
        idempotency_required=False,
        owner_approval_required=False,
        evidence_result_contract="BEACON.INTELLIGENCE.v1",
    ),
    ToolSpec(
        tool_id="list_signals",
        version=1,
        owning_domain="Beacon",
        required_permission=AnalyticsPermission.READ,
        input_schema="BoundedSignalQuery.v1",
        branch_scoped=True,
        mutability=ToolMutability.READ_ONLY,
        risk=ActionRisk.READ_ONLY,
        reversibility=Reversibility.READ_ONLY,
        idempotency_required=False,
        owner_approval_required=False,
        evidence_result_contract="BEACON.INTELLIGENCE.v1",
    ),
    ToolSpec(
        tool_id="get_job",
        version=1,
        owning_domain="Jobs",
        required_permission=JobPermission.READ,
        input_schema="ScopedEntityVersionInput.v1",
        branch_scoped=True,
        mutability=ToolMutability.READ_ONLY,
        risk=ActionRisk.READ_ONLY,
        reversibility=Reversibility.READ_ONLY,
        idempotency_required=False,
        owner_approval_required=False,
        evidence_result_contract="LIA_EVIDENCE_ENVELOPE.v1",
    ),
    ToolSpec(
        tool_id="get_customer_operational_context",
        version=1,
        owning_domain="Customers",
        required_permission=CustomerPermission.READ,
        input_schema="MinimumNecessaryCustomerInput.v1",
        branch_scoped=False,
        mutability=ToolMutability.READ_ONLY,
        risk=ActionRisk.READ_ONLY,
        reversibility=Reversibility.READ_ONLY,
        idempotency_required=False,
        owner_approval_required=False,
        evidence_result_contract="LIA_EVIDENCE_ENVELOPE.v1",
    ),
    ToolSpec(
        tool_id="get_invoice_status",
        version=1,
        owning_domain="Invoices",
        required_permission=InvoicePermission.READ,
        input_schema="ScopedEntityVersionInput.v1",
        branch_scoped=True,
        mutability=ToolMutability.READ_ONLY,
        risk=ActionRisk.READ_ONLY,
        reversibility=Reversibility.READ_ONLY,
        idempotency_required=False,
        owner_approval_required=False,
        evidence_result_contract="LIA_EVIDENCE_ENVELOPE.v1",
    ),
    ToolSpec(
        tool_id="prepare_action",
        version=1,
        owning_domain="LIA",
        required_permission="DOMAIN_PERMISSION_RESOLVED_AT_PROPOSAL_TIME",
        input_schema="LIA_PROPOSED_ACTION.v1",
        branch_scoped=True,
        mutability=ToolMutability.PROPOSAL_ONLY,
        risk=ActionRisk.OPERATIONAL_MUTATION,
        reversibility=Reversibility.COMPENSATABLE,
        idempotency_required=True,
        owner_approval_required=True,
        evidence_result_contract="PROPOSAL_NOT_EXECUTED",
    ),
)


def source_for(source_id: str) -> SourceSpec:
    return next(item for item in SOURCE_REGISTRY if item.source_id == source_id)


def permitted_sources(
    principal: PrincipalSnapshot, requested: tuple[str, ...], budget: ContextBudget
) -> tuple[SourceSpec, ...]:
    if len(requested) > budget.max_sources:
        raise ValueError("Requested sources exceed the deterministic context budget.")
    unique = tuple(dict.fromkeys(requested))
    resolved = tuple(source_for(source_id) for source_id in unique)
    return tuple(
        item
        for item in resolved
        if item.required_permission in principal.permission_codes
        and item.sensitivity is not Sensitivity.CREDENTIAL_SECRET
    )


def validate_candidate(
    candidate: ProviderCandidate,
    *,
    principal: PrincipalSnapshot,
    evidence: tuple[EvidenceEnvelope, ...],
    tools: tuple[ToolSpec, ...],
) -> AnswerEvidenceContract:
    evidence_by_id = {item.evidence_id: item for item in evidence}
    if any(item not in evidence_by_id for item in candidate.evidence_ids):
        support = SupportState.UNSUPPORTED
    elif any(
        evidence_by_id[item].state is EvidenceState.CONFLICTING
        for item in candidate.evidence_ids
    ):
        support = SupportState.CONFLICTING
    elif not candidate.evidence_ids:
        support = SupportState.UNSUPPORTED
    elif any(
        evidence_by_id[item].state
        in (EvidenceState.PARTIAL, EvidenceState.STALE, EvidenceState.UNRESOLVED)
        for item in candidate.evidence_ids
    ):
        support = SupportState.PARTIALLY_SUPPORTED
    else:
        support = SupportState.SUPPORTED
    if candidate.requested_tool_id is not None:
        tool = next(
            (item for item in tools if item.tool_id == candidate.requested_tool_id),
            None,
        )
        if (
            tool is None
            or tool.required_permission not in principal.permission_codes
            or tool.mutability is ToolMutability.DOMAIN_EXECUTION
        ):
            support = SupportState.AUTHORIZATION_DENIED
    payload = {
        "output_class": candidate.output_class.value,
        "support_state": support.value,
        "evidence_ids": sorted(candidate.evidence_ids),
        "principal_digest": principal.digest,
    }
    return AnswerEvidenceContract(
        output_class=(
            OutputClass.AUTHORIZATION_DENIED
            if support is SupportState.AUTHORIZATION_DENIED
            else candidate.output_class
        ),
        support_state=support,
        evidence_ids=tuple(sorted(candidate.evidence_ids)),
        freshness="PRESERVED_FROM_EVIDENCE",
        limitations=("Generated text is non-authoritative and evidence-bound.",),
        principal_digest=principal.digest,
        generated_at=datetime.fromisoformat("2026-08-30T00:00:00+00:00"),
        claim_digest=_digest(payload),
    )


def _digest(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
