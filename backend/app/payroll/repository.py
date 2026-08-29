"""Company-scoped Payroll authority persistence queries."""

from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import CompanyPayrollPolicyVersion, EmployeeCompensationAuthorityVersion


class PayrollAuthorityRepository:
    async def policy_by_id(
        self, session: AsyncSession, *, company_id: UUID, policy_id: UUID
    ) -> CompanyPayrollPolicyVersion | None:
        return await session.scalar(
            select(CompanyPayrollPolicyVersion).where(
                CompanyPayrollPolicyVersion.company_id == company_id,
                CompanyPayrollPolicyVersion.id == policy_id,
            )
        )

    async def policies_at(
        self, session: AsyncSession, *, company_id: UUID, as_of_date: date
    ) -> tuple[CompanyPayrollPolicyVersion, ...]:
        values = await session.scalars(
            select(CompanyPayrollPolicyVersion).where(
                CompanyPayrollPolicyVersion.company_id == company_id,
                CompanyPayrollPolicyVersion.lifecycle.in_(("approved", "superseded")),
                CompanyPayrollPolicyVersion.effective_start <= as_of_date,
                (
                    CompanyPayrollPolicyVersion.effective_end.is_(None)
                    | (CompanyPayrollPolicyVersion.effective_end > as_of_date)
                ),
            )
        )
        return tuple(values.all())

    async def overlapping_policies(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        effective_start: date,
        effective_end: date | None,
        exclude_policy_id: UUID | None = None,
    ) -> tuple[CompanyPayrollPolicyVersion, ...]:
        query = select(CompanyPayrollPolicyVersion).where(
            CompanyPayrollPolicyVersion.company_id == company_id,
            CompanyPayrollPolicyVersion.lifecycle.in_(("approved", "superseded")),
            (
                CompanyPayrollPolicyVersion.effective_end.is_(None)
                | (CompanyPayrollPolicyVersion.effective_end > effective_start)
            ),
        )
        if effective_end is not None:
            query = query.where(
                CompanyPayrollPolicyVersion.effective_start < effective_end
            )
        if exclude_policy_id is not None:
            query = query.where(CompanyPayrollPolicyVersion.id != exclude_policy_id)
        values = await session.scalars(query)
        return tuple(values.all())

    async def compensation_by_id(
        self, session: AsyncSession, *, company_id: UUID, authority_id: UUID
    ) -> EmployeeCompensationAuthorityVersion | None:
        return await session.scalar(
            select(EmployeeCompensationAuthorityVersion).where(
                EmployeeCompensationAuthorityVersion.company_id == company_id,
                EmployeeCompensationAuthorityVersion.id == authority_id,
            )
        )

    async def compensations_at(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        employee_id: UUID,
        as_of_date: date,
    ) -> tuple[EmployeeCompensationAuthorityVersion, ...]:
        values = await session.scalars(
            select(EmployeeCompensationAuthorityVersion).where(
                EmployeeCompensationAuthorityVersion.company_id == company_id,
                EmployeeCompensationAuthorityVersion.employee_id == employee_id,
                EmployeeCompensationAuthorityVersion.lifecycle.in_(
                    ("approved", "superseded")
                ),
                EmployeeCompensationAuthorityVersion.effective_start <= as_of_date,
                (
                    EmployeeCompensationAuthorityVersion.effective_end.is_(None)
                    | (EmployeeCompensationAuthorityVersion.effective_end > as_of_date)
                ),
            )
        )
        return tuple(values.all())

    async def overlapping_compensations(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        employee_id: UUID,
        effective_start: date,
        effective_end: date | None,
        exclude_authority_id: UUID | None = None,
    ) -> tuple[EmployeeCompensationAuthorityVersion, ...]:
        query = select(EmployeeCompensationAuthorityVersion).where(
            EmployeeCompensationAuthorityVersion.company_id == company_id,
            EmployeeCompensationAuthorityVersion.employee_id == employee_id,
            EmployeeCompensationAuthorityVersion.lifecycle.in_(
                ("approved", "superseded")
            ),
            (
                EmployeeCompensationAuthorityVersion.effective_end.is_(None)
                | (EmployeeCompensationAuthorityVersion.effective_end > effective_start)
            ),
        )
        if effective_end is not None:
            query = query.where(
                EmployeeCompensationAuthorityVersion.effective_start < effective_end
            )
        if exclude_authority_id is not None:
            query = query.where(
                EmployeeCompensationAuthorityVersion.id != exclude_authority_id
            )
        values = await session.scalars(query)
        return tuple(values.all())


payroll_authority_repository = PayrollAuthorityRepository()
