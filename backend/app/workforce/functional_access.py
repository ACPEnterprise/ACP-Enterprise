from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.schemas import BusinessEventCreate
from app.events.service import BusinessEventService
from app.events.types import EventType
from app.platform.audit.service import AuditEntry, audit_service
from app.platform.company.membership_models import Membership
from app.platform.employees.models import Employee
from app.platform.permissions.authorization import AuthorizationContext
from app.platform.permissions.models import MembershipRole, Role
from app.platform.users.models import User

FUNCTIONAL_ROLE_MAP: dict[tuple[str, str], str] = {
    ("FIELD_OPERATIONS", "TECHNICIAN"): "TECHNICIAN",
    ("CUSTOMER_SERVICE", "CSR"): "CSR",
    ("DISPATCH", "DISPATCHER"): "DISPATCHER",
    ("REPORTING_ECONOMICS", "READ"): "AUDITOR",
}


class FunctionalAccessConflict(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class FunctionalAccessView:
    assignment_id: UUID
    employee_id: UUID
    functional_area: str
    access_level: str
    role_code: str
    effective_at: datetime
    expires_at: datetime | None
    effective: bool
    lifecycle_state: str
    revoked_at: datetime | None
    reason: str


class FunctionalAccessService:
    async def list(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        employee_id: UUID,
    ) -> tuple[FunctionalAccessView, ...]:
        employee = await self._employee(session, context, employee_id)
        if employee.membership_id is None:
            return ()
        rows = (
            await session.execute(
                select(MembershipRole, Role)
                .join(Role, Role.id == MembershipRole.role_id)
                .where(
                    MembershipRole.company_id == context.company.id,
                    MembershipRole.membership_id == employee.membership_id,
                    MembershipRole.functional_area.is_not(None),
                )
                .order_by(
                    MembershipRole.functional_area,
                    MembershipRole.effective_at,
                    MembershipRole.id,
                )
            )
        ).all()
        now = datetime.now(timezone.utc)
        return tuple(
            FunctionalAccessView(
                assignment_id=assignment.id,
                employee_id=employee.id,
                functional_area=assignment.functional_area or "",
                access_level=assignment.access_level or "",
                role_code=role.code,
                effective_at=assignment.effective_at or assignment.assigned_at,
                expires_at=assignment.expires_at,
                effective=(
                    assignment.revoked_at is None
                    and (
                        assignment.effective_at is None
                        or assignment.effective_at <= now
                    )
                    and (assignment.expires_at is None or assignment.expires_at > now)
                ),
                lifecycle_state=(
                    "REVOKED"
                    if assignment.revoked_at is not None
                    else "SCHEDULED"
                    if assignment.effective_at is not None
                    and assignment.effective_at > now
                    else "EXPIRED"
                    if assignment.expires_at is not None
                    and assignment.expires_at <= now
                    else "EFFECTIVE"
                ),
                revoked_at=assignment.revoked_at,
                reason=assignment.grant_reason or "",
            )
            for assignment, role in rows
        )

    async def grant(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        employee_id: UUID,
        functional_area: str,
        access_level: str,
        effective_at: datetime,
        expires_at: datetime | None,
        reason: str,
    ) -> FunctionalAccessView:
        key = (functional_area, access_level)
        role_code = FUNCTIONAL_ROLE_MAP.get(key)
        if role_code is None:
            raise FunctionalAccessConflict(
                "Functional access level has no canonical permission bundle."
            )
        if expires_at is not None and expires_at <= effective_at:
            raise FunctionalAccessConflict("Access expiration must follow its start.")
        now = datetime.now(timezone.utc)
        async with session.begin():
            employee = await self._employee(session, context, employee_id, lock=True)
            if employee.membership_id is None:
                raise FunctionalAccessConflict(
                    "Employee requires a canonical Membership before platform access."
                )
            role = await session.scalar(
                select(Role).where(
                    Role.company_id == context.company.id,
                    Role.code == role_code,
                    Role.status == "active",
                    Role.archived_at.is_(None),
                )
            )
            if role is None:
                raise FunctionalAccessConflict(
                    "Canonical role reconciliation is required before access can be granted."
                )
            existing = tuple(
                (
                    await session.scalars(
                        select(MembershipRole)
                        .where(
                            MembershipRole.company_id == context.company.id,
                            MembershipRole.membership_id == employee.membership_id,
                            MembershipRole.revoked_at.is_(None),
                            or_(
                                MembershipRole.functional_area == functional_area,
                                MembershipRole.role_id == role.id,
                            ),
                        )
                        .with_for_update()
                    )
                ).all()
            )
            for assignment in existing:
                assignment.revoked_at = now
                assignment.revoked_by_user_id = context.user.id
                assignment.revocation_reason = "Superseded by functional access update"
            if existing:
                await session.flush()
            assignment = MembershipRole(
                company_id=context.company.id,
                membership_id=employee.membership_id,
                role_id=role.id,
                assigned_at=now,
                assigned_by_user_id=context.user.id,
                functional_area=functional_area,
                access_level=access_level,
                effective_at=effective_at,
                expires_at=expires_at,
                grant_reason=reason.strip(),
            )
            session.add(assignment)
            await self._advance_authorization(session, employee)
            await session.flush()
            self._record_change(
                session,
                context=context,
                employee=employee,
                assignment=assignment,
                role_code=role_code,
                action="workforce.functional_access_granted",
            )
        return FunctionalAccessView(
            assignment_id=assignment.id,
            employee_id=employee.id,
            functional_area=functional_area,
            access_level=access_level,
            role_code=role_code,
            effective_at=effective_at,
            expires_at=expires_at,
            effective=effective_at <= now and (expires_at is None or expires_at > now),
            lifecycle_state=(
                "SCHEDULED"
                if effective_at > now
                else "EXPIRED"
                if expires_at is not None and expires_at <= now
                else "EFFECTIVE"
            ),
            revoked_at=None,
            reason=reason.strip(),
        )

    async def revoke(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        employee_id: UUID,
        assignment_id: UUID,
        reason: str,
    ) -> None:
        now = datetime.now(timezone.utc)
        async with session.begin():
            employee = await self._employee(session, context, employee_id, lock=True)
            assignment = await session.scalar(
                select(MembershipRole)
                .where(
                    MembershipRole.id == assignment_id,
                    MembershipRole.company_id == context.company.id,
                    MembershipRole.membership_id == employee.membership_id,
                    MembershipRole.functional_area.is_not(None),
                )
                .with_for_update()
            )
            if assignment is None:
                raise FunctionalAccessConflict("Functional access was not found.")
            if assignment.revoked_at is None:
                assignment.revoked_at = now
                assignment.revoked_by_user_id = context.user.id
                assignment.revocation_reason = reason.strip()
                await self._advance_authorization(session, employee)
                role_code = await session.scalar(
                    select(Role.code).where(Role.id == assignment.role_id)
                )
                self._record_change(
                    session,
                    context=context,
                    employee=employee,
                    assignment=assignment,
                    role_code=role_code or "UNKNOWN",
                    action="workforce.functional_access_revoked",
                )

    @staticmethod
    async def _employee(
        session: AsyncSession,
        context: AuthorizationContext,
        employee_id: UUID,
        *,
        lock: bool = False,
    ) -> Employee:
        statement = select(Employee).where(
            Employee.id == employee_id,
            Employee.company_id == context.company.id,
            Employee.archived_at.is_(None),
        )
        if lock:
            statement = statement.with_for_update()
        employee = await session.scalar(statement)
        if employee is None or (
            employee.home_branch_id is not None
            and not context.can_access_branch(employee.home_branch_id)
        ):
            raise FunctionalAccessConflict("Employee was not found.")
        return employee

    @staticmethod
    async def _advance_authorization(session: AsyncSession, employee: Employee) -> None:
        if employee.membership_id is None:
            return
        membership = await session.scalar(
            select(Membership).where(
                Membership.company_id == employee.company_id,
                Membership.id == employee.membership_id,
            )
        )
        if membership is not None:
            bound_user = await session.get(User, membership.user_id)
            if bound_user is not None:
                bound_user.authorization_version += 1

    @staticmethod
    def _record_change(
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        employee: Employee,
        assignment: MembershipRole,
        role_code: str,
        action: str,
    ) -> None:
        details: dict[str, object] = {
            "functional_area": assignment.functional_area,
            "access_level": assignment.access_level,
            "role_code": role_code,
            "effective_at": assignment.effective_at.isoformat()
            if assignment.effective_at
            else None,
            "expires_at": assignment.expires_at.isoformat()
            if assignment.expires_at
            else None,
        }
        audit_service.stage(
            session,
            AuditEntry(
                action=action,
                resource_type="employee_functional_access",
                actor_user_id=context.user.id,
                company_id=context.company.id,
                branch_id=employee.home_branch_id,
                resource_id=assignment.id,
                reason_code="OWNER_ACCESS_DECISION",
                details=details,
            ),
        )
        BusinessEventService.stage(
            session,
            BusinessEventCreate(
                event_type=EventType.EMPLOYEE_FUNCTIONAL_ACCESS_CHANGED,
                entity_type="employee",
                entity_id=employee.id,
                company_id=context.company.id,
                branch_id=employee.home_branch_id,
                user_id=context.user.id,
                payload={**details, "schema_version": 1},
            ),
        )


functional_access_service = FunctionalAccessService()
