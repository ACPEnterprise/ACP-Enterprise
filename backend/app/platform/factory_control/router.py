from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.platform.factory_control.models import FactoryControlEvent, FactoryLaneState
from app.platform.factory_control.roadmap import RoadmapError
from app.platform.factory_control.schemas import (
    FactoryEventIn,
    FactoryEventResponse,
    FactoryLaneDrilldownResponse,
    FactoryLaneResponse,
    FactoryMetricsResponse,
    FactoryOverviewResponse,
)
from app.platform.factory_control.service import (
    FactoryEventConflict,
    factory_control_service,
)
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.codes import LaunchPlatformPermission
from app.platform.permissions.dependencies import require_permission

router = APIRouter(prefix="/api/v1/platform/factory-control", tags=["Factory Control"])
DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]
CompanyAdministrator = Annotated[
    AuthorizationContext,
    Depends(require_permission(LaunchPlatformPermission.FACTORY_CONTROL_READ)),
]
ALLOWED_ROLES = frozenset({"OWNER", "ADMIN"})


def require_platform_owner_admin(context: CompanyAdministrator) -> AuthorizationContext:
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="PLATFORM_IDENTITY_HUMAN_GATE",
    )


OwnerAdmin = Annotated[AuthorizationContext, Depends(require_platform_owner_admin)]


def lane_response(lane: FactoryLaneState) -> FactoryLaneResponse:
    return FactoryLaneResponse(
        lane_code=lane.lane_code,
        milestone_code=lane.milestone_code,
        lifecycle_state=lane.lifecycle_state,
        queue_depth=lane.queue_depth,
        active_since=lane.active_since,
        last_handoff_at=lane.last_handoff_at,
        last_event_at=lane.last_event_at,
    )


@router.get("/overview", response_model=FactoryOverviewResponse)
async def overview(
    context: OwnerAdmin, session: DatabaseSession
) -> FactoryOverviewResponse:
    try:
        roadmap, _, lanes, metrics, generated = await factory_control_service.overview(
            session, company_id=context.company.id
        )
    except RoadmapError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Canonical factory roadmap is unavailable.",
        ) from error
    return FactoryOverviewResponse(
        roadmap_digest=roadmap.digest,
        roadmap_milestones=len(roadmap.milestones),
        metrics=FactoryMetricsResponse(**metrics),
        lanes=[lane_response(lane) for lane in lanes],
        generated_at=generated,
        p0_backlog=sum(
            item.launch_class == "P0" and item.lifecycle_status != "CLOSED"
            for item in roadmap.milestones
        ),
        p1_backlog=sum(
            item.launch_class == "P1" and item.lifecycle_status != "CLOSED"
            for item in roadmap.milestones
        ),
        human_gates=sum(
            item.owner_acceptance_status == "HUMAN_GATE" for item in roadmap.milestones
        ),
        provider_gates=sum(
            item.owner_acceptance_status == "PROVIDER_GATE"
            for item in roadmap.milestones
        ),
        owner_actions=[
            {
                "milestone_code": item.code,
                "priority": item.launch_class,
                "action": item.next_admissible_action,
                "why_blocked": item.owner_acceptance_status,
                "workflow": item.title,
                "estimated_owner_minutes": None,
                "resume_action": item.next_admissible_action,
                "gate_type": item.owner_acceptance_status,
            }
            for item in roadmap.milestones
            if item.owner_acceptance_status
            in {"HUMAN_GATE", "OWNER_ACCEPTANCE_REQUIRED", "PROVIDER_GATE"}
            and item.next_admissible_action
        ],
    )


@router.get("/lanes/{lane_code}", response_model=FactoryLaneDrilldownResponse)
async def lane_drilldown(
    lane_code: str,
    context: OwnerAdmin,
    session: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> FactoryLaneDrilldownResponse:
    lane = await session.scalar(
        select(FactoryLaneState).where(
            FactoryLaneState.company_id == context.company.id,
            FactoryLaneState.lane_code == lane_code,
        )
    )
    if lane is None:
        raise HTTPException(status_code=404, detail="Factory lane was not found.")
    events = list(
        (
            await session.scalars(
                select(FactoryControlEvent)
                .where(
                    FactoryControlEvent.company_id == context.company.id,
                    FactoryControlEvent.lane_code == lane_code,
                )
                .order_by(
                    FactoryControlEvent.occurred_at.desc(),
                    FactoryControlEvent.id.desc(),
                )
                .limit(limit)
            )
        ).all()
    )
    return FactoryLaneDrilldownResponse(
        lane=lane_response(lane),
        events=[
            {
                "id": str(event.id),
                "milestone_code": event.milestone_code,
                "event_type": event.event_type,
                "lifecycle_state": event.lifecycle_state,
                "occurred_at": event.occurred_at.isoformat(),
                "details": event.details,
            }
            for event in events
        ],
    )


@router.post("/internal/events", response_model=FactoryEventResponse, status_code=202)
async def ingest_event(
    data: FactoryEventIn, context: OwnerAdmin, session: DatabaseSession
) -> FactoryEventResponse:
    try:
        async with session.begin():
            event, duplicate = await factory_control_service.ingest(
                session,
                company_id=context.company.id,
                actor_user_id=context.user.id,
                data=data,
            )
    except FactoryEventConflict as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Factory event replay conflicts with accepted evidence.",
        ) from error
    return FactoryEventResponse(id=str(event.id), duplicate=duplicate)


@router.post("/internal/snapshots", status_code=201)
async def capture_snapshot(
    snapshot_key: Annotated[str, Query(min_length=1, max_length=200)],
    context: OwnerAdmin,
    session: DatabaseSession,
) -> dict[str, str]:
    try:
        async with session.begin():
            snapshot, duplicate = await factory_control_service.capture_snapshot(
                session,
                company_id=context.company.id,
                actor_user_id=context.user.id,
                snapshot_key=snapshot_key,
            )
    except RoadmapError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Canonical factory roadmap is unavailable.",
        ) from error
    return {
        "id": str(snapshot.id),
        "snapshot_key": snapshot.snapshot_key,
        "duplicate": str(duplicate).lower(),
    }
