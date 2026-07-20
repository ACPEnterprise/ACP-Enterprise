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
