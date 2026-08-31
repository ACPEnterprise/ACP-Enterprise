"""Provider-neutral overhead pool and allocation evidence authority.

This module deliberately contains no Company defaults.  It validates supplied,
approved policy and source evidence before delegating arithmetic to Economics.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import ROUND_FLOOR, Decimal
from enum import StrEnum
from hashlib import sha256
from uuid import UUID, uuid5

OVERHEAD_NAMESPACE = UUID("ab5675ab-39d7-53ca-95fa-f68df4ab7ba5")
CONTRACT_VERSION = "economics.overhead-allocation-evidence.v1"


class OverheadAuthorityError(ValueError):
    """Raised when overhead evidence is not admissible."""


class AllocationBasisType(StrEnum):
    LABOR_HOURS = "labor_hours"
    DIRECT_LABOR_COST = "direct_labor_cost"
    REVENUE = "revenue"
    JOB_COUNT = "job_count"
    SERVICE_CATEGORY_MEASURE = "service_category_measure"
    EXPLICIT_REFERENCE = "explicit_reference"


class AllocationReadiness(StrEnum):
    CONFIGURED = "configured"
    UNCONFIGURED = "unconfigured"
    INSUFFICIENT_SOURCE = "insufficient_source"
    STALE = "stale"
    CONFLICTING = "conflicting"
    POLICY_REQUIRED = "policy_required"
    READY = "ready"


@dataclass(frozen=True, slots=True)
class OverheadSourceEvidence:
    evidence_id: str
    digest: str
    company_id: UUID
    branch_id: UUID | None
    period_start: date
    period_end: date
    currency: str
    amount_minor: int
    accepted_at: datetime
    complete: bool

    def __post_init__(self) -> None:
        if not self.evidence_id.strip() or len(self.digest) != 64:
            raise OverheadAuthorityError(
                "source evidence identity and digest are required"
            )
        if self.period_end < self.period_start:
            raise OverheadAuthorityError("source evidence period is invalid")
        if len(self.currency) != 3 or not self.currency.isalpha():
            raise OverheadAuthorityError("source evidence currency is invalid")


@dataclass(frozen=True, slots=True)
class OverheadPoolAuthority:
    pool_id: UUID
    company_id: UUID
    branch_id: UUID | None
    pool_key: str
    version: int
    effective_start: date
    effective_end: date | None
    currency: str
    source_requirement_refs: tuple[str, ...]
    approved: bool
    authority_digest: str
    supersedes_pool_id: UUID | None = None

    def __post_init__(self) -> None:
        if not self.pool_key.strip() or self.version < 1:
            raise OverheadAuthorityError(
                "pool identity and positive version are required"
            )
        if self.effective_end is not None and self.effective_end < self.effective_start:
            raise OverheadAuthorityError("pool effective interval is invalid")
        if len(self.currency) != 3 or not self.currency.isalpha():
            raise OverheadAuthorityError("pool currency is invalid")
        if not self.source_requirement_refs or len(self.authority_digest) != 64:
            raise OverheadAuthorityError(
                "pool requires source rules and authority digest"
            )


@dataclass(frozen=True, slots=True)
class AllocationPolicyAuthority:
    policy_id: UUID
    company_id: UUID
    branch_id: UUID | None
    policy_key: str
    version: int
    pool_id: UUID
    basis_type: AllocationBasisType
    basis_reference: str
    effective_start: date
    effective_end: date | None
    maximum_source_age_days: int
    approved: bool
    authority_digest: str
    supersedes_policy_id: UUID | None = None

    def __post_init__(self) -> None:
        if not self.policy_key.strip() or self.version < 1:
            raise OverheadAuthorityError(
                "allocation policy identity and version are required"
            )
        if not self.basis_reference.strip():
            raise OverheadAuthorityError(
                "allocation basis requires an evidence reference"
            )
        if self.maximum_source_age_days < 1:
            raise OverheadAuthorityError("source freshness window must be positive")
        if self.effective_end is not None and self.effective_end < self.effective_start:
            raise OverheadAuthorityError("policy effective interval is invalid")
        if len(self.authority_digest) != 64:
            raise OverheadAuthorityError("policy authority digest is invalid")


@dataclass(frozen=True, slots=True)
class AllocationBasisEvidence:
    target_kind: str
    target_id: UUID
    company_id: UUID
    branch_id: UUID | None
    period_start: date
    period_end: date
    basis_value: Decimal
    evidence_id: str
    digest: str
    accepted_at: datetime
    complete: bool

    def __post_init__(self) -> None:
        if not self.target_kind.strip() or self.basis_value < 0:
            raise OverheadAuthorityError(
                "basis target and non-negative value are required"
            )
        if not self.evidence_id.strip() or len(self.digest) != 64:
            raise OverheadAuthorityError(
                "basis evidence identity and digest are required"
            )


@dataclass(frozen=True, slots=True)
class AllocationReadinessResult:
    state: AllocationReadiness
    blockers: tuple[str, ...]
    pool_id: UUID | None
    policy_id: UUID | None


@dataclass(frozen=True, slots=True)
class OverheadAllocationLine:
    target_kind: str
    target_id: UUID
    branch_id: UUID | None
    basis_value: str
    amount_minor: int
    source_digest: str


@dataclass(frozen=True, slots=True)
class OverheadAllocationEvidence:
    allocation_id: UUID
    company_id: UUID
    pool_id: UUID
    pool_version: int
    policy_id: UUID
    policy_version: int
    period_start: date
    period_end: date
    currency: str
    amount_minor: int
    lines: tuple[OverheadAllocationLine, ...]
    source_evidence_digests: tuple[str, ...]
    authority_digests: tuple[str, ...]
    predecessor_allocation_id: UUID | None
    contract_version: str
    allocation_digest: str


def assess_configuration_readiness(
    pools: tuple[OverheadPoolAuthority, ...],
    policies: tuple[AllocationPolicyAuthority, ...],
) -> AllocationReadinessResult:
    """Classify policy configuration without pretending source evidence is ready."""
    if not pools:
        return AllocationReadinessResult(
            AllocationReadiness.UNCONFIGURED,
            ("overhead_pool_required",),
            None,
            None,
        )
    approved_pools = tuple(item for item in pools if item.approved)
    if not approved_pools:
        return AllocationReadinessResult(
            AllocationReadiness.POLICY_REQUIRED,
            ("approved_pool_required",),
            None,
            None,
        )
    if len(approved_pools) != 1:
        return AllocationReadinessResult(
            AllocationReadiness.CONFLICTING,
            ("pool_authority_conflict",),
            None,
            None,
        )
    pool = approved_pools[0]
    approved_policies = tuple(
        item for item in policies if item.approved and item.pool_id == pool.pool_id
    )
    if not approved_policies:
        return AllocationReadinessResult(
            AllocationReadiness.POLICY_REQUIRED,
            ("approved_allocation_policy_required",),
            pool.pool_id,
            None,
        )
    if len(approved_policies) != 1:
        return AllocationReadinessResult(
            AllocationReadiness.CONFLICTING,
            ("allocation_policy_conflict",),
            pool.pool_id,
            None,
        )
    return AllocationReadinessResult(
        AllocationReadiness.CONFIGURED,
        (),
        pool.pool_id,
        approved_policies[0].policy_id,
    )


def assess_allocation_readiness(
    *,
    company_id: UUID,
    branch_id: UUID | None,
    period_start: date,
    period_end: date,
    currency: str,
    as_of: datetime,
    pools: tuple[OverheadPoolAuthority, ...],
    policies: tuple[AllocationPolicyAuthority, ...],
    sources: tuple[OverheadSourceEvidence, ...],
    basis: tuple[AllocationBasisEvidence, ...],
) -> AllocationReadinessResult:
    if not pools:
        return AllocationReadinessResult(
            AllocationReadiness.UNCONFIGURED, ("overhead_pool_required",), None, None
        )
    eligible_pools = tuple(
        item
        for item in pools
        if item.approved
        and _covers(item.effective_start, item.effective_end, period_start, period_end)
    )
    if not eligible_pools:
        return AllocationReadinessResult(
            AllocationReadiness.POLICY_REQUIRED,
            ("approved_effective_pool_required",),
            None,
            None,
        )
    if len(eligible_pools) != 1:
        return AllocationReadinessResult(
            AllocationReadiness.CONFLICTING, ("overlapping_pool_authority",), None, None
        )
    pool = eligible_pools[0]
    eligible_policies = tuple(
        item
        for item in policies
        if item.approved
        and item.pool_id == pool.pool_id
        and _covers(item.effective_start, item.effective_end, period_start, period_end)
    )
    if not eligible_policies:
        return AllocationReadinessResult(
            AllocationReadiness.POLICY_REQUIRED,
            ("approved_allocation_policy_required",),
            pool.pool_id,
            None,
        )
    if len(eligible_policies) != 1:
        return AllocationReadinessResult(
            AllocationReadiness.CONFLICTING,
            ("overlapping_allocation_policy",),
            pool.pool_id,
            None,
        )
    policy = eligible_policies[0]
    if (
        any(item.company_id != company_id for item in sources)
        or any(item.company_id != company_id for item in basis)
        or pool.company_id != company_id
        or policy.company_id != company_id
    ):
        return AllocationReadinessResult(
            AllocationReadiness.CONFLICTING,
            ("cross_company_evidence",),
            pool.pool_id,
            policy.policy_id,
        )
    if (
        pool.branch_id != branch_id
        or policy.branch_id != branch_id
        or any(item.branch_id != branch_id for item in sources)
        or any(item.branch_id != branch_id for item in basis)
    ):
        return AllocationReadinessResult(
            AllocationReadiness.CONFLICTING,
            ("cross_branch_evidence",),
            pool.pool_id,
            policy.policy_id,
        )
    if pool.currency.upper() != currency.upper() or any(
        item.currency.upper() != currency.upper() for item in sources
    ):
        return AllocationReadinessResult(
            AllocationReadiness.CONFLICTING,
            ("currency_mismatch",),
            pool.pool_id,
            policy.policy_id,
        )
    if any(
        item.period_start != period_start or item.period_end != period_end
        for item in sources
    ) or any(
        item.period_start != period_start or item.period_end != period_end
        for item in basis
    ):
        return AllocationReadinessResult(
            AllocationReadiness.CONFLICTING,
            ("period_mismatch",),
            pool.pool_id,
            policy.policy_id,
        )
    if (
        not sources
        or not basis
        or not all(item.complete for item in sources)
        or not all(item.complete for item in basis)
        or sum(item.basis_value for item in basis) <= 0
    ):
        return AllocationReadinessResult(
            AllocationReadiness.INSUFFICIENT_SOURCE,
            ("complete_pool_and_basis_evidence_required",),
            pool.pool_id,
            policy.policy_id,
        )
    cutoff = (
        as_of.astimezone(timezone.utc).date().toordinal()
        - policy.maximum_source_age_days
    )
    if any(
        item.accepted_at.astimezone(timezone.utc).date().toordinal() < cutoff
        for item in sources
    ) or any(
        item.accepted_at.astimezone(timezone.utc).date().toordinal() < cutoff
        for item in basis
    ):
        return AllocationReadinessResult(
            AllocationReadiness.STALE,
            ("source_evidence_stale",),
            pool.pool_id,
            policy.policy_id,
        )
    if len({(item.target_kind, item.target_id) for item in basis}) != len(basis):
        return AllocationReadinessResult(
            AllocationReadiness.CONFLICTING,
            ("duplicate_target_basis",),
            pool.pool_id,
            policy.policy_id,
        )
    return AllocationReadinessResult(
        AllocationReadiness.READY, (), pool.pool_id, policy.policy_id
    )


def allocate_overhead(
    *,
    company_id: UUID,
    branch_id: UUID | None,
    period_start: date,
    period_end: date,
    currency: str,
    as_of: datetime,
    pool: OverheadPoolAuthority,
    policy: AllocationPolicyAuthority,
    sources: tuple[OverheadSourceEvidence, ...],
    basis: tuple[AllocationBasisEvidence, ...],
    predecessor_allocation_id: UUID | None = None,
) -> OverheadAllocationEvidence:
    readiness = assess_allocation_readiness(
        company_id=company_id,
        branch_id=branch_id,
        period_start=period_start,
        period_end=period_end,
        currency=currency,
        as_of=as_of,
        pools=(pool,),
        policies=(policy,),
        sources=sources,
        basis=basis,
    )
    if readiness.state is not AllocationReadiness.READY:
        raise OverheadAuthorityError(
            f"allocation admission blocked: {readiness.state.value}:{','.join(readiness.blockers)}"
        )
    total = sum(item.amount_minor for item in sources)
    ordered = tuple(
        sorted(basis, key=lambda item: (item.target_kind, str(item.target_id)))
    )
    denominator = sum(item.basis_value for item in ordered)
    unsigned = abs(total)
    amounts = [
        int(
            (Decimal(unsigned) * item.basis_value / denominator).to_integral_value(
                rounding=ROUND_FLOOR
            )
        )
        for item in ordered
    ]
    remainder = unsigned - sum(amounts)
    for index in range(remainder):
        amounts[index % len(amounts)] += 1
    if total < 0:
        amounts = [-item for item in amounts]
    manifest = {
        "contract_version": CONTRACT_VERSION,
        "company_id": str(company_id),
        "branch_id": str(branch_id) if branch_id else None,
        "period": [period_start.isoformat(), period_end.isoformat()],
        "currency": currency.upper(),
        "pool": [str(pool.pool_id), pool.version, pool.authority_digest],
        "policy": [
            str(policy.policy_id),
            policy.version,
            policy.basis_type.value,
            policy.basis_reference,
            policy.authority_digest,
        ],
        "sources": sorted(
            (item.evidence_id, item.digest, item.amount_minor) for item in sources
        ),
        "basis": [
            (item.target_kind, str(item.target_id), str(item.basis_value), item.digest)
            for item in ordered
        ],
        "predecessor": str(predecessor_allocation_id)
        if predecessor_allocation_id
        else None,
    }
    digest = sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    allocation_id = uuid5(OVERHEAD_NAMESPACE, digest)
    lines = tuple(
        OverheadAllocationLine(
            item.target_kind,
            item.target_id,
            item.branch_id,
            str(item.basis_value),
            amount,
            item.digest,
        )
        for item, amount in zip(ordered, amounts, strict=True)
    )
    if sum(item.amount_minor for item in lines) != total:
        raise OverheadAuthorityError("allocation residual did not reconcile")
    return OverheadAllocationEvidence(
        allocation_id,
        company_id,
        pool.pool_id,
        pool.version,
        policy.policy_id,
        policy.version,
        period_start,
        period_end,
        currency.upper(),
        total,
        lines,
        tuple(
            sorted(
                (*[item.digest for item in sources], *[item.digest for item in basis])
            )
        ),
        tuple(sorted((pool.authority_digest, policy.authority_digest))),
        predecessor_allocation_id,
        CONTRACT_VERSION,
        digest,
    )


def callback_economics_requirements() -> dict[str, object]:
    """Safe seam only; callback/warranty economics remains externally gated."""
    return {
        "state": "external_gate",
        "required_authorities": [
            "authoritative_callback_or_warranty_job_relationship",
            "accepted_incremental_labor_evidence",
            "accepted_incremental_material_evidence",
            "approved_overhead_pool_and_allocation_policy",
        ],
        "prohibition": "no callback cost or causality may be inferred from labels or free text",
    }


def _covers(
    start: date, end: date | None, period_start: date, period_end: date
) -> bool:
    return start <= period_start and (end is None or period_end <= end)
