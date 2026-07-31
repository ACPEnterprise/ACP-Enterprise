from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class MeasurementStatus(StrEnum):
    MEASURED = "measured"
    ESTIMATED = "estimated"
    UNKNOWN = "unknown"


class EconomicCategory(StrEnum):
    REVENUE = "revenue"
    LABOR = "labor"
    MATERIALS = "materials"
    EQUIPMENT = "equipment"
    TRUCK = "truck"
    OVERHEAD = "overhead"
    GROSS_PROFIT = "gross_profit"
    NET_PROFIT = "net_profit"


class EvidenceKind(StrEnum):
    BUSINESS_EVENT = "business_event"
    SOURCE_RECORD = "source_record"
    ALLOCATION = "allocation"
    REASONING = "reasoning"


class AllocationStrategy(StrEnum):
    LABOR_HOURS = "labor_hours"
    REVENUE = "revenue"
    TRUCK_DAYS = "truck_days"
    JOB_DURATION = "job_duration"
    BRANCH = "branch"
    COMPANY = "company"


@dataclass(frozen=True, slots=True)
class Confidence:
    status: MeasurementStatus
    percentage: int
    explanation: str

    def __post_init__(self) -> None:
        if not 0 <= self.percentage <= 100:
            raise ValueError("confidence percentage must be between 0 and 100")
        if not self.explanation.strip():
            raise ValueError("confidence explanation is required")
        if self.status is MeasurementStatus.MEASURED and self.percentage != 100:
            raise ValueError("measured confidence must be 100 percent")
        if self.status is MeasurementStatus.UNKNOWN and self.percentage != 0:
            raise ValueError("unknown confidence must be 0 percent")


@dataclass(frozen=True, slots=True)
class EvidenceReference:
    kind: EvidenceKind
    reference_id: str
    source_system: str
    source_version: str
    explanation: str

    def __post_init__(self) -> None:
        for value in (
            self.reference_id,
            self.source_system,
            self.source_version,
            self.explanation,
        ):
            if not value.strip():
                raise ValueError("evidence fields must not be blank")


@dataclass(frozen=True, slots=True)
class BusinessFact:
    id: UUID
    company_id: UUID
    branch_id: UUID | None
    subject_type: str
    subject_id: UUID
    category: EconomicCategory
    amount_minor: int | None
    currency: str
    confidence: Confidence
    evidence: tuple[EvidenceReference, ...]
    occurred_at: datetime
    version: int = 1

    def __post_init__(self) -> None:
        if (
            self.amount_minor is None
            and self.confidence.status is not MeasurementStatus.UNKNOWN
        ):
            raise ValueError("a known fact requires an amount")
        if (
            self.amount_minor is not None
            and self.confidence.status is MeasurementStatus.UNKNOWN
        ):
            raise ValueError("an unknown fact cannot have an amount")
        if len(self.currency) != 3 or not self.currency.isalpha():
            raise ValueError("currency must be an ISO 4217 alpha code")
        if self.version < 1:
            raise ValueError("fact version must be positive")
        if self.amount_minor is not None and not self.evidence:
            raise ValueError("a known fact requires evidence")


@dataclass(frozen=True, slots=True)
class MeasuredCost:
    category: EconomicCategory
    amount_minor: int | None
    currency: str
    confidence: Confidence
    evidence: tuple[EvidenceReference, ...]


@dataclass(frozen=True, slots=True)
class Allocation:
    id: UUID
    source_fact_id: UUID
    subject_type: str
    subject_id: UUID
    strategy: str
    numerator: int
    denominator: int
    allocated_amount_minor: int
    strategy_version: str
    evidence: tuple[EvidenceReference, ...]

    def __post_init__(self) -> None:
        if self.denominator <= 0 or self.numerator < 0:
            raise ValueError(
                "allocation weights must be non-negative with a positive total"
            )
        if self.numerator > self.denominator:
            raise ValueError("allocation numerator cannot exceed denominator")
        if not self.strategy.strip() or not self.strategy_version.strip():
            raise ValueError("allocation strategy and version are required")


@dataclass(frozen=True, slots=True)
class ProfitMeasurement:
    subject_type: str
    subject_id: UUID
    currency: str
    revenue: MeasuredCost
    labor: MeasuredCost
    materials: MeasuredCost
    equipment: MeasuredCost
    truck: MeasuredCost
    overhead: MeasuredCost
    gross_profit: MeasuredCost
    net_profit: MeasuredCost
    confidence: Confidence
    evidence: tuple[EvidenceReference, ...]
    engine_version: str
