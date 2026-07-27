from datetime import datetime
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from .contracts import RepositoryAuthorizationState, RepositoryOperationType


class AuthorizationSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, from_attributes=True)


class RepositoryAuthorizationRequest(AuthorizationSchema):
    review_id: UUID
    review_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_type: RepositoryOperationType
    file_boundary: tuple[str, ...] = Field(min_length=1, max_length=200)
    expected_branch: str = Field(min_length=1, max_length=255)
    expected_base_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    expires_at: AwareDatetime
    idempotency_key: str = Field(min_length=3, max_length=200)


class RepositoryAuthorizationSummary(AuthorizationSchema):
    id: UUID
    command_id: UUID
    review_id: UUID
    operation_type: RepositoryOperationType
    expected_branch: str
    expected_base_commit: str
    state: RepositoryAuthorizationState
    version: int
    authorized_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    consumed_at: datetime | None


class RepositoryAuthorizationDetail(RepositoryAuthorizationSummary):
    capability_id: UUID
    execution_id: UUID
    result_id: UUID
    review_decision_id: UUID
    file_boundary: tuple[str, ...]
    review_digest: str
    authorization_digest: str
    authorization_eligible: bool


class RepositoryAuthorizationList(AuthorizationSchema):
    items: tuple[RepositoryAuthorizationSummary, ...]


class RepositoryAuthorizationValidationRequest(AuthorizationSchema):
    capability_id: UUID
    authorization_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    operation_type: RepositoryOperationType
    file_boundary: tuple[str, ...] = Field(min_length=1, max_length=200)
    expected_branch: str = Field(min_length=1, max_length=255)
    expected_base_commit: str = Field(pattern=r"^[0-9a-f]{40}$")


class RepositoryAuthorizationEligibilityResponse(AuthorizationSchema):
    eligible: bool
    reason_code: str | None
    review_id: UUID | None
    operation_type: RepositoryOperationType


class RepositoryAuthorizationRevokeRequest(AuthorizationSchema):
    expected_version: int = Field(ge=1)
    reason_code: str = Field(min_length=3, max_length=80)
