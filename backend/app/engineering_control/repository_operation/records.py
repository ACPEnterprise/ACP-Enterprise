from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from .contracts import (
    RepositoryOperationEventType,
    RepositoryOperationState,
    RepositoryOperationType,
)


@dataclass(frozen=True)
class ExecuteRepositoryCommit:
    authorization_id: UUID
    capability_id: UUID
    authorization_digest: str
    commit_subject: str
    idempotency_key: str


@dataclass(frozen=True)
class RepositoryOperationRecord:
    id: UUID
    company_id: UUID
    authorization_id: UUID
    command_id: UUID
    execution_id: UUID
    review_decision_id: UUID
    requested_by_user_id: UUID
    operation_type: RepositoryOperationType
    commit_subject: str
    expected_branch: str
    expected_base_commit: str
    file_boundary: tuple[str, ...]
    boundary_digest: str
    idempotency_key: str
    state: RepositoryOperationState
    resulting_commit_sha: str | None
    failure_classification: str | None
    failure_detail: str | None
    version: int
    requested_at: datetime
    reserved_at: datetime | None
    execution_started_at: datetime | None
    succeeded_at: datetime | None
    failed_at: datetime | None
    reconciliation_required_at: datetime | None
    updated_at: datetime


@dataclass(frozen=True)
class RepositoryOperationEventRecord:
    id: UUID
    company_id: UUID
    operation_id: UUID
    actor_user_id: UUID
    event_type: RepositoryOperationEventType
    state: RepositoryOperationState
    version: int
    resulting_commit_sha: str | None
    failure_classification: str | None
    created_at: datetime
