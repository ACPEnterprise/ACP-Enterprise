from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.dependencies import ResolvedAuthorization

from .models import MigrationSupportCaseModel
from .schemas import MigrationSupportCaseCreate, MigrationSupportCaseView

router = APIRouter(prefix="/api/v1/migration-support", tags=["Migration Support"])
Session = Annotated[AsyncSession, Depends(get_database_session)]


@router.post("/cases", response_model=MigrationSupportCaseView, status_code=status.HTTP_201_CREATED)
async def create_case(
    data: MigrationSupportCaseCreate,
    context: ResolvedAuthorization,
    session: Session,
) -> MigrationSupportCaseView:
    case = MigrationSupportCaseModel(
        company_id=context.company.id,
        created_by_user_id=context.user.id,
        onboarding_stage=data.onboarding_stage,
        source=data.source,
        domain=data.domain,
        message=data.message,
    )
    session.add(case)
    await session.flush()
    return MigrationSupportCaseView.model_validate(case, from_attributes=True)
