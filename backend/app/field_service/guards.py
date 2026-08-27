from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dispatch.models import (
    DispatchAssignment,
    DispatchAssignmentHistory,
    DispatchCrewMember,
)
from app.field_service.models import FieldCustomerApproval, FieldWorkNote
from app.jobs.errors import JobCompletionBlockedError, JobInvalidTransitionError
from app.jobs.guards import JobGuardContext
from app.platform.employees.models import Employee
from app.platform.permissions.authorization import AuthorizationContext


class FieldJobGuard:
    async def validate_execution(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        job: JobGuardContext,
        action: str,
    ) -> None:
        assignment = await self._assignment(session, context, job)
        if assignment is None:
            return
        await self._require_actor(session, context, assignment)
        if assignment.status == "reconciliation_required":
            raise JobInvalidTransitionError("Dispatch reconciliation is required.")
        if action == "start":
            arrived = await session.scalar(
                select(DispatchAssignmentHistory.id)
                .where(
                    DispatchAssignmentHistory.company_id == context.company.id,
                    DispatchAssignmentHistory.assignment_id == assignment.id,
                    DispatchAssignmentHistory.event_type == "technician_arrived",
                )
                .limit(1)
            )
            if arrived is None:
                raise JobInvalidTransitionError(
                    "Technician arrival is required before work starts."
                )

    async def validate_completion(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        job: JobGuardContext,
    ) -> None:
        assignment = await self._assignment(session, context, job)
        if assignment is None:
            return
        await self._require_actor(session, context, assignment)
        if assignment.status == "reconciliation_required":
            raise JobCompletionBlockedError("Dispatch reconciliation is required.")
        summary = await session.scalar(
            select(FieldWorkNote.id)
            .where(
                FieldWorkNote.company_id == context.company.id,
                FieldWorkNote.job_id == job.job_id,
                FieldWorkNote.note_type == "work_performed",
            )
            .limit(1)
        )
        approval = await session.scalar(
            select(FieldCustomerApproval.id)
            .where(
                FieldCustomerApproval.company_id == context.company.id,
                FieldCustomerApproval.job_id == job.job_id,
            )
            .limit(1)
        )
        if summary is None or approval is None:
            raise JobCompletionBlockedError(
                "Field work summary and customer disposition are required."
            )

    @staticmethod
    async def _assignment(
        session: AsyncSession, context: AuthorizationContext, job: JobGuardContext
    ) -> DispatchAssignment | None:
        return await session.scalar(
            select(DispatchAssignment)
            .where(
                DispatchAssignment.company_id == context.company.id,
                DispatchAssignment.branch_id == job.branch_id,
                DispatchAssignment.job_id == job.job_id,
                DispatchAssignment.status.in_(
                    ("assigned", "acknowledged", "reconciliation_required")
                ),
            )
            .limit(1)
        )

    @staticmethod
    async def _require_actor(
        session: AsyncSession,
        context: AuthorizationContext,
        assignment: DispatchAssignment,
    ) -> None:
        employee_ids = select(Employee.id).where(
            Employee.company_id == context.company.id,
            Employee.membership_id == context.membership.id,
            Employee.status == "active",
            Employee.archived_at.is_(None),
        )
        crew_ids = select(DispatchCrewMember.employee_id).where(
            DispatchCrewMember.company_id == context.company.id,
            DispatchCrewMember.assignment_id == assignment.id,
            DispatchCrewMember.status == "active",
        )
        assigned = await session.scalar(
            select(Employee.id)
            .where(
                Employee.id.in_(employee_ids),
                or_(
                    Employee.id == assignment.primary_employee_id,
                    Employee.id.in_(crew_ids),
                ),
            )
            .limit(1)
        )
        if assigned is None:
            raise JobInvalidTransitionError("Assigned technician was not found.")


field_job_guard = FieldJobGuard()
