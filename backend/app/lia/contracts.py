from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class LiaSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TruthClassification(StrEnum):
    KNOWN = "KNOWN"
    DERIVED = "DERIVED"
    INCOMPLETE = "INCOMPLETE"
    STALE = "STALE"
    CONFLICTING = "CONFLICTING"
    UNAVAILABLE = "UNAVAILABLE"
    UNAUTHORIZED = "UNAUTHORIZED"
    POLICY_REQUIRED = "POLICY_REQUIRED"
    EXTERNAL_GATE = "EXTERNAL_GATE"


class AnswerAuthority(StrEnum):
    ACP_AUTHORITATIVE = "ACP_AUTHORITATIVE"
    SOURCE_BACKED = "SOURCE_BACKED"
    PARTIAL = "PARTIAL"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class LiaTemporalContext(LiaSchema):
    start_date: date
    end_date: date
    as_of: datetime
    timezone: str = Field(min_length=1, max_length=64)
    period_label: str = Field(min_length=1, max_length=100)
    comparison_start: date | None = None
    comparison_end: date | None = None
    comparison_label: str | None = Field(default=None, max_length=100)
    prior_start: date | None = None
    prior_end: date | None = None
    prior_label: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def validate_ranges(self) -> LiaTemporalContext:
        if self.end_date < self.start_date:
            raise ValueError("temporal end_date must not precede start_date")
        if (self.comparison_start is None) != (self.comparison_end is None):
            raise ValueError(
                "comparison_start and comparison_end must be supplied together"
            )
        if (
            self.comparison_start is not None
            and self.comparison_end is not None
            and self.comparison_end < self.comparison_start
        ):
            raise ValueError("comparison_end must not precede comparison_start")
        if (self.prior_start is None) != (self.prior_end is None):
            raise ValueError("prior_start and prior_end must be supplied together")
        return self


class LiaContext(LiaSchema):
    domain: str | None = Field(default=None, max_length=64)
    entity_id: UUID | None = None
    authorization_version: int | None = Field(default=None, ge=0)
    evidence_digest: str | None = Field(default=None, pattern="^[a-f0-9]{64}$")
    as_of: datetime | None = None
    topic_domains: tuple[str, ...] = Field(default=(), max_length=8)
    temporal: LiaTemporalContext | None = None


class LiaRequest(LiaSchema):
    question: str = Field(min_length=1, max_length=1000)
    conversation_id: UUID | None = None
    context: LiaContext | None = None


class EvidenceReference(LiaSchema):
    domain: str
    label: str
    authority: str
    observed_at: datetime
    freshness: str
    entity_id: UUID | None = None
    evidence_digest: str
    count: int | None = None
    state: str | None = None
    source_contract_version: str | None = None
    company_id: UUID | None = None
    branch_ids: tuple[UUID, ...] = ()
    authorization_version: int | None = None
    limitations: tuple[str, ...] = ()
    period_start: date | None = None
    period_end: date | None = None
    period_label: str | None = None
    timezone: str | None = None
    accounting_basis: str | None = None


class NavigationSuggestion(LiaSchema):
    label: str
    internal_path: str
    required_permission: str | None = None
    available: bool = True
    unavailable_reason: str | None = None
    entity_type: str | None = None
    entity_id: UUID | None = None
    action_category: str = "NAVIGATION"
    source_identity: str | None = None


class SpeechInterpretation(LiaSchema):
    """Transient, bounded speech understanding; never canonical business truth."""

    state: str = Field(pattern="^(CONFIDENT|CONFIRM_RECOMMENDED|UNCERTAIN)$")
    heard_text: str = Field(min_length=1, max_length=500)
    evidence_digest: str | None = Field(default=None, pattern="^[a-f0-9]{64}$")
    possible_meaning: str | None = Field(default=None, max_length=500)
    suggested_confirmation: str | None = Field(default=None, max_length=500)
    source_language: str = Field(min_length=2, max_length=32)
    interpreted_language: str | None = Field(default=None, max_length=32)
    translation_state: str = Field(
        default="NOT_TRANSLATED", pattern="^(NOT_TRANSLATED|TRANSLATED|UNAVAILABLE)$"
    )
    translation_provenance: str | None = Field(default=None, max_length=500)
    as_of: datetime
    confirmed: bool = False
    owning_fact_type: str = Field(min_length=1, max_length=100)
    context: dict[str, str] = Field(default_factory=dict)


class CustomerIntakeBranch(LiaSchema):
    """Canonical Customer match state consumed by CSR/Dispatch surfaces."""

    state: str = Field(pattern="^(EXISTING|NEW_CUSTOMER_INTAKE_REQUIRED|AMBIGUOUS)$")
    customer_id: UUID | None = None
    location_id: UUID | None = None
    missing_fields: tuple[str, ...] = ()
    next_questions: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()


class CsrDispatchCopilot(LiaSchema):
    """Server-owned, non-mutating CSR guidance contract."""

    contract_version: str = "lia.csr.dispatch.copilot.v1"
    suggested_question: str | None = None
    customer_branch: CustomerIntakeBranch
    speech_interpretations: tuple[SpeechInterpretation, ...] = ()
    clarification_required: bool = False
    translation_available: bool = False
    recommendation_state: str = Field(
        default="PROVISIONAL", pattern="^(CURRENT|PROVISIONAL|UNAVAILABLE|EXPIRED)$"
    )
    primary_ghost_slot: dict[str, object] | None = None
    alternates: tuple[dict[str, object], ...] = ()
    constrained_options: tuple[dict[str, object], ...] = ()
    action_metadata: tuple[NavigationSuggestion, ...] = ()
    limitations: tuple[str, ...] = ()
    mutation_authority: str = "none"


class ActionProposal(LiaSchema):
    proposal_id: UUID
    action: str
    state: str = "REVIEW_REQUIRED"
    required_permission: str | None = None
    expires_at: datetime
    digest: str


class LiaResponse(LiaSchema):
    request_id: UUID
    conversation_id: UUID
    classification: TruthClassification
    authority: AnswerAuthority
    answer: str
    response_mode: str = Field(pattern="^(BRIEF|NORMAL|DETAILED|EVIDENCE)$")
    evidence: tuple[EvidenceReference, ...] = ()
    limitations: tuple[str, ...] = ()
    navigation: tuple[NavigationSuggestion, ...] = ()
    csr_dispatch: CsrDispatchCopilot | None = None
    proposals: tuple[ActionProposal, ...] = ()
    completeness: str
    freshness: str
    provider: str
    provider_version: str
    policy_version: str
    evidence_digest: str
    authorization_version: int
    company_id: UUID
    branch_ids: tuple[UUID, ...] = ()
    subject_domain: str | None = None
    subject_id: UUID | None = None
    source_systems: tuple[str, ...] = ()
    missing_evidence: tuple[str, ...] = ()
    safe_next_action: str | None = None
    as_of: datetime
    generated_at: datetime
    temporal: LiaTemporalContext | None = None


class LiaReadiness(LiaSchema):
    state: str
    provider_state: str
    policy_state: str
    deterministic_capabilities: tuple[str, ...]
    generative_capabilities: tuple[str, ...]
    policy_version: str
    retention_state: str


class LiaFeedback(LiaSchema):
    request_id: UUID
    rating: str = Field(
        pattern="^(HELPFUL|NOT_HELPFUL|INCOMPLETE|STALE|CONFUSING|HUMAN_REVIEW)$"
    )
    reason_code: str | None = Field(default=None, max_length=64, pattern="^[A-Z0-9_]+$")


class LiaFeedbackReceipt(LiaSchema):
    feedback_id: UUID
    state: str = "EPHEMERAL_TELEMETRY_ACCEPTED"
