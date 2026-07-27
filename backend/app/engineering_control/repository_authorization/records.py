from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from .contracts import (
    RepositoryAuthorizationEventType,
    RepositoryAuthorizationState,
    RepositoryOperationType,
)


@dataclass(frozen=True)
class RequestRepositoryAuthorization:
    review_id: UUID
    review_digest: str
    operation_type: RepositoryOperationType
    file_boundary: tuple[str, ...]
    expected_branch: str
    expected_base_commit: str
    expires_at: datetime
    idempotency_key: str


@dataclass(frozen=True)
class RepositoryAuthorizationRecord:
    id: UUID
    capability_id: UUID
    company_id: UUID
    command_id: UUID
    execution_id: UUID
    result_id: UUID
    review_id: UUID
    review_decision_id: UUID
    authorized_by_user_id: UUID
    operation_type: RepositoryOperationType
    file_boundary: tuple[str, ...]
    expected_branch: str
    expected_base_commit: str
    review_digest: str
    authorization_digest: str
    idempotency_key: str
    state: RepositoryAuthorizationState
    version: int
    authorized_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    consumed_at: datetime | None
    updated_at: datetime


@dataclass(frozen=True)
class RepositoryAuthorizationEventRecord:
    id: UUID
    company_id: UUID
    authorization_id: UUID
    actor_user_id: UUID
    event_type: RepositoryAuthorizationEventType
    state: RepositoryAuthorizationState
    version: int
    reason_code: str | None
    created_at: datetime


@dataclass(frozen=True)
class RepositoryAuthorizationEligibility:
    eligible: bool
    reason_code: str | None
    review_id: UUID
    operation_type: RepositoryOperationType


@dataclass(frozen=True)
class ValidateRepositoryAuthorization:
    authorization_id: UUID
    capability_id: UUID
    authorization_digest: str
    operation_type: RepositoryOperationType
    file_boundary: tuple[str, ...]
    expected_branch: str
    expected_base_commit: str


@dataclass(frozen=True)
class RevokeRepositoryAuthorization:
    authorization_id: UUID
    expected_version: int
    reason_code: str
