from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.beacon.catalog import (
    OperationalConflictPolicy,
    OperationalSignalAdmission,
    OperationalSignalFamily,
    SignalClassification,
)
from app.beacon.contracts import (
    BeaconCategory,
    BeaconConfidenceLevel,
    BeaconExpirationPolicy,
    BeaconLifecycleAction,
    BeaconLifecycleStatus,
    BeaconPriorityBand,
    BeaconRankingFactorAvailability,
    BeaconSeverity,
    BeaconSignalSource,
    BeaconWorkflowAction,
)
from app.beacon.escalation import EscalationEligibility, EscalationState
from app.beacon.evidence_evaluation import EvaluationReadiness
from app.beacon.quality import (
    EvidenceCompletenessState,
    EvidenceConfidenceState,
    EvidenceFreshnessState,
    EvidenceReconciliationState,
    StaleEvidenceBehavior,
)


class BeaconConfidenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    level: BeaconConfidenceLevel
    basis: str


class BeaconEvidenceQualityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    definition_id: str
    definition_version: int
    source_authority: str
    effective_at: datetime | None
    observed_as_of: datetime | None
    evaluated_at: datetime
    completeness: EvidenceCompletenessState
    reconciliation: EvidenceReconciliationState
    freshness: EvidenceFreshnessState
    confidence: EvidenceConfidenceState
    freshness_policy_id: str | None
    freshness_policy_version: int | None
    stale_behavior: StaleEvidenceBehavior | None
    limitations: tuple[str, ...]
    quality_digest: str
    conclusion_admissible: bool
    explanation: str


class BeaconEvidenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    entity_type: str
    entity_id: UUID
    event_id: UUID | None
    event_type: str | None
    occurred_at: datetime | None


class BeaconSupportingFactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    value: str | int | bool
    source: str
    measured_at: datetime
    evidence: tuple[BeaconEvidenceResponse, ...]
    unit: str | None


class BeaconRankingFactorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    value: str | int | bool | None
    unit: str | None
    availability: BeaconRankingFactorAvailability
    contribution: int
    explanation: str


class BeaconPriorityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    band: BeaconPriorityBand
    score: int
    rank: int
    ranking_factors: tuple[BeaconRankingFactorResponse, ...]
    explanation: str
    evaluated_at: datetime
    tie_break_semantics: str


class BeaconLifecycleEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    condition_key: UUID
    signal_id: UUID
    rule_code: str
    signal_source: BeaconSignalSource
    evidence_digest: str
    action: BeaconLifecycleAction
    actor_membership_id: UUID
    action_at: datetime
    snooze_until: datetime | None
    created_at: datetime


class BeaconLifecycleProjectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: BeaconLifecycleStatus
    latest_event: BeaconLifecycleEventResponse | None
    temporarily_suppressed: bool


class BeaconSignalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    condition_key: UUID
    evidence_digest: str
    definition_id: str
    definition_version: int
    rule_code: str
    source: BeaconSignalSource
    title: str
    category: BeaconCategory
    severity: BeaconSeverity
    priority: BeaconPriorityResponse
    lifecycle: BeaconLifecycleProjectionResponse
    confidence: BeaconConfidenceResponse
    evidence_quality: BeaconEvidenceQualityResponse | None
    supporting_facts: tuple[BeaconSupportingFactResponse, ...]
    recommended_action: str
    created_at: datetime
    expires_at: datetime
    expiration_policy: BeaconExpirationPolicy
    escalation: "EscalationProjectionResponse | None" = None


class BeaconSignalPage(BaseModel):
    items: tuple[BeaconSignalResponse, ...]
    snoozed_items: tuple[BeaconSignalResponse, ...]
    evaluated_at: datetime
    expires_at: datetime
    lifecycle_commands_available: bool


class OperationalRankingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    position: int
    ranking_version: str
    ranking_digest: str
    severity: BeaconSeverity
    priority_band: BeaconPriorityBand
    urgency_policy_id: str | None
    urgency_policy_version: int | None
    urgency_value: str | None
    urgency_unit: str | None
    confidence_state: str
    freshness_state: str
    tie_break_identity: UUID
    ranking_reason: str


class PrioritizedOperationalSignalResponse(BaseModel):
    signal: BeaconSignalResponse
    ranking: OperationalRankingResponse


class OperationalAttentionQueueResponse(BaseModel):
    company_id: UUID
    branch_id: UUID | None
    evaluated_at: datetime
    ranking_version: str
    ranking_digest: str
    items: tuple[PrioritizedOperationalSignalResponse, ...]


class BeaconLifecycleCommandRequest(BaseModel):
    evidence_digest: str = Field(min_length=64, max_length=64)


class BeaconSnoozeCommandRequest(BeaconLifecycleCommandRequest):
    snooze_until: datetime


class BeaconLifecycleHistoryResponse(BaseModel):
    items: tuple[BeaconLifecycleEventResponse, ...]


class BeaconWorkflowCommandRequest(BaseModel):
    evidence_digest: str = Field(min_length=64, max_length=64)
    request_id: UUID
    expected_version: int | None = Field(default=None, ge=0)
    owner_user_id: UUID | None = None


class BeaconWorkflowStateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    company_id: UUID
    branch_id: UUID | None
    condition_key: UUID
    signal_id: UUID
    definition_id: str
    definition_version: int
    evidence_digest: str
    workflow_version: int
    acknowledged: bool
    acknowledged_by_user_id: UUID | None
    acknowledged_at: datetime | None
    owner_user_id: UUID | None
    owned_since: datetime | None
    last_action: BeaconWorkflowAction | None
    last_actor_user_id: UUID | None
    updated_at: datetime | None


class BeaconWorkflowEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    state: BeaconWorkflowStateResponse
    action: BeaconWorkflowAction
    actor_user_id: UUID
    previous_owner_user_id: UUID | None
    request_id: UUID
    occurred_at: datetime


class BeaconWorkflowHistoryResponse(BaseModel):
    items: tuple[BeaconWorkflowEventResponse, ...]


class OperationalWorkflowSignalResponse(BaseModel):
    signal: BeaconSignalResponse
    ranking: OperationalRankingResponse
    workflow: BeaconWorkflowStateResponse | None
    escalation: "EscalationProjectionResponse"


class OperationalWorkflowQueueResponse(BaseModel):
    view: str
    ranking_version: str
    ranking_digest: str
    items: tuple[OperationalWorkflowSignalResponse, ...]


class BeaconActionContractResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    action: str
    available: bool
    required_permission: str
    execution_authority: str


class BeaconSourceReferenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    domain: str
    entity_type: str
    entity_id: UUID
    evidence_event_id: UUID | None
    observed_at: datetime | None


class BeaconIntelligencePacketResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    contract_version: str
    company_id: UUID
    branch_id: UUID | None
    signal_id: UUID
    condition_key: UUID
    definition_id: str
    definition_version: int
    evidence_digest: str
    title: str
    state: str
    explanation: str
    recommended_human_action: str
    priority_position: int
    priority_band: str
    priority_reason: str
    severity: str
    confidence: str
    completeness: str
    freshness: str
    reconciliation: str
    limitations: tuple[str, ...]
    owner_user_id: UUID | None
    acknowledged: bool
    escalation_state: str
    escalation_reason: str
    source_references: tuple[BeaconSourceReferenceResponse, ...]
    actions: tuple[BeaconActionContractResponse, ...]
    generated_at: datetime
    packet_digest: str


class BeaconSystemReadinessResponse(BaseModel):
    catalog_id: str
    catalog_digest: str
    company_id: UUID
    active_branch_id: UUID | None
    definitions_total: int
    evaluable: int
    partially_evaluable: int
    not_evaluable: int
    conflicting: int
    escalation_ready: int
    escalation_policy_unconfigured: int
    source_blockers: tuple[str, ...]
    production_policy_state: str
    autonomous_action: bool


class EscalationRegistrationResponse(BaseModel):
    definition_id: str
    definition_version: int
    family: OperationalSignalFamily
    evaluation_readiness: EvaluationReadiness
    eligibility: EscalationEligibility
    rule_available: bool
    rule_id: str | None
    rule_version: int | None
    rule_digest: str | None
    blocker: str | None


class EscalationRegistryResponse(BaseModel):
    catalog_id: str
    catalog_digest: str
    company_id: UUID
    active_branch_id: UUID | None
    registrations: tuple[EscalationRegistrationResponse, ...]


class EscalationProjectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    signal_id: UUID
    condition_key: UUID
    company_id: UUID
    branch_id: UUID | None
    state: EscalationState
    eligibility: EscalationEligibility
    escalation_rule_id: str | None
    escalation_rule_version: int | None
    escalation_rule_digest: str | None
    escalated_at: datetime | None
    reason: str
    acknowledged: bool
    owner_user_id: UUID | None


class OperationalSignalDefinitionResponse(BaseModel):
    definition_id: str
    version: int
    definition_digest: str
    family: OperationalSignalFamily
    subject_type: str
    source_authority: str
    condition: str
    explanation_safe_fields: tuple[str, ...]
    required_evidence_types: tuple[str, ...]
    base_severity: BeaconSeverity
    base_priority: BeaconPriorityBand
    expiration_policy: BeaconExpirationPolicy
    ttl_seconds: int
    conflict_policy: OperationalConflictPolicy
    admission: OperationalSignalAdmission
    evaluator_rule_code: str | None
    signal_classification: SignalClassification
    scope: str


class OperationalSignalCatalogResponse(BaseModel):
    catalog_id: str
    version: int
    catalog_digest: str
    company_id: UUID
    active_branch_id: UUID | None
    definitions: tuple[OperationalSignalDefinitionResponse, ...]


class EvidenceEvaluationRegistrationResponse(BaseModel):
    definition_id: str
    family: OperationalSignalFamily
    readiness: EvaluationReadiness
    authoritative_source_contract: str
    required_fact_contract: tuple[str, ...]
    evaluator_implemented: bool
    blocker: str | None
    limitations: tuple[str, ...]


class EvidenceEvaluationRegistryResponse(BaseModel):
    catalog_id: str
    catalog_digest: str
    company_id: UUID
    active_branch_id: UUID | None
    registrations: tuple[EvidenceEvaluationRegistrationResponse, ...]


class DefinitionQualitySemanticsResponse(BaseModel):
    definition_id: str
    readiness: EvaluationReadiness
    confidence_semantics_available: bool
    freshness_semantics_available: bool
    freshness_policy_id: str | None
    freshness_policy_version: int | None
    policy_source: str | None
    blocker: str | None


class DefinitionQualityRegistryResponse(BaseModel):
    catalog_id: str
    catalog_digest: str
    company_id: UUID
    active_branch_id: UUID | None
    definitions: tuple[DefinitionQualitySemanticsResponse, ...]
