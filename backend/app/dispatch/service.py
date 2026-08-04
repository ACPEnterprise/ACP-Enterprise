from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dispatch.errors import DispatchConflict, DispatchNotFound, DispatchValidation
from app.dispatch.models import (
    DispatchAssignment,
    DispatchAssignmentHistory,
    DispatchCrewMember,
)
from app.dispatch.schemas import (
    AssignmentItem,
    CrewMemberItem,
    DispatchBoardItem,
    DispatchBoardPage,
)
from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.jobs.models import JobAppointmentLink
from app.platform.employees.models import Employee
from app.platform.permissions.authorization import AuthorizationContext
from app.scheduling.models import Appointment
from app.workforce.query import WorkforceEligibilityQuery
from app.workforce.query_service import workforce_eligibility_service

ACTIVE = ("proposed", "assigned", "acknowledged", "reconciliation_required")


class DispatchService:
    async def board(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        start_at: datetime,
        end_at: datetime,
        branch_id: UUID | None,
    ) -> DispatchBoardPage:
        if end_at <= start_at:
            raise DispatchValidation("Dispatch range is invalid.")
        branches = (
            context.authorized_branch_ids
            if branch_id is None
            else frozenset({branch_id})
        )
        if branch_id is not None and not context.can_access_branch(branch_id):
            raise DispatchNotFound("Branch was not found.")
        appointments = tuple(
            (
                await session.scalars(
                    select(Appointment)
                    .where(
                        Appointment.company_id == context.company.id,
                        Appointment.branch_id.in_(branches),
                        Appointment.status.in_(("scheduled", "confirmed")),
                        Appointment.arrival_window_start_at < end_at,
                        Appointment.arrival_window_end_at > start_at,
                    )
                    .order_by(Appointment.arrival_window_start_at, Appointment.id)
                )
            ).all()
        )
        items: list[DispatchBoardItem] = []
        for appointment in appointments:
            if (
                appointment.arrival_window_start_at is None
                or appointment.arrival_window_end_at is None
            ):
                continue
            assignment = await self._get_assignment(
                session, context.company.id, appointment.id
            )
            job_id = await session.scalar(
                select(JobAppointmentLink.job_id)
                .where(
                    JobAppointmentLink.company_id == context.company.id,
                    JobAppointmentLink.appointment_id == appointment.id,
                )
                .limit(1)
            )
            items.append(
                DispatchBoardItem(
                    appointment_id=appointment.id,
                    appointment_number=appointment.appointment_number,
                    job_id=job_id,
                    branch_id=appointment.branch_id,
                    status=appointment.status,
                    window_start_at=appointment.arrival_window_start_at,
                    window_end_at=appointment.arrival_window_end_at,
                    assignment=await self._item(
                        session, assignment, appointment.appointment_number
                    )
                    if assignment
                    else None,
                )
            )
        return DispatchBoardPage(items=tuple(items), total_count=len(items))

    async def detail(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        appointment_id: UUID,
    ) -> AssignmentItem:
        appointment = await self._appointment(session, context, appointment_id)
        assignment = await self._get_assignment(
            session, context.company.id, appointment_id
        )
        if assignment is None:
            raise DispatchNotFound("Assignment was not found.")
        return await self._item(session, assignment, appointment.appointment_number)

    async def eligible(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        appointment_id: UUID,
    ):
        appointment = await self._appointment(session, context, appointment_id)
        if (
            appointment.arrival_window_start_at is None
            or appointment.arrival_window_end_at is None
        ):
            raise DispatchValidation("Appointment has no authoritative time window.")
        return await workforce_eligibility_service.eligible_technicians(
            session,
            context=context,
            query=WorkforceEligibilityQuery(
                company_id=context.company.id,
                authorized_branch_ids=context.authorized_branch_ids,
                branch_id=appointment.branch_id,
                window_start_at=appointment.arrival_window_start_at,
                window_end_at=appointment.arrival_window_end_at,
            ),
        )

    async def assign(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        appointment_id: UUID,
        employee_id: UUID,
        reason: str,
        idempotency_key: str,
        expected_version: int | None = None,
    ) -> AssignmentItem:
        async with session.begin():
            appointment = await self._appointment(
                session, context, appointment_id, lock=True
            )
            existing = await self._get_assignment(
                session, context.company.id, appointment_id, lock=True
            )
            if (
                await self._duplicate(session, context.company.id, idempotency_key)
                and existing
            ):
                return await self._item(
                    session, existing, appointment.appointment_number
                )
            if existing and existing.status in ACTIVE:
                if existing.primary_employee_id == employee_id:
                    return await self._item(
                        session, existing, appointment.appointment_number
                    )
                raise DispatchConflict(
                    "A primary technician is already assigned; use replacement."
                )
            if (
                appointment.arrival_window_start_at is None
                or appointment.arrival_window_end_at is None
            ):
                raise DispatchValidation(
                    "Appointment has no authoritative time window."
                )
            await self._employee_lock(session, context.company.id, employee_id)
            await self._require_eligible(session, context, appointment, employee_id)
            job_id = await session.scalar(
                select(JobAppointmentLink.job_id)
                .where(
                    JobAppointmentLink.company_id == context.company.id,
                    JobAppointmentLink.appointment_id == appointment.id,
                )
                .limit(1)
            )
            now = datetime.now(timezone.utc)
            if existing is None:
                assignment = DispatchAssignment(
                    company_id=context.company.id,
                    branch_id=appointment.branch_id,
                    appointment_id=appointment.id,
                    job_id=job_id,
                    primary_employee_id=employee_id,
                    status="assigned",
                    assignment_reason=reason,
                    assigned_by_user_id=context.user.id,
                    window_start_at=appointment.arrival_window_start_at,
                    window_end_at=appointment.arrival_window_end_at,
                    effective_at=now,
                    version=1,
                    created_at=now,
                    updated_at=now,
                )
                session.add(assignment)
                await session.flush()
            else:
                if (
                    expected_version is not None
                    and existing.version != expected_version
                ):
                    raise DispatchConflict("Assignment version is stale.")
                assignment = existing
                assignment.primary_employee_id = employee_id
                assignment.status = "assigned"
                assignment.assignment_reason = reason
                assignment.assigned_by_user_id = context.user.id
                assignment.effective_at = now
                assignment.released_at = None
                assignment.release_reason = None
                assignment.version += 1
                assignment.updated_at = now
            self._history(
                session,
                assignment,
                "created",
                None,
                "assigned",
                context.user.id,
                reason,
                idempotency_key,
            )
            self._event(
                session,
                assignment,
                EventType.DISPATCH_ASSIGNMENT_CREATED,
                context.user.id,
            )
            await session.flush()
            return await self._item(session, assignment, appointment.appointment_number)

    async def replace(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        appointment_id: UUID,
        employee_id: UUID,
        reason: str,
        idempotency_key: str,
        expected_version: int,
    ) -> AssignmentItem:
        async with session.begin():
            appointment = await self._appointment(
                session, context, appointment_id, lock=True
            )
            assignment = await self._required_assignment(
                session, context.company.id, appointment_id, lock=True
            )
            if await self._duplicate(session, context.company.id, idempotency_key):
                return await self._item(
                    session, assignment, appointment.appointment_number
                )
            self._version(assignment, expected_version)
            await self._employee_lock(session, context.company.id, employee_id)
            await self._require_eligible(session, context, appointment, employee_id)
            old = assignment.primary_employee_id
            now = datetime.now(timezone.utc)
            assignment.primary_employee_id = employee_id
            assignment.status = "assigned"
            assignment.assignment_reason = reason
            assignment.assigned_by_user_id = context.user.id
            assignment.replaced_at = now
            assignment.effective_at = now
            assignment.version += 1
            assignment.updated_at = now
            self._history(
                session,
                assignment,
                "replaced",
                "assigned",
                "assigned",
                context.user.id,
                reason,
                idempotency_key,
            )
            self._event(
                session,
                assignment,
                EventType.DISPATCH_ASSIGNMENT_REPLACED,
                context.user.id,
                {"prior_employee_id": str(old) if old else None},
            )
            await session.flush()
            return await self._item(session, assignment, appointment.appointment_number)

    async def release(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        appointment_id: UUID,
        reason: str,
        idempotency_key: str,
        expected_version: int,
    ) -> AssignmentItem:
        async with session.begin():
            appointment = await self._appointment(
                session, context, appointment_id, lock=True
            )
            assignment = await self._required_assignment(
                session, context.company.id, appointment_id, lock=True
            )
            if (
                await self._duplicate(session, context.company.id, idempotency_key)
                or assignment.status == "released"
            ):
                return await self._item(
                    session, assignment, appointment.appointment_number
                )
            self._version(assignment, expected_version)
            prior = assignment.status
            assignment.status = "released"
            assignment.released_at = datetime.now(timezone.utc)
            assignment.release_reason = reason
            assignment.version += 1
            self._history(
                session,
                assignment,
                "released",
                prior,
                "released",
                context.user.id,
                reason,
                idempotency_key,
            )
            self._event(
                session,
                assignment,
                EventType.DISPATCH_ASSIGNMENT_RELEASED,
                context.user.id,
            )
            await session.flush()
            return await self._item(session, assignment, appointment.appointment_number)

    async def crew(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        appointment_id: UUID,
        employee_id: UUID,
        reason: str,
        idempotency_key: str,
        expected_version: int,
        remove: bool = False,
    ) -> AssignmentItem:
        async with session.begin():
            appointment = await self._appointment(
                session, context, appointment_id, lock=True
            )
            assignment = await self._required_assignment(
                session, context.company.id, appointment_id, lock=True
            )
            self._version(assignment, expected_version)
            if await self._duplicate(session, context.company.id, idempotency_key):
                return await self._item(
                    session, assignment, appointment.appointment_number
                )
            member = await session.scalar(
                select(DispatchCrewMember)
                .where(
                    DispatchCrewMember.company_id == context.company.id,
                    DispatchCrewMember.assignment_id == assignment.id,
                    DispatchCrewMember.employee_id == employee_id,
                    DispatchCrewMember.status == "active",
                )
                .with_for_update()
            )
            if remove:
                if member is None:
                    return await self._item(
                        session, assignment, appointment.appointment_number
                    )
                member.status = "removed"
                member.removed_by_user_id = context.user.id
                member.removed_at = datetime.now(timezone.utc)
                member.removal_reason = reason
                member.version += 1
                event = EventType.DISPATCH_CREW_MEMBER_REMOVED
                kind = "crew_removed"
            else:
                if employee_id == assignment.primary_employee_id:
                    raise DispatchConflict(
                        "Primary technician cannot also be a crew member."
                    )
                if member is not None:
                    return await self._item(
                        session, assignment, appointment.appointment_number
                    )
                await self._employee_lock(session, context.company.id, employee_id)
                await self._require_eligible(session, context, appointment, employee_id)
                session.add(
                    DispatchCrewMember(
                        company_id=context.company.id,
                        assignment_id=assignment.id,
                        employee_id=employee_id,
                        added_by_user_id=context.user.id,
                    )
                )
                event = EventType.DISPATCH_CREW_MEMBER_ADDED
                kind = "crew_added"
            assignment.version += 1
            assignment.updated_at = datetime.now(timezone.utc)
            self._history(
                session,
                assignment,
                kind,
                assignment.status,
                assignment.status,
                context.user.id,
                reason,
                idempotency_key,
            )
            self._event(
                session,
                assignment,
                event,
                context.user.id,
                {"employee_id": str(employee_id)},
            )
            await session.flush()
            return await self._item(session, assignment, appointment.appointment_number)

    async def reconcile(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        appointment_id: UUID,
        reason: str,
        idempotency_key: str,
        expected_version: int,
        resolution: str | None = None,
    ) -> AssignmentItem:
        async with session.begin():
            appointment = await self._appointment(
                session, context, appointment_id, lock=True
            )
            assignment = await self._required_assignment(
                session, context.company.id, appointment_id, lock=True
            )
            if await self._duplicate(session, context.company.id, idempotency_key):
                return await self._item(
                    session, assignment, appointment.appointment_number
                )
            self._version(assignment, expected_version)
            prior = assignment.status
            if resolution is None:
                new = "reconciliation_required"
                event = EventType.DISPATCH_ASSIGNMENT_RECONCILIATION_REQUIRED
                kind = "reconciliation_required"
            elif prior != "reconciliation_required":
                raise DispatchConflict("Assignment does not require reconciliation.")
            elif resolution == "restore_assigned":
                new = "assigned"
                event = EventType.DISPATCH_ASSIGNMENT_RECONCILED
                kind = "reconciled"
            else:
                new = "released"
                assignment.released_at = datetime.now(timezone.utc)
                assignment.release_reason = reason
                event = EventType.DISPATCH_ASSIGNMENT_RECONCILED
                kind = "reconciled"
            assignment.status = new
            assignment.version += 1
            assignment.updated_at = datetime.now(timezone.utc)
            self._history(
                session,
                assignment,
                kind,
                prior,
                new,
                context.user.id,
                reason,
                idempotency_key,
            )
            self._event(
                session, assignment, event, context.user.id, {"resolution": resolution}
            )
            await session.flush()
            return await self._item(session, assignment, appointment.appointment_number)

    async def _appointment(self, session, context, appointment_id, lock=False):
        stmt = select(Appointment).where(
            Appointment.company_id == context.company.id,
            Appointment.id == appointment_id,
            Appointment.branch_id.in_(context.authorized_branch_ids),
        )
        stmt = stmt.with_for_update() if lock else stmt
        item = await session.scalar(stmt)
        if item is None:
            raise DispatchNotFound("Appointment was not found.")
        if item.status not in {"scheduled", "confirmed"}:
            raise DispatchConflict(
                "Appointment is not assignable in its current lifecycle state."
            )
        return item

    async def _require_eligible(self, session, context, appointment, employee_id):
        options = await self.eligible(
            session, context=context, appointment_id=appointment.id
        )
        option = next((x for x in options if x.employee_id == employee_id), None)
        if option is None:
            raise DispatchNotFound(
                "Employee was not found in the authorized Workforce scope."
            )
        if not option.eligible:
            raise DispatchConflict(f"Technician is not eligible: {option.decision}.")

    async def _get_assignment(self, session, company_id, appointment_id, lock=False):
        stmt = select(DispatchAssignment).where(
            DispatchAssignment.company_id == company_id,
            DispatchAssignment.appointment_id == appointment_id,
        )
        stmt = stmt.with_for_update() if lock else stmt
        return await session.scalar(stmt)

    async def _required_assignment(
        self, session, company_id, appointment_id, lock=False
    ):
        item = await self._get_assignment(session, company_id, appointment_id, lock)
        if item is None:
            raise DispatchNotFound("Assignment was not found.")
        return item

    async def _duplicate(self, session, company_id, key):
        return (
            await session.scalar(
                select(DispatchAssignmentHistory.id).where(
                    DispatchAssignmentHistory.company_id == company_id,
                    DispatchAssignmentHistory.evidence_reference == key,
                )
            )
            is not None
        )

    @staticmethod
    def _version(item, expected):
        if item.version != expected:
            raise DispatchConflict("Assignment version is stale.")

    @staticmethod
    async def _employee_lock(session, company_id, employee_id) -> None:
        """Serialize assignment decisions for one Company employee."""
        await session.execute(
            select(
                func.pg_advisory_xact_lock(
                    func.hashtextextended(f"{company_id}:{employee_id}", 0)
                )
            )
        )

    @staticmethod
    def _history(session, item, kind, prior, new, actor, reason, key):
        session.add(
            DispatchAssignmentHistory(
                company_id=item.company_id,
                assignment_id=item.id,
                event_type=kind,
                prior_status=prior,
                new_status=new,
                primary_employee_id=item.primary_employee_id,
                actor_user_id=actor,
                reason=reason,
                evidence_reference=key,
                version=item.version,
            )
        )

    @staticmethod
    def _event(session, item, event, actor, extra=None):
        BusinessEventService.stage(
            session,
            BusinessEventCreate(
                event_type=event,
                entity_type="dispatch_assignment",
                entity_id=item.id,
                company_id=item.company_id,
                branch_id=item.branch_id,
                user_id=actor,
                payload={
                    "assignment_id": str(item.id),
                    "appointment_id": str(item.appointment_id),
                    "job_id": str(item.job_id) if item.job_id else None,
                    "primary_employee_id": str(item.primary_employee_id)
                    if item.primary_employee_id
                    else None,
                    "status": item.status,
                    "version": item.version,
                    **(extra or {}),
                },
            ),
        )

    async def _item(self, session, item, number):
        primary = (
            await session.scalar(
                select(Employee.display_name).where(
                    Employee.company_id == item.company_id,
                    Employee.id == item.primary_employee_id,
                )
            )
            if item.primary_employee_id
            else None
        )
        rows = (
            await session.execute(
                select(DispatchCrewMember, Employee.display_name)
                .join(
                    Employee,
                    and_(
                        Employee.company_id == DispatchCrewMember.company_id,
                        Employee.id == DispatchCrewMember.employee_id,
                    ),
                )
                .where(
                    DispatchCrewMember.company_id == item.company_id,
                    DispatchCrewMember.assignment_id == item.id,
                    DispatchCrewMember.status == "active",
                )
                .order_by(Employee.display_name)
            )
        ).all()
        crew = tuple(
            CrewMemberItem(
                id=m.id,
                employee_id=m.employee_id,
                display_name=name,
                status=m.status,
                added_at=m.added_at,
            )
            for m, name in rows
        )
        return AssignmentItem(
            id=item.id,
            appointment_id=item.appointment_id,
            appointment_number=number,
            job_id=item.job_id,
            company_id=item.company_id,
            branch_id=item.branch_id,
            primary_employee_id=item.primary_employee_id,
            primary_employee_name=primary,
            status=item.status,
            assignment_reason=item.assignment_reason,
            window_start_at=item.window_start_at,
            window_end_at=item.window_end_at,
            effective_at=item.effective_at,
            released_at=item.released_at,
            version=item.version,
            crew_members=crew,
        )


dispatch_service = DispatchService()
