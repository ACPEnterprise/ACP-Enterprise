from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictAdminSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MembershipCreateRequest(StrictAdminSchema):
    user_id: UUID
    status: str = "invited"
    default_branch_id: UUID | None = None
    has_all_branch_access: bool = False


class StatusUpdateRequest(StrictAdminSchema):
    status: str = Field(min_length=1, max_length=20)


class AllBranchAccessRequest(StrictAdminSchema):
    enabled: bool


class RoleCreateRequest(StrictAdminSchema):
    code: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.strip().upper()


class MembershipResponse(StrictAdminSchema):
    id: UUID
    user_id: UUID
    company_id: UUID
    status: str
    default_branch_id: UUID | None
    has_all_branch_access: bool
    invited_at: datetime | None
    accepted_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class RoleResponse(StrictAdminSchema):
    id: UUID
    company_id: UUID
    code: str
    name: str
    description: str | None
    status: str
    is_system: bool
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class PermissionCatalogResponse(StrictAdminSchema):
    id: UUID
    code: str
    name: str
    description: str | None
    scope: str
    active: bool
    assignable: bool
    assigned: bool
    reconciliation_required: bool = False
    category: str
    access_nature: str
    own_data: bool
    high_impact: bool


class AssignmentResponse(StrictAdminSchema):
    id: UUID
    created: bool = True


class MutationResponse(StrictAdminSchema):
    changed: bool


class CanonicalRoleSyncApplyRequest(StrictAdminSchema):
    expected_plan_digest: str = Field(min_length=64, max_length=64)


class CanonicalRoleSyncItemResponse(StrictAdminSchema):
    code: str
    classification: str
    missing_permissions: tuple[str, ...]
    metadata_update_required: bool


class CanonicalRoleSyncPlanResponse(StrictAdminSchema):
    company_id: UUID
    plan_digest: str
    safe_to_apply: bool
    items: tuple[CanonicalRoleSyncItemResponse, ...]


class CanonicalRoleSyncResultResponse(StrictAdminSchema):
    plan: CanonicalRoleSyncPlanResponse
    roles_created: tuple[str, ...]
    permissions_added: tuple[str, ...]
    metadata_restored: tuple[str, ...]
    authorization_users_advanced: int
