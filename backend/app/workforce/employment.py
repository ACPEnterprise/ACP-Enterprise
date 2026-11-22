from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.audit.service import AuditEntry, audit_service
from app.platform.auth.services import utc_now
from app.platform.branch.models import Branch
from app.platform.employees.models import Employee
from app.platform.permissions.authorization import AuthorizationContext
from app.workforce.schemas import (
    EmployeeDeactivationRequest,
    EmployeeProfileUpdateRequest,
)


class EmployeeEmploymentConflict(ValueError):
    pass


class EmployeeEmploymentService:
    async def update_profile(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        employee_id: UUID,
        data: EmployeeProfileUpdateRequest,
    ) -> None:
        async with session.begin():
            employee = await session.scalar(
                select(Employee)
                .where(
                    Employee.company_id == context.company.id,
                    Employee.id == employee_id,
                )
                .with_for_update()
            )
            if employee is None:
                raise EmployeeEmploymentConflict("Employee was not found.")
            if employee.home_branch_id and not context.can_access_branch(
                employee.home_branch_id
            ):
                raise EmployeeEmploymentConflict(
                    "The Employee is outside your Branch authority."
                )
            requested_fields = data.model_fields_set - {"expected_updated_at"}
            requested_values = {
                "home_branch_id": data.home_branch_id,
                "phone": data.phone.strip() if data.phone else None,
                "job_title": data.job_title.strip() if data.job_title else None,
            }
            if requested_fields and all(
                getattr(employee, field) == requested_values[field]
                for field in requested_fields
            ):
                return
            if not requested_fields:
                return
            if (
                data.expected_updated_at is not None
                and employee.updated_at != data.expected_updated_at
            ):
                raise EmployeeEmploymentConflict(
                    "Employee details changed. Refresh before saving again."
                )
            if "home_branch_id" in data.model_fields_set:
                if data.home_branch_id is not None:
                    branch = await session.scalar(
                        select(Branch).where(
                            Branch.company_id == context.company.id,
                            Branch.id == data.home_branch_id,
                        )
                    )
                    if branch is None or not context.can_access_branch(branch.id):
                        raise EmployeeEmploymentConflict(
                            "The selected Branch is outside your Company authority."
                        )
                employee.home_branch_id = data.home_branch_id
            if "phone" in data.model_fields_set:
                employee.phone = data.phone.strip() if data.phone else None
            if "job_title" in data.model_fields_set:
                employee.job_title = data.job_title.strip() if data.job_title else None

            now = datetime.now(timezone.utc)
            employee.updated_at = now
            employee.updated_by_user_id = context.user.id
            audit_service.stage(
                session,
                AuditEntry(
                    action="workforce.employee_profile_updated",
                    resource_type="employee",
                    resource_id=employee_id,
                    actor_user_id=context.user.id,
                    company_id=context.company.id,
                    branch_id=context.active_branch.id
                    if context.active_branch
                    else None,
                    details={
                        "changed_fields": sorted(
                            data.model_fields_set - {"expected_updated_at"}
                        )
                    },
                    occurred_at=now,
                ),
            )

    async def deactivate(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        employee_id: UUID,
        data: EmployeeDeactivationRequest,
    ) -> None:
        async with session.begin():
            employee = await session.scalar(
                select(Employee)
                .where(
                    Employee.company_id == context.company.id,
                    Employee.id == employee_id,
                )
                .with_for_update()
            )
            if employee is None:
                raise EmployeeEmploymentConflict("Employee was not found.")
            if employee.home_branch_id and not context.can_access_branch(
                employee.home_branch_id
            ):
                raise EmployeeEmploymentConflict(
                    "The Employee is outside your Branch authority."
                )
            if employee.status != "active":
                if (
                    employee.status == "inactive"
                    and employee.termination_date == data.effective_date
                ):
                    return
                raise EmployeeEmploymentConflict(
                    "Only an active employee can be deactivated."
                )
            if employee.hire_date and data.effective_date < employee.hire_date:
                raise EmployeeEmploymentConflict(
                    "The deactivation date cannot precede the hire date."
                )
            reason = data.reason.strip()
            if len(reason) < 3:
                raise EmployeeEmploymentConflict(
                    "A deactivation reason of at least 3 characters is required."
                )

            previous_status = employee.status
            now = utc_now()
            employee.status = "inactive"
            employee.termination_date = data.effective_date
            employee.updated_at = now
            employee.updated_by_user_id = context.user.id
            audit_service.stage(
                session,
                AuditEntry(
                    action="workforce.employee_deactivated",
                    resource_type="employee",
                    resource_id=employee_id,
                    actor_user_id=context.user.id,
                    company_id=context.company.id,
                    branch_id=context.active_branch.id
                    if context.active_branch
                    else None,
                    reason_code="employment_deactivation",
                    details={
                        "previous_status": previous_status,
                        "resulting_status": employee.status,
                        "effective_date": data.effective_date.isoformat(),
                        "reason": reason,
                        "access_lock_unchanged": True,
                    },
                    occurred_at=now,
                ),
            )


employee_employment_service = EmployeeEmploymentService()
