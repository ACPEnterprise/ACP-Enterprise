from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.platform.audit.service import AuditEntry, audit_service
from app.platform.auth.services import AuthenticationService
from app.platform.company.membership_models import Membership
from app.platform.employees.models import Employee
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.users.models import User, UserCredential


class EmployeeAccessLockConflict(ValueError):
    pass


class EmployeeAccessLockService:
    async def set_locked(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        employee_id: UUID,
        locked: bool,
        reason: str,
        expected_authorization_version: int,
    ) -> None:
        normalized_reason = reason.strip()
        if len(normalized_reason) < 3:
            raise EmployeeAccessLockConflict("A lock reason is required.")

        async with session.begin():
            row = (
                await session.execute(
                    select(Employee, Membership, User)
                    .join(
                        Membership,
                        (Membership.id == Employee.membership_id)
                        & (Membership.company_id == Employee.company_id),
                    )
                    .join(User, User.id == Membership.user_id)
                    .where(
                        Employee.company_id == context.company.id,
                        Employee.id == employee_id,
                        User.archived_at.is_(None),
                    )
                    .with_for_update()
                )
            ).one_or_none()
            if row is None:
                raise EmployeeAccessLockConflict(
                    "The Employee does not have a lockable Company identity."
                )
            _employee, _membership, user = row
            desired_status = "locked" if locked else "active"
            if user.status == desired_status:
                return
            if user.authorization_version != expected_authorization_version:
                raise EmployeeAccessLockConflict(
                    "Employee access changed. Refresh before trying again."
                )
            if locked and user.status != "active":
                raise EmployeeAccessLockConflict(
                    "Only an active login can be emergency locked."
                )
            if not locked and user.status != "locked":
                raise EmployeeAccessLockConflict(
                    "Only an emergency-locked login can be unlocked."
                )

            now = datetime.now(timezone.utc)
            previous_status = user.status
            user.status = desired_status
            user.disabled_at = now if locked else None
            user.authorization_version += 1
            credential = await session.scalar(
                select(UserCredential)
                .where(UserCredential.user_id == user.id)
                .with_for_update()
            )
            if credential is not None:
                credential.credential_version += 1
            await AuthenticationService.revoke_user_sessions(
                session,
                user_id=user.id,
                reason="employee_access_locked" if locked else "employee_access_unlocked",
                now=now,
                revoked_by_user_id=context.user.id,
            )

            action = "workforce.employee_access_locked" if locked else "workforce.employee_access_unlocked"
            event_type = (
                EventType.USER_ACCESS_LOCKED if locked else EventType.USER_ACCESS_UNLOCKED
            )
            details: dict[str, object] = {
                "employee_id": str(employee_id),
                "user_id": str(user.id),
                "previous_state": previous_status,
                "resulting_state": desired_status,
                "reason": normalized_reason,
                "authorization_version": user.authorization_version,
            }
            audit_service.stage(
                session,
                AuditEntry(
                    action=action,
                    resource_type="employee",
                    resource_id=employee_id,
                    actor_user_id=context.user.id,
                    company_id=context.company.id,
                    branch_id=context.active_branch.id if context.active_branch else None,
                    reason_code="emergency_access_lock" if locked else "access_unlock",
                    details=details,
                    occurred_at=now,
                ),
            )
            BusinessEventService.stage(
                session,
                BusinessEventCreate(
                    event_type=event_type,
                    entity_type="employee",
                    entity_id=employee_id,
                    company_id=context.company.id,
                    branch_id=context.active_branch.id if context.active_branch else None,
                    user_id=context.user.id,
                    payload=details,
                    occurred_at=now,
                ),
            )


employee_access_lock_service = EmployeeAccessLockService()
