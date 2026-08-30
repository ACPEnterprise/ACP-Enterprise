from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.platform.auth.dependencies import AuthenticatedIdentity
from app.platform.launch_controls import LAUNCH_ROLE_MATRIX
from app.platform.permissions.authorization import (
    AuthorizationContext,
    authorization_service,
)
from app.platform.permissions.codes import AdministrationPermission
from app.platform.permissions.dependencies import (
    ResolvedAuthorization,
    require_permission,
)
from app.platform.permissions.schemas import (
    AccessibleBranchResponse,
    AccessibleCompanyResponse,
    EffectiveAuthorizationResponse,
    LaunchRoleResponse,
    PermissionExplanationResponse,
)

router = APIRouter(prefix="/api/v1/authorization", tags=["Authorization"])
DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]


@router.get("/context", response_model=EffectiveAuthorizationResponse)
async def effective_authorization(
    context: ResolvedAuthorization,
) -> EffectiveAuthorizationResponse:
    return EffectiveAuthorizationResponse(
        company_id=context.company.id,
        active_branch_id=context.active_branch.id if context.active_branch else None,
        permission_codes=sorted(context.permission_codes),
    )


@router.get("/explain", response_model=PermissionExplanationResponse)
async def explain_effective_permission(
    permission_code: str,
    context: ResolvedAuthorization,
    branch_id: UUID | None = None,
) -> PermissionExplanationResponse:
    reasons: list[str] = []
    if permission_code not in context.permission_codes:
        reasons.append("DENIED_MISSING_PERMISSION")
    if branch_id is not None and not context.can_access_branch(branch_id):
        reasons.append("DENIED_BRANCH_SCOPE")
    if not reasons:
        reasons.append("ALLOWED_BY_ROLE")
    return PermissionExplanationResponse(
        permission_code=permission_code,
        branch_id=branch_id,
        decision="ALLOWED" if reasons == ["ALLOWED_BY_ROLE"] else "DENIED",
        reasons=reasons,
    )


RoleReader = Annotated[
    AuthorizationContext,
    Depends(require_permission(AdministrationPermission.ROLE_READ)),
]


@router.get("/launch-role-matrix", response_model=list[LaunchRoleResponse])
async def launch_role_matrix(_: RoleReader) -> list[LaunchRoleResponse]:
    return [
        LaunchRoleResponse(
            code=role.code.value,
            purpose=role.purpose,
            permission_codes=sorted(role.permission_codes),
            branch_access_required=role.branch_access_required,
        )
        for role in LAUNCH_ROLE_MATRIX
    ]


@router.get("/companies", response_model=list[AccessibleCompanyResponse])
async def list_accessible_companies(
    authenticated: AuthenticatedIdentity,
    session: DatabaseSession,
) -> list[AccessibleCompanyResponse]:
    access = await authorization_service.list_accessible_companies(
        session,
        authenticated=authenticated,
    )
    return [
        AccessibleCompanyResponse(
            id=item.company.id,
            code=item.company.code,
            name=item.company.name,
            membership_id=item.membership.id,
            default_branch_id=item.membership.default_branch_id,
            has_all_branch_access=item.membership.has_all_branch_access,
            branches=[
                AccessibleBranchResponse(
                    id=branch.id,
                    code=branch.code,
                    name=branch.name,
                    is_primary=branch.is_primary,
                )
                for branch in item.authorized_branches
            ],
        )
        for item in access
    ]
