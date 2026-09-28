from zoneinfo import ZoneInfo

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dispatch.models import DispatchAssignment, DispatchCrewMember
from app.platform.branch.models import Branch
from app.platform.company.membership_models import Membership, MembershipBranchAccess
from app.platform.employees.models import Employee
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.models import MembershipRole, Role
from app.platform.users.models import User
from app.scheduling.models import (
    BranchSchedulingCalendar,
    BranchSchedulingException,
    BranchSchedulingWeeklyInterval,
)
from app.workforce.employee_identity_classification import employee_is_synthetic
from app.workforce.models import (
    Capability,
    Language,
    WorkforceBranchEligibility,
    WorkforceCapability,
    WorkforceCapabilityProfile,
    WorkforceLanguageCapability,
    WorkforceWorkingAvailability,
)
from app.workforce.query import EligibleTechnician, WorkforceEligibilityQuery


class WorkforceEligibilityService:
    """Read-only, immutable eligibility projection over Workforce-owned facts."""

    async def eligible_technicians(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        query: WorkforceEligibilityQuery,
    ) -> tuple[EligibleTechnician, ...]:
        if (
            query.company_id != context.company.id
            or query.authorized_branch_ids != context.authorized_branch_ids
            or not context.can_access_branch(query.branch_id)
        ):
            raise ValueError("Workforce query scope is invalid.")
        if query.window_end_at <= query.window_start_at:
            raise ValueError("Assignment window is invalid.")
        today = query.window_start_at.date()
        rows = (
            await session.execute(
                select(Employee, WorkforceCapabilityProfile, WorkforceBranchEligibility)
                .outerjoin(
                    WorkforceCapabilityProfile,
                    and_(
                        WorkforceCapabilityProfile.company_id == Employee.company_id,
                        WorkforceCapabilityProfile.employee_id == Employee.id,
                    ),
                )
                .outerjoin(
                    WorkforceBranchEligibility,
                    and_(
                        WorkforceBranchEligibility.company_id == Employee.company_id,
                        WorkforceBranchEligibility.profile_id
                        == WorkforceCapabilityProfile.id,
                        WorkforceBranchEligibility.branch_id == query.branch_id,
                        WorkforceBranchEligibility.status == "active",
                        or_(
                            WorkforceBranchEligibility.starts_on.is_(None),
                            WorkforceBranchEligibility.starts_on <= today,
                        ),
                        or_(
                            WorkforceBranchEligibility.ends_on.is_(None),
                            WorkforceBranchEligibility.ends_on >= today,
                        ),
                    ),
                )
                .where(
                    Employee.company_id == query.company_id,
                    Employee.archived_at.is_(None),
                )
                .order_by(Employee.display_name, Employee.id)
            )
        ).all()
        branch_schedule_available = await self._branch_schedule_available(
            session, query=query
        )
        result: list[EligibleTechnician] = []
        for employee, profile, branch_eligibility in rows:
            if await employee_is_synthetic(session, employee=employee):
                continue
            membership = (
                None
                if employee.membership_id is None
                else await session.scalar(
                    select(Membership).where(
                        Membership.company_id == query.company_id,
                        Membership.id == employee.membership_id,
                    )
                )
            )
            user = (
                None
                if membership is None
                else await session.scalar(
                    select(User).where(
                        User.id == membership.user_id,
                        User.status == "active",
                        User.archived_at.is_(None),
                    )
                )
            )
            role_codes = (
                frozenset()
                if membership is None
                else frozenset(
                    await session.scalars(
                        select(Role.code)
                        .join(MembershipRole, MembershipRole.role_id == Role.id)
                        .where(
                            MembershipRole.company_id == query.company_id,
                            MembershipRole.membership_id == membership.id,
                            MembershipRole.revoked_at.is_(None),
                            or_(
                                MembershipRole.effective_at.is_(None),
                                MembershipRole.effective_at <= query.window_start_at,
                            ),
                            or_(
                                MembershipRole.expires_at.is_(None),
                                MembershipRole.expires_at > query.window_start_at,
                            ),
                            Role.status == "active",
                            Role.archived_at.is_(None),
                        )
                    )
                )
            )
            explicit_branch_access = bool(
                membership
                and await session.scalar(
                    select(MembershipBranchAccess.id)
                    .where(
                        MembershipBranchAccess.membership_id == membership.id,
                        MembershipBranchAccess.branch_id == query.branch_id,
                    )
                    .limit(1)
                )
            )
            membership_branch_ready = bool(
                membership
                and (
                    membership.has_all_branch_access
                    or membership.default_branch_id == query.branch_id
                    or explicit_branch_access
                )
            )
            capabilities = (
                ()
                if profile is None
                else tuple(
                    (
                        await session.scalars(
                            select(Capability.code)
                            .join(
                                WorkforceCapability,
                                WorkforceCapability.capability_id == Capability.id,
                            )
                            .where(
                                WorkforceCapability.company_id == query.company_id,
                                WorkforceCapability.profile_id == profile.id,
                                WorkforceCapability.status == "active",
                                Capability.status == "active",
                            )
                            .order_by(Capability.code)
                        )
                    ).all()
                )
            )
            languages = (
                ()
                if profile is None
                else tuple(
                    (
                        await session.scalars(
                            select(Language.code)
                            .join(
                                WorkforceLanguageCapability,
                                WorkforceLanguageCapability.language_id == Language.id,
                            )
                            .where(
                                WorkforceLanguageCapability.company_id
                                == query.company_id,
                                WorkforceLanguageCapability.profile_id == profile.id,
                                WorkforceLanguageCapability.status == "active",
                                WorkforceLanguageCapability.customer_facing_eligible.is_(
                                    True
                                ),
                                Language.status == "active",
                            )
                            .order_by(Language.code)
                        )
                    ).all()
                )
            )
            conflict = await session.scalar(
                select(DispatchAssignment.id)
                .where(
                    DispatchAssignment.company_id == query.company_id,
                    DispatchAssignment.primary_employee_id == employee.id,
                    DispatchAssignment.status.in_(
                        (
                            "proposed",
                            "assigned",
                            "acknowledged",
                            "reconciliation_required",
                        )
                    ),
                    DispatchAssignment.window_start_at < query.window_end_at,
                    DispatchAssignment.window_end_at > query.window_start_at,
                    *(
                        (
                            DispatchAssignment.appointment_id
                            != query.exclude_appointment_id,
                        )
                        if query.exclude_appointment_id is not None
                        else ()
                    ),
                )
                .limit(1)
            )
            crew_conflict = await session.scalar(
                select(DispatchCrewMember.id)
                .join(
                    DispatchAssignment,
                    DispatchAssignment.id == DispatchCrewMember.assignment_id,
                )
                .where(
                    DispatchCrewMember.company_id == query.company_id,
                    DispatchCrewMember.employee_id == employee.id,
                    DispatchCrewMember.status == "active",
                    DispatchAssignment.status.in_(
                        (
                            "proposed",
                            "assigned",
                            "acknowledged",
                            "reconciliation_required",
                        )
                    ),
                    DispatchAssignment.window_start_at < query.window_end_at,
                    DispatchAssignment.window_end_at > query.window_start_at,
                    *(
                        (
                            DispatchAssignment.appointment_id
                            != query.exclude_appointment_id,
                        )
                        if query.exclude_appointment_id is not None
                        else ()
                    ),
                )
                .limit(1)
            )
            reasons: list[str] = []
            if membership is None or membership.status != "active" or user is None:
                reasons.append("identity_not_ready")
            if not membership_branch_ready:
                reasons.append("membership_branch_not_ready")
            if "TECHNICIAN" not in role_codes:
                reasons.append("technician_role_missing")
            if employee.hire_date is not None and employee.hire_date > today:
                reasons.append("employment_not_yet_effective")
            if (
                employee.termination_date is not None
                and employee.termination_date <= today
            ):
                reasons.append("employment_ended")
            if employee.status != "active" or (
                profile is not None and profile.status != "active"
            ):
                reasons.append("inactive")
            if (
                branch_eligibility is None
                and employee.home_branch_id != query.branch_id
            ):
                reasons.append("wrong_branch")
            if not query.required_capability_codes.issubset(capabilities):
                reasons.append("missing_required_capability")
            if not query.required_language_codes.issubset(languages):
                reasons.append("missing_required_language")
            if conflict or crew_conflict:
                reasons.append("conflicting_assignment")
            availability = (
                None
                if profile is None
                else await session.scalar(
                    select(WorkforceWorkingAvailability)
                    .where(
                        WorkforceWorkingAvailability.company_id == query.company_id,
                        WorkforceWorkingAvailability.profile_id == profile.id,
                        WorkforceWorkingAvailability.branch_id == query.branch_id,
                        WorkforceWorkingAvailability.status == "available",
                        WorkforceWorkingAvailability.start_at <= query.window_start_at,
                        WorkforceWorkingAvailability.end_at >= query.window_end_at,
                    )
                    .limit(1)
                )
            )
            unavailable = (
                None
                if profile is None
                else await session.scalar(
                    select(WorkforceWorkingAvailability.id)
                    .where(
                        WorkforceWorkingAvailability.company_id == query.company_id,
                        WorkforceWorkingAvailability.profile_id == profile.id,
                        WorkforceWorkingAvailability.branch_id == query.branch_id,
                        WorkforceWorkingAvailability.status == "unavailable",
                        WorkforceWorkingAvailability.start_at < query.window_end_at,
                        WorkforceWorkingAvailability.end_at > query.window_start_at,
                    )
                    .limit(1)
                )
            )
            if unavailable:
                reasons.append("unavailable")
            elif availability is None and not branch_schedule_available:
                reasons.append("outside_branch_schedule")
            reasons = list(dict.fromkeys(reasons))
            eligible = not reasons
            decision = "eligible" if eligible else reasons[0]
            result.append(
                EligibleTechnician(
                    employee.id,
                    employee.employee_number,
                    employee.display_name,
                    query.branch_id,
                    employee.job_title,
                    capabilities,
                    languages,
                    decision,
                    tuple(reasons),
                    "employee_override"
                    if availability is not None or unavailable
                    else "branch_schedule",
                    eligible,
                )
            )
        return tuple(result)

    @staticmethod
    async def _branch_schedule_available(
        session: AsyncSession, *, query: WorkforceEligibilityQuery
    ) -> bool:
        branch = await session.scalar(
            select(Branch).where(
                Branch.company_id == query.company_id,
                Branch.id == query.branch_id,
                Branch.status == "active",
                Branch.archived_at.is_(None),
            )
        )
        calendar = await session.scalar(
            select(BranchSchedulingCalendar).where(
                BranchSchedulingCalendar.company_id == query.company_id,
                BranchSchedulingCalendar.branch_id == query.branch_id,
            )
        )
        if branch is None or calendar is None:
            return False
        local_start = query.window_start_at.astimezone(ZoneInfo(branch.timezone))
        local_end = query.window_end_at.astimezone(ZoneInfo(branch.timezone))
        if local_start.date() != local_end.date():
            return False
        start_minute = local_start.hour * 60 + local_start.minute
        end_minute = local_end.hour * 60 + local_end.minute
        exception = await session.scalar(
            select(BranchSchedulingException).where(
                BranchSchedulingException.calendar_id == calendar.id,
                BranchSchedulingException.exception_date == local_start.date(),
                or_(
                    BranchSchedulingException.start_minute.is_(None),
                    and_(
                        BranchSchedulingException.start_minute <= start_minute,
                        BranchSchedulingException.end_minute >= end_minute,
                    ),
                ),
            )
        )
        if exception is not None:
            return not exception.is_closed
        interval = await session.scalar(
            select(BranchSchedulingWeeklyInterval.id).where(
                BranchSchedulingWeeklyInterval.calendar_id == calendar.id,
                BranchSchedulingWeeklyInterval.day_of_week == local_start.weekday(),
                BranchSchedulingWeeklyInterval.start_minute <= start_minute,
                BranchSchedulingWeeklyInterval.end_minute >= end_minute,
            )
        )
        return interval is not None


workforce_eligibility_service = WorkforceEligibilityService()
