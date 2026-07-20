from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.platform.auth.dependencies import AuthenticatedIdentity
from app.platform.permissions.authorization import authorization_service
from app.platform.permissions.schemas import (
    AccessibleBranchResponse,
    AccessibleCompanyResponse,
)


router = APIRouter(prefix="/api/v1/authorization", tags=["Authorization"])
DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]


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
