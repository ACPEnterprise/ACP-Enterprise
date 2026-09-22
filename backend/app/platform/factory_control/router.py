from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_database_session
from app.platform.factory_control.authority import (
    FactoryControllerContext,
    PlatformReader,
    require_factory_controller_permission,
)
from app.platform.factory_control.models import (
    FactoryControlEvent,
    FactoryControlSnapshot,
    FactoryLaneState,
)
from app.platform.factory_control.roadmap import RoadmapError, RoadmapMilestone
from app.platform.factory_control.schemas import (
    FactoryEventIn,
    FactoryEventResponse,
    FactoryLaneDrilldownResponse,
    FactoryLaneResponse,
    FactoryLiveSyncIn,
    FactoryMetricsResponse,
    FactoryOverviewResponse,
    FactorySnapshotIn,
    OperationalAcceptanceSurfaceResponse,
)
from app.platform.factory_control.service import (
    FactoryEventConflict,
    FactoryEvidenceError,
    factory_control_service,
)
from app.platform.permissions.codes import LaunchPlatformPermission

router = APIRouter(prefix="/api/v1/platform/factory-control", tags=["Factory Control"])
DatabaseSession = Annotated[AsyncSession, Depends(get_database_session)]
EventController = Annotated[
    FactoryControllerContext,
    Depends(
        require_factory_controller_permission(
            LaunchPlatformPermission.FACTORY_CONTROL_INGEST
        )
    ),
]
SnapshotController = Annotated[
    FactoryControllerContext,
    Depends(
        require_factory_controller_permission(
            LaunchPlatformPermission.FACTORY_CONTROL_SNAPSHOT
        )
    ),
]


def lane_response(
    lane: FactoryLaneState, *, now: datetime | None = None
) -> FactoryLaneResponse:
    observed_at = now or datetime.now(timezone.utc)
    idle_seconds = (
        max(0.0, (observed_at - lane.eligible_idle_since).total_seconds())
        if lane.eligible_idle_since is not None
        and lane.lifecycle_state == "ELIGIBLE_IDLE"
        else None
    )
    violations: list[str] = []
    if idle_seconds is not None and idle_seconds > 600:
        violations.append("ELIGIBLE_IDLE_REFILL_OVER_10_MINUTES")
    if lane.lifecycle_state == "WAITING_INTEGRATION" and lane.last_handoff_at:
        wait_seconds = max(0.0, (observed_at - lane.last_handoff_at).total_seconds())
        limit = 1200 if lane.controlling_enterprise == "OM1E" else 900
        if wait_seconds > limit:
            violations.append(
                "RELEASE_PICKUP_OVER_20_MINUTES"
                if limit == 1200
                else "DOMAIN_PICKUP_OVER_15_MINUTES"
            )
    sla_state = cast(
        Literal["HEALTHY", "VIOLATED", "NOT_APPLICABLE"],
        "VIOLATED"
        if violations
        else "HEALTHY"
        if lane.lifecycle_state
        in {"ACTIVE", "ASSIGNED", "ELIGIBLE_IDLE", "WAITING_INTEGRATION"}
        else "NOT_APPLICABLE",
    )
    return FactoryLaneResponse(
        lane_code=lane.lane_code,
        milestone_code=lane.milestone_code,
        lifecycle_state=lane.lifecycle_state,
        queue_depth=lane.queue_depth,
        machine=lane.machine,
        current_assignment=lane.current_assignment,
        next_queued_item=lane.next_queued_item,
        controlling_enterprise=lane.controlling_enterprise,
        self_refill_health=lane.self_refill_health,
        idle_duration_seconds=idle_seconds,
        sla_state=sla_state,
        sla_violations=violations,
        active_since=lane.active_since,
        last_handoff_at=lane.last_handoff_at,
        last_event_at=lane.last_event_at,
    )


def _durable_owner_actions(
    roadmap_actions: list[dict], events: list[FactoryControlEvent]
) -> list[dict]:
    queue = {
        str(item["milestone_code"]): item
        for item in roadmap_actions
        if item.get("milestone_code")
    }
    for event in sorted(events, key=lambda row: (row.occurred_at, row.id)):
        gate_id = str(event.details.get("gate_id", ""))
        if not gate_id:
            continue
        if event.event_type == "gate_closed":
            queue.pop(gate_id, None)
            continue
        if event.event_type != "gate_opened":
            continue
        gate_type = event.details.get("gate_type")
        if gate_type not in {
            "OWNER_ACCEPTANCE_REQUIRED",
            "HUMAN_GATE",
            "PROVIDER_GATE",
        }:
            continue
        if event.details.get("engineering_prerequisites_resolved") is not True:
            continue
        minutes = event.details.get("estimated_owner_minutes")
        if not isinstance(minutes, int) or isinstance(minutes, bool) or minutes < 1:
            continue
        queue[gate_id] = {
            "milestone_code": event.milestone_code or gate_id,
            "priority": event.details.get("priority", "P1"),
            "action": event.details.get("action", "Human action required."),
            "why_blocked": event.details.get("why_blocked", gate_type),
            "workflow": event.details.get("workflow", event.lane_code),
            "estimated_owner_minutes": minutes,
            "resume_action": event.details.get("resume_action", "Resume engineering."),
            "gate_type": gate_type,
        }
    return sorted(
        queue.values(),
        key=lambda item: (str(item["priority"]), str(item["milestone_code"])),
    )


def _engineering_prerequisites_ready(
    item: RoadmapMilestone, milestones: dict[str, RoadmapMilestone]
) -> bool:
    ready = {"ENGINEERING_READY", "INTEGRATED", "DEPLOYED_BETA", "CLOSED"}
    if item.engineering_status not in ready:
        return False
    return all(
        dependency in milestones and milestones[dependency].engineering_status in ready
        for dependency in item.prerequisites
    )


def _roadmap_owner_action(
    item: RoadmapMilestone, milestones: dict[str, RoadmapMilestone]
) -> dict | None:
    gate_type = item.owner_acceptance_status
    if (
        gate_type
        not in {
            "HUMAN_GATE",
            "OWNER_ACCEPTANCE_REQUIRED",
            "PROVIDER_GATE",
        }
        or not item.human_provider_gates
    ):
        return None
    if not _engineering_prerequisites_ready(item, milestones):
        return None
    if gate_type == "OWNER_ACCEPTANCE_REQUIRED" and item.beta_deployment_status not in {
        "DEPLOYED_BETA",
        "CLOSED",
    }:
        return None
    expected_minutes = {
        "OWNER_ACCEPTANCE_REQUIRED": 10,
        "HUMAN_GATE": 15,
        "PROVIDER_GATE": 20,
    }[gate_type]
    return {
        "milestone_code": item.code,
        "priority": item.launch_class,
        "action": "; ".join(item.human_provider_gates),
        "why_blocked": (
            "Engineering prerequisites are complete; only the named authorized "
            "human or provider can supply this decision or physical evidence."
        ),
        "workflow": item.title,
        "estimated_owner_minutes": expected_minutes,
        "resume_action": item.next_admissible_action,
        "gate_type": gate_type,
    }


def _backlog_item(item: RoadmapMilestone) -> dict[str, object]:
    return {
        "milestone_code": item.code,
        "title": item.title,
        "priority": item.launch_class,
        "lifecycle_status": item.lifecycle_status,
        "engineering_status": item.engineering_status,
        "owner_acceptance_status": item.owner_acceptance_status,
        "next_admissible_action": item.next_admissible_action,
    }


@router.get("/overview", response_model=FactoryOverviewResponse)
async def overview(
    _: PlatformReader, session: DatabaseSession
) -> FactoryOverviewResponse:
    try:
        (
            roadmap,
            events,
            lanes,
            metrics,
            generated,
        ) = await factory_control_service.overview(session)
    except RoadmapError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Canonical factory roadmap is unavailable.",
        ) from error
    milestones = {item.code: item for item in roadmap.milestones}
    latest_snapshot_at = await session.scalar(
        select(func.max(FactoryControlSnapshot.captured_at))
    )
    last_controller_ingestion_at = await session.scalar(
        select(func.max(FactoryControlEvent.received_at)).where(
            FactoryControlEvent.event_type == "controller_sync"
        )
    )
    freshness = cast(
        Literal["LIVE", "STALE", "NOT_YET_MEASURED"],
        "NOT_YET_MEASURED"
        if last_controller_ingestion_at is None or latest_snapshot_at is None
        else "LIVE"
        if generated - last_controller_ingestion_at <= timedelta(minutes=15)
        else "STALE",
    )
    active_p0 = [
        _backlog_item(item)
        for item in roadmap.milestones
        if item.launch_class == "P0" and item.lifecycle_status != "CLOSED"
    ]
    active_p1 = [
        _backlog_item(item)
        for item in roadmap.milestones
        if item.launch_class == "P1" and item.lifecycle_status != "CLOSED"
    ]
    engineering_complete = {"ENGINEERING_READY", "INTEGRATED", "DEPLOYED_BETA", "CLOSED"}
    bottlenecks = [
        item
        for item in (*active_p0, *active_p1)
        if item["engineering_status"] not in engineering_complete
        and item["lifecycle_status"]
        not in {"HUMAN_GATE", "PROVIDER_GATE", "OWNER_ACCEPTANCE_REQUIRED"}
    ]
    priority_rank = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    acceptance_defects = sorted(
        (
            item
            for item in roadmap.operational_acceptance
            if item.status == "DEFECT"
        ),
        key=lambda item: (priority_rank[item.priority], item.acceptance_id),
    )
    current_bottleneck: dict[str, object] | None
    if acceptance_defects:
        physical = acceptance_defects[0]
        current_bottleneck = {
            "milestone_code": physical.milestone_code,
            "title": f"Real operational acceptance: {physical.surface}",
            "priority": physical.priority,
            "lifecycle_status": physical.status,
            "engineering_status": "ACTIVE",
            "owner_acceptance_status": "BLOCKED",
            "next_admissible_action": physical.blocker,
        }
    else:
        current_bottleneck = next(iter(bottlenecks or active_p0 or active_p1), None)
    roadmap_actions = [
        action
        for item in roadmap.milestones
        if (action := _roadmap_owner_action(item, milestones)) is not None
    ]
    return FactoryOverviewResponse(
        roadmap_digest=roadmap.digest,
        roadmap_milestones=len(roadmap.milestones),
        metrics=FactoryMetricsResponse(**metrics),
        lanes=[lane_response(lane, now=generated) for lane in lanes],
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
        owner_actions=_durable_owner_actions(roadmap_actions, events),
        lifecycle_counts=dict(
            sorted(
                Counter(str(item.lifecycle_status) for item in roadmap.milestones).items()
            )
        ),
        active_p0=active_p0,
        active_p1=active_p1,
        current_bottleneck=current_bottleneck,
        recent_movements=[
            {
                "id": str(event.id),
                "event_type": event.event_type,
                "milestone_code": event.milestone_code,
                "lane_code": event.lane_code,
                "occurred_at": event.occurred_at.isoformat(),
            }
            for event in sorted(
                events,
                key=lambda row: (row.occurred_at, row.idempotency_key),
                reverse=True,
            )[:20]
        ],
        latest_snapshot_at=latest_snapshot_at,
        last_controller_ingestion_at=last_controller_ingestion_at,
        telemetry_freshness=freshness,
        real_operational_acceptance=[
            OperationalAcceptanceSurfaceResponse(
                acceptance_id=item.acceptance_id,
                surface=item.surface,
                milestone_code=item.milestone_code,
                owner_task=item.owner_task,
                real_data_required=item.real_data_required,
                current_result=item.current_result,
                blocker=item.blocker,
                owning_domain=item.owning_domain,
                priority=item.priority,
                status=item.status,
                beta_operable=item.beta_operable,
                owner_accepted=item.owner_accepted,
                evidence=list(item.evidence),
            )
            for item in roadmap.operational_acceptance
        ],
    )


@router.get("/lanes/{lane_code}", response_model=FactoryLaneDrilldownResponse)
async def lane_drilldown(
    lane_code: str,
    _: PlatformReader,
    session: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> FactoryLaneDrilldownResponse:
    lane = await session.scalar(
        select(FactoryLaneState).where(FactoryLaneState.lane_code == lane_code)
    )
    if lane is None:
        raise HTTPException(status_code=404, detail="Factory lane was not found.")
    events = list(
        (
            await session.scalars(
                select(FactoryControlEvent)
                .where(FactoryControlEvent.lane_code == lane_code)
                .order_by(
                    FactoryControlEvent.occurred_at.desc(),
                    FactoryControlEvent.idempotency_key.desc(),
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
    data: FactoryEventIn, context: EventController, session: DatabaseSession
) -> FactoryEventResponse:
    try:
        async with session.begin():
            event, duplicate = await factory_control_service.ingest(
                session,
                controller_worker_identity_id=context.worker_identity_id,
                controller_tenant_company_id=context.tenant_company_id,
                data=data,
            )
    except FactoryEventConflict as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Factory event replay conflicts with accepted evidence.",
        ) from error
    except FactoryEvidenceError as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Factory event evidence is outside controller authority.",
        ) from error
    return FactoryEventResponse(id=str(event.id), duplicate=duplicate)


@router.post("/internal/sync", response_model=FactoryEventResponse, status_code=202)
async def sync_controller(
    context: EventController, session: DatabaseSession
) -> FactoryEventResponse:
    try:
        async with session.begin():
            event, duplicate = await factory_control_service.sync_controller_lane(
                session,
                controller_worker_identity_id=context.worker_identity_id,
                controller_worker_id=context.worker_id,
                controller_tenant_company_id=context.tenant_company_id,
            )
    except FactoryEvidenceError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Development Factory evidence is unavailable.",
        ) from error
    return FactoryEventResponse(id=str(event.id), duplicate=duplicate)


@router.post("/internal/live-sync", status_code=202)
async def live_sync_controllers(
    data: FactoryLiveSyncIn, context: EventController, session: DatabaseSession
) -> dict[str, list[dict[str, str | bool]]]:
    try:
        async with session.begin():
            results = await factory_control_service.sync_authoritative_lanes(
                session,
                controller_worker_identity_id=context.worker_identity_id,
                controller_tenant_company_id=context.tenant_company_id,
                targets=data.targets,
                observed_at=data.observed_at,
            )
    except FactoryEvidenceError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Development Factory evidence is unavailable.",
        ) from error
    return {
        "events": [
            {"id": str(event.id), "duplicate": duplicate}
            for event, duplicate in results
        ]
    }


@router.post("/internal/snapshots", status_code=201)
async def capture_snapshot(
    data: FactorySnapshotIn,
    context: SnapshotController,
    session: DatabaseSession,
) -> dict[str, str]:
    try:
        async with session.begin():
            snapshot, duplicate = await factory_control_service.capture_snapshot(
                session,
                controller_worker_identity_id=context.worker_identity_id,
                controller_tenant_company_id=context.tenant_company_id,
                snapshot_key=data.snapshot_key,
                captured_at=data.captured_at,
                tenant_company_id=data.tenant_company_id,
                protected_sha=data.protected_sha,
                beta_sha=data.beta_sha,
            )
    except FactoryEventConflict as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Factory snapshot replay conflicts with accepted evidence.",
        ) from error
    except FactoryEvidenceError as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Factory snapshot evidence is outside controller authority.",
        ) from error
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
