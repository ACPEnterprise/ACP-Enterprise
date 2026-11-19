from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.demo.models import DemoEnvironment, DemoFeedback, DemoScenario
from app.demo.schemas import (
    DemoFeedbackCreate,
    DemoFeedbackResponse,
    DemoProvisionResponse,
    DemoScenarioResponse,
)
from app.demo.service import sales_demo_service
from app.platform.onboarding.service import OnboardingConflictError
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import AdministrationPermission, CustomerPermission
from app.platform.permissions.dependencies import require_permission

router = APIRouter(prefix="/api/v1/demo", tags=["Sales Demo"])
DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]
ProvisionContext = Annotated[
    AuthorizationContext,
    Depends(require_permission(AdministrationPermission.COMPANY_ADMINISTER)),
]
DemoContext = Annotated[
    AuthorizationContext, Depends(require_permission(CustomerPermission.MANAGE))
]


def _response(result) -> DemoProvisionResponse:
    return DemoProvisionResponse(
        environment_id=result.environment_id,
        company_id=result.company_id,
        branch_id=result.branch_id,
        generation=result.generation,
        action=result.action,
        counts=result.counts,
    )


@router.post("/provision", response_model=DemoProvisionResponse)
async def provision(
    context: ProvisionContext, session: DatabaseSession
) -> DemoProvisionResponse:
    try:
        result = await sales_demo_service.provision(session, context=context)
        await session.commit()
        return _response(result)
    except OnboardingConflictError as error:
        await session.rollback()
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/reset", response_model=DemoProvisionResponse)
async def reset(
    context: DemoContext, session: DatabaseSession
) -> DemoProvisionResponse:
    try:
        result = await sales_demo_service.provision(
            session, context=context, reset=True
        )
        await session.commit()
        return _response(result)
    except OnboardingConflictError as error:
        await session.rollback()
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/scenarios", response_model=list[DemoScenarioResponse])
async def scenarios(
    context: DemoContext, session: DatabaseSession
) -> list[DemoScenarioResponse]:
    environment = await session.scalar(
        select(DemoEnvironment).where(
            DemoEnvironment.owner_user_id == context.user.id,
            DemoEnvironment.active_company_id == context.company.id,
            DemoEnvironment.status == "ready",
        )
    )
    if environment is None:
        raise HTTPException(status_code=404, detail="Active Demo Company not found.")
    rows = (
        await session.scalars(
            select(DemoScenario)
            .where(
                DemoScenario.environment_id == environment.id,
                DemoScenario.company_id == context.company.id,
            )
            .order_by(DemoScenario.position)
        )
    ).all()
    return [
        DemoScenarioResponse(
            code=row.code,
            title=row.title,
            position=row.position,
            guided_steps=row.guided_steps,
            condition=row.condition,
            record_refs=row.record_refs,
        )
        for row in rows
    ]


@router.post("/feedback", response_model=DemoFeedbackResponse)
async def create_feedback(
    payload: DemoFeedbackCreate, context: DemoContext, session: DatabaseSession
) -> DemoFeedbackResponse:
    try:
        item = await sales_demo_service.feedback(
            session, context=context, **payload.model_dump()
        )
        await session.commit()
        return DemoFeedbackResponse.model_validate(item, from_attributes=True)
    except (OnboardingConflictError, ValueError) as error:
        await session.rollback()
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.get("/feedback", response_model=list[DemoFeedbackResponse])
async def list_feedback(
    context: DemoContext, session: DatabaseSession
) -> list[DemoFeedbackResponse]:
    rows = (
        await session.scalars(
            select(DemoFeedback)
            .where(DemoFeedback.company_id == context.company.id)
            .order_by(DemoFeedback.created_at.desc())
            .limit(200)
        )
    ).all()
    return [
        DemoFeedbackResponse.model_validate(row, from_attributes=True) for row in rows
    ]
