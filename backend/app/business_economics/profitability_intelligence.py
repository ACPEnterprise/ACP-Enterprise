"""Immutable contracts for evidence-backed profitability intelligence.

This module intentionally contains no persistence, calculation service, runtime
execution, provider, or Luminary implementation. Economics is the authority for
the values described here; consumers may explain them but cannot amend them.
"""

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from string import hexdigits
from uuid import UUID

from app.business_economics.profitability_domain import EconomicCategory


class ProfitabilityValueState(StrEnum):
    MEASURED = "measured"
    ALLOCATED = "allocated"
    ESTIMATED = "estimated"
    MISSING = "missing"


class ProfitabilityBasis(StrEnum):
    ACTUAL = "actual"
    ESTIMATED = "estimated"


class ProfitabilityScope(StrEnum):
    JOB = "job"
    TECHNICIAN = "technician"
    BRANCH = "branch"
    COMPANY = "company"


class AllocationBoundary(StrEnum):
    DIRECT = "direct"
    JOB = "job"
    TECHNICIAN = "technician"
    TRUCK_DAY = "truck_day"
    BRANCH = "branch"
    COMPANY = "company"


class ProfitabilityFindingKind(StrEnum):
    DRIVER = "driver"
    VARIANCE = "variance"
    MISSING_EVIDENCE = "missing_evidence"
    INTEGRITY = "integrity"


class ProfitabilityActionKind(StrEnum):
    CLASSIFY = "classify"
    ATTRIBUTE = "attribute"
    CORRECT = "correct"
    APPROVE_POLICY = "approve_policy"
    INVESTIGATE = "investigate"


def _required(value: str, name: str) -> None:
    if not value.strip():
        raise ValueError(f"{name} is required")


def _sha256(value: str, name: str) -> None:
    if len(value) != 64 or any(character not in hexdigits for character in value):
        raise ValueError(f"{name} must be a SHA-256 digest")


@dataclass(frozen=True, slots=True)
class ProfitabilityPeriod:
    start: date
    end: date
    as_of: datetime
    close_state: str
    accounting_basis: str

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError("profitability period end cannot precede its start")
        _required(self.close_state, "close state")
        _required(self.accounting_basis, "accounting basis")


@dataclass(frozen=True, slots=True)
class ProfitabilityEvidence:
    owner: str
    source_system: str
    record_type: str
    record_id: str
    source_version: str
    content_digest: str
    effective_at: datetime
    business_event_id: UUID | None = None

    def __post_init__(self) -> None:
        for value, name in (
            (self.owner, "evidence owner"),
            (self.source_system, "evidence source system"),
            (self.record_type, "evidence record type"),
            (self.record_id, "evidence record id"),
            (self.source_version, "evidence source version"),
        ):
            _required(value, name)
        _sha256(self.content_digest, "evidence content digest")


@dataclass(frozen=True, slots=True)
class ProfitabilityQuality:
    confidence_percent: int
    completeness_percent: int
    fresh_as_of: datetime
    freshness_status: str
    explanation: str
    missing_categories: tuple[EconomicCategory, ...] = ()

    def __post_init__(self) -> None:
        if not 0 <= self.confidence_percent <= 100:
            raise ValueError("confidence must be between 0 and 100")
        if not 0 <= self.completeness_percent <= 100:
            raise ValueError("completeness must be between 0 and 100")
        _required(self.freshness_status, "freshness status")
        _required(self.explanation, "quality explanation")
        if self.completeness_percent == 100 and self.missing_categories:
            raise ValueError("complete profitability cannot name missing categories")
        if self.completeness_percent < 100 and not self.missing_categories:
            raise ValueError("incomplete profitability must name missing categories")


@dataclass(frozen=True, slots=True)
class AllocationPolicyReference:
    policy_id: UUID
    policy_key: str
    policy_version: int
    run_id: UUID
    run_version: int
    boundary: AllocationBoundary
    driver: str
    input_digest: str
    explanation: str

    def __post_init__(self) -> None:
        _required(self.policy_key, "allocation policy key")
        _required(self.driver, "allocation driver")
        _required(self.explanation, "allocation explanation")
        if self.policy_version < 1 or self.run_version < 1:
            raise ValueError("allocation policy and run versions must be positive")
        _sha256(self.input_digest, "allocation input digest")


@dataclass(frozen=True, slots=True)
class ProfitabilityComponent:
    category: EconomicCategory
    state: ProfitabilityValueState
    amount_minor: int | None
    currency: str
    confidence_percent: int
    explanation: str
    evidence: tuple[ProfitabilityEvidence, ...] = ()
    allocations: tuple[AllocationPolicyReference, ...] = ()

    def __post_init__(self) -> None:
        if len(self.currency) != 3 or not self.currency.isalpha():
            raise ValueError("component currency must be an ISO 4217 alpha code")
        if not 0 <= self.confidence_percent <= 100:
            raise ValueError("component confidence must be between 0 and 100")
        _required(self.explanation, "component explanation")
        if self.state is ProfitabilityValueState.MISSING:
            if self.amount_minor is not None or self.confidence_percent != 0:
                raise ValueError("missing component has no amount and zero confidence")
            if self.evidence or self.allocations:
                raise ValueError(
                    "missing component cannot claim evidence or allocations"
                )
            return
        if self.amount_minor is None:
            raise ValueError("known component requires an amount")
        if not self.evidence:
            raise ValueError("known component requires evidence")
        if (
            self.state is ProfitabilityValueState.MEASURED
            and self.confidence_percent != 100
        ):
            raise ValueError("measured component confidence must be 100")
        if self.state is ProfitabilityValueState.MEASURED and self.allocations:
            raise ValueError("measured component cannot claim allocation lineage")
        if self.state is ProfitabilityValueState.ALLOCATED and not self.allocations:
            raise ValueError("allocated component requires allocation lineage")
        if self.state is not ProfitabilityValueState.ALLOCATED and self.allocations:
            raise ValueError("only allocated components may claim allocation lineage")


@dataclass(frozen=True, slots=True)
class ProfitabilityAnalysis:
    analysis_id: UUID
    company_id: UUID
    branch_id: UUID | None
    scope: ProfitabilityScope
    subject_id: UUID
    period: ProfitabilityPeriod
    basis: ProfitabilityBasis
    revenue: ProfitabilityComponent
    labor: ProfitabilityComponent
    materials: ProfitabilityComponent
    equipment: ProfitabilityComponent
    truck: ProfitabilityComponent
    overhead: ProfitabilityComponent
    gross_profit: ProfitabilityComponent
    net_profit: ProfitabilityComponent
    quality: ProfitabilityQuality
    measurement_ids: tuple[UUID, ...]
    projection_ids: tuple[UUID, ...]
    lineage_digest: str
    engine_version: str
    version: int

    def __post_init__(self) -> None:
        components = (
            self.revenue,
            self.labor,
            self.materials,
            self.equipment,
            self.truck,
            self.overhead,
            self.gross_profit,
            self.net_profit,
        )
        expected = (
            EconomicCategory.REVENUE,
            EconomicCategory.LABOR,
            EconomicCategory.MATERIALS,
            EconomicCategory.EQUIPMENT,
            EconomicCategory.TRUCK,
            EconomicCategory.OVERHEAD,
            EconomicCategory.GROSS_PROFIT,
            EconomicCategory.NET_PROFIT,
        )
        if tuple(item.category for item in components) != expected:
            raise ValueError(
                "profitability components are assigned to wrong categories"
            )
        if len({item.currency.upper() for item in components}) != 1:
            raise ValueError("profitability analysis cannot mix currencies")
        if self.version < 1:
            raise ValueError("profitability analysis version must be positive")
        if not self.measurement_ids or not self.projection_ids:
            raise ValueError("analysis requires measurement and projection lineage")
        _sha256(self.lineage_digest, "analysis lineage digest")
        _required(self.engine_version, "analysis engine version")
        direct_inputs = components[:5]
        if all(item.amount_minor is not None for item in direct_inputs):
            revenue, labor, materials, equipment, truck = (
                item.amount_minor for item in direct_inputs
            )
            assert revenue is not None
            assert labor is not None
            assert materials is not None
            assert equipment is not None
            assert truck is not None
            gross = revenue - labor - materials - equipment - truck
            if self.gross_profit.amount_minor != gross:
                raise ValueError(
                    "gross profit does not reconcile to measured components"
                )
        elif self.gross_profit.state is not ProfitabilityValueState.MISSING:
            raise ValueError(
                "gross profit remains missing when direct inputs are missing"
            )
        overhead = self.overhead.amount_minor
        gross_amount = self.gross_profit.amount_minor
        if overhead is not None and gross_amount is not None:
            if self.net_profit.amount_minor != gross_amount - overhead:
                raise ValueError("net profit does not reconcile to measured components")
        elif self.net_profit.state is not ProfitabilityValueState.MISSING:
            raise ValueError(
                "net profit remains missing when required inputs are missing"
            )


@dataclass(frozen=True, slots=True)
class ProfitabilityComparison:
    actual_analysis_id: UUID
    estimated_analysis_id: UUID
    revenue_variance_minor: int | None
    labor_variance_minor: int | None
    materials_variance_minor: int | None
    equipment_variance_minor: int | None
    truck_variance_minor: int | None
    overhead_variance_minor: int | None
    net_profit_variance_minor: int | None
    explanation: str

    def __post_init__(self) -> None:
        if self.actual_analysis_id == self.estimated_analysis_id:
            raise ValueError("actual and estimated analyses must be distinct")
        _required(self.explanation, "comparison explanation")


@dataclass(frozen=True, slots=True)
class ProfitabilityFinding:
    kind: ProfitabilityFindingKind
    summary: str
    component_categories: tuple[EconomicCategory, ...]
    evidence_digests: tuple[str, ...]
    explanation: str

    def __post_init__(self) -> None:
        _required(self.summary, "finding summary")
        _required(self.explanation, "finding explanation")
        if not self.component_categories:
            raise ValueError("finding requires at least one component category")
        for digest in self.evidence_digests:
            _sha256(digest, "finding evidence digest")
        if self.kind is not ProfitabilityFindingKind.MISSING_EVIDENCE and not (
            self.evidence_digests
        ):
            raise ValueError("evidence-backed finding requires evidence digests")


@dataclass(frozen=True, slots=True)
class ProfitabilityRecommendation:
    kind: ProfitabilityActionKind
    action: str
    responsible_owner: str
    expected_evidence: str
    rationale: str

    def __post_init__(self) -> None:
        for value, name in (
            (self.action, "recommended action"),
            (self.responsible_owner, "recommendation owner"),
            (self.expected_evidence, "recommendation evidence"),
            (self.rationale, "recommendation rationale"),
        ):
            _required(value, name)


@dataclass(frozen=True, slots=True)
class ProfitabilityExplanation:
    analysis_id: UUID
    analysis_version: int
    answer: str
    findings: tuple[ProfitabilityFinding, ...]
    recommendations: tuple[ProfitabilityRecommendation, ...]
    limitations: tuple[str, ...]
    lineage_digest: str

    def __post_init__(self) -> None:
        if self.analysis_version < 1:
            raise ValueError("explanation analysis version must be positive")
        _required(self.answer, "profitability answer")
        if not self.findings:
            raise ValueError("profitability explanation requires findings")
        if not self.limitations:
            raise ValueError("profitability explanation requires limitations")
        if any(not item.strip() for item in self.limitations):
            raise ValueError("profitability limitations must not be blank")
        _sha256(self.lineage_digest, "explanation lineage digest")
