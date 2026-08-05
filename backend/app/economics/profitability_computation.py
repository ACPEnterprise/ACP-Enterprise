"""Deterministic application service for profitability analysis.

The ports expose immutable Economics inputs. This module owns no operational
transactions or persistence and performs no scheduling or provider calls.
"""

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Protocol
from uuid import UUID, uuid5

from app.economics.domain import EconomicCategory
from app.economics.profitability_intelligence import (
    AllocationPolicyReference,
    ProfitabilityActionKind,
    ProfitabilityAnalysis,
    ProfitabilityBasis,
    ProfitabilityComponent,
    ProfitabilityEvidence,
    ProfitabilityExplanation,
    ProfitabilityFinding,
    ProfitabilityFindingKind,
    ProfitabilityPeriod,
    ProfitabilityQuality,
    ProfitabilityRecommendation,
    ProfitabilityScope,
    ProfitabilityValueState,
)

INPUT_CATEGORIES = (
    EconomicCategory.REVENUE,
    EconomicCategory.LABOR,
    EconomicCategory.MATERIALS,
    EconomicCategory.EQUIPMENT,
    EconomicCategory.TRUCK,
    EconomicCategory.OVERHEAD,
)
ANALYSIS_NAMESPACE = UUID("99ec1731-3fe7-5a62-aaf4-f690673fce8d")
ENGINE_VERSION = "profitability-computation-v1"


class ProfitabilityComputationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ProfitabilityComputationRequest:
    company_id: UUID
    branch_id: UUID | None
    scope: ProfitabilityScope
    subject_id: UUID
    period: ProfitabilityPeriod
    basis: ProfitabilityBasis
    currency: str
    projection_ids: tuple[UUID, ...]
    responsible_owner: str
    maximum_evidence_age: timedelta
    analysis_version: int = 1

    def __post_init__(self) -> None:
        if len(self.currency) != 3 or not self.currency.isalpha():
            raise ValueError("request currency must be an ISO 4217 alpha code")
        if not self.projection_ids:
            raise ValueError("request requires projection lineage")
        if not self.responsible_owner.strip():
            raise ValueError("request responsible owner is required")
        if self.maximum_evidence_age <= timedelta(0):
            raise ValueError("maximum evidence age must be positive")
        if self.analysis_version < 1:
            raise ValueError("analysis version must be positive")


@dataclass(frozen=True, slots=True)
class ProfitabilityFactInput:
    fact_id: UUID
    measurement_id: UUID
    company_id: UUID
    branch_id: UUID | None
    scope: ProfitabilityScope
    subject_id: UUID
    period_start: date
    period_end: date
    basis: ProfitabilityBasis
    category: EconomicCategory
    fact_key: str
    version: int
    state: ProfitabilityValueState
    amount_minor: int
    currency: str
    confidence_percent: int
    evidence: tuple[ProfitabilityEvidence, ...]

    def __post_init__(self) -> None:
        if self.category not in INPUT_CATEGORIES:
            raise ValueError("fact category is not a profitability input")
        if self.state not in {
            ProfitabilityValueState.MEASURED,
            ProfitabilityValueState.ESTIMATED,
        }:
            raise ValueError("facts must be measured or estimated")
        if not self.fact_key.strip() or self.version < 1:
            raise ValueError("fact key and positive version are required")
        if not 0 <= self.confidence_percent <= 100 or not self.evidence:
            raise ValueError("fact requires confidence and evidence")
        if self.state is ProfitabilityValueState.MEASURED and (
            self.confidence_percent != 100
        ):
            raise ValueError("measured fact confidence must be 100")


@dataclass(frozen=True, slots=True)
class ProfitabilityAllocationInput:
    allocation_id: UUID
    company_id: UUID
    branch_id: UUID | None
    scope: ProfitabilityScope
    subject_id: UUID
    period_start: date
    period_end: date
    basis: ProfitabilityBasis
    category: EconomicCategory
    amount_minor: int
    currency: str
    confidence_percent: int
    policy: AllocationPolicyReference
    evidence: tuple[ProfitabilityEvidence, ...]

    def __post_init__(self) -> None:
        if self.category not in INPUT_CATEGORIES:
            raise ValueError("allocation category is not a profitability input")
        if not 0 <= self.confidence_percent <= 100 or not self.evidence:
            raise ValueError("allocation requires confidence and evidence")


class ProfitabilityFactPort(Protocol):
    def facts_for(
        self, request: ProfitabilityComputationRequest
    ) -> Sequence[ProfitabilityFactInput]: ...


class ProfitabilityAllocationPort(Protocol):
    def allocations_for(
        self, request: ProfitabilityComputationRequest
    ) -> Sequence[ProfitabilityAllocationInput]: ...


@dataclass(frozen=True, slots=True)
class ProfitabilityComputationResult:
    analysis: ProfitabilityAnalysis
    explanation: ProfitabilityExplanation


class ProfitabilityComputationService:
    def __init__(
        self,
        fact_port: ProfitabilityFactPort,
        allocation_port: ProfitabilityAllocationPort,
    ) -> None:
        self._fact_port = fact_port
        self._allocation_port = allocation_port

    def compute(
        self, request: ProfitabilityComputationRequest
    ) -> ProfitabilityComputationResult:
        facts = self._facts(request)
        allocations = self._allocations(request)
        evidence = self._evidence(request, facts, allocations)
        lineage_digest = self._lineage_digest(request, facts, allocations)
        components = {
            category: self._component(request, category, facts, allocations)
            for category in INPUT_CATEGORIES
        }
        gross = self._profit_component(
            EconomicCategory.GROSS_PROFIT,
            (
                components[EconomicCategory.REVENUE],
                components[EconomicCategory.LABOR],
                components[EconomicCategory.MATERIALS],
                components[EconomicCategory.EQUIPMENT],
                components[EconomicCategory.TRUCK],
            ),
            request.currency,
        )
        net = self._profit_component(
            EconomicCategory.NET_PROFIT,
            (gross, components[EconomicCategory.OVERHEAD]),
            request.currency,
        )
        missing = tuple(
            category
            for category in INPUT_CATEGORIES
            if components[category].state is ProfitabilityValueState.MISSING
        )
        confidence = min(
            (components[item].confidence_percent for item in INPUT_CATEGORIES),
            default=0,
        )
        completeness = ((len(INPUT_CATEGORIES) - len(missing)) * 100) // len(
            INPUT_CATEGORIES
        )
        quality = ProfitabilityQuality(
            confidence_percent=confidence,
            completeness_percent=completeness,
            fresh_as_of=min(item.effective_at for item in evidence),
            freshness_status="current",
            explanation=(
                "All required profitability categories are present and current."
                if not missing
                else "Required categories are missing; dependent profit is unknown."
            ),
            missing_categories=missing,
        )
        analysis = ProfitabilityAnalysis(
            analysis_id=uuid5(ANALYSIS_NAMESPACE, lineage_digest),
            company_id=request.company_id,
            branch_id=request.branch_id,
            scope=request.scope,
            subject_id=request.subject_id,
            period=request.period,
            basis=request.basis,
            revenue=components[EconomicCategory.REVENUE],
            labor=components[EconomicCategory.LABOR],
            materials=components[EconomicCategory.MATERIALS],
            equipment=components[EconomicCategory.EQUIPMENT],
            truck=components[EconomicCategory.TRUCK],
            overhead=components[EconomicCategory.OVERHEAD],
            gross_profit=gross,
            net_profit=net,
            quality=quality,
            measurement_ids=tuple(
                sorted({item.measurement_id for item in facts}, key=str)
            ),
            projection_ids=tuple(sorted(set(request.projection_ids), key=str)),
            lineage_digest=lineage_digest,
            engine_version=ENGINE_VERSION,
            version=request.analysis_version,
        )
        return ProfitabilityComputationResult(
            analysis=analysis,
            explanation=self._explanation(analysis, request.responsible_owner),
        )

    def _facts(
        self, request: ProfitabilityComputationRequest
    ) -> tuple[ProfitabilityFactInput, ...]:
        values = tuple(self._fact_port.facts_for(request))
        self._validate_scope(request, values)
        if request.basis is ProfitabilityBasis.ACTUAL and any(
            item.state is ProfitabilityValueState.ESTIMATED for item in values
        ):
            raise ProfitabilityComputationError(
                "actual analysis cannot consume estimated facts"
            )
        identities: dict[tuple[str, int], ProfitabilityFactInput] = {}
        for item in values:
            identity = (item.fact_key, item.version)
            prior = identities.get(identity)
            if prior is not None and prior != item:
                raise ProfitabilityComputationError("contradictory fact versions")
            identities[identity] = item
        return tuple(sorted(identities.values(), key=self._fact_key))

    def _allocations(
        self, request: ProfitabilityComputationRequest
    ) -> tuple[ProfitabilityAllocationInput, ...]:
        values = tuple(self._allocation_port.allocations_for(request))
        self._validate_scope(request, values)
        identities: dict[UUID, ProfitabilityAllocationInput] = {}
        for item in values:
            prior = identities.get(item.allocation_id)
            if prior is not None and prior != item:
                raise ProfitabilityComputationError("contradictory allocation versions")
            identities[item.allocation_id] = item
        return tuple(
            sorted(identities.values(), key=lambda item: str(item.allocation_id))
        )

    @staticmethod
    def _validate_scope(
        request: ProfitabilityComputationRequest,
        values: Sequence[ProfitabilityFactInput | ProfitabilityAllocationInput],
    ) -> None:
        for item in values:
            if (
                item.company_id != request.company_id
                or item.branch_id != request.branch_id
                or item.scope is not request.scope
                or item.subject_id != request.subject_id
                or item.period_start != request.period.start
                or item.period_end != request.period.end
                or item.basis is not request.basis
                or item.currency.upper() != request.currency.upper()
            ):
                raise ProfitabilityComputationError(
                    "profitability input is outside the requested scope"
                )

    @staticmethod
    def _evidence(
        request: ProfitabilityComputationRequest,
        facts: tuple[ProfitabilityFactInput, ...],
        allocations: tuple[ProfitabilityAllocationInput, ...],
    ) -> tuple[ProfitabilityEvidence, ...]:
        identities: dict[tuple[str, str, str, str], ProfitabilityEvidence] = {}
        cutoff = request.period.as_of - request.maximum_evidence_age
        sources: tuple[ProfitabilityFactInput | ProfitabilityAllocationInput, ...] = (
            *facts,
            *allocations,
        )
        for source in sources:
            for item in source.evidence:
                if item.effective_at > request.period.as_of:
                    raise ProfitabilityComputationError(
                        "future evidence is contradictory"
                    )
                if item.effective_at < cutoff:
                    raise ProfitabilityComputationError(
                        "evidence is stale beyond policy"
                    )
                identity = (
                    item.source_system,
                    item.record_type,
                    item.record_id,
                    item.source_version,
                )
                prior = identities.get(identity)
                if prior is not None and prior.content_digest != item.content_digest:
                    raise ProfitabilityComputationError(
                        "evidence identity has contradictory digests"
                    )
                identities[identity] = item
        if not identities:
            raise ProfitabilityComputationError(
                "no authoritative evidence is available"
            )
        return tuple(
            sorted(
                identities.values(),
                key=ProfitabilityComputationService._evidence_key,
            )
        )

    @staticmethod
    def _component(
        request: ProfitabilityComputationRequest,
        category: EconomicCategory,
        facts: tuple[ProfitabilityFactInput, ...],
        allocations: tuple[ProfitabilityAllocationInput, ...],
    ) -> ProfitabilityComponent:
        category_facts = tuple(item for item in facts if item.category is category)
        category_allocations = tuple(
            item for item in allocations if item.category is category
        )
        if not category_facts and not category_allocations:
            return ProfitabilityComponent(
                category=category,
                state=ProfitabilityValueState.MISSING,
                amount_minor=None,
                currency=request.currency,
                confidence_percent=0,
                explanation=f"Authoritative {category.value} evidence is missing.",
            )
        sources: tuple[ProfitabilityFactInput | ProfitabilityAllocationInput, ...] = (
            *category_facts,
            *category_allocations,
        )
        evidence = tuple(
            sorted(
                {item for source in sources for item in source.evidence},
                key=ProfitabilityComputationService._evidence_key,
            )
        )
        policy_refs = tuple(item.policy for item in category_allocations)
        state = (
            ProfitabilityValueState.ALLOCATED
            if category_allocations
            else ProfitabilityValueState.ESTIMATED
            if any(
                item.state is ProfitabilityValueState.ESTIMATED
                for item in category_facts
            )
            else ProfitabilityValueState.MEASURED
        )
        amounts = [item.amount_minor for item in category_facts]
        amounts.extend(item.amount_minor for item in category_allocations)
        confidence = min(
            [item.confidence_percent for item in category_facts]
            + [item.confidence_percent for item in category_allocations]
        )
        return ProfitabilityComponent(
            category=category,
            state=state,
            amount_minor=sum(amounts),
            currency=request.currency,
            confidence_percent=confidence,
            explanation=f"{category.value} is derived from authoritative Economics inputs.",
            evidence=evidence,
            allocations=policy_refs,
        )

    @staticmethod
    def _profit_component(
        category: EconomicCategory,
        inputs: tuple[ProfitabilityComponent, ...],
        currency: str,
    ) -> ProfitabilityComponent:
        if any(item.state is ProfitabilityValueState.MISSING for item in inputs):
            return ProfitabilityComponent(
                category=category,
                state=ProfitabilityValueState.MISSING,
                amount_minor=None,
                currency=currency,
                confidence_percent=0,
                explanation=f"{category.value} is unknown because required inputs are missing.",
            )
        evidence = tuple(
            sorted(
                {item for source in inputs for item in source.evidence},
                key=ProfitabilityComputationService._evidence_key,
            )
        )
        allocations = tuple(
            sorted(
                {item for source in inputs for item in source.allocations},
                key=lambda item: (
                    item.policy_key,
                    item.policy_version,
                    str(item.run_id),
                ),
            )
        )
        state = (
            ProfitabilityValueState.ALLOCATED
            if allocations
            else ProfitabilityValueState.ESTIMATED
            if any(item.state is ProfitabilityValueState.ESTIMATED for item in inputs)
            else ProfitabilityValueState.MEASURED
        )
        amounts = [item.amount_minor for item in inputs]
        assert all(item is not None for item in amounts)
        amount = amounts[0]
        assert amount is not None
        for item in amounts[1:]:
            assert item is not None
            amount -= item
        return ProfitabilityComponent(
            category=category,
            state=state,
            amount_minor=amount,
            currency=currency,
            confidence_percent=min(item.confidence_percent for item in inputs),
            explanation=f"{category.value} reconciles deterministically to its inputs.",
            evidence=evidence,
            allocations=allocations,
        )

    @staticmethod
    def _explanation(
        analysis: ProfitabilityAnalysis, responsible_owner: str
    ) -> ProfitabilityExplanation:
        findings: list[ProfitabilityFinding] = []
        recommendations: list[ProfitabilityRecommendation] = []
        for category in analysis.quality.missing_categories:
            findings.append(
                ProfitabilityFinding(
                    kind=ProfitabilityFindingKind.MISSING_EVIDENCE,
                    summary=f"{category.value} is missing.",
                    component_categories=(category,),
                    evidence_digests=(),
                    explanation="Profit cannot be completed without authoritative evidence.",
                )
            )
            recommendations.append(
                ProfitabilityRecommendation(
                    kind=ProfitabilityActionKind.CLASSIFY,
                    action=f"Supply authoritative {category.value} evidence.",
                    responsible_owner=responsible_owner,
                    expected_evidence=f"Versioned {category.value} source evidence.",
                    rationale="Missing values cannot be inferred or treated as zero.",
                )
            )
        if not findings:
            costs = (
                analysis.labor,
                analysis.materials,
                analysis.equipment,
                analysis.truck,
                analysis.overhead,
            )
            driver = max(costs, key=lambda item: abs(item.amount_minor or 0))
            findings.append(
                ProfitabilityFinding(
                    kind=ProfitabilityFindingKind.DRIVER,
                    summary=f"{driver.category.value} is the largest cost component.",
                    component_categories=(driver.category,),
                    evidence_digests=tuple(
                        item.content_digest for item in driver.evidence
                    ),
                    explanation="The driver is selected from reconciled component amounts.",
                )
            )
        net = analysis.net_profit.amount_minor
        answer = (
            "Exact net profitability is unknown because required evidence is missing."
            if net is None
            else f"Reconciled net profit is {net} minor currency units."
        )
        limitations = tuple(
            f"Missing authoritative {item.value} evidence."
            for item in analysis.quality.missing_categories
        ) or (
            "Explanation is limited to the supplied authoritative Economics evidence.",
        )
        return ProfitabilityExplanation(
            analysis_id=analysis.analysis_id,
            analysis_version=analysis.version,
            answer=answer,
            findings=tuple(findings),
            recommendations=tuple(recommendations),
            limitations=limitations,
            lineage_digest=analysis.lineage_digest,
        )

    @staticmethod
    def _lineage_digest(
        request: ProfitabilityComputationRequest,
        facts: tuple[ProfitabilityFactInput, ...],
        allocations: tuple[ProfitabilityAllocationInput, ...],
    ) -> str:
        payload = {
            "request": {
                "company_id": str(request.company_id),
                "branch_id": str(request.branch_id) if request.branch_id else None,
                "scope": request.scope.value,
                "subject_id": str(request.subject_id),
                "period": [
                    request.period.start.isoformat(),
                    request.period.end.isoformat(),
                ],
                "as_of": request.period.as_of.isoformat(),
                "basis": request.basis.value,
                "currency": request.currency.upper(),
                "projection_ids": sorted(str(item) for item in request.projection_ids),
                "analysis_version": request.analysis_version,
            },
            "facts": [
                [
                    str(item.fact_id),
                    item.fact_key,
                    item.version,
                    item.category.value,
                    item.state.value,
                    item.amount_minor,
                    item.currency.upper(),
                    item.confidence_percent,
                    [
                        e.content_digest
                        for e in sorted(
                            item.evidence,
                            key=ProfitabilityComputationService._evidence_key,
                        )
                    ],
                ]
                for item in facts
            ],
            "allocations": [
                [
                    str(item.allocation_id),
                    item.category.value,
                    item.amount_minor,
                    item.currency.upper(),
                    item.confidence_percent,
                    item.policy.input_digest,
                    [
                        e.content_digest
                        for e in sorted(
                            item.evidence,
                            key=ProfitabilityComputationService._evidence_key,
                        )
                    ],
                ]
                for item in allocations
            ],
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    @staticmethod
    def _evidence_key(item: ProfitabilityEvidence) -> tuple[str, ...]:
        return (
            item.source_system,
            item.record_type,
            item.record_id,
            item.source_version,
            item.content_digest,
        )

    @staticmethod
    def _fact_key(item: ProfitabilityFactInput) -> tuple[str, int, str]:
        return (item.fact_key, item.version, str(item.fact_id))
