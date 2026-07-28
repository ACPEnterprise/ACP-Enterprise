from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from .contracts import EngineeringReviewDecision, EngineeringReviewState


@dataclass(frozen=True)
class EngineeringReviewRecord:
    id: UUID
    company_id: UUID
    command_id: UUID
    execution_id: UUID
    composition_id: UUID | None
    attempt_id: UUID | None
    result_id: UUID | None
    provider_identifier: str
    instruction_digest: str
    request_digest: str
    composition_digest: str
    review_digest: str
    state: EngineeringReviewState
    version: int
    created_at: datetime
    updated_at: datetime
    decided_at: datetime | None
    controlled_result_id: UUID | None = None


@dataclass(frozen=True)
class EngineeringReviewDecisionRecord:
    id: UUID
    company_id: UUID
    review_id: UUID
    reviewer_user_id: UUID
    decision: EngineeringReviewDecision
    review_digest: str
    reason_code: str | None
    decided_at: datetime


@dataclass(frozen=True)
class EngineeringReviewPackage:
    review: EngineeringReviewRecord
    ecid: str
    command_type: str
    owner_instruction: str
    requested_code_changes: bool
    repository_key: str
    expected_branch: str
    expected_head: str
    result_status: str
    result_disposition: str
    evidence_summary: Mapping[str, object]
    validation_summary: Mapping[str, object]
    output_references: tuple[str, ...]
    failure_classification: str | None
    repository_mutated: bool
    result_received_at: datetime
    decision: EngineeringReviewDecisionRecord | None


@dataclass(frozen=True)
class DecideEngineeringReview:
    review_id: UUID
    expected_version: int
    review_digest: str
    decision: EngineeringReviewDecision
    reason_code: str | None = None
