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
from app.demo.enrichment import DEMO_COMPANY_ID, demo_enrichment_service
from app.demo.estimating import create_water_heater_drafts
from app.estimates.errors import EstimateError
from app.platform.permissions.codes import AdministrationPermission, CustomerPermission, EstimatePermission
from app.platform.onboarding.service import OnboardingConflictError
from app.platform.permissions.authorization import AuthorizationContext
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
EstimateDraftContext = Annotated[
    AuthorizationContext, Depends(require_permission(EstimatePermission.MANAGE))
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


@router.post("/enrich", response_model=dict[str, object])
async def enrich(
    context: DemoContext, session: DatabaseSession
) -> dict[str, object]:
    """Resume the bounded synthetic Sales Forward enrichment in place.

    This endpoint cannot create tenants or memberships and is hard-scoped to the
    preserved Demo company.  Replays are deterministic and idempotent.
    """
    if context.company.id != DEMO_COMPANY_ID:
        raise HTTPException(status_code=403, detail="Demo enrichment is tenant-scoped.")
    try:
        result = await demo_enrichment_service.enrich(
            session, company_id=context.company.id, actor_id=context.user.id
        )
        await session.commit()
        return {
            "company_id": str(result.company_id),
            "version": result.version,
            "created": result.created,
            "existing": result.existing,
            "synthetic": True,
        }
    except ValueError as error:
        await session.rollback()
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.post("/estimating/water-heater-drafts", response_model=dict[str, object])
async def water_heater_drafts(
    context: EstimateDraftContext, session: DatabaseSession
) -> dict[str, object]:
    """Create or reuse the three editable Demo Good/Better/Best drafts."""
    if context.company.id != DEMO_COMPANY_ID:
        raise HTTPException(status_code=403, detail="Demo estimating is tenant-scoped.")
    try:
        drafts = await create_water_heater_drafts(session, context=context)
        if drafts is None:
            await session.rollback()
            raise HTTPException(status_code=422, detail="Synthetic estimating evidence is not ready.")
        await session.commit()
        return {"company_id": str(context.company.id), "synthetic": True, "drafts": drafts}
    except EstimateError as error:
        await session.rollback()
        raise HTTPException(status_code=422, detail=str(error)) from error


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
