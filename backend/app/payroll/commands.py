"""Commands for Payroll policy and compensation authority."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from .contracts import CompanyPayrollPolicyDefinition, CompensationType


@dataclass(frozen=True)
class DraftPayrollPolicy:
    policy_version: int
    effective_start: date
    effective_end: date | None
    definition: CompanyPayrollPolicyDefinition
    decision_evidence_digest: str
    audit_reason: str
    supersedes_policy_id: UUID | None = None


@dataclass(frozen=True)
class DraftCompensationAuthority:
    employee_id: UUID
    authority_version: int
    effective_start: date
    effective_end: date | None
    compensation_type: CompensationType
    hourly_rate: Decimal | None
    salary_amount: Decimal | None
    salary_frequency: str | None
    worker_class_reference: str | None
    additional_earning_types: tuple[str, ...]
    recurring_components: tuple[dict[str, object], ...]
    decision_evidence_digest: str
    audit_reason: str
    supersedes_authority_id: UUID | None = None
