"""Resolution of Payroll calculation inputs without performing calculations."""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import PayrollInputAuthorityVersion


class InputResolutionState(StrEnum):
    READY = "ready"
    MISSING_OWNER_INPUT = "missing_owner_input"
    MISSING_EMPLOYEE_INPUT = "missing_employee_input"
    MISSING_ACCOUNTANT_INPUT = "missing_accountant_input"
    MISSING_YTD_AUTHORITY = "missing_ytd_authority"
    ENGINEERING_BLOCKER = "engineering_blocker"


@dataclass(frozen=True)
class TaxDeductionRequirementResolution:
    employee_id: UUID
    as_of_date: date
    state: InputResolutionState
    authority_ids: tuple[UUID, ...]
    authority_digests: tuple[str, ...]
    blockers: tuple[str, ...]


async def resolve_tax_deduction_requirements(
    session: AsyncSession,
    *,
    company_id: UUID,
    employee_id: UUID,
    as_of_date: date,
) -> TaxDeductionRequirementResolution:
    """Resolve only explicit approved authority; never infer elections or jurisdiction."""
    values = tuple(
        (
            await session.scalars(
                select(PayrollInputAuthorityVersion).where(
                    PayrollInputAuthorityVersion.company_id == company_id,
                    PayrollInputAuthorityVersion.employee_id == employee_id,
                    PayrollInputAuthorityVersion.effective_start <= as_of_date,
                    (
                        PayrollInputAuthorityVersion.effective_end.is_(None)
                        | (PayrollInputAuthorityVersion.effective_end > as_of_date)
                    ),
                )
            )
        ).all()
    )
    active = tuple(item for item in values if item.lifecycle == "approved")
    if not active:
        return TaxDeductionRequirementResolution(
            employee_id,
            as_of_date,
            InputResolutionState.MISSING_EMPLOYEE_INPUT,
            (),
            (),
            ("MISSING_TAX_DEDUCTION_AUTHORITY",),
        )
    conflicts = tuple(
        item.authority_key
        for item in active
        if item.authority_domain in {"tax", "deduction"}
        and item.applicability == "required"
        and item.protected_envelope_id is None
    )
    if conflicts:
        return TaxDeductionRequirementResolution(
            employee_id,
            as_of_date,
            InputResolutionState.MISSING_EMPLOYEE_INPUT,
            tuple(item.id for item in active),
            tuple(item.authority_digest for item in active),
            tuple(f"MISSING_PROTECTED_INPUT:{key}" for key in conflicts),
        )
    return TaxDeductionRequirementResolution(
        employee_id,
        as_of_date,
        InputResolutionState.READY,
        tuple(item.id for item in active),
        tuple(item.authority_digest for item in active),
        (),
    )
