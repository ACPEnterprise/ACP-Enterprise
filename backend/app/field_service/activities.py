from __future__ import annotations

import hashlib
import json
from datetime import date
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.field_service.errors import FieldServiceConflict, FieldServiceValidation
from app.field_service.models import FieldJobActivityEvent, FieldJobContinuation
from app.field_service.service import field_service
from app.jobs.models import Job
from app.platform.permissions.authorization import AuthorizationContext
from app.scheduling.models import Appointment


class FieldActivityService:
    async def record(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        job_id: UUID,
        action: str,
        activity: str | None,
        expected_job_version: int,
        expected_appointment_version: int,
        idempotency_key: str,
    ) -> FieldJobActivityEvent:
        employee = await field_service._employee(session, context)
        digest = self._digest(action, activity, job_id, expected_job_version, expected_appointment_version)
        async with session.begin():
            replay = await session.scalar(
                select(FieldJobActivityEvent).where(
                    FieldJobActivityEvent.company_id == context.company.id,
                    FieldJobActivityEvent.employee_id == employee.id,
                    FieldJobActivityEvent.idempotency_key == idempotency_key,
                )
            )
            if replay is not None:
                if replay.evidence_digest != digest:
                    raise FieldServiceConflict("Activity replay does not match the accepted intent.")
                return replay
            assignment = await field_service._assigned_job(session, context, job_id, for_update=True)
            if assignment.appointment_id is None:
                raise FieldServiceValidation("Assigned Job has no Appointment visit authority.")
            job = await session.scalar(select(Job).where(Job.company_id == context.company.id, Job.id == job_id).with_for_update())
            appointment = await session.scalar(select(Appointment).where(Appointment.company_id == context.company.id, Appointment.id == assignment.appointment_id).with_for_update())
            if job is None or appointment is None:
                raise FieldServiceValidation("Assigned Job visit authority is incomplete.")
            if job.concurrency_version != expected_job_version or appointment.concurrency_version != expected_appointment_version:
                raise FieldServiceConflict("Job or Appointment version is stale.")
            latest = await session.scalar(
                select(FieldJobActivityEvent)
                .where(
                    FieldJobActivityEvent.company_id == context.company.id,
                    FieldJobActivityEvent.employee_id == employee.id,
                    FieldJobActivityEvent.appointment_id == appointment.id,
                )
                .order_by(FieldJobActivityEvent.occurred_at.desc(), FieldJobActivityEvent.id.desc())
                .limit(1)
            )
            active = latest is not None and latest.action != "finish_visit"
            current = latest.activity if active and latest is not None else None
            if action == "start" and (active or activity != "working"):
                raise FieldServiceConflict("Start Job requires no active visit and begins Working.")
            if action == "change" and (not active or activity not in {"working", "parts_run"} or activity == current):
                raise FieldServiceConflict("Activity change requires a different active Job activity.")
            if action == "finish_visit" and (not active or activity is not None):
                raise FieldServiceConflict("Finish for Today requires an active Job activity.")
            event = FieldJobActivityEvent(
                company_id=context.company.id,
                branch_id=assignment.branch_id,
                employee_id=employee.id,
                job_id=job.id,
                appointment_id=appointment.id,
                assignment_id=assignment.id,
                action=action,
                activity=activity,
                job_version=job.concurrency_version,
                appointment_version=appointment.concurrency_version,
                idempotency_key=idempotency_key,
                evidence_digest=digest,
                recorded_by_user_id=context.user.id,
            )
            session.add(event)
            await session.flush()
            BusinessEventService.stage(session, BusinessEventCreate(
                event_type=EventType.FIELD_JOB_ACTIVITY_RECORDED,
                entity_type="field_job_activity",
                entity_id=event.id,
                company_id=context.company.id,
                branch_id=assignment.branch_id,
                user_id=context.user.id,
                correlation_id=uuid4(),
                payload={"job_id": str(job.id), "appointment_id": str(appointment.id), "employee_id": str(employee.id), "action": action, "activity": activity, "job_version": job.concurrency_version, "appointment_version": appointment.concurrency_version, "evidence_digest": digest},
            ))
            return event

    async def continue_job(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        job_id: UUID,
        reason: str,
        requested_return_date: date | None,
        needs_scheduling: bool,
        note: str | None,
        idempotency_key: str,
    ) -> FieldJobContinuation:
        employee = await field_service._employee(session, context)
        async with session.begin():
            replay = await session.scalar(select(FieldJobContinuation).where(FieldJobContinuation.company_id == context.company.id, FieldJobContinuation.employee_id == employee.id, FieldJobContinuation.idempotency_key == idempotency_key))
            if replay is not None:
                if (replay.job_id, replay.reason, replay.requested_return_date, replay.needs_scheduling, replay.note) != (job_id, reason, requested_return_date, needs_scheduling, note):
                    raise FieldServiceConflict("Continuation replay does not match the accepted intent.")
                return replay
            assignment = await field_service._assigned_job(session, context, job_id, for_update=True)
            if assignment.appointment_id is None:
                raise FieldServiceValidation("Assigned Job has no Appointment visit authority.")
            latest = await session.scalar(select(FieldJobActivityEvent).where(FieldJobActivityEvent.company_id == context.company.id, FieldJobActivityEvent.employee_id == employee.id, FieldJobActivityEvent.appointment_id == assignment.appointment_id).order_by(FieldJobActivityEvent.occurred_at.desc(), FieldJobActivityEvent.id.desc()).limit(1))
            if latest is None or latest.action != "finish_visit":
                raise FieldServiceConflict("Finish for Today must be recorded before continuation.")
            if not needs_scheduling and requested_return_date is None:
                raise FieldServiceValidation("A planned continuation requires a return date.")
            record = FieldJobContinuation(company_id=context.company.id, branch_id=assignment.branch_id, employee_id=employee.id, job_id=job_id, appointment_id=assignment.appointment_id, assignment_id=assignment.id, reason=reason, requested_return_date=requested_return_date, needs_scheduling=needs_scheduling, note=note.strip() if note else None, idempotency_key=idempotency_key, recorded_by_user_id=context.user.id)
            session.add(record)
            await session.flush()
            BusinessEventService.stage(session, BusinessEventCreate(event_type=EventType.FIELD_JOB_CONTINUATION_REQUESTED, entity_type="field_job_continuation", entity_id=record.id, company_id=context.company.id, branch_id=assignment.branch_id, user_id=context.user.id, correlation_id=uuid4(), payload={"job_id": str(job_id), "appointment_id": str(assignment.appointment_id), "employee_id": str(employee.id), "reason": reason, "requested_return_date": requested_return_date.isoformat() if requested_return_date else None, "needs_scheduling": needs_scheduling}))
            return record

    @staticmethod
    def _digest(action: str, activity: str | None, job_id: UUID, job_version: int, appointment_version: int) -> str:
        return hashlib.sha256(json.dumps({"action": action, "activity": activity, "job_id": str(job_id), "job_version": job_version, "appointment_version": appointment_version}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


field_activity_service = FieldActivityService()
