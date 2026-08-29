"""Deterministic, persistence-free profitability cost allocation engine."""

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum
from uuid import UUID, uuid5

from app.business_economics.profitability_domain import EconomicCategory
from app.business_economics.profitability_intelligence import (
    AllocationBoundary,
    AllocationPolicyReference,
    ProfitabilityEvidence,
    ProfitabilityValueState,
)

ALLOCATION_NAMESPACE = UUID("6fbda4f2-e421-5873-9867-6b28da0549c1")
SUPPORTED_BOUNDARIES = {
    AllocationBoundary.DIRECT,
    AllocationBoundary.TECHNICIAN,
    AllocationBoundary.TRUCK_DAY,
    AllocationBoundary.BRANCH,
    AllocationBoundary.COMPANY,
}


class DeterministicAllocationError(ValueError):
    pass


class AllocationStrategyKind(StrEnum):
    DIRECT = "direct"
    PROPORTIONAL = "proportional"
    LABOR_HOUR = "labor_hour"
    REVENUE_SHARE = "revenue_share"
    TRUCK_DAY = "truck_day"
    TECHNICIAN = "technician"
    BRANCH = "branch"
    COMPANY = "company"
    FIXED = "fixed"
    CUSTOM = "custom"


@dataclass(frozen=True, slots=True)
class CostPoolInput:
    source_fact_id: UUID
    source_version: int
    company_id: UUID
    branch_id: UUID | None
    category: EconomicCategory
    amount_minor: int
    currency: str
    state: ProfitabilityValueState
    confidence_percent: int
    period_start: date
    period_end: date
    evidence: tuple[ProfitabilityEvidence, ...]
    acquisition_digest: str
    completeness_percent: int
    source_subject_ids: tuple[UUID, ...] = ()

    def __post_init__(self) -> None:
        if self.category in {
            EconomicCategory.REVENUE,
            EconomicCategory.GROSS_PROFIT,
            EconomicCategory.NET_PROFIT,
        }:
            raise ValueError("allocation engine accepts cost categories only")
        if self.state not in {
            ProfitabilityValueState.MEASURED,
            ProfitabilityValueState.ESTIMATED,
        }:
            raise ValueError("cost pool must be measured or estimated")
        if self.source_version < 1 or not self.evidence:
            raise ValueError("cost pool requires versioned source evidence")
        if not 0 <= self.confidence_percent <= 100:
            raise ValueError("cost pool confidence must be between 0 and 100")
        if self.state is ProfitabilityValueState.MEASURED and (
            self.confidence_percent != 100
        ):
            raise ValueError("measured cost pool confidence must be 100")
        if len(self.currency) != 3 or not self.currency.isalpha():
            raise ValueError("cost pool currency must be an ISO 4217 code")
        if self.period_end < self.period_start:
            raise ValueError("cost pool period is invalid")
        if len(self.acquisition_digest) != 64:
            raise ValueError("cost pool acquisition digest must be SHA-256")
        if not 0 <= self.completeness_percent <= 100:
            raise ValueError("cost pool completeness must be between 0 and 100")


@dataclass(frozen=True, slots=True)
class AllocationPolicyInput:
    policy_id: UUID
    policy_key: str
    policy_version: int
    run_version: int
    boundary: AllocationBoundary
    strategy: AllocationStrategyKind
    driver: str
    effective_start: date
    effective_end: date | None
    explanation: str
    as_of: datetime
    maximum_evidence_age: timedelta

    def __post_init__(self) -> None:
        if self.boundary not in SUPPORTED_BOUNDARIES:
            raise ValueError("allocation boundary is not supported by Phase 8")
        if not self.policy_key.strip() or not self.driver.strip():
            raise ValueError("allocation policy key and driver are required")
        if not self.explanation.strip():
            raise ValueError("allocation policy explanation is required")
        if self.policy_version < 1 or self.run_version < 1:
            raise ValueError("allocation policy and run versions must be positive")
        if self.effective_end is not None and self.effective_end < self.effective_start:
            raise ValueError("allocation policy effective period is invalid")
        if self.maximum_evidence_age <= timedelta(0):
            raise ValueError("allocation evidence age policy must be positive")
        if self.strategy is AllocationStrategyKind.DIRECT and (
            self.boundary is not AllocationBoundary.DIRECT
        ):
            raise ValueError("direct strategy requires the direct boundary")


@dataclass(frozen=True, slots=True)
class AllocationTargetInput:
    company_id: UUID
    branch_id: UUID | None
    subject_type: str
    subject_id: UUID
    weight: int
    confidence_percent: int
    completeness_percent: int
    driver_evidence: tuple[ProfitabilityEvidence, ...]

    def __post_init__(self) -> None:
        if not self.subject_type.strip() or self.weight < 0:
            raise ValueError(
                "allocation target requires a subject and non-negative weight"
            )
        if not self.driver_evidence:
            raise ValueError("allocation target requires driver evidence")
        if (
            not 0 <= self.confidence_percent <= 100
            or not 0 <= self.completeness_percent <= 100
        ):
            raise ValueError("target confidence and completeness must be percentages")


@dataclass(frozen=True, slots=True)
class AllocationLine:
    line_id: UUID
    target_subject_type: str
    target_subject_id: UUID
    branch_id: UUID | None
    numerator: int
    denominator: int
    allocated_amount_minor: int
    confidence_percent: int
    completeness_percent: int
    evidence: tuple[ProfitabilityEvidence, ...]


@dataclass(frozen=True, slots=True)
class DeterministicAllocation:
    allocation_id: UUID
    company_id: UUID
    source_fact_id: UUID
    category: EconomicCategory
    amount_minor: int
    currency: str
    state: ProfitabilityValueState
    policy: AllocationPolicyReference
    lines: tuple[AllocationLine, ...]
    residual_minor: int
    evidence_digest: str

    def __post_init__(self) -> None:
        if (
            tuple(
                sorted(
                    self.lines,
                    key=lambda item: (
                        item.target_subject_type,
                        str(item.target_subject_id),
                    ),
                )
            )
            != self.lines
        ):
            raise ValueError("allocation lines must be canonically ordered")
        if sum(item.allocated_amount_minor for item in self.lines) != self.amount_minor:
            raise ValueError("allocation lines must balance to the cost pool")
        if self.residual_minor != 0:
            raise ValueError("deterministic allocation cannot retain a residual")


class DeterministicAllocationEngine:
    def allocate(
        self,
        pool: CostPoolInput,
        policy: AllocationPolicyInput,
        targets: tuple[AllocationTargetInput, ...],
        prior_allocation_ids: tuple[UUID, ...] = (),
    ) -> DeterministicAllocation:
        self._validate(pool, policy, targets)
        ordered = tuple(
            sorted(targets, key=lambda item: (item.subject_type, str(item.subject_id)))
        )
        denominator = sum(item.weight for item in ordered)
        magnitude = abs(pool.amount_minor)
        sign = -1 if pool.amount_minor < 0 else 1
        amounts = [sign * (magnitude * item.weight // denominator) for item in ordered]
        remainder = pool.amount_minor - sum(amounts)
        for index in range(abs(remainder)):
            amounts[index % len(amounts)] += 1 if remainder > 0 else -1

        manifest = {
            "pool": [
                str(pool.source_fact_id),
                pool.source_version,
                pool.category.value,
                pool.amount_minor,
                pool.currency.upper(),
                pool.state.value,
                pool.confidence_percent,
                [item.content_digest for item in self._evidence(pool.evidence)],
            ],
            "policy": [
                str(policy.policy_id),
                policy.policy_key,
                policy.policy_version,
                policy.run_version,
                policy.boundary.value,
                policy.strategy.value,
                policy.driver,
            ],
            "targets": [
                [
                    item.subject_type,
                    str(item.subject_id),
                    str(item.company_id),
                    str(item.branch_id) if item.branch_id else None,
                    item.weight,
                    [
                        evidence.content_digest
                        for evidence in self._evidence(item.driver_evidence)
                    ],
                ]
                for item in ordered
            ],
        }
        digest = hashlib.sha256(
            json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        allocation_id = uuid5(ALLOCATION_NAMESPACE, digest)
        if allocation_id in prior_allocation_ids:
            raise DeterministicAllocationError("duplicate allocation identity")
        run_id = uuid5(ALLOCATION_NAMESPACE, f"run:{digest}")
        policy_reference = AllocationPolicyReference(
            policy_id=policy.policy_id,
            policy_key=policy.policy_key,
            policy_version=policy.policy_version,
            run_id=run_id,
            run_version=policy.run_version,
            boundary=policy.boundary,
            driver=policy.driver,
            input_digest=digest,
            explanation=policy.explanation,
        )
        lines = tuple(
            AllocationLine(
                line_id=uuid5(
                    ALLOCATION_NAMESPACE,
                    f"{digest}:{item.subject_type}:{item.subject_id}",
                ),
                target_subject_type=item.subject_type,
                target_subject_id=item.subject_id,
                branch_id=item.branch_id,
                numerator=item.weight,
                denominator=denominator,
                allocated_amount_minor=amount,
                confidence_percent=pool.confidence_percent,
                completeness_percent=min(
                    pool.completeness_percent, item.completeness_percent
                ),
                evidence=self._evidence((*pool.evidence, *item.driver_evidence)),
            )
            for item, amount in zip(ordered, amounts, strict=True)
        )
        return DeterministicAllocation(
            allocation_id=allocation_id,
            company_id=pool.company_id,
            source_fact_id=pool.source_fact_id,
            category=pool.category,
            amount_minor=pool.amount_minor,
            currency=pool.currency.upper(),
            state=ProfitabilityValueState.ALLOCATED,
            policy=policy_reference,
            lines=lines,
            residual_minor=pool.amount_minor
            - sum(item.allocated_amount_minor for item in lines),
            evidence_digest=digest,
        )

    @staticmethod
    def _validate(
        pool: CostPoolInput,
        policy: AllocationPolicyInput,
        targets: tuple[AllocationTargetInput, ...],
    ) -> None:
        if not targets or sum(item.weight for item in targets) <= 0:
            raise DeterministicAllocationError(
                "allocation requires positive target weight"
            )
        identities = {(item.subject_type, item.subject_id) for item in targets}
        if len(identities) != len(targets):
            raise DeterministicAllocationError("allocation targets must be unique")
        if any(item.company_id != pool.company_id for item in targets):
            raise DeterministicAllocationError(
                "allocation cannot cross Company boundaries"
            )
        if any(item.subject_id in pool.source_subject_ids for item in targets):
            raise DeterministicAllocationError("circular allocation is prohibited")
        if (
            pool.branch_id is not None
            and policy.boundary
            not in {
                AllocationBoundary.COMPANY,
                AllocationBoundary.BRANCH,
            }
            and any(item.branch_id != pool.branch_id for item in targets)
        ):
            raise DeterministicAllocationError(
                "allocation cannot cross Branch boundaries"
            )
        if policy.boundary is AllocationBoundary.DIRECT and len(targets) != 1:
            raise DeterministicAllocationError(
                "direct cost requires exactly one target"
            )
        if pool.period_start < policy.effective_start or (
            policy.effective_end is not None and pool.period_end > policy.effective_end
        ):
            raise DeterministicAllocationError("allocation policy is not effective")
        if pool.currency.upper() != "USD":
            raise DeterministicAllocationError("allocation currency is unsupported")
        cutoff = policy.as_of - policy.maximum_evidence_age
        evidence = (
            *pool.evidence,
            *(item for target in targets for item in target.driver_evidence),
        )
        if any(item.effective_at < cutoff for item in evidence):
            raise DeterministicAllocationError("allocation evidence is stale")
        DeterministicAllocationEngine._evidence(tuple(evidence))

    @staticmethod
    def _evidence(
        values: tuple[ProfitabilityEvidence, ...],
    ) -> tuple[ProfitabilityEvidence, ...]:
        identities: dict[tuple[str, str, str, str], ProfitabilityEvidence] = {}
        for item in values:
            key = (
                item.source_system,
                item.record_type,
                item.record_id,
                item.source_version,
            )
            prior = identities.get(key)
            if prior is not None and prior.content_digest != item.content_digest:
                raise DeterministicAllocationError(
                    "allocation evidence identity has contradictory digests"
                )
            identities[key] = item
        return tuple(
            sorted(
                identities.values(),
                key=lambda item: (
                    item.source_system,
                    item.record_type,
                    item.record_id,
                    item.source_version,
                    item.content_digest,
                ),
            )
        )
