"""Deterministic adapter from persisted Payroll authority to engine contracts.

This module deliberately does not invent providers or tax elections. Callers must
provide approved authorities and an explicit provider/instruction policy.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from .calculation import PayPeriodCalculationContext
from .contracts import (
    ApprovedCompensationAuthority,
    ApprovedPayrollPolicy,
    PayrollAdmissionResult,
)
from .tax_authority import AuthorityRequirement, PayrollInputDomain
from .tax_calculation import DeductionBasis, DeductionInstruction


@dataclass(frozen=True)
class GrossEngineInputs:
    company_id: UUID
    employee_id: UUID
    period: PayPeriodCalculationContext
    admission: PayrollAdmissionResult
    policy: ApprovedPayrollPolicy
    compensation: ApprovedCompensationAuthority


def build_gross_inputs(
    *,
    company_id: UUID,
    employee_id: UUID,
    pay_period_id: UUID,
    period_start: date,
    period_end: date,
    schedule_definition_id: str,
    schedule_version: int,
    admission: PayrollAdmissionResult,
    policy: ApprovedPayrollPolicy,
    compensation: ApprovedCompensationAuthority,
) -> GrossEngineInputs:
    """Build the exact gross-engine contract without deriving any values."""
    if company_id != policy.company_id or company_id != compensation.company_id:
        raise ValueError("Payroll authority Company scope mismatch")
    if employee_id != compensation.employee_id:
        raise ValueError("Payroll compensation Employee scope mismatch")
    if admission.pay_period_id != pay_period_id or admission.employee_id != employee_id:
        raise ValueError("Payroll admission scope mismatch")
    policy.verify()
    compensation.verify()
    admission.verify()
    return GrossEngineInputs(
        company_id=company_id,
        employee_id=employee_id,
        period=PayPeriodCalculationContext(
            pay_period_id=pay_period_id,
            period_start=period_start,
            period_end=period_end,
            schedule_definition_id=schedule_definition_id,
            schedule_version=schedule_version,
        ),
        admission=admission,
        policy=policy,
        compensation=compensation,
    )


def required_tax_authorities(employee_id: UUID) -> tuple[AuthorityRequirement, ...]:
    """Return only explicit requirements; elections/jurisdiction remain inputs."""
    return (
        AuthorityRequirement(PayrollInputDomain.TAX, "federal_income_tax", employee_id),
        AuthorityRequirement(PayrollInputDomain.TAX, "social_security_employee", employee_id),
        AuthorityRequirement(PayrollInputDomain.TAX, "medicare_employee", employee_id),
    )


def deduction_instruction_from_authority(
    *,
    authority_id: UUID,
    authority_digest: str,
    authority_key: str,
    currency: str,
    public_parameters: dict[str, object],
    priority: int,
) -> DeductionInstruction:
    """Convert explicit approved public deduction parameters only."""
    basis = public_parameters.get("basis")
    fixed = public_parameters.get("fixed_amount")
    percentage = public_parameters.get("percentage")
    cap = public_parameters.get("cap_amount")
    if basis not in {item.value for item in DeductionBasis}:
        raise ValueError(f"unsupported deduction basis for {authority_key}")
    return DeductionInstruction(
        component_key=authority_key,
        authority_id=authority_id,
        authority_digest=authority_digest,
        basis=DeductionBasis(str(basis)),
        priority=priority,
        currency=currency,
        fixed_amount=Decimal(str(fixed)) if fixed is not None else None,
        percentage=Decimal(str(percentage)) if percentage is not None else None,
        cap_amount=Decimal(str(cap)) if cap is not None else None,
    )
