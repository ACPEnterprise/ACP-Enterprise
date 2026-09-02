from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dispatch.models import DispatchAssignment, DispatchCrewMember
from app.platform.employees.models import Employee
from app.platform.permissions.authorization import AuthorizationContext
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
                .join(
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
        result: list[EligibleTechnician] = []
        for employee, profile, branch_eligibility in rows:
            capabilities = tuple(
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
            languages = tuple(
                (
                    await session.scalars(
                        select(Language.code)
                        .join(
                            WorkforceLanguageCapability,
                            WorkforceLanguageCapability.language_id == Language.id,
                        )
                        .where(
                            WorkforceLanguageCapability.company_id == query.company_id,
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
            if employee.status != "active" or profile.status != "active":
                reasons.append("inactive")
            if (
                branch_eligibility is None
                and employee.home_branch_id != query.branch_id
            ):
                reasons.append("wrong_branch")
            if "technician" not in capabilities:
                reasons.append("missing_required_capability")
            if not query.required_capability_codes.issubset(capabilities):
                reasons.append("missing_required_capability")
            if not query.required_language_codes.issubset(languages):
                reasons.append("missing_required_language")
            if conflict or crew_conflict:
                reasons.append("conflicting_assignment")
            availability = await session.scalar(
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
            unavailable = await session.scalar(
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
            if unavailable:
                reasons.append("unavailable")
            elif availability is None:
                reasons.append("availability_unknown")
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
                    "authoritative"
                    if availability is not None or unavailable
                    else "unknown",
                    eligible,
                )
            )
        return tuple(result)


workforce_eligibility_service = WorkforceEligibilityService()
