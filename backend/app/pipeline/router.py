from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.pipeline.models import Lead
from app.pipeline.schemas import (
    ContactActivityCreate,
    LeadCreate,
    LeadHistoryResponse,
    LeadList,
    LeadResponse,
    LeadTransition,
    PipelineProjection,
)
from app.pipeline.service import (
    PipelineConflict,
    PipelineNotFound,
    attention_state,
    pipeline_service,
)
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import CustomerPermission
from app.platform.permissions.dependencies import require_permission

router = APIRouter(prefix="/api/v1/pipeline", tags=["Pipeline"])
DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]
ReadContext = Annotated[
    AuthorizationContext, Depends(require_permission(CustomerPermission.READ))
]
ManageContext = Annotated[
    AuthorizationContext, Depends(require_permission(CustomerPermission.MANAGE))
]


def response(lead: Lead) -> LeadResponse:
    result = LeadResponse.model_validate(lead)
    return result.model_copy(
        update={"attention_state": attention_state(lead, datetime.now(timezone.utc))}
    )


def pipeline_error(error: Exception) -> HTTPException:
    if isinstance(error, PipelineConflict):
        return HTTPException(status.HTTP_409_CONFLICT, str(error))
    return HTTPException(status.HTTP_404_NOT_FOUND, "Lead not found")


@router.get("", response_model=LeadList)
async def list_leads(
    context: ReadContext,
    session: DatabaseSession,
    view: Annotated[str, Query()] = "all",
    stage: Annotated[str | None, Query()] = None,
    assigned_user_id: Annotated[UUID | None, Query()] = None,
    source: Annotated[str | None, Query()] = None,
    service_category: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> LeadList:
    records, total = await pipeline_service.list(
        session,
        context=context,
        view=view,
        stage=stage,
        assigned_user_id=assigned_user_id,
        source=source,
        service_category=service_category,
        limit=limit,
        offset=offset,
    )
    return LeadList(
        items=tuple(response(record) for record in records),
        total=total,
        filters={
            "view": view,
            "stage": stage,
            "assigned_user_id": str(assigned_user_id) if assigned_user_id else None,
            "source": source,
            "service_category": service_category,
        },
    )


@router.post("", response_model=LeadResponse, status_code=status.HTTP_201_CREATED)
async def create_lead(
    payload: LeadCreate, context: ManageContext, session: DatabaseSession
) -> LeadResponse:
    try:
        return response(
            await pipeline_service.create(session, context=context, data=payload)
        )
    except PipelineNotFound as error:
        raise pipeline_error(error) from error


@router.get("/projection", response_model=PipelineProjection)
async def pipeline_projection(
    context: ReadContext, session: DatabaseSession
) -> PipelineProjection:
    return await pipeline_service.projection(session, context=context)


@router.get("/{lead_id}", response_model=LeadResponse)
async def get_lead(
    lead_id: UUID, context: ReadContext, session: DatabaseSession
) -> LeadResponse:
    try:
        return response(
            await pipeline_service.get(session, context=context, lead_id=lead_id)
        )
    except PipelineNotFound as error:
        raise pipeline_error(error) from error


@router.get("/{lead_id}/history", response_model=tuple[LeadHistoryResponse, ...])
async def lead_history(
    lead_id: UUID, context: ReadContext, session: DatabaseSession
) -> tuple[LeadHistoryResponse, ...]:
    try:
        records = await pipeline_service.history(
            session, context=context, lead_id=lead_id
        )
    except PipelineNotFound as error:
        raise pipeline_error(error) from error
    return tuple(LeadHistoryResponse.model_validate(record) for record in records)


@router.post("/{lead_id}/transition", response_model=LeadResponse)
async def transition_lead(
    lead_id: UUID,
    payload: LeadTransition,
    context: ManageContext,
    session: DatabaseSession,
) -> LeadResponse:
    try:
        lead = await pipeline_service.transition(
            session, context=context, lead_id=lead_id, data=payload
        )
    except (PipelineConflict, PipelineNotFound) as error:
        raise pipeline_error(error) from error
    return response(lead)


@router.post("/{lead_id}/contacts", response_model=LeadResponse)
async def record_contact(
    lead_id: UUID,
    payload: ContactActivityCreate,
    context: ManageContext,
    session: DatabaseSession,
) -> LeadResponse:
    try:
        lead = await pipeline_service.record_contact(
            session, context=context, lead_id=lead_id, data=payload
        )
    except PipelineNotFound as error:
        raise pipeline_error(error) from error
    return response(lead)
