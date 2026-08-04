from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .contracts import EngineeringReviewDecision, EngineeringReviewState


class ReviewSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, from_attributes=True)


class EngineeringReviewSummary(ReviewSchema):
    id: UUID
    command_id: UUID
    execution_id: UUID
    provider_identifier: str
    review_digest: str
    state: EngineeringReviewState
    version: int
    created_at: datetime
    updated_at: datetime
    decided_at: datetime | None


class EngineeringReviewDecisionResponse(ReviewSchema):
    id: UUID
    reviewer_user_id: UUID
    decision: EngineeringReviewDecision
    review_digest: str
    reason_code: str | None
    decided_at: datetime


class EngineeringReviewPackageResponse(ReviewSchema):
    review: EngineeringReviewSummary
    ecid: str
    command_type: str
    owner_instruction: str
    requested_code_changes: bool
    repository_key: str
    expected_branch: str
    expected_head: str
    result_status: str
    result_disposition: str
    evidence_summary: dict[str, object]
    validation_summary: dict[str, object]
    output_references: tuple[str, ...]
    failure_classification: str | None
    repository_mutated: bool
    result_received_at: datetime
    decision: EngineeringReviewDecisionResponse | None


class EngineeringReviewDecisionRequest(ReviewSchema):
    expected_version: int = Field(ge=1)
    review_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision: EngineeringReviewDecision
    reason_code: str | None = Field(default=None, min_length=3, max_length=80)


class EngineeringReviewListResponse(ReviewSchema):
    items: tuple[EngineeringReviewSummary, ...]
