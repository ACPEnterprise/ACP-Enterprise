from uuid import UUID

from pydantic import BaseModel, ConfigDict


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AccessibleBranchResponse(StrictSchema):
    id: UUID
    code: str
    name: str
    is_primary: bool


class AccessibleCompanyResponse(StrictSchema):
    id: UUID
    code: str
    name: str
    membership_id: UUID
    default_branch_id: UUID | None
    has_all_branch_access: bool
    branches: list[AccessibleBranchResponse]


class EffectiveAuthorizationResponse(StrictSchema):
    company_id: UUID
    active_branch_id: UUID | None
    permission_codes: list[str]


class LaunchRoleResponse(StrictSchema):
    code: str
    purpose: str
    permission_codes: list[str]
    branch_access_required: bool


class PermissionExplanationResponse(StrictSchema):
    permission_code: str
    branch_id: UUID | None
    decision: str
    reasons: list[str]
