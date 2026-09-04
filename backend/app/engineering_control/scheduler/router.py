from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import EngineeringCommandPermission
from app.platform.permissions.dependencies import require_permission

from .delegation import (
    ActivateDelegation,
    SchedulerDelegationDenied,
    SchedulerDelegationService,
)

router = APIRouter(
    prefix="/api/v1/engineering-scheduler/delegations", tags=["Engineering Scheduler"]
)
Session = Annotated[AsyncSession, Depends(get_database_session)]
Context = Annotated[
    AuthorizationContext,
    Depends(require_permission(EngineeringCommandPermission.MANAGE)),
]
service = SchedulerDelegationService()


class ActivateRequest(BaseModel):
    authority_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    expires_at: datetime


class EndRequest(BaseModel):
    state: Literal["revoked", "paused_p0"] = "revoked"
    reason: str = Field(min_length=3, max_length=240)


class DelegationResponse(BaseModel):
    model_config = {"from_attributes": True}
    id: UUID
    queue_id: str
    queue_fingerprint: str
    authority_sha: str
    state: str
    activated_at: datetime
    expires_at: datetime
    ended_at: datetime | None


@router.post("/activate", response_model=DelegationResponse, status_code=201)
async def activate(data: ActivateRequest, context: Context, session: Session) -> object:
    try:
        return await service.activate(
            session,
            context=context,
            request=ActivateDelegation(**data.model_dump()),
            now=datetime.now(timezone.utc),
        )
    except SchedulerDelegationDenied as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/{delegation_id}/deactivate", response_model=DelegationResponse)
async def deactivate(
    delegation_id: UUID, data: EndRequest, context: Context, session: Session
) -> object:
    try:
        return await service.end(
            session,
            delegation_id=delegation_id,
            context=context,
            now=datetime.now(timezone.utc),
            state=data.state,
            reason=data.reason,
        )
    except SchedulerDelegationDenied as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
