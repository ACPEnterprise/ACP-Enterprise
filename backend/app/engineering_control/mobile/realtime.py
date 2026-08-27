import asyncio
import json
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from uuid import UUID

import asyncpg  # type: ignore[import-untyped]
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.database.session import AsyncSessionFactory
from app.engineering_control.mobile.roadmaps import (
    EngineeringMilestone,
    EngineeringMilestoneEvent,
)
from app.engineering_control.review.models import EngineeringExecutionReview
from app.engineering_control.workstream_runtime import (
    EngineeringWorkstreamEvent,
    EngineeringWorkstreamRuntime,
)
from app.engineering_execution.controlled.models import ControlledExecutionResultModel
from app.engineering_execution.models import EngineeringExecution


class InvalidResumeToken(ValueError):
    pass


def _notification(event: EngineeringWorkstreamEvent) -> str | None:
    if event.runtime_state == "waiting_for_owner":
        return "waiting_for_owner"
    if event.runtime_state == "recovering" and event.reason_code in {
        "reconciliation_required",
        "ambiguous_interrupted_execution",
    }:
        return "manual_recovery"
    return None


def _notifications(event: EngineeringWorkstreamEvent) -> tuple[str, ...]:
    primary = _notification(event)
    return (primary,) if primary else ()


async def validate_resume_token(
    db: AsyncSession, company_id: UUID, token: UUID | None
) -> None:
    if token is None:
        return
    found = await db.scalar(
        select(EngineeringWorkstreamEvent.id).where(
            EngineeringWorkstreamEvent.company_id == company_id,
            EngineeringWorkstreamEvent.id == token,
        )
    )
    milestone_found = None
    if found is None:
        milestone_found = await db.scalar(
            select(EngineeringMilestoneEvent.id).where(
                EngineeringMilestoneEvent.company_id == company_id,
                EngineeringMilestoneEvent.id == token,
            )
        )
    if found is None and milestone_found is None:
        raise InvalidResumeToken(
            "The realtime resume token is unknown in this Company scope."
        )


async def _events_after(
    company_id: UUID, token: UUID | None
) -> tuple[dict[str, object], ...]:
    async with AsyncSessionFactory() as db:
        boundary = None
        milestone_boundary = None
        if token is not None:
            boundary = await db.scalar(
                select(EngineeringWorkstreamEvent).where(
                    EngineeringWorkstreamEvent.company_id == company_id,
                    EngineeringWorkstreamEvent.id == token,
                )
            )
            if boundary is None:
                milestone_boundary = await db.scalar(
                    select(EngineeringMilestoneEvent).where(
                        EngineeringMilestoneEvent.company_id == company_id,
                        EngineeringMilestoneEvent.id == token,
                    )
                )
        statement = select(EngineeringWorkstreamEvent).where(
            EngineeringWorkstreamEvent.company_id == company_id
        )
        if boundary is not None:
            statement = statement.where(
                EngineeringWorkstreamEvent.sequence_id > boundary.sequence_id
            )
        elif milestone_boundary is not None:
            statement = statement.where(
                EngineeringWorkstreamEvent.occurred_at > milestone_boundary.occurred_at
            )
        events = tuple(
            (
                await db.scalars(
                    statement.order_by(EngineeringWorkstreamEvent.sequence_id).limit(
                        500
                    )
                )
            ).all()
        )
        payloads: list[dict[str, object]] = []
        for event in events:
            runtime = await db.scalar(
                select(EngineeringWorkstreamRuntime).where(
                    EngineeringWorkstreamRuntime.company_id == company_id,
                    EngineeringWorkstreamRuntime.command_id == event.command_id,
                )
            )
            now = datetime.now(timezone.utc)
            heartbeat_age = (
                max(0, int((now - runtime.heartbeat_at).total_seconds()))
                if runtime
                else None
            )
            history = tuple(
                (
                    await db.scalars(
                        select(EngineeringWorkstreamEvent)
                        .where(
                            EngineeringWorkstreamEvent.company_id == company_id,
                            EngineeringWorkstreamEvent.command_id == event.command_id,
                            or_(
                                EngineeringWorkstreamEvent.occurred_at
                                < event.occurred_at,
                                and_(
                                    EngineeringWorkstreamEvent.occurred_at
                                    == event.occurred_at,
                                    EngineeringWorkstreamEvent.id <= event.id,
                                ),
                            ),
                        )
                        .order_by(
                            EngineeringWorkstreamEvent.occurred_at,
                            EngineeringWorkstreamEvent.id,
                        )
                    )
                ).all()
            )
            acknowledgement_latency = _latency(
                history, start_event="owner_request", end_event="worker_acknowledgement"
            )
            execution_latency = _state_latency(
                history,
                starts={"acknowledged", "running"},
                ends={"completed", "failed", "cancelled"},
            )
            validation_latency = _state_latency(
                history,
                starts={"validating"},
                ends={"deploying_preview", "completed", "failed"},
            )
            deployment_latency = _state_latency(
                history,
                starts={"deploying_preview"},
                ends={"completed", "failed"},
            )
            worker_events = tuple(
                item for item in history if item.worker_id is not None
            )
            worker_uptime = (
                max(
                    0,
                    int(
                        (
                            (runtime.heartbeat_at if runtime else now)
                            - worker_events[0].occurred_at
                        ).total_seconds()
                    ),
                )
                if worker_events
                else None
            )
            session_count = await db.scalar(
                select(
                    func.count(
                        func.distinct(EngineeringWorkstreamEvent.worker_session_id)
                    )
                ).where(
                    EngineeringWorkstreamEvent.company_id == company_id,
                    EngineeringWorkstreamEvent.command_id == event.command_id,
                    EngineeringWorkstreamEvent.worker_session_id.is_not(None),
                )
            )
            payloads.append(
                {
                    "event_id": str(event.id),
                    "command_id": str(event.command_id),
                    "event_type": event.event_type,
                    "action": event.action,
                    "runtime_state": event.runtime_state,
                    "reason_code": event.reason_code,
                    "occurred_at": event.occurred_at.isoformat(),
                    "notification": _notification(event),
                    "notifications": _notifications(event),
                    "runtime_version": runtime.version if runtime else None,
                    "worker_health": runtime.worker_health if runtime else None,
                    "progress_percent": runtime.progress_percent if runtime else None,
                    "current_activity": runtime.current_activity if runtime else None,
                    "heartbeat_at": runtime.heartbeat_at.isoformat()
                    if runtime
                    else None,
                    "heartbeat_age_seconds": heartbeat_age,
                    "acknowledgement_latency_ms": acknowledgement_latency,
                    "execution_latency_ms": execution_latency,
                    "validation_latency_ms": validation_latency,
                    "deployment_latency_ms": deployment_latency,
                    "worker_uptime_seconds": worker_uptime,
                    "current_worker": str(runtime.worker_id) if runtime else None,
                    "current_session": str(runtime.worker_session_id)
                    if runtime
                    else None,
                    "reconnect_count": max(0, int(session_count or 0) - 1),
                    "worker_available": bool(
                        runtime and heartbeat_age is not None and heartbeat_age < 300
                    ),
                    "recovery_state": runtime.runtime_state
                    if runtime and runtime.runtime_state == "recovering"
                    else None,
                }
            )
        milestone_statement = select(EngineeringMilestoneEvent).where(
            EngineeringMilestoneEvent.company_id == company_id,
            or_(
                EngineeringMilestoneEvent.event_type.like("external_%"),
                EngineeringMilestoneEvent.new_status.in_(
                    {"ready", "waiting_review", "waiting_approval"}
                ),
            ),
        )
        boundary_time = (
            boundary.occurred_at
            if boundary is not None
            else milestone_boundary.occurred_at
            if milestone_boundary is not None
            else None
        )
        if boundary_time is not None:
            milestone_statement = milestone_statement.where(
                EngineeringMilestoneEvent.occurred_at > boundary_time
            )
        milestone_events = tuple(
            (
                await db.scalars(
                    milestone_statement.order_by(
                        EngineeringMilestoneEvent.occurred_at,
                        EngineeringMilestoneEvent.id,
                    ).limit(500)
                )
            ).all()
        )
        for milestone_event in milestone_events:
            owner_notification = {
                "ready": "ready",
                "waiting_review": "waiting_for_review",
                "waiting_approval": "waiting_for_approval",
            }.get(milestone_event.new_status)
            payloads.append(
                {
                    "event_id": str(milestone_event.id),
                    "command_id": str(milestone_event.milestone_id),
                    "event_type": milestone_event.event_type,
                    "action": milestone_event.event_type.removeprefix("external_"),
                    "runtime_state": milestone_event.new_status,
                    "reason_code": None,
                    "occurred_at": milestone_event.occurred_at.isoformat(),
                    "notification": owner_notification,
                    "notifications": (owner_notification,)
                    if owner_notification
                    else (),
                    "runtime_version": None,
                    "worker_health": None,
                    "progress_percent": None,
                    "current_activity": None,
                    "heartbeat_at": None,
                    "heartbeat_age_seconds": None,
                    "acknowledgement_latency_ms": None,
                    "execution_latency_ms": None,
                    "validation_latency_ms": None,
                    "deployment_latency_ms": None,
                    "worker_uptime_seconds": None,
                    "current_worker": None,
                    "current_session": None,
                    "reconnect_count": 0,
                    "worker_available": False,
                    "recovery_state": None,
                    "external_milestone_id": str(milestone_event.milestone_id),
                }
            )
        payloads.sort(
            key=lambda item: (str(item["occurred_at"]), str(item["event_id"]))
        )
        return tuple(payloads[:500])


def _latency(
    events: tuple[EngineeringWorkstreamEvent, ...],
    *,
    start_event: str,
    end_event: str,
) -> int | None:
    start = next(
        (item.occurred_at for item in events if item.event_type == start_event), None
    )
    end = next(
        (
            item.occurred_at
            for item in events
            if item.event_type == end_event
            and start is not None
            and item.occurred_at >= start
        ),
        None,
    )
    return _milliseconds(start, end)


def _state_latency(
    events: tuple[EngineeringWorkstreamEvent, ...],
    *,
    starts: set[str],
    ends: set[str],
) -> int | None:
    start = next(
        (item.occurred_at for item in events if item.runtime_state in starts), None
    )
    end = next(
        (
            item.occurred_at
            for item in events
            if item.runtime_state in ends
            and start is not None
            and item.occurred_at >= start
        ),
        None,
    )
    return _milliseconds(start, end)


def _milliseconds(start: datetime | None, end: datetime | None) -> int | None:
    if start is None or end is None:
        return None
    return max(0, int((end - start).total_seconds() * 1000))


async def persist_expired_heartbeats(company_id: UUID) -> None:
    """Project stale runtime truth into one durable, idempotent recovery event."""
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=5)
    terminal = {"completed", "failed", "cancelled"}
    async with AsyncSessionFactory() as db, db.begin():
        runtimes = tuple(
            (
                await db.scalars(
                    select(EngineeringWorkstreamRuntime)
                    .where(
                        EngineeringWorkstreamRuntime.company_id == company_id,
                        EngineeringWorkstreamRuntime.heartbeat_at <= cutoff,
                        EngineeringWorkstreamRuntime.runtime_state.not_in(terminal),
                        EngineeringWorkstreamRuntime.worker_health != "unhealthy",
                    )
                    .with_for_update(skip_locked=True)
                )
            ).all()
        )
        for runtime in runtimes:
            preserve_terminal_review = False
            milestone = await db.scalar(
                select(EngineeringMilestone).where(
                    EngineeringMilestone.company_id == company_id,
                    EngineeringMilestone.command_id == runtime.command_id,
                    EngineeringMilestone.status == "waiting_review",
                    EngineeringMilestone.reconciliation_state == "current",
                )
            )
            result = await db.scalar(
                select(ControlledExecutionResultModel)
                .where(
                    ControlledExecutionResultModel.company_id == company_id,
                    ControlledExecutionResultModel.command_id == runtime.command_id,
                    ControlledExecutionResultModel.outcome == "succeeded",
                )
                .order_by(ControlledExecutionResultModel.completed_at.desc())
                .limit(1)
            )
            if milestone is not None and result is not None:
                execution = await db.get(EngineeringExecution, result.execution_id)
                reviews = tuple(
                    (
                        await db.scalars(
                            select(EngineeringExecutionReview).where(
                                EngineeringExecutionReview.company_id == company_id,
                                EngineeringExecutionReview.command_id
                                == runtime.command_id,
                                EngineeringExecutionReview.execution_id
                                == result.execution_id,
                                EngineeringExecutionReview.controlled_result_id
                                == result.id,
                                EngineeringExecutionReview.state == "pending",
                            )
                        )
                    ).all()
                )
                adoption = result.output.get("adoption")
                published_commit = result.output.get("published_commit_sha")
                convergence_recorded = False
                if len(reviews) == 1:
                    convergence_recorded = bool(
                        await db.scalar(
                            select(EngineeringWorkstreamEvent.id).where(
                                EngineeringWorkstreamEvent.company_id == company_id,
                                EngineeringWorkstreamEvent.command_id
                                == runtime.command_id,
                                EngineeringWorkstreamEvent.idempotency_key
                                == (
                                    f"adopted-owner-review:{result.id}:{reviews[0].id}"
                                ),
                            )
                        )
                    )
                preserve_terminal_review = (
                    execution is not None
                    and execution.state == "completed"
                    and execution.status == "succeeded"
                    and result.repository_mutated is True
                    and isinstance(published_commit, str)
                    and len(published_commit) == 40
                    and isinstance(adoption, dict)
                    and len(str(adoption.get("evidence_digest", ""))) == 64
                    and adoption.get("historical_publication_head") == published_commit
                    and len(reviews) == 1
                    and convergence_recorded
                )
            runtime.runtime_state = (
                "waiting_for_owner" if preserve_terminal_review else "recovering"
            )
            runtime.worker_health = "unhealthy"
            runtime.reason_code = "heartbeat_expired"
            runtime.updated_at = now
            runtime.version += 1
            db.add(
                EngineeringWorkstreamEvent(
                    company_id=runtime.company_id,
                    command_id=runtime.command_id,
                    control_id=runtime.control_id,
                    control_version=runtime.acknowledged_control_version,
                    worker_id=runtime.worker_id,
                    worker_session_id=runtime.worker_session_id,
                    event_type="runtime_transition",
                    action=runtime.acknowledged_action,
                    runtime_state=runtime.runtime_state,
                    reason_code="heartbeat_expired",
                    idempotency_key=f"heartbeat-expired:{runtime.id}:{runtime.version}",
                    occurred_at=now,
                )
            )


def _sse(payload: dict[str, object]) -> bytes:
    return f"id: {payload['event_id']}\nevent: engineering-runtime\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n".encode()


async def event_stream(
    company_id: UUID, resume_token: UUID | None
) -> AsyncIterator[bytes]:
    queue: asyncio.Queue[str] = asyncio.Queue(maxsize=128)
    connection = await asyncpg.connect(
        settings.database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    )

    def receive(_connection: object, _pid: int, _channel: str, payload: str) -> None:
        try:
            message = json.loads(payload)
            if message.get("company_id") == str(company_id):
                queue.put_nowait(payload)
        except (json.JSONDecodeError, asyncio.QueueFull):
            pass

    await connection.add_listener("engineering_workstream_events", receive)
    current = resume_token
    try:
        while True:
            await persist_expired_heartbeats(company_id)
            for payload in await _events_after(company_id, current):
                current = UUID(str(payload["event_id"]))
                yield _sse(payload)
            try:
                await asyncio.wait_for(queue.get(), timeout=20)
            except TimeoutError:
                yield b": keepalive\n\n"
    finally:
        await connection.remove_listener("engineering_workstream_events", receive)
        await connection.close()
