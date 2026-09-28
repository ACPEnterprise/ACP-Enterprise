"""Authorized, owner-readable Employee history assembled from canonical evidence."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dispatch.models import DispatchAssignmentHistory
from app.platform.audit.models import AuditRecord
from app.platform.company.membership_models import Membership
from app.platform.employees.models import Employee
from app.platform.onboarding.models import IdentityOnboardingRequest
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.models import MembershipRole, Role
from app.platform.users.models import User
from app.timekeeping.models import JobWorkedClockEvent, WorkdayPunchEvent
from app.workforce.models import (
    Capability,
    WorkforceCapability,
    WorkforceCapabilityProfile,
    WorkforceWorkingAvailability,
)
from app.workforce.schemas import EmployeeTimeline, EmployeeTimelineItem


class EmployeeTimelineService:
    async def read(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        employee_id: UUID,
    ) -> EmployeeTimeline | None:
        employee = await session.scalar(
            select(Employee).where(
                Employee.company_id == context.company.id,
                Employee.id == employee_id,
            )
        )
        if employee is None:
            return None

        actor_ids: set[UUID] = set()
        items = [
            self._item(
                "EMPLOYEE_CREATED",
                employee.created_at,
                "employee",
                "Employee record created.",
                employee_id,
                employee.created_by_user_id,
            )
        ]
        if employee.created_by_user_id:
            actor_ids.add(employee.created_by_user_id)

        onboarding = await session.scalar(
            select(IdentityOnboardingRequest).where(
                IdentityOnboardingRequest.company_id == context.company.id,
                IdentityOnboardingRequest.employee_id == employee_id,
            )
        )
        if onboarding:
            actor_ids.add(onboarding.initiated_by_user_id)
            items.append(
                self._item(
                    "ONBOARDING_STARTED",
                    onboarding.created_at,
                    "identity_onboarding",
                    "Protected Employee onboarding started.",
                    employee_id,
                    onboarding.initiated_by_user_id,
                    "/administration/identity-onboarding",
                )
            )
            if onboarding.activated_at:
                items.append(
                    self._item(
                        "ACCOUNT_ACTIVATED",
                        onboarding.activated_at,
                        "identity_onboarding",
                        "Employee established account access.",
                        employee_id,
                        None,
                        "/employees",
                    )
                )

        membership = None
        if employee.membership_id:
            membership = await session.scalar(
                select(Membership).where(
                    Membership.company_id == context.company.id,
                    Membership.id == employee.membership_id,
                )
            )
        if membership:
            items.append(
                self._item(
                    "MEMBERSHIP_CREATED",
                    membership.created_at,
                    "membership",
                    f"Company Membership created with {membership.status} status.",
                    employee_id,
                    None,
                )
            )
            roles = (
                await session.execute(
                    select(MembershipRole, Role)
                    .join(Role, Role.id == MembershipRole.role_id)
                    .where(
                        MembershipRole.company_id == context.company.id,
                        MembershipRole.membership_id == membership.id,
                    )
                )
            ).all()
            for assignment, role in roles:
                if assignment.assigned_by_user_id:
                    actor_ids.add(assignment.assigned_by_user_id)
                items.append(
                    self._item(
                        "MOBILE_ROLE_ASSIGNED"
                        if role.code == "ACP_EMPLOYEE_MOBILE"
                        else "ROLE_ASSIGNED",
                        assignment.assigned_at,
                        "membership_role",
                        f"{role.name} role assigned.",
                        employee_id,
                        assignment.assigned_by_user_id,
                    )
                )
                if assignment.revoked_at:
                    items.append(
                        self._item(
                            "MOBILE_ROLE_REMOVED"
                            if role.code == "ACP_EMPLOYEE_MOBILE"
                            else "ROLE_REMOVED",
                            assignment.revoked_at,
                            "membership_role",
                            f"{role.name} role removed.",
                            employee_id,
                            None,
                        )
                    )

        access_events = (
            await session.scalars(
                select(AuditRecord)
                .where(
                    AuditRecord.company_id == context.company.id,
                    AuditRecord.resource_type == "employee",
                    AuditRecord.resource_id == employee_id,
                    AuditRecord.action.in_(
                        (
                            "workforce.employee_access_locked",
                            "workforce.employee_access_unlocked",
                        )
                    ),
                )
                .order_by(AuditRecord.occurred_at, AuditRecord.id)
            )
        ).all()
        for event in access_events:
            if event.actor_user_id:
                actor_ids.add(event.actor_user_id)
            locked = event.action.endswith("_locked")
            items.append(
                self._item(
                    "ACCESS_LOCKED" if locked else "ACCESS_UNLOCKED",
                    event.occurred_at,
                    "security_audit",
                    f"Employee access {'locked' if locked else 'unlocked'}; employment and operating history were unchanged.",
                    employee_id,
                    event.actor_user_id,
                )
            )

        profile = await session.scalar(
            select(WorkforceCapabilityProfile).where(
                WorkforceCapabilityProfile.company_id == context.company.id,
                WorkforceCapabilityProfile.employee_id == employee_id,
            )
        )
        if profile:
            capabilities = (
                await session.execute(
                    select(WorkforceCapability, Capability)
                    .join(
                        Capability, Capability.id == WorkforceCapability.capability_id
                    )
                    .where(
                        WorkforceCapability.company_id == context.company.id,
                        WorkforceCapability.profile_id == profile.id,
                    )
                )
            ).all()
            for evidence, capability in capabilities:
                items.append(
                    self._item(
                        "CAPABILITY_CERTIFIED",
                        evidence.verified_at or evidence.created_at,
                        "workforce_capability",
                        f"{capability.display_name} capability recorded as {evidence.status}.",
                        employee_id,
                        None,
                    )
                )
            availability = (
                await session.scalars(
                    select(WorkforceWorkingAvailability).where(
                        WorkforceWorkingAvailability.company_id == context.company.id,
                        WorkforceWorkingAvailability.profile_id == profile.id,
                    )
                )
            ).all()
            for window in availability:
                items.append(
                    self._item(
                        "AVAILABILITY_RECORDED",
                        window.created_at,
                        "workforce_availability",
                        f"Bounded Branch availability recorded as {window.status}.",
                        employee_id,
                        None,
                    )
                )

        assignment_history = (
            await session.scalars(
                select(DispatchAssignmentHistory).where(
                    DispatchAssignmentHistory.company_id == context.company.id,
                    DispatchAssignmentHistory.primary_employee_id == employee_id,
                )
            )
        ).all()
        for dispatch_event in assignment_history:
            actor_ids.add(dispatch_event.actor_user_id)
            items.append(
                self._item(
                    "ASSIGNMENT_CHANGED",
                    dispatch_event.occurred_at,
                    "dispatch_assignment",
                    f"Dispatch assignment changed to {dispatch_event.new_status}.",
                    employee_id,
                    dispatch_event.actor_user_id,
                    "/dispatch",
                )
            )

        punches = (
            await session.scalars(
                select(WorkdayPunchEvent).where(
                    WorkdayPunchEvent.company_id == context.company.id,
                    WorkdayPunchEvent.employee_id == employee_id,
                )
            )
        ).all()
        for punch_event in punches:
            actor_ids.add(punch_event.recorded_by_user_id)
            items.append(
                self._item(
                    "TIMEKEEPING_PUNCH",
                    punch_event.occurred_at,
                    "timekeeping",
                    f"{punch_event.kind.replace('_', ' ').title()} recorded.",
                    employee_id,
                    punch_event.recorded_by_user_id,
                    "/employees#timecard-operations",
                )
            )

        job_clocks = (
            await session.scalars(
                select(JobWorkedClockEvent).where(
                    JobWorkedClockEvent.company_id == context.company.id,
                    JobWorkedClockEvent.employee_id == employee_id,
                )
            )
        ).all()
        for clock_event in job_clocks:
            actor_ids.add(clock_event.recorded_by_user_id)
            items.append(
                self._item(
                    "JOB_CLOCK_STARTED"
                    if clock_event.kind == "start"
                    else "JOB_CLOCK_STOPPED",
                    clock_event.occurred_at,
                    "job_timekeeping",
                    "Job clock started."
                    if clock_event.kind == "start"
                    else "Job clock stopped.",
                    employee_id,
                    clock_event.recorded_by_user_id,
                    f"/jobs/{clock_event.job_id}",
                )
            )

        actors = await self._actors(session, actor_ids)
        resolved = [
            item.model_copy(
                update={"actor_display_name": actors.get(str(item.actor_user_id))}
            )
            if item.actor_user_id
            else item
            for item in items
        ]
        resolved.sort(key=lambda item: item.occurred_at, reverse=True)
        return EmployeeTimeline(employee_id=employee_id, items=tuple(resolved))

    @staticmethod
    async def _actors(session: AsyncSession, actor_ids: set[UUID]) -> dict[str, str]:
        if not actor_ids:
            return {}
        users = (
            await session.scalars(select(User).where(User.id.in_(actor_ids)))
        ).all()
        return {str(user.id): user.display_name for user in users}

    @staticmethod
    def _item(
        event_type,
        occurred_at,
        source,
        description,
        employee_id,
        actor_id,
        navigation=None,
    ):
        return EmployeeTimelineItem(
            event_type=event_type,
            occurred_at=occurred_at,
            authority="ACP_NATIVE",
            source=source,
            actor_user_id=actor_id,
            actor_display_name=None,
            description=description,
            employee_id=employee_id,
            navigation_reference=navigation,
        )


employee_timeline_service = EmployeeTimelineService()
