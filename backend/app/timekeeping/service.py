"""Transaction owner for authoritative paid-time evidence."""

from collections.abc import Mapping
from datetime import date, datetime, timezone
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.platform.audit.service import AuditEntry, AuditService, audit_service
from app.platform.permissions.authorization import AuthorizationContext

from .commands import (
    CorrectJobWorkedInterval,
    CorrectTimeEntry,
    CreatePayPeriod,
    RecordJobClock,
    RecordManualTime,
    RecordPunch,
)
from .contracts import (
    PAYROLL_INPUT_PROJECTION_VERSION,
    ApprovedWorkdayTimeFact,
    PayrollInputEvidence,
    PayrollInputExclusionReason,
    PayrollInputProjection,
    PunchKind,
    TimeEntryProvenance,
    TimeEntryState,
    WorkdayAuthorizationError,
    WorkdayConflictError,
    WorkdayTimeError,
    canonical_digest,
    duration_minutes,
    seal_payroll_time_input,
)
from .models import (
    JobWorkedClockEvent,
    JobWorkedIntervalRevision,
    PayPeriod,
    PayrollTimeInputRecord,
    WorkdayPunchEvent,
    WorkdayTimeEntryRevision,
)
from .permissions import TimekeepingPermission
from .repository import TimekeepingRepository, timekeeping_repository


class WorkdayTimeService:
    def __init__(
        self,
        repository: TimekeepingRepository = timekeeping_repository,
        *,
        audit: AuditService = audit_service,
    ) -> None:
        self._repository = repository
        self._audit = audit

    async def record_job_clock(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command: RecordJobClock,
    ) -> tuple[JobWorkedClockEvent, JobWorkedIntervalRevision | None]:
        self._require_permission(context, TimekeepingPermission.OWN_PUNCH)
        self._require_branch(context, command.branch_id)
        self._validate_idempotency_key(command.idempotency_key)
        if command.occurred_at.tzinfo is None:
            raise WorkdayTimeError("Job clock timestamp must be timezone-aware")
        employee = await self._repository.employee_for_membership(
            session,
            company_id=context.company.id,
            membership_id=context.membership.id,
        )
        if employee is None or employee.id != command.employee_id:
            raise WorkdayAuthorizationError(
                "an employee may clock only their own Job work"
            )
        request_digest = canonical_digest(
            {
                "company_id": str(context.company.id),
                "branch_id": str(command.branch_id),
                "employee_id": str(command.employee_id),
                "job_id": str(command.job_id),
                "appointment_id": str(command.appointment_id)
                if command.appointment_id
                else None,
                "kind": command.kind.value,
            }
        )
        existing = await self._repository.job_clock_by_idempotency_key(
            session,
            company_id=context.company.id,
            recorded_by_user_id=context.user.id,
            idempotency_key=command.idempotency_key,
        )
        if existing is not None:
            if existing.request_digest != request_digest:
                raise WorkdayConflictError(
                    "idempotency key was used for a different Job clock"
                )
            return existing, await self._repository.interval_for_job_clock_event(
                session, company_id=context.company.id, event_id=existing.id
            )
        # An exact retry recovers immutable evidence even if the mutable Job or
        # Appointment relationship changed after the original response was lost.
        # Current scope is required only before admitting a new clock event.
        if not await self._repository.job_scope_exists(
            session,
            company_id=context.company.id,
            branch_id=command.branch_id,
            employee_id=command.employee_id,
            job_id=command.job_id,
            appointment_id=command.appointment_id,
        ):
            raise WorkdayTimeError("Job or Appointment scope is invalid")
        async with session.begin_nested():
            await self._repository.lock_employee_job_clock(
                session, company_id=context.company.id, employee_id=command.employee_id
            )
            latest = await self._repository.latest_job_clock_event(
                session, company_id=context.company.id, employee_id=command.employee_id
            )
            if command.kind.value == "start":
                if latest is not None and latest.kind == "start":
                    raise WorkdayConflictError(
                        "employee already has an active Job clock"
                    )
            else:
                if latest is None or latest.kind != "start":
                    raise WorkdayConflictError("Job clock stop has no active start")
                if (latest.job_id, latest.appointment_id, latest.branch_id) != (
                    command.job_id,
                    command.appointment_id,
                    command.branch_id,
                ):
                    raise WorkdayConflictError(
                        "Job clock stop scope differs from active start"
                    )
                if command.occurred_at <= latest.occurred_at:
                    raise WorkdayConflictError(
                        "Job clock stop must follow active start"
                    )
            event_id = uuid4()
            event_values = {
                "event_id": str(event_id),
                "request_digest": request_digest,
                "occurred_at": command.occurred_at.isoformat(),
                "recorded_by_user_id": str(context.user.id),
            }
            event = JobWorkedClockEvent(
                id=event_id,
                company_id=context.company.id,
                branch_id=command.branch_id,
                employee_id=command.employee_id,
                job_id=command.job_id,
                appointment_id=command.appointment_id,
                kind=command.kind.value,
                occurred_at=command.occurred_at,
                source="employee_clock",
                recorded_by_user_id=context.user.id,
                idempotency_key=command.idempotency_key,
                request_digest=request_digest,
                event_digest=canonical_digest(event_values),
            )
            session.add(event)
            interval = None
            if latest is not None and command.kind.value == "stop":
                duration_seconds = int(
                    (command.occurred_at - latest.occurred_at).total_seconds()
                )
                interval_id, revision_id = uuid4(), uuid4()
                values = {
                    "interval_id": str(interval_id),
                    "revision_id": str(revision_id),
                    "employee_id": str(command.employee_id),
                    "job_id": str(command.job_id),
                    "appointment_id": str(command.appointment_id)
                    if command.appointment_id
                    else None,
                    "start_at": latest.occurred_at.isoformat(),
                    "stop_at": command.occurred_at.isoformat(),
                    "source_event_ids": (str(latest.id), str(event.id)),
                }
                interval = JobWorkedIntervalRevision(
                    id=revision_id,
                    interval_id=interval_id,
                    revision_number=1,
                    supersedes_revision_id=None,
                    company_id=context.company.id,
                    branch_id=command.branch_id,
                    employee_id=command.employee_id,
                    job_id=command.job_id,
                    appointment_id=command.appointment_id,
                    start_at=latest.occurred_at,
                    stop_at=command.occurred_at,
                    duration_seconds=duration_seconds,
                    duration_minutes=duration_seconds // 60,
                    source="employee_clock",
                    correction_state="original",
                    audit_lineage=[str(revision_id)],
                    source_event_ids=[str(latest.id), str(event.id)],
                    validity="valid",
                    confidence="authoritative",
                    correction_reason=None,
                    corrected_by_user_id=None,
                    correction_idempotency_key=None,
                    correction_request_digest=None,
                    evidence_digest=canonical_digest(values),
                )
                session.add(interval)
            self._stage_action(
                session,
                context=context,
                event_type=EventType.JOB_WORK_CLOCK_RECORDED,
                entity_id=event.id,
                action="timekeeping.job_clock.recorded",
                branch_id=command.branch_id,
                details={
                    "employee_id": str(command.employee_id),
                    "job_id": str(command.job_id),
                    "kind": command.kind.value,
                },
            )
        try:
            await session.commit()
            return event, interval
        except IntegrityError:
            await session.rollback()
            existing = await self._repository.job_clock_by_idempotency_key(
                session,
                company_id=context.company.id,
                recorded_by_user_id=context.user.id,
                idempotency_key=command.idempotency_key,
            )
            if existing is None or existing.request_digest != request_digest:
                raise WorkdayConflictError(
                    "concurrent Job clock request could not be reconciled"
                )
            return existing, await self._repository.interval_for_job_clock_event(
                session, company_id=context.company.id, event_id=existing.id
            )

    async def correct_job_interval(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command: CorrectJobWorkedInterval,
    ) -> JobWorkedIntervalRevision:
        self._require_permission(context, TimekeepingPermission.CORRECT)
        self._validate_idempotency_key(command.idempotency_key)
        if (
            not command.reason.strip()
            or command.start_at.tzinfo is None
            or command.stop_at.tzinfo is None
        ):
            raise WorkdayTimeError(
                "valid correction reason and timezone-aware interval are required"
            )
        if command.stop_at <= command.start_at:
            raise WorkdayTimeError("corrected stop must follow start")
        request_digest = canonical_digest(
            {
                "revision_id": str(command.revision_id),
                "start_at": command.start_at.isoformat(),
                "stop_at": command.stop_at.isoformat(),
                "reason": command.reason.strip(),
            }
        )
        existing = await self._repository.job_interval_correction_by_idempotency_key(
            session,
            company_id=context.company.id,
            corrected_by_user_id=context.user.id,
            idempotency_key=command.idempotency_key,
        )
        if existing is not None:
            if existing.correction_request_digest != request_digest:
                raise WorkdayConflictError(
                    "idempotency key was used for a different Job correction"
                )
            return existing
        prior = await self._repository.latest_job_interval_revision(
            session, company_id=context.company.id, revision_id=command.revision_id
        )
        if prior is None:
            raise WorkdayTimeError("Job worked interval does not exist")
        self._require_branch(context, prior.branch_id)
        async with session.begin_nested():
            await self._repository.lock_employee_job_clock(
                session, company_id=context.company.id, employee_id=prior.employee_id
            )
            others = await self._repository.current_job_intervals(
                session,
                company_id=context.company.id,
                employee_ids=(prior.employee_id,),
                start_at=command.start_at,
                stop_at=command.stop_at,
            )
            if any(value.interval_id != prior.interval_id for value in others):
                raise WorkdayConflictError(
                    "corrected Job worked interval overlaps current evidence"
                )
            revision_id = uuid4()
            duration_seconds = int((command.stop_at - command.start_at).total_seconds())
            values = {
                "revision_id": str(revision_id),
                "prior_digest": prior.evidence_digest,
                "start_at": command.start_at.isoformat(),
                "stop_at": command.stop_at.isoformat(),
                "request_digest": request_digest,
            }
            result = JobWorkedIntervalRevision(
                id=revision_id,
                interval_id=prior.interval_id,
                revision_number=prior.revision_number + 1,
                supersedes_revision_id=prior.id,
                company_id=prior.company_id,
                branch_id=prior.branch_id,
                employee_id=prior.employee_id,
                job_id=prior.job_id,
                appointment_id=prior.appointment_id,
                start_at=command.start_at,
                stop_at=command.stop_at,
                duration_seconds=duration_seconds,
                duration_minutes=duration_seconds // 60,
                source="authorized_manual",
                correction_state="corrected",
                audit_lineage=[*prior.audit_lineage, str(revision_id)],
                source_event_ids=list(prior.source_event_ids),
                validity="valid",
                confidence=prior.confidence,
                correction_reason=command.reason.strip(),
                corrected_by_user_id=context.user.id,
                correction_idempotency_key=command.idempotency_key,
                correction_request_digest=request_digest,
                evidence_digest=canonical_digest(values),
            )
            session.add(result)
            self._stage_action(
                session,
                context=context,
                event_type=EventType.JOB_WORK_INTERVAL_CORRECTED,
                entity_id=result.id,
                action="timekeeping.job_interval.corrected",
                branch_id=result.branch_id,
                details={
                    "employee_id": str(result.employee_id),
                    "job_id": str(result.job_id),
                    "supersedes_revision_id": str(prior.id),
                },
            )
        try:
            await session.commit()
            return result
        except IntegrityError:
            await session.rollback()
            existing = (
                await self._repository.job_interval_correction_by_idempotency_key(
                    session,
                    company_id=context.company.id,
                    corrected_by_user_id=context.user.id,
                    idempotency_key=command.idempotency_key,
                )
            )
            if existing is None or existing.correction_request_digest != request_digest:
                raise WorkdayConflictError(
                    "concurrent Job correction could not be reconciled"
                )
            return existing

    async def record_punch(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command: RecordPunch,
    ) -> tuple[WorkdayPunchEvent, WorkdayTimeEntryRevision | None]:
        self._require_permission(context, TimekeepingPermission.OWN_PUNCH)
        self._require_branch(context, command.branch_id)
        employee = await self._repository.employee_for_membership(
            session,
            company_id=context.company.id,
            membership_id=context.membership.id,
        )
        if employee is None or employee.id != command.employee_id:
            raise WorkdayAuthorizationError("an employee may punch only their own time")
        request_digest = self._punch_request_digest(context, command)
        if command.idempotency_key is not None:
            self._validate_idempotency_key(command.idempotency_key)
            existing = await self._repository.punch_by_idempotency_key(
                session,
                company_id=context.company.id,
                recorded_by_user_id=context.user.id,
                idempotency_key=command.idempotency_key,
            )
            if existing is not None:
                if existing.request_digest != request_digest:
                    raise WorkdayConflictError(
                        "idempotency key was used for a different punch request"
                    )
                return existing, await self._repository.revision_for_punch(
                    session,
                    company_id=context.company.id,
                    punch_id=existing.id,
                )
        if command.occurred_at.tzinfo is None:
            raise WorkdayTimeError("punch timestamp must be timezone-aware")
        self._validate_timezone(command.timezone)
        async with session.begin_nested():
            latest = await self._repository.latest_punch(
                session,
                company_id=context.company.id,
                employee_id=command.employee_id,
            )
            self._validate_punch_transition(latest, command)
            event = self._new_punch(context, command)
            session.add(event)
            revision = None
            if command.kind is PunchKind.CLOCK_OUT:
                clock_in = await self._repository.latest_clock_in(
                    session,
                    company_id=context.company.id,
                    employee_id=command.employee_id,
                )
                if clock_in is None or clock_in.occurred_at >= command.occurred_at:
                    raise WorkdayConflictError("clock out has no valid active clock in")
                revision = await self._new_time_revision(
                    session,
                    context=context,
                    employee_id=command.employee_id,
                    branch_id=command.branch_id,
                    work_date=clock_in.occurred_at.astimezone(
                        ZoneInfo(command.timezone)
                    ).date(),
                    timezone_name=command.timezone,
                    provenance=TimeEntryProvenance.EMPLOYEE_PUNCH,
                    start_at=clock_in.occurred_at,
                    end_at=command.occurred_at,
                    approved_duration_minutes=None,
                    punch_event_ids=(clock_in.id, event.id),
                    manual_reason=None,
                    state=TimeEntryState.RECORDED,
                    responsible_user_id=context.user.id,
                )
            self._stage_action(
                session,
                context=context,
                event_type=EventType.WORKDAY_PUNCH_RECORDED,
                entity_id=event.id,
                action="timekeeping.punch.recorded",
                branch_id=command.branch_id,
                details={
                    "kind": command.kind.value,
                    "employee_id": str(command.employee_id),
                },
            )
        try:
            await session.commit()
            return event, revision
        except IntegrityError:
            await session.rollback()
            if command.idempotency_key is None:
                raise
            existing = await self._repository.punch_by_idempotency_key(
                session,
                company_id=context.company.id,
                recorded_by_user_id=context.user.id,
                idempotency_key=command.idempotency_key,
            )
            if existing is None or existing.request_digest != request_digest:
                raise WorkdayConflictError(
                    "concurrent punch request could not be reconciled"
                )
            return existing, await self._repository.revision_for_punch(
                session, company_id=context.company.id, punch_id=existing.id
            )

    async def record_manual_time(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command: RecordManualTime,
    ) -> WorkdayTimeEntryRevision:
        self._require_permission(context, TimekeepingPermission.MANUAL_ENTRY)
        self._require_branch(context, command.branch_id)
        if not command.reason.strip():
            raise WorkdayTimeError("manual-entry reason is required")
        request_digest = self._manual_request_digest(context, command)
        if command.idempotency_key is not None:
            self._validate_idempotency_key(command.idempotency_key)
            existing = await self._repository.manual_revision_by_idempotency_key(
                session,
                company_id=context.company.id,
                responsible_user_id=context.user.id,
                idempotency_key=command.idempotency_key,
            )
            if existing is not None:
                if existing.origin_request_digest != request_digest:
                    raise WorkdayConflictError(
                        "idempotency key was used for a different manual entry"
                    )
                return existing
        self._validate_timezone(command.timezone)
        if not await self._repository.employee_exists(
            session, company_id=context.company.id, employee_id=command.employee_id
        ):
            raise WorkdayTimeError("employee does not exist in Company")
        duration_minutes(
            command.start_at, command.end_at, command.approved_duration_minutes
        )
        async with session.begin_nested():
            revision = await self._new_time_revision(
                session,
                context=context,
                employee_id=command.employee_id,
                branch_id=command.branch_id,
                work_date=command.work_date,
                timezone_name=command.timezone,
                provenance=TimeEntryProvenance.AUTHORIZED_MANUAL_ENTRY,
                start_at=command.start_at,
                end_at=command.end_at,
                approved_duration_minutes=command.approved_duration_minutes,
                punch_event_ids=(),
                manual_reason=command.reason.strip(),
                state=TimeEntryState.RECORDED,
                responsible_user_id=context.user.id,
                origin_idempotency_key=command.idempotency_key,
                origin_request_digest=request_digest,
            )
            self._stage_action(
                session,
                context=context,
                event_type=EventType.WORKDAY_MANUAL_TIME_RECORDED,
                entity_id=revision.id,
                action="timekeeping.manual.recorded",
                branch_id=command.branch_id,
                details={"employee_id": str(command.employee_id)},
            )
        try:
            await session.commit()
            return revision
        except IntegrityError:
            await session.rollback()
            if command.idempotency_key is None:
                raise
            existing = await self._repository.manual_revision_by_idempotency_key(
                session,
                company_id=context.company.id,
                responsible_user_id=context.user.id,
                idempotency_key=command.idempotency_key,
            )
            if existing is None or existing.origin_request_digest != request_digest:
                raise WorkdayConflictError(
                    "concurrent manual-entry request could not be reconciled"
                )
            return existing

    async def submit(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        revision_id: UUID,
    ) -> WorkdayTimeEntryRevision:
        prior = await self._require_latest(session, context, revision_id)
        employee = await self._repository.employee_for_membership(
            session,
            company_id=context.company.id,
            membership_id=context.membership.id,
        )
        owns_time = employee is not None and employee.id == prior.employee_id
        if owns_time:
            self._require_permission(context, TimekeepingPermission.OWN_PUNCH)
        elif (
            prior.provenance != TimeEntryProvenance.AUTHORIZED_MANUAL_ENTRY.value
            or not context.has_permission(TimekeepingPermission.MANUAL_ENTRY)
        ):
            raise WorkdayAuthorizationError(
                "time submission requires ownership or manual-entry authority"
            )
        if prior.state not in {
            TimeEntryState.RECORDED.value,
            TimeEntryState.CORRECTED.value,
        }:
            raise WorkdayConflictError(
                "only recorded or corrected time may be submitted"
            )
        async with session.begin_nested():
            result = self._copy_revision(
                prior,
                state=TimeEntryState.SUBMITTED,
                actor_user_id=context.user.id,
            )
            session.add(result)
            self._stage_action(
                session,
                context=context,
                event_type=EventType.WORKDAY_TIME_SUBMITTED,
                entity_id=result.id,
                action="timekeeping.time.submitted",
                branch_id=result.branch_id,
                details={"employee_id": str(result.employee_id)},
            )
        await session.commit()
        return result

    async def approve(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        revision_id: UUID,
    ) -> WorkdayTimeEntryRevision:
        self._require_permission(context, TimekeepingPermission.APPROVE)
        prior = await self._require_latest(session, context, revision_id)
        employee = await self._repository.employee_for_membership(
            session,
            company_id=context.company.id,
            membership_id=context.membership.id,
        )
        if employee is not None and employee.id == prior.employee_id:
            raise WorkdayAuthorizationError(
                "employees cannot approve their own Workday Time"
            )
        if prior.state != TimeEntryState.SUBMITTED.value:
            raise WorkdayConflictError("only submitted time may be approved")
        now = datetime.now(timezone.utc)
        async with session.begin_nested():
            result = self._copy_revision(
                prior,
                state=TimeEntryState.APPROVED,
                actor_user_id=context.user.id,
                approval_id=uuid4(),
                approved_at=now,
            )
            session.add(result)
            self._stage_action(
                session,
                context=context,
                event_type=EventType.WORKDAY_TIME_APPROVED,
                entity_id=result.id,
                action="timekeeping.time.approved",
                branch_id=result.branch_id,
                details={"employee_id": str(result.employee_id)},
            )
        await session.commit()
        return result

    async def correct(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command: CorrectTimeEntry,
    ) -> WorkdayTimeEntryRevision:
        self._require_permission(context, TimekeepingPermission.CORRECT)
        self._validate_idempotency_key(command.idempotency_key)
        if not command.reason.strip():
            raise WorkdayTimeError("correction reason is required")
        request_digest = canonical_digest(
            {
                "revision_id": str(command.revision_id),
                "start_at": command.start_at.isoformat() if command.start_at else None,
                "end_at": command.end_at.isoformat() if command.end_at else None,
                "approved_duration_minutes": command.approved_duration_minutes,
                "reason": command.reason.strip(),
                "correction_kind": command.correction_kind.value,
            }
        )
        existing = await self._repository.correction_by_idempotency_key(
            session,
            company_id=context.company.id,
            responsible_user_id=context.user.id,
            idempotency_key=command.idempotency_key,
        )
        if existing is not None:
            if existing.correction_request_digest != request_digest:
                raise WorkdayConflictError(
                    "idempotency key was used for a different correction"
                )
            return existing
        duration_minutes(
            command.start_at, command.end_at, command.approved_duration_minutes
        )
        prior = await self._require_latest(session, context, command.revision_id)
        await self._reject_overlap(
            session,
            company_id=context.company.id,
            employee_id=prior.employee_id,
            work_date=prior.work_date,
            start_at=command.start_at,
            end_at=command.end_at,
            exclude_entry_id=prior.entry_id,
        )
        async with session.begin_nested():
            result = self._copy_revision(
                prior,
                state=TimeEntryState.CORRECTED,
                actor_user_id=context.user.id,
                start_at=command.start_at,
                end_at=command.end_at,
                approved_duration_minutes=command.approved_duration_minutes,
                correction_reason=command.reason.strip(),
                correction_kind=command.correction_kind.value,
                correction_idempotency_key=command.idempotency_key,
                correction_request_digest=request_digest,
                approval_id=None,
                approved_at=None,
                replace_time=True,
            )
            session.add(result)
            self._stage_action(
                session,
                context=context,
                event_type=EventType.WORKDAY_TIME_CORRECTED,
                entity_id=result.id,
                action="timekeeping.time.corrected",
                branch_id=result.branch_id,
                details={
                    "employee_id": str(result.employee_id),
                    "superseded_revision_id": str(prior.id),
                },
            )
            BusinessEventService.stage(
                session,
                BusinessEventCreate(
                    event_type=EventType.WORKDAY_TIME_SUPERSEDED,
                    entity_type="workday_time",
                    entity_id=prior.id,
                    company_id=context.company.id,
                    branch_id=prior.branch_id,
                    user_id=context.user.id,
                    payload={"successor_revision_id": str(result.id)},
                ),
            )
        try:
            await session.commit()
            return result
        except IntegrityError:
            await session.rollback()
            existing = await self._repository.correction_by_idempotency_key(
                session,
                company_id=context.company.id,
                responsible_user_id=context.user.id,
                idempotency_key=command.idempotency_key,
            )
            if existing is None or existing.correction_request_digest != request_digest:
                raise WorkdayConflictError(
                    "concurrent correction could not be reconciled"
                )
            return existing

    async def create_pay_period(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        command: CreatePayPeriod,
    ) -> PayPeriod:
        self._require_permission(context, TimekeepingPermission.APPROVE)
        if command.schedule_version < 1:
            raise WorkdayTimeError("pay-period schedule version must be positive")
        self._validate_timezone(command.timezone)
        overlap = await self._repository.overlapping_pay_period(
            session,
            company_id=context.company.id,
            period_start=command.period_start,
            period_end=command.period_end,
        )
        if overlap is not None:
            raise WorkdayConflictError("pay periods may not overlap")
        period = PayPeriod(
            company_id=context.company.id,
            period_start=command.period_start,
            period_end=command.period_end,
            processing_date=command.processing_date,
            payday=command.payday,
            timezone=command.timezone,
            schedule_definition_id=command.schedule_definition_id,
            schedule_version=command.schedule_version,
            created_by_user_id=context.user.id,
        )
        async with session.begin_nested():
            session.add(period)
        await session.commit()
        return period

    async def seal_payroll_input(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        employee_id: UUID,
        pay_period: PayPeriod,
    ):
        self._require_permission(context, TimekeepingPermission.APPROVE)
        if pay_period.company_id != context.company.id:
            raise WorkdayAuthorizationError("pay period Company mismatch")
        projection, facts = await self._payroll_input_projection(
            session,
            context=context,
            employee_id=employee_id,
            pay_period=pay_period,
        )
        if any(
            item.reason is PayrollInputExclusionReason.OVERLAPS_APPROVED_INTERVAL
            for item in projection.excluded
        ):
            raise WorkdayConflictError(
                "Payroll Time Input has overlapping accepted intervals"
            )
        snapshot = seal_payroll_time_input(
            company_id=context.company.id,
            employee_id=employee_id,
            pay_period_id=pay_period.id,
            period_start=pay_period.period_start,
            period_end=pay_period.period_end,
            approved_entries=facts,
        )
        existing = await session.scalar(
            select(PayrollTimeInputRecord.id).where(
                PayrollTimeInputRecord.company_id == snapshot.company_id,
                PayrollTimeInputRecord.snapshot_digest == snapshot.snapshot_digest,
            )
        )
        if existing is not None:
            return snapshot
        async with session.begin_nested():
            session.add(
                PayrollTimeInputRecord(
                    snapshot_identity=snapshot.snapshot_id,
                    snapshot_version=snapshot.version,
                    company_id=snapshot.company_id,
                    employee_id=snapshot.employee_id,
                    pay_period_id=snapshot.pay_period_id,
                    approved_revision_ids=[str(value.revision_id) for value in facts],
                    total_approved_minutes=snapshot.total_approved_minutes,
                    snapshot_digest=snapshot.snapshot_digest,
                    created_by_user_id=context.user.id,
                )
            )
        await session.commit()
        return snapshot

    async def payroll_input_projection(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        employee_id: UUID,
        pay_period: PayPeriod,
    ) -> PayrollInputProjection:
        self._require_permission(context, TimekeepingPermission.APPROVE)
        if pay_period.company_id != context.company.id:
            raise WorkdayAuthorizationError("pay period Company mismatch")
        projection, _ = await self._payroll_input_projection(
            session,
            context=context,
            employee_id=employee_id,
            pay_period=pay_period,
        )
        return projection

    async def _payroll_input_projection(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        employee_id: UUID,
        pay_period: PayPeriod,
    ) -> tuple[PayrollInputProjection, tuple[ApprovedWorkdayTimeFact, ...]]:
        revisions = await self._repository.current_employee_revisions(
            session,
            company_id=context.company.id,
            employee_id=employee_id,
            start_date=pay_period.period_start,
            end_date=pay_period.period_end,
        )
        approved = [
            (value, self._approved_fact(value))
            for value in revisions
            if value.state == TimeEntryState.APPROVED.value
        ]
        overlap_ids: set[UUID] = set()
        timed = sorted(
            (
                pair
                for pair in approved
                if pair[1].start_at is not None and pair[1].end_at is not None
            ),
            key=lambda pair: (
                pair[1].start_at,
                pair[1].end_at,
                str(pair[1].revision_id),
            ),
        )
        for index, (_, current) in enumerate(timed):
            assert current.start_at is not None
            for _, previous in timed[:index]:
                assert previous.end_at is not None
                if current.start_at < previous.end_at:
                    overlap_ids.update((current.revision_id, previous.revision_id))

        included_facts = tuple(
            fact for _, fact in approved if fact.revision_id not in overlap_ids
        )
        included = tuple(
            PayrollInputEvidence(
                entry_id=fact.entry_id,
                revision_id=fact.revision_id,
                state=TimeEntryState.APPROVED.value,
                eligible=True,
                reason=None,
                approved_minutes=fact.approved_duration_minutes,
                evidence_digest=fact.evidence_digest,
            )
            for fact in included_facts
        )
        excluded: list[PayrollInputEvidence] = []
        for revision in revisions:
            reason: PayrollInputExclusionReason | None = None
            if revision.id in overlap_ids:
                reason = PayrollInputExclusionReason.OVERLAPS_APPROVED_INTERVAL
            elif revision.state == TimeEntryState.RECORDED.value:
                reason = PayrollInputExclusionReason.NOT_SUBMITTED
            elif revision.state == TimeEntryState.SUBMITTED.value:
                reason = PayrollInputExclusionReason.AWAITING_APPROVAL
            elif revision.state == TimeEntryState.CORRECTED.value:
                reason = PayrollInputExclusionReason.CORRECTION_AWAITING_APPROVAL
            if reason is not None:
                excluded.append(
                    PayrollInputEvidence(
                        entry_id=revision.entry_id,
                        revision_id=revision.id,
                        state=revision.state,
                        eligible=False,
                        reason=reason,
                        approved_minutes=None,
                        evidence_digest=revision.evidence_digest,
                    )
                )
        latest_job_clock = await self._repository.latest_job_clock_event(
            session, company_id=context.company.id, employee_id=employee_id
        )
        if latest_job_clock is not None and latest_job_clock.kind == "start":
            excluded.append(
                PayrollInputEvidence(
                    entry_id=None,
                    revision_id=None,
                    state="open_job_clock",
                    eligible=False,
                    reason=PayrollInputExclusionReason.OPEN_JOB_CLOCK_NON_PAYABLE,
                    approved_minutes=None,
                    evidence_digest=latest_job_clock.event_digest,
                )
            )
        excluded_tuple = tuple(
            sorted(
                excluded,
                key=lambda item: (
                    item.reason.value if item.reason else "",
                    str(item.revision_id or ""),
                ),
            )
        )
        draft = PayrollInputProjection(
            version=PAYROLL_INPUT_PROJECTION_VERSION,
            employee_id=employee_id,
            pay_period_id=pay_period.id,
            included=included,
            excluded=excluded_tuple,
            total_eligible_minutes=sum(
                fact.approved_duration_minutes for fact in included_facts
            ),
            projection_digest="",
        )
        projection = PayrollInputProjection(
            **{
                **draft.__dict__,
                "projection_digest": canonical_digest(draft.canonical_content()),
            }
        )
        return projection, included_facts

    async def _new_time_revision(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        employee_id: UUID,
        branch_id: UUID | None,
        work_date: date,
        timezone_name: str,
        provenance: TimeEntryProvenance,
        start_at: datetime | None,
        end_at: datetime | None,
        approved_duration_minutes: int | None,
        punch_event_ids: tuple[UUID, ...],
        manual_reason: str | None,
        state: TimeEntryState,
        responsible_user_id: UUID,
        origin_idempotency_key: str | None = None,
        origin_request_digest: str | None = None,
    ) -> WorkdayTimeEntryRevision:
        await self._reject_overlap(
            session,
            company_id=context.company.id,
            employee_id=employee_id,
            work_date=work_date,
            start_at=start_at,
            end_at=end_at,
        )
        entry_id = uuid4()
        values = {
            "entry_id": str(entry_id),
            "revision_number": 1,
            "company_id": str(context.company.id),
            "branch_id": str(branch_id) if branch_id else None,
            "employee_id": str(employee_id),
            "work_date": work_date.isoformat(),
            "timezone": timezone_name,
            "provenance": provenance.value,
            "start_at": start_at.isoformat() if start_at else None,
            "end_at": end_at.isoformat() if end_at else None,
            "approved_duration_minutes": approved_duration_minutes,
            "punch_event_ids": tuple(str(value) for value in punch_event_ids),
            "manual_reason": manual_reason,
            "state": state.value,
            "responsible_user_id": str(responsible_user_id),
            "origin_idempotency_key": origin_idempotency_key,
            "origin_request_digest": origin_request_digest,
        }
        revision = WorkdayTimeEntryRevision(
            entry_id=entry_id,
            revision_number=1,
            supersedes_revision_id=None,
            lineage_revision_ids=[],
            company_id=context.company.id,
            branch_id=branch_id,
            employee_id=employee_id,
            work_date=work_date,
            timezone=timezone_name,
            provenance=provenance.value,
            start_at=start_at,
            end_at=end_at,
            approved_duration_minutes=approved_duration_minutes,
            punch_event_ids=[str(value) for value in punch_event_ids],
            manual_reason=manual_reason,
            origin_idempotency_key=origin_idempotency_key,
            origin_request_digest=origin_request_digest,
            state=state.value,
            source_user_id=responsible_user_id,
            responsible_user_id=responsible_user_id,
            approval_id=None,
            approved_by_user_id=None,
            approved_at=None,
            correction_reason=None,
            evidence_digest=canonical_digest(values),
        )
        session.add(revision)
        return revision

    def _copy_revision(
        self,
        prior: WorkdayTimeEntryRevision,
        *,
        state: TimeEntryState,
        actor_user_id: UUID,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        approved_duration_minutes: int | None = None,
        correction_reason: str | None = None,
        correction_kind: str | None = None,
        correction_idempotency_key: str | None = None,
        correction_request_digest: str | None = None,
        approval_id: UUID | None = None,
        approved_at: datetime | None = None,
        replace_time: bool = False,
    ) -> WorkdayTimeEntryRevision:
        actual_start = start_at if replace_time else prior.start_at
        actual_end = end_at if replace_time else prior.end_at
        actual_duration = (
            approved_duration_minutes
            if replace_time
            else prior.approved_duration_minutes
        )
        revision_id = uuid4()
        values = {
            "revision_id": str(revision_id),
            "entry_id": str(prior.entry_id),
            "revision_number": prior.revision_number + 1,
            "supersedes_revision_id": str(prior.id),
            "state": state.value,
            "start_at": actual_start.isoformat() if actual_start else None,
            "end_at": actual_end.isoformat() if actual_end else None,
            "approved_duration_minutes": actual_duration,
            "actor_user_id": str(actor_user_id),
            "approval_id": str(approval_id) if approval_id else None,
            "approved_at": approved_at.isoformat() if approved_at else None,
            "correction_reason": correction_reason,
            "correction_kind": correction_kind,
            "correction_idempotency_key": correction_idempotency_key,
            "correction_request_digest": correction_request_digest,
            "prior_digest": prior.evidence_digest,
        }
        return WorkdayTimeEntryRevision(
            id=revision_id,
            entry_id=prior.entry_id,
            revision_number=prior.revision_number + 1,
            supersedes_revision_id=prior.id,
            lineage_revision_ids=[*prior.lineage_revision_ids, str(prior.id)],
            company_id=prior.company_id,
            branch_id=prior.branch_id,
            employee_id=prior.employee_id,
            work_date=prior.work_date,
            timezone=prior.timezone,
            provenance=prior.provenance,
            start_at=actual_start,
            end_at=actual_end,
            approved_duration_minutes=actual_duration,
            punch_event_ids=list(prior.punch_event_ids),
            manual_reason=prior.manual_reason,
            origin_idempotency_key=prior.origin_idempotency_key,
            origin_request_digest=prior.origin_request_digest,
            state=state.value,
            source_user_id=prior.source_user_id,
            responsible_user_id=actor_user_id,
            approval_id=approval_id,
            approved_by_user_id=actor_user_id if approval_id else None,
            approved_at=approved_at,
            correction_reason=correction_reason,
            correction_kind=correction_kind,
            correction_idempotency_key=correction_idempotency_key,
            correction_request_digest=correction_request_digest,
            evidence_digest=canonical_digest(values),
        )

    async def _reject_overlap(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        employee_id: UUID,
        work_date: date,
        start_at: datetime | None,
        end_at: datetime | None,
        exclude_entry_id: UUID | None = None,
    ) -> None:
        if start_at is None or end_at is None:
            return
        existing = await self._repository.current_employee_revisions(
            session,
            company_id=company_id,
            employee_id=employee_id,
            start_date=work_date,
            end_date=work_date,
        )
        if any(
            value.entry_id != exclude_entry_id
            and value.start_at is not None
            and value.end_at is not None
            and start_at < value.end_at
            and end_at > value.start_at
            for value in existing
        ):
            raise WorkdayConflictError("Workday Time intervals overlap")

    async def _require_latest(
        self, session: AsyncSession, context: AuthorizationContext, revision_id: UUID
    ) -> WorkdayTimeEntryRevision:
        revision = await self._repository.latest_revision(
            session, company_id=context.company.id, revision_id=revision_id
        )
        if revision is None or revision.id != revision_id:
            raise WorkdayConflictError("time revision is missing or superseded")
        self._require_branch(context, revision.branch_id)
        return revision

    @staticmethod
    def _approved_fact(revision: WorkdayTimeEntryRevision) -> ApprovedWorkdayTimeFact:
        if (
            revision.approval_id is None
            or revision.approved_by_user_id is None
            or revision.approved_at is None
        ):
            raise WorkdayTimeError("approved revision lacks approval evidence")
        minutes = duration_minutes(
            revision.start_at, revision.end_at, revision.approved_duration_minutes
        )
        draft = ApprovedWorkdayTimeFact(
            entry_id=revision.entry_id,
            revision_id=revision.id,
            revision_number=revision.revision_number,
            company_id=revision.company_id,
            branch_id=revision.branch_id,
            employee_id=revision.employee_id,
            work_date=revision.work_date,
            timezone=revision.timezone,
            provenance=TimeEntryProvenance(revision.provenance),
            start_at=revision.start_at,
            end_at=revision.end_at,
            approved_duration_minutes=minutes,
            punch_event_ids=tuple(UUID(value) for value in revision.punch_event_ids),
            correction_lineage=tuple(
                UUID(value) for value in revision.lineage_revision_ids
            ),
            entered_by_user_id=(
                revision.source_user_id
                if revision.provenance
                == TimeEntryProvenance.AUTHORIZED_MANUAL_ENTRY.value
                else None
            ),
            approval_id=revision.approval_id,
            approved_by_user_id=revision.approved_by_user_id,
            approved_at=revision.approved_at,
            evidence_digest="",
        )
        return ApprovedWorkdayTimeFact(
            **{
                **draft.__dict__,
                "evidence_digest": canonical_digest(draft.canonical_content()),
            }
        )

    @staticmethod
    def _validate_punch_transition(
        latest: WorkdayPunchEvent | None, command: RecordPunch
    ) -> None:
        kind = command.kind
        prior = None if latest is None else PunchKind(latest.kind)
        allowed: Mapping[PunchKind, set[PunchKind | None]] = {
            PunchKind.CLOCK_IN: {None, PunchKind.CLOCK_OUT},
            PunchKind.BREAK_START: {PunchKind.CLOCK_IN, PunchKind.BREAK_END},
            PunchKind.BREAK_END: {PunchKind.BREAK_START},
            PunchKind.CLOCK_OUT: {PunchKind.CLOCK_IN, PunchKind.BREAK_END},
        }
        if prior not in allowed[kind]:
            raise WorkdayConflictError("invalid or overlapping punch transition")
        if latest is not None and command.occurred_at <= latest.occurred_at:
            raise WorkdayConflictError("punch time must follow prior punch")

    @staticmethod
    def _new_punch(
        context: AuthorizationContext, command: RecordPunch
    ) -> WorkdayPunchEvent:
        event_id = uuid4()
        request_digest = WorkdayTimeService._punch_request_digest(context, command)
        digest = canonical_digest(
            {
                "id": str(event_id),
                "company_id": str(context.company.id),
                "branch_id": str(command.branch_id) if command.branch_id else None,
                "employee_id": str(command.employee_id),
                "kind": command.kind.value,
                "occurred_at": command.occurred_at.isoformat(),
                "timezone": command.timezone,
                "recorded_by_user_id": str(context.user.id),
                "source_device_reference": command.source_device_reference,
                "idempotency_key": command.idempotency_key,
                "request_digest": request_digest,
            }
        )
        return WorkdayPunchEvent(
            id=event_id,
            company_id=context.company.id,
            branch_id=command.branch_id,
            employee_id=command.employee_id,
            kind=command.kind.value,
            occurred_at=command.occurred_at,
            timezone=command.timezone,
            recorded_by_user_id=context.user.id,
            source_device_reference=command.source_device_reference,
            idempotency_key=command.idempotency_key,
            request_digest=request_digest,
            event_digest=digest,
        )

    @staticmethod
    def _punch_request_digest(
        context: AuthorizationContext, command: RecordPunch
    ) -> str:
        return canonical_digest(
            {
                "company_id": str(context.company.id),
                "branch_id": str(command.branch_id) if command.branch_id else None,
                "employee_id": str(command.employee_id),
                "actor_user_id": str(context.user.id),
                "kind": command.kind.value,
                "timezone": command.timezone,
                "source_device_reference": command.source_device_reference,
            }
        )

    @staticmethod
    def _manual_request_digest(
        context: AuthorizationContext, command: RecordManualTime
    ) -> str:
        return canonical_digest(
            {
                "company_id": str(context.company.id),
                "branch_id": str(command.branch_id) if command.branch_id else None,
                "employee_id": str(command.employee_id),
                "actor_user_id": str(context.user.id),
                "work_date": command.work_date.isoformat(),
                "timezone": command.timezone,
                "start_at": command.start_at.isoformat() if command.start_at else None,
                "end_at": command.end_at.isoformat() if command.end_at else None,
                "approved_duration_minutes": command.approved_duration_minutes,
                "reason": command.reason.strip(),
            }
        )

    @staticmethod
    def _validate_idempotency_key(value: str) -> None:
        if not value.strip() or len(value) > 128:
            raise WorkdayTimeError("idempotency key must contain 1-128 characters")

    def _stage_action(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        event_type: EventType,
        entity_id: UUID,
        action: str,
        branch_id: UUID | None,
        details: dict[str, object],
    ) -> None:
        BusinessEventService.stage(
            session,
            BusinessEventCreate(
                event_type=event_type,
                entity_type="workday_time",
                entity_id=entity_id,
                company_id=context.company.id,
                branch_id=branch_id,
                user_id=context.user.id,
                payload=details,
            ),
        )
        self._audit.stage(
            session,
            AuditEntry(
                action=action,
                resource_type="workday_time",
                actor_user_id=context.user.id,
                company_id=context.company.id,
                branch_id=branch_id,
                resource_id=entity_id,
                details=details,
            ),
        )

    @staticmethod
    def _require_permission(context: AuthorizationContext, permission: str) -> None:
        if not context.has_permission(permission):
            raise WorkdayAuthorizationError("timekeeping permission denied")

    @staticmethod
    def _require_branch(context: AuthorizationContext, branch_id: UUID | None) -> None:
        if branch_id is not None and not context.can_access_branch(branch_id):
            raise WorkdayAuthorizationError("timekeeping Branch access denied")

    @staticmethod
    def _validate_timezone(timezone_name: str) -> None:
        try:
            ZoneInfo(timezone_name)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise WorkdayTimeError(
                "timekeeping timezone must be a valid IANA zone"
            ) from exc


workday_time_service = WorkdayTimeService()
