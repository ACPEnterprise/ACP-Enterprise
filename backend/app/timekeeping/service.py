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

from .commands import CorrectTimeEntry, CreatePayPeriod, RecordManualTime, RecordPunch
from .contracts import (
    ApprovedWorkdayTimeFact,
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
        if not command.reason.strip():
            raise WorkdayTimeError("correction reason is required")
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
        await session.commit()
        return result

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
        revisions = await self._repository.current_employee_revisions(
            session,
            company_id=context.company.id,
            employee_id=employee_id,
            start_date=pay_period.period_start,
            end_date=pay_period.period_end,
        )
        facts = tuple(
            self._approved_fact(value)
            for value in revisions
            if value.state == TimeEntryState.APPROVED.value
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
            raise WorkdayTimeError("timekeeping timezone must be a valid IANA zone") from exc


workday_time_service = WorkdayTimeService()
