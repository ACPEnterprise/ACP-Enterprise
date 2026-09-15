from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


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


class LiaContext(LiaSchema):
    domain: str | None = Field(default=None, max_length=64)
    entity_id: UUID | None = None
    authorization_version: int | None = Field(default=None, ge=0)
    evidence_digest: str | None = Field(default=None, pattern="^[a-f0-9]{64}$")
    as_of: datetime | None = None
    topic_domains: tuple[str, ...] = Field(default=(), max_length=8)


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


class NavigationSuggestion(LiaSchema):
    label: str
    internal_path: str


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
    evidence: tuple[EvidenceReference, ...] = ()
    limitations: tuple[str, ...] = ()
    navigation: tuple[NavigationSuggestion, ...] = ()
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
