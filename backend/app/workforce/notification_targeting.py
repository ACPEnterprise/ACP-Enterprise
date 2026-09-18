"""Read-only authority for targeting operational Employee notifications."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.company.membership_models import Membership, MembershipBranchAccess
from app.platform.employees.models import Employee
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.models import MembershipRole, Role
from app.platform.users.models import User
from app.workforce.schemas import EmployeeNotificationTarget

SUPPORTED_EVENTS = frozenset(
    {
        "NEW_ASSIGNMENT",
        "ASSIGNMENT_CHANGED",
        "JOB_CANCELED",
        "EMPLOYEE_ACTION_REQUIRED",
        "TIMEKEEPING_ISSUE",
    }
)


class EmployeeNotificationTargetingService:
    async def resolve(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        employee_id: UUID,
        event_type: str,
        branch_id: UUID,
    ) -> EmployeeNotificationTarget | None:
        if event_type not in SUPPORTED_EVENTS:
            raise ValueError("Unsupported Employee notification event type.")

        employee = await session.scalar(
            select(Employee).where(
                Employee.company_id == context.company.id,
                Employee.id == employee_id,
            )
        )
        if employee is None:
            return None

        blockers: list[str] = []
        if employee.status != "active" or employee.archived_at is not None:
            blockers.append("EMPLOYEE_INACTIVE")
        if employee.membership_id is None:
            blockers.append("MEMBERSHIP_MISSING")
            return self._result(employee, event_type, branch_id, None, None, blockers)

        membership = await session.scalar(
            select(Membership).where(
                Membership.company_id == context.company.id,
                Membership.id == employee.membership_id,
            )
        )
        if membership is None:
            blockers.append("MEMBERSHIP_MISSING")
            return self._result(employee, event_type, branch_id, None, None, blockers)
        if membership.status != "active" or membership.revoked_at is not None:
            blockers.append("MEMBERSHIP_INACTIVE")

        user = await session.scalar(select(User).where(User.id == membership.user_id))
        if user is None:
            blockers.append("USER_MISSING")
        elif user.status != "active" or user.archived_at is not None:
            blockers.append("USER_INACTIVE")

        explicit_branch = bool(
            await session.scalar(
                select(MembershipBranchAccess.id).where(
                    MembershipBranchAccess.membership_id == membership.id,
                    MembershipBranchAccess.branch_id == branch_id,
                )
            )
        )
        branch_ready = (
            bool(
                membership.has_all_branch_access
                or membership.default_branch_id == branch_id
                or explicit_branch
            )
            and employee.home_branch_id == branch_id
        )
        if not branch_ready:
            blockers.append("BRANCH_NOT_AUTHORIZED")

        mobile_role = bool(
            await session.scalar(
                select(MembershipRole.id)
                .join(Role, Role.id == MembershipRole.role_id)
                .where(
                    MembershipRole.company_id == context.company.id,
                    MembershipRole.membership_id == membership.id,
                    MembershipRole.revoked_at.is_(None),
                    Role.code == "ACP_EMPLOYEE_MOBILE",
                    Role.status == "active",
                    Role.archived_at.is_(None),
                )
            )
        )
        if not mobile_role:
            blockers.append("MOBILE_ROLE_MISSING")

        return self._result(employee, event_type, branch_id, membership, user, blockers)

    @staticmethod
    def _result(employee, event_type, branch_id, membership, user, blockers):
        return EmployeeNotificationTarget(
            employee_id=employee.id,
            event_type=event_type,
            company_id=employee.company_id,
            branch_id=branch_id,
            membership_id=membership.id if membership else None,
            user_id=user.id if user else None,
            authorization_version=user.authorization_version if user else None,
            state="READY" if not blockers else "BLOCKED",
            blockers=tuple(blockers),
            delivery_channel="EMPLOYEE_INBOX",
            external_push_state="PROVIDER_REQUIRED",
        )


employee_notification_targeting_service = EmployeeNotificationTargetingService()
