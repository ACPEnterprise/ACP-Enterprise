"""Reconciled profitability metrics and comparisons over Phase 6 inputs."""

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID, uuid5

from app.business_economics.profitability_computation import (
    ProfitabilityAllocationInput,
    ProfitabilityAllocationPort,
    ProfitabilityComputationRequest,
    ProfitabilityComputationResult,
    ProfitabilityComputationService,
    ProfitabilityFactInput,
    ProfitabilityFactPort,
)
from app.business_economics.profitability_intelligence import (
    ProfitabilityBasis,
    ProfitabilityScope,
)

ENGINE_NAMESPACE = UUID("3233107b-5c38-52c6-a5f2-7f9ce44b62c7")


class AllocationCostRole(StrEnum):
    DIRECT = "direct"
    TECHNICIAN_BURDEN = "technician_burden"
    BRANCH_OVERHEAD = "branch_overhead"
    COMPANY_OVERHEAD = "company_overhead"
    ADMINISTRATIVE_OVERHEAD = "administrative_overhead"


class ProfitabilityEngineError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class AcquiredProfitabilityFact:
    fact: ProfitabilityFactInput
    acquisition_digest: str
    completeness_percent: int
    explanation_id: UUID


@dataclass(frozen=True, slots=True)
class AllocatedProfitabilityCost:
    allocation: ProfitabilityAllocationInput
    role: AllocationCostRole
    allocation_digest: str
    completeness_percent: int


@dataclass(frozen=True, slots=True)
class ProfitabilityMetrics:
    contribution_margin_minor: int | None
    gross_margin_basis_points: int | None
    net_margin_basis_points: int | None
    allocated_cost_minor: int
    fully_burdened_cost_minor: int | None


@dataclass(frozen=True, slots=True)
class ReconciledProfitabilityResult:
    result_id: UUID
    computation: ProfitabilityComputationResult
    metrics: ProfitabilityMetrics
    acquisition_digests: tuple[str, ...]
    allocation_digests: tuple[str, ...]
    explanation_ids: tuple[UUID, ...]
    digest: str


@dataclass(frozen=True, slots=True)
class ProfitabilityComparisonResult:
    comparison_id: UUID
    left_result_id: UUID
    right_result_id: UUID
    scope: ProfitabilityScope
    left_basis: ProfitabilityBasis
    right_basis: ProfitabilityBasis
    revenue_variance_minor: int | None
    gross_profit_variance_minor: int | None
    net_profit_variance_minor: int | None
    allocated_cost_variance_minor: int
    digest: str


class _FactPort(ProfitabilityFactPort):
    def __init__(self, values: tuple[ProfitabilityFactInput, ...]) -> None:
        self.values = values

    def facts_for(self, request: ProfitabilityComputationRequest):
        return self.values


class _AllocationPort(ProfitabilityAllocationPort):
    def __init__(self, values: tuple[ProfitabilityAllocationInput, ...]) -> None:
        self.values = values

    def allocations_for(self, request: ProfitabilityComputationRequest):
        return self.values


class ReconciledProfitabilityEngine:
    def compute(
        self,
        request: ProfitabilityComputationRequest,
        facts: tuple[AcquiredProfitabilityFact, ...],
        allocations: tuple[AllocatedProfitabilityCost, ...],
    ) -> ReconciledProfitabilityResult:
        self._validate_lineage(facts, allocations)
        computation = ProfitabilityComputationService(
            _FactPort(tuple(item.fact for item in facts)),
            _AllocationPort(tuple(item.allocation for item in allocations)),
        ).compute(request)
        analysis = computation.analysis
        revenue = analysis.revenue.amount_minor
        gross = analysis.gross_profit.amount_minor
        net = analysis.net_profit.amount_minor
        allocated = sum(item.allocation.amount_minor for item in allocations)
        direct_values = (
            analysis.labor.amount_minor,
            analysis.materials.amount_minor,
            analysis.equipment.amount_minor,
            analysis.truck.amount_minor,
            analysis.overhead.amount_minor,
        )
        fully_burdened = (
            None
            if any(item is None for item in direct_values)
            else sum(item for item in direct_values if item is not None) + allocated
        )
        metrics = ProfitabilityMetrics(
            contribution_margin_minor=gross,
            gross_margin_basis_points=self._margin(gross, revenue),
            net_margin_basis_points=self._margin(net, revenue),
            allocated_cost_minor=allocated,
            fully_burdened_cost_minor=fully_burdened,
        )
        acquisition_digests = tuple(sorted({item.acquisition_digest for item in facts}))
        allocation_digests = tuple(
            sorted({item.allocation_digest for item in allocations})
        )
        explanation_ids = tuple(
            sorted({item.explanation_id for item in facts}, key=str)
        )
        payload = {
            "analysis": analysis.lineage_digest,
            "acquisition": acquisition_digests,
            "allocation": allocation_digests,
            "explanations": [str(item) for item in explanation_ids],
            "metrics": [
                metrics.contribution_margin_minor,
                metrics.gross_margin_basis_points,
                metrics.net_margin_basis_points,
                metrics.allocated_cost_minor,
                metrics.fully_burdened_cost_minor,
            ],
        }
        digest = self._digest(payload)
        return ReconciledProfitabilityResult(
            result_id=uuid5(ENGINE_NAMESPACE, digest),
            computation=computation,
            metrics=metrics,
            acquisition_digests=acquisition_digests,
            allocation_digests=allocation_digests,
            explanation_ids=explanation_ids,
            digest=digest,
        )

    @staticmethod
    def compare(
        left: ReconciledProfitabilityResult,
        right: ReconciledProfitabilityResult,
    ) -> ProfitabilityComparisonResult:
        left_analysis = left.computation.analysis
        right_analysis = right.computation.analysis
        if left_analysis.scope is not right_analysis.scope:
            raise ProfitabilityEngineError("comparison scopes must match")
        payload = [left.digest, right.digest, left_analysis.scope.value]
        digest = ReconciledProfitabilityEngine._digest(payload)
        return ProfitabilityComparisonResult(
            comparison_id=uuid5(ENGINE_NAMESPACE, f"comparison:{digest}"),
            left_result_id=left.result_id,
            right_result_id=right.result_id,
            scope=left_analysis.scope,
            left_basis=left_analysis.basis,
            right_basis=right_analysis.basis,
            revenue_variance_minor=ReconciledProfitabilityEngine._variance(
                left_analysis.revenue.amount_minor, right_analysis.revenue.amount_minor
            ),
            gross_profit_variance_minor=ReconciledProfitabilityEngine._variance(
                left_analysis.gross_profit.amount_minor,
                right_analysis.gross_profit.amount_minor,
            ),
            net_profit_variance_minor=ReconciledProfitabilityEngine._variance(
                left_analysis.net_profit.amount_minor,
                right_analysis.net_profit.amount_minor,
            ),
            allocated_cost_variance_minor=(
                left.metrics.allocated_cost_minor - right.metrics.allocated_cost_minor
            ),
            digest=digest,
        )

    @staticmethod
    def _validate_lineage(
        facts: tuple[AcquiredProfitabilityFact, ...],
        allocations: tuple[AllocatedProfitabilityCost, ...],
    ) -> None:
        for digest in (
            *(item.acquisition_digest for item in facts),
            *(item.allocation_digest for item in allocations),
        ):
            if len(digest) != 64:
                raise ProfitabilityEngineError("lineage digest must be SHA-256")
        completeness = [item.completeness_percent for item in facts]
        completeness.extend(item.completeness_percent for item in allocations)
        if any(not 0 <= item <= 100 for item in completeness):
            raise ProfitabilityEngineError("lineage completeness must be a percentage")

    @staticmethod
    def _margin(profit: int | None, revenue: int | None) -> int | None:
        if profit is None or revenue is None or revenue == 0:
            return None
        return profit * 10_000 // revenue

    @staticmethod
    def _variance(left: int | None, right: int | None) -> int | None:
        return None if left is None or right is None else left - right

    @staticmethod
    def _digest(payload: object) -> str:
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
