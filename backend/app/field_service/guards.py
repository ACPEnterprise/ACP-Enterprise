from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dispatch.models import (
    DispatchAssignment,
    DispatchAssignmentHistory,
    DispatchCrewMember,
)
from app.estimates.models import Estimate, EstimateJobConversion
from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.field_service.models import (
    FieldCompletionEvidence,
    FieldCompletionRequirementSnapshot,
    FieldNonBillableDisposition,
)
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
        correlation_id: UUID,
    ) -> None:
        assignment = await self._assignment(session, context, job)
        if assignment is None:
            return
        await self._require_actor(session, context, assignment)
        if assignment.status == "reconciliation_required":
            raise JobCompletionBlockedError("Dispatch reconciliation is required.")
        snapshot = await session.scalar(
            select(FieldCompletionRequirementSnapshot)
            .where(
                FieldCompletionRequirementSnapshot.company_id == context.company.id,
                FieldCompletionRequirementSnapshot.job_id == job.job_id,
            )
            .with_for_update()
        )
        if snapshot is None:
            raise JobCompletionBlockedError(
                "Immutable field completion requirements were not established."
            )
        evidence = set(
            (
                await session.scalars(
                    select(FieldCompletionEvidence.requirement_code).where(
                        FieldCompletionEvidence.company_id == context.company.id,
                        FieldCompletionEvidence.snapshot_id == snapshot.id,
                    )
                )
            ).all()
        )
        accepted_estimate = await session.scalar(
            select(Estimate.id)
            .join(
                EstimateJobConversion,
                (EstimateJobConversion.company_id == Estimate.company_id)
                & (EstimateJobConversion.estimate_id == Estimate.id),
            )
            .where(
                Estimate.company_id == context.company.id,
                Estimate.branch_id == job.branch_id,
                EstimateJobConversion.job_id == job.job_id,
                Estimate.status.in_(("approved", "accepted")),
                Estimate.acceptance_status.in_(("approved", "accepted")),
            )
            .limit(1)
        )
        non_billable = await session.scalar(
            select(FieldNonBillableDisposition).where(
                FieldNonBillableDisposition.company_id == context.company.id,
                FieldNonBillableDisposition.job_id == job.job_id,
                FieldNonBillableDisposition.active.is_(True),
            )
        )
        commercial_source = accepted_estimate or (
            non_billable.id if non_billable else None
        )
        if commercial_source is not None and "commercial_authorization" not in evidence:
            session.add(
                FieldCompletionEvidence(
                    company_id=context.company.id,
                    branch_id=job.branch_id,
                    job_id=job.job_id,
                    snapshot_id=snapshot.id,
                    requirement_code="commercial_authorization",
                    source_type=(
                        "accepted_estimate"
                        if accepted_estimate
                        else "field_non_billable_disposition"
                    ),
                    source_id=commercial_source,
                    recorded_by_user_id=context.user.id,
                )
            )
            evidence.add("commercial_authorization")
        missing = [code for code in snapshot.requirements if code not in evidence]
        if missing:
            raise JobCompletionBlockedError(
                "Field completion requirements are missing: " + ", ".join(missing)
            )
        BusinessEventService.stage(
            session,
            BusinessEventCreate(
                event_type=EventType.FIELD_COMPLETION_REQUIREMENTS_SATISFIED,
                entity_type="field_job",
                entity_id=job.job_id,
                company_id=context.company.id,
                branch_id=job.branch_id,
                user_id=context.user.id,
                correlation_id=correlation_id,
                payload={
                    "job_id": str(job.job_id),
                    "snapshot_id": str(snapshot.id),
                    "snapshot_version": snapshot.version,
                    "requirements_fingerprint": snapshot.requirements_fingerprint,
                },
            ),
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
