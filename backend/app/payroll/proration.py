"""Governed compensation-proration policy and deterministic hourly allocation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import StrEnum
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.permissions.authorization import AuthorizationContext
from app.timekeeping.contracts import ApprovedWorkdayTimeFact

from .contracts import (
    ApprovedCompensationAuthority,
    CompensationType,
    PayrollAuthorizationError,
    PayrollConflictError,
    canonical_digest,
)
from .models import PayrollCompensationProrationPolicyVersion
from .permissions import PayrollPermission

PRORATION_POLICY_VERSION = "payroll.compensation-proration-policy.v1"
PRORATION_ALLOCATION_VERSION = "payroll.compensation-proration-allocation.v1"


class CompensationProrationMethod(StrEnum):
    UNSELECTED = "unselected"
    BLOCK_PAYROLL = "block_payroll"
    BY_WORK_DATE = "by_work_date"


@dataclass(frozen=True)
class ApprovedProrationPolicy:
    policy_id: UUID
    company_id: UUID
    policy_version: int
    effective_start: date
    effective_end: date | None
    method: CompensationProrationMethod
    rationale: str
    provenance: str
    approved_by_user_id: UUID
    approved_at: datetime
    supersedes_policy_id: UUID | None
    policy_digest: str


@dataclass(frozen=True)
class ProratedTimeAllocation:
    time_revision_id: UUID
    compensation_authority_id: UUID
    compensation_digest: str
    work_date: date
    payable_minutes: int

    def canonical_content(self) -> dict[str, object]:
        return {
            "time_revision_id": str(self.time_revision_id),
            "compensation_authority_id": str(self.compensation_authority_id),
            "compensation_digest": self.compensation_digest,
            "work_date": self.work_date.isoformat(),
            "payable_minutes": self.payable_minutes,
        }


@dataclass(frozen=True)
class CompensationProrationResult:
    definition_version: str
    company_id: UUID
    employee_id: UUID
    policy_id: UUID
    policy_digest: str
    allocations: tuple[ProratedTimeAllocation, ...]
    total_payable_minutes: int
    result_digest: str


def allocate_hourly_time(
    *,
    company_id: UUID,
    employee_id: UUID,
    policy: ApprovedProrationPolicy,
    time: tuple[ApprovedWorkdayTimeFact, ...],
    compensation: tuple[ApprovedCompensationAuthority, ...],
) -> CompensationProrationResult:
    if policy.company_id != company_id:
        raise PayrollConflictError("proration policy Company scope mismatch")
    if policy.method in {
        CompensationProrationMethod.UNSELECTED,
        CompensationProrationMethod.BLOCK_PAYROLL,
    }:
        raise PayrollConflictError("compensation proration policy blocks Payroll")
    if not time:
        raise PayrollConflictError("accepted time evidence is required")
    authorities = tuple(sorted(compensation, key=lambda item: item.effective_start))
    if not authorities or any(
        item.company_id != company_id
        or item.employee_id != employee_id
        or item.compensation_type is not CompensationType.HOURLY
        for item in authorities
    ):
        raise PayrollConflictError(
            "hourly compensation authority scope or type is unsupported"
        )
    allocations: list[ProratedTimeAllocation] = []
    seen: set[UUID] = set()
    for fact in sorted(time, key=lambda item: (item.work_date, str(item.revision_id))):
        fact.verify()
        if fact.company_id != company_id or fact.employee_id != employee_id:
            raise PayrollConflictError("accepted time evidence scope mismatch")
        if fact.revision_id in seen:
            raise PayrollConflictError("accepted time revision is duplicated")
        seen.add(fact.revision_id)
        candidates = tuple(
            item
            for item in authorities
            if item.effective_start <= fact.work_date
            and (item.effective_end is None or fact.work_date < item.effective_end)
        )
        superseded = {
            item.supersedes_authority_id
            for item in candidates
            if item.supersedes_authority_id is not None
        }
        applicable = tuple(
            item for item in candidates if item.authority_id not in superseded
        )
        if len(applicable) != 1:
            raise PayrollConflictError(
                "accepted time must map to exactly one compensation revision"
            )
        authority = applicable[0]
        allocations.append(
            ProratedTimeAllocation(
                time_revision_id=fact.revision_id,
                compensation_authority_id=authority.authority_id,
                compensation_digest=authority.authority_digest,
                work_date=fact.work_date,
                payable_minutes=fact.approved_duration_minutes,
            )
        )
    ordered = tuple(allocations)
    content = {
        "definition_version": PRORATION_ALLOCATION_VERSION,
        "company_id": str(company_id),
        "employee_id": str(employee_id),
        "policy_id": str(policy.policy_id),
        "policy_digest": policy.policy_digest,
        "allocations": tuple(item.canonical_content() for item in ordered),
    }
    return CompensationProrationResult(
        definition_version=PRORATION_ALLOCATION_VERSION,
        company_id=company_id,
        employee_id=employee_id,
        policy_id=policy.policy_id,
        policy_digest=policy.policy_digest,
        allocations=ordered,
        total_payable_minutes=sum(item.payable_minutes for item in ordered),
        result_digest=canonical_digest(content),
    )


class CompensationProrationPolicyService:
    async def draft(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        policy_version: int,
        effective_start: date,
        effective_end: date | None,
        method: CompensationProrationMethod,
        rationale: str,
        provenance: str,
        supersedes_policy_id: UUID | None = None,
    ) -> PayrollCompensationProrationPolicyVersion:
        self._require(context, PayrollPermission.COMPENSATION_MANAGE)
        if policy_version < 1 or not rationale.strip() or not provenance.strip():
            raise PayrollConflictError("proration policy evidence is incomplete")
        if effective_end is not None and effective_end <= effective_start:
            raise PayrollConflictError("proration policy interval is invalid")
        content = {
            "definition_version": PRORATION_POLICY_VERSION,
            "company_id": str(context.company.id),
            "policy_version": policy_version,
            "effective_start": effective_start.isoformat(),
            "effective_end": effective_end.isoformat() if effective_end else None,
            "method": method.value,
            "rationale": rationale.strip(),
            "provenance": provenance.strip(),
            "supersedes_policy_id": str(supersedes_policy_id)
            if supersedes_policy_id
            else None,
        }
        value = PayrollCompensationProrationPolicyVersion(
            company_id=context.company.id,
            policy_version=policy_version,
            effective_start=effective_start,
            effective_end=effective_end,
            method=method.value,
            lifecycle="draft",
            rationale=rationale.strip(),
            provenance=provenance.strip(),
            policy_digest=canonical_digest(content),
            drafted_by_user_id=context.user.id,
            supersedes_policy_id=supersedes_policy_id,
        )
        session.add(value)
        await session.commit()
        return value

    async def approve(
        self,
        session: AsyncSession,
        *,
        context: AuthorizationContext,
        policy_id: UUID,
    ) -> PayrollCompensationProrationPolicyVersion:
        self._require(context, PayrollPermission.COMPENSATION_APPROVE)
        value = await session.scalar(
            select(PayrollCompensationProrationPolicyVersion).where(
                PayrollCompensationProrationPolicyVersion.company_id
                == context.company.id,
                PayrollCompensationProrationPolicyVersion.id == policy_id,
            )
        )
        if value is None or value.lifecycle != "draft":
            raise PayrollConflictError("only draft proration policy may be approved")
        if value.drafted_by_user_id == context.user.id:
            raise PayrollAuthorizationError(
                "proration policy drafter cannot approve the same policy"
            )
        if value.method == CompensationProrationMethod.UNSELECTED.value:
            raise PayrollConflictError("unselected proration policy cannot be approved")
        active = await self.resolve_record(
            session, company_id=context.company.id, as_of_date=value.effective_start
        )
        if active is not None and active.id != value.supersedes_policy_id:
            raise PayrollConflictError("approved proration policy interval overlaps")
        now = datetime.now(timezone.utc)
        value.lifecycle = "approved"
        value.approved_by_user_id = context.user.id
        value.approved_at = now
        if value.supersedes_policy_id is not None:
            prior = await session.get(
                PayrollCompensationProrationPolicyVersion,
                value.supersedes_policy_id,
            )
            if prior is None or prior.company_id != context.company.id:
                raise PayrollConflictError("superseded proration policy is unavailable")
            prior.lifecycle = "superseded"
        await session.commit()
        return value

    async def resolve_record(
        self,
        session: AsyncSession,
        *,
        company_id: UUID,
        as_of_date: date,
    ) -> PayrollCompensationProrationPolicyVersion | None:
        values = tuple(
            (
                await session.scalars(
                    select(PayrollCompensationProrationPolicyVersion).where(
                        PayrollCompensationProrationPolicyVersion.company_id
                        == company_id,
                        PayrollCompensationProrationPolicyVersion.lifecycle.in_(
                            ("approved", "superseded")
                        ),
                        PayrollCompensationProrationPolicyVersion.effective_start
                        <= as_of_date,
                        (
                            PayrollCompensationProrationPolicyVersion.effective_end.is_(
                                None
                            )
                            | (
                                PayrollCompensationProrationPolicyVersion.effective_end
                                > as_of_date
                            )
                        ),
                    )
                )
            ).all()
        )
        superseded = {
            item.supersedes_policy_id
            for item in values
            if item.supersedes_policy_id is not None
        }
        active = tuple(item for item in values if item.id not in superseded)
        if not active:
            return None
        if len(active) != 1:
            raise PayrollConflictError("proration policy resolution is ambiguous")
        return active[0]

    @staticmethod
    def _require(context: AuthorizationContext, permission: str) -> None:
        if not context.has_permission(permission):
            raise PayrollAuthorizationError("Payroll proration permission denied")
