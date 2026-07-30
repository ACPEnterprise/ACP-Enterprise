from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.engineering_control.records import (
    EngineeringApprovalState,
    EngineeringExecutionState,
)
from app.engineering_control.review.contracts import (
    EngineeringReviewDecision,
    EngineeringReviewState,
)
from app.engineering_control.schemas import EngineeringCancellationReason


class MobileEngineeringSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, from_attributes=True)


class MobileCommandSummary(MobileEngineeringSchema):
    id: UUID
    ecid: str
    command_type: str
    repository_key: str
    expected_branch: str
    expected_head: str
    requested_code_changes: bool
    approval_state: EngineeringApprovalState
    execution_state: EngineeringExecutionState
    created_at: datetime
    expires_at: datetime
    version: int


class MobileCommandDetail(MobileCommandSummary):
    owner_instruction: str
    instruction_digest: str
    request_digest: str
    updated_at: datetime
    approved_at: datetime | None
    approved_by_user_id: UUID | None
    canceled_at: datetime | None
    canceled_by_user_id: UUID | None
    cancellation_reason_code: str | None
    result_reference: str | None
    can_approve: bool
    can_cancel: bool
    execution_connected: bool = False


class MobileCommandPage(MobileEngineeringSchema):
    items: tuple[MobileCommandSummary, ...]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total_count: int = Field(ge=0)
    total_pages: int = Field(ge=0)


class MobileEngineeringConnectivity(MobileEngineeringSchema):
    state: str
    session_id: UUID | None
    last_contact_at: datetime | None
    heartbeat_at: datetime | None


class MobileOwnerReviewSummary(MobileEngineeringSchema):
    id: UUID
    command_id: UUID
    execution_id: UUID
    ecid: str
    provider_identifier: str
    result_status: str
    result_disposition: str
    validation_summary: dict[str, object]
    file_boundary: tuple[str, ...]
    state: EngineeringReviewState
    created_at: datetime
    decision: EngineeringReviewDecision | None
    decided_at: datetime | None


class MobileOwnerReviewPage(MobileEngineeringSchema):
    items: tuple[MobileOwnerReviewSummary, ...]
    connectivity: MobileEngineeringConnectivity
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total_count: int = Field(ge=0)
    total_pages: int = Field(ge=0)


class MobileWorkstreamSummary(MobileEngineeringSchema):
    command_id: UUID
    ecid: str
    repository_key: str
    expected_branch: str
    expected_head: str
    approval_state: str
    lifecycle_state: str
    progress_summary: str
    owner_action_required: bool
    next_owner_action: str
    connection_state: str
    assigned_worker_id: UUID | None
    execution_id: UUID | None
    offer_or_lease_state: str | None
    heartbeat_at: datetime | None
    review_id: UUID | None
    review_state: str | None
    authorization_id: UUID | None
    authorization_status: str | None
    repository_operation_id: UUID | None
    repository_operation_status: str | None
    failure_classification: str | None
    resulting_commit_sha: str | None
    repository_clean: bool | None
    owner_attention_required: bool
    updated_at: datetime


class MobileWorkstreamPage(MobileEngineeringSchema):
    items: tuple[MobileWorkstreamSummary, ...]
    connectivity: MobileEngineeringConnectivity
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)
    total_count: int = Field(ge=0)
    total_pages: int = Field(ge=0)


class MobileApprovalRequest(MobileEngineeringSchema):
    expected_version: int = Field(ge=1)
    instruction_digest: str = Field(min_length=1, max_length=128)
    request_digest: str = Field(min_length=1, max_length=128)
    repository_key: str = Field(min_length=1, max_length=100)
    expected_branch: str = Field(min_length=1, max_length=255)
    expected_head: str = Field(pattern=r"^[0-9a-f]{40}$")
    requested_code_changes: bool


class MobileCancellationRequest(MobileEngineeringSchema):
    expected_version: int = Field(ge=1)
    reason_code: EngineeringCancellationReason
