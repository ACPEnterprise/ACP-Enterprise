from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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
    internal_path: str = Field(min_length=1, max_length=500)

    @field_validator("internal_path")
    @classmethod
    def internal_path_is_bounded(cls, value: str) -> str:
        if (
            not value.startswith("/")
            or value.startswith("//")
            or "\\" in value
            or any(ord(character) < 32 for character in value)
            or ".." in value.split("?")[0].split("#")[0].split("/")
        ):
            raise ValueError("navigation destination must be a bounded internal path")
        return value


def evidence_set_digest(evidence: tuple[EvidenceReference, ...]) -> str:
    """Bind continuation identity to exact evidence and its authorization scope."""
    canonical = [
        {
            "domain": item.domain,
            "entity_id": str(item.entity_id) if item.entity_id is not None else None,
            "authority": item.authority,
            "evidence_digest": item.evidence_digest,
            "source_contract_version": item.source_contract_version,
            "company_id": str(item.company_id) if item.company_id is not None else None,
            "branch_ids": sorted(str(branch_id) for branch_id in item.branch_ids),
            "authorization_version": item.authorization_version,
            "period_start": item.period_start.isoformat()
            if item.period_start is not None
            else None,
            "period_end": item.period_end.isoformat()
            if item.period_end is not None
            else None,
            "timezone": item.timezone,
            "accounting_basis": item.accounting_basis,
        }
        for item in evidence
    ]
    canonical.sort(
        key=lambda item: (
            str(item["domain"]),
            str(item["entity_id"]),
            str(item["evidence_digest"]),
        )
    )
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


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
