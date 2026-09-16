"""Exact, certified direct-expense-to-Job attribution contract."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Final
from uuid import UUID

from .policy_authority import canonical_digest

CONTRACT_VERSION: Final = "economics.job-direct-expense-allocation.v1"


class DirectExpenseAuthorityError(ValueError):
    pass


class AllocationStatus(StrEnum):
    DRAFT = "draft"
    READY_FOR_CERTIFICATION = "ready_for_certification"
    CERTIFIED = "certified"
    SUPERSEDED = "superseded"
    INACTIVE = "inactive"


@dataclass(frozen=True)
class JobExpenseSplit:
    job_id: UUID
    branch_id: UUID
    amount_minor: int


@dataclass(frozen=True)
class DirectExpenseAllocation:
    company_id: UUID
    source_system: str
    source_record_type: str
    source_transaction_id: str
    source_line_id: str
    source_evidence_digest: str
    source_amount_minor: int
    currency: str
    effective_date: date
    allocation_version: int
    allocation_basis: str
    splits: tuple[JobExpenseSplit, ...]
    status: AllocationStatus
    rationale: str
    actor_user_id: UUID
    certified_by_user_id: UUID | None
    certified_at: datetime | None
    supersedes_allocation_digest: str | None = None

    def validate(self) -> None:
        if not all(
            (
                self.source_system,
                self.source_record_type,
                self.source_transaction_id,
                self.source_line_id,
                self.rationale,
            )
        ):
            raise DirectExpenseAuthorityError("exact source identity is required")
        if len(self.source_evidence_digest) != 64:
            raise DirectExpenseAuthorityError("source evidence digest is required")
        if self.source_amount_minor <= 0 or self.allocation_version < 1:
            raise DirectExpenseAuthorityError("positive source amount and version required")
        if len(self.currency) != 3 or self.currency != self.currency.upper():
            raise DirectExpenseAuthorityError("ISO currency is required")
        if not self.splits or any(item.amount_minor <= 0 for item in self.splits):
            raise DirectExpenseAuthorityError("positive exact Job splits are required")
        if len({item.job_id for item in self.splits}) != len(self.splits):
            raise DirectExpenseAuthorityError("a Job may appear only once per allocation")
        if sum(item.amount_minor for item in self.splits) != self.source_amount_minor:
            raise DirectExpenseAuthorityError("Job splits must reconcile to source amount")
        if self.status is AllocationStatus.CERTIFIED and (
            self.certified_by_user_id is None or self.certified_at is None
        ):
            raise DirectExpenseAuthorityError("certified allocation requires reviewer")

    def digest(self) -> str:
        self.validate()
        return canonical_digest(
            {
                "contract_version": CONTRACT_VERSION,
                "company_id": str(self.company_id),
                "source": [
                    self.source_system,
                    self.source_record_type,
                    self.source_transaction_id,
                    self.source_line_id,
                    self.source_evidence_digest,
                ],
                "source_amount_minor": self.source_amount_minor,
                "currency": self.currency,
                "effective_date": self.effective_date.isoformat(),
                "allocation_version": self.allocation_version,
                "allocation_basis": self.allocation_basis,
                "splits": sorted(
                    (
                        str(item.job_id),
                        str(item.branch_id),
                        item.amount_minor,
                    )
                    for item in self.splits
                ),
                "status": self.status.value,
                "rationale": self.rationale,
                "actor_user_id": str(self.actor_user_id),
                "certified_by_user_id": str(self.certified_by_user_id)
                if self.certified_by_user_id
                else None,
                "certified_at": self.certified_at.isoformat()
                if self.certified_at
                else None,
                "supersedes": self.supersedes_allocation_digest,
            }
        )


def admitted_job_costs(
    allocation: DirectExpenseAllocation,
) -> tuple[JobExpenseSplit, ...]:
    allocation.validate()
    if allocation.status is not AllocationStatus.CERTIFIED:
        raise DirectExpenseAuthorityError(
            "only certified allocation may feed Job economics"
        )
    return allocation.splits
