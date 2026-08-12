from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.engineering_control.records import (
    EngineeringApprovalState,
    EngineeringExecutionState,
)


class EngineeringApiSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, from_attributes=True)


class ExecutionBoundarySchema(EngineeringApiSchema):
    allowed_repository: str = Field(min_length=1, max_length=100)
    allowed_branch: str = Field(min_length=1, max_length=255)
    expected_head: str = Field(pattern=r"^[0-9a-f]{40}$")
    allowed_paths: tuple[str, ...] = Field(min_length=1, max_length=500)
    forbidden_paths: tuple[str, ...] = Field(min_length=1, max_length=100)
    permitted_operations: tuple[
        Literal[
            "inspect",
            "modify",
            "validate",
            "commit",
            "mechanical_reconcile",
            "push",
        ],
        ...,
    ]
    validation_requirements: tuple[str, ...] = Field(min_length=1, max_length=50)


class EngineeringCommandCreateRequest(EngineeringApiSchema):
    command_type: str = Field(min_length=3, max_length=80)
    owner_instruction: str = Field(min_length=1, max_length=12_000)
    repository_key: str = Field(min_length=1, max_length=100)
    expected_branch: str = Field(min_length=1, max_length=255)
    expected_head: str = Field(pattern=r"^[0-9a-f]{40}$")
    requested_code_changes: bool
    expires_at: AwareDatetime
    idempotency_key: str = Field(min_length=3, max_length=200)
    execution_boundary: ExecutionBoundarySchema


class EngineeringCommandApproveRequest(EngineeringApiSchema):
    expected_version: int = Field(ge=1)
    instruction_digest: str = Field(min_length=1, max_length=128)
    request_digest: str = Field(min_length=1, max_length=128)
    repository_key: str = Field(min_length=1, max_length=100)
    expected_branch: str = Field(min_length=1, max_length=255)
    expected_head: str = Field(pattern=r"^[0-9a-f]{40}$")
    requested_code_changes: bool
    execution_boundary_digest: str = Field(min_length=64, max_length=64)


EngineeringCancellationReason = Literal[
    "owner_requested", "scope_changed", "no_longer_needed"
]


class EngineeringCommandCancelRequest(EngineeringApiSchema):
    expected_version: int = Field(ge=1)
    reason_code: EngineeringCancellationReason


class EngineeringCommandSummaryResponse(EngineeringApiSchema):
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
    execution_boundary_digest: str


class EngineeringCommandDetailResponse(EngineeringCommandSummaryResponse):
    owner_instruction: str
    instruction_digest: str
    request_digest: str
    updated_at: datetime
    approved_at: datetime | None
    approved_by_user_id: UUID | None
    canceled_at: datetime | None
    canceled_by_user_id: UUID | None
    cancellation_reason_code: str | None
    execution_boundary: dict[str, object]


class EngineeringCommandPageResponse(EngineeringApiSchema):
    items: tuple[EngineeringCommandSummaryResponse, ...]
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=200)
    total_count: int = Field(ge=0)
    total_pages: int = Field(ge=0)


class EngineeringErrorResponse(EngineeringApiSchema):
    code: str
    message: str
