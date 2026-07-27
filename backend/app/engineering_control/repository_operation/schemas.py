from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .contracts import RepositoryOperationState, RepositoryOperationType


class OperationSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, from_attributes=True)


class ExecuteRepositoryCommitRequest(OperationSchema):
    authorization_id: UUID
    capability_id: UUID
    authorization_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    commit_subject: str = Field(min_length=1, max_length=120)
    idempotency_key: str = Field(min_length=3, max_length=200)


class RepositoryOperationSummary(OperationSchema):
    id: UUID
    authorization_id: UUID
    command_id: UUID
    operation_type: RepositoryOperationType
    commit_subject: str
    expected_branch: str
    expected_base_commit: str
    state: RepositoryOperationState
    resulting_commit_sha: str | None
    failure_classification: str | None
    version: int
    requested_at: datetime
    reserved_at: datetime | None
    execution_started_at: datetime | None
    succeeded_at: datetime | None
    failed_at: datetime | None
    reconciliation_required_at: datetime | None


class RepositoryOperationDetail(RepositoryOperationSummary):
    execution_id: UUID
    review_decision_id: UUID
    file_boundary: tuple[str, ...]
    boundary_digest: str
    failure_detail: str | None
    owner_attention_required: bool


class RepositoryOperationList(OperationSchema):
    items: tuple[RepositoryOperationSummary, ...]


class RepositoryOperationReadinessResponse(OperationSchema):
    eligible: bool
    reason_code: str | None
    inspected_at: datetime
