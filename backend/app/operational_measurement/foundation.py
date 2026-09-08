"""Policy-neutral operational measurement facts and deterministic packets.

Facts in this module describe source evidence.  They do not select an
efficiency, allocation, pricing, staffing, or profitability policy.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Final
from uuid import UUID

CONTRACT_VERSION: Final = "economics.operational-measurement.v1"
MAX_FACTS_PER_PACKET: Final = 10_000


class EvidenceState(StrEnum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    ABSENT = "ABSENT"
    CONFLICTING = "CONFLICTING"
    SOURCE_REQUIRED = "SOURCE_REQUIRED"
    EXTERNAL_GATE = "EXTERNAL_GATE"


class FactClass(StrEnum):
    MEASURED_FACT = "MEASURED_FACT"
    DERIVED_MEASUREMENT = "DERIVED_MEASUREMENT"
    POLICY_PARAMETER = "POLICY_PARAMETER"
    MODEL_OUTPUT = "MODEL_OUTPUT"
    RECOMMENDATION = "RECOMMENDATION"
    OWNER_DECISION = "OWNER_DECISION"


class TimeMeasure(StrEnum):
    PAID_TIME = "PAID_TIME"
    AVAILABLE_TIME = "AVAILABLE_TIME"
    SCHEDULED_TIME = "SCHEDULED_TIME"
    TRAVEL_TIME = "TRAVEL_TIME"
    ARRIVAL_WAIT_TIME = "ARRIVAL_WAIT_TIME"
    ACTIVE_JOB_TIME = "ACTIVE_JOB_TIME"
    PAUSED_JOB_TIME = "PAUSED_JOB_TIME"
    NONPRODUCTIVE_TIME = "NONPRODUCTIVE_TIME"
    BREAK_TIME = "BREAK_TIME"
    OVERTIME = "OVERTIME"
    UNCLASSIFIED_TIME = "UNCLASSIFIED_TIME"


@dataclass(frozen=True, slots=True)
class Dimension:
    company_id: UUID
    branch_id: UUID | None
    period_start: date
    period_end: date
    employee_id: UUID | None = None
    job_id: UUID | None = None
    service_category: str | None = None

    def __post_init__(self) -> None:
        if self.period_end < self.period_start:
            raise ValueError("measurement period end precedes start")


@dataclass(frozen=True, slots=True)
class MeasurementFact:
    fact_id: UUID
    dimension: Dimension
    measure: str
    fact_class: FactClass
    state: EvidenceState
    value: Decimal | int | str | None
    unit: str | None
    source_authority: str
    source_record_ids: tuple[str, ...]
    source_version: str
    observed_at: datetime
    freshness_at: datetime | None
    missing_inputs: tuple[str, ...] = ()
    conflicting_inputs: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    sample_count: int | None = None
    predecessor_fact_id: UUID | None = None
    correction_reason: str | None = None

    def __post_init__(self) -> None:
        if self.fact_class not in {
            FactClass.MEASURED_FACT,
            FactClass.DERIVED_MEASUREMENT,
        }:
            raise ValueError("operational packets accept facts and derivations only")
        if self.observed_at.tzinfo is None:
            raise ValueError("observed_at must be timezone-aware")
        if self.freshness_at is not None and self.freshness_at.tzinfo is None:
            raise ValueError("freshness_at must be timezone-aware")
        if self.state is EvidenceState.AVAILABLE and self.value is None:
            raise ValueError("available evidence requires a value")
        if self.state is not EvidenceState.AVAILABLE and self.value is not None:
            raise ValueError("incomplete evidence cannot carry a precise value")
        if self.sample_count is not None and self.sample_count < 0:
            raise ValueError("sample_count cannot be negative")
        if self.predecessor_fact_id is not None and not self.correction_reason:
            raise ValueError("a correction requires a reason")

    @property
    def digest(self) -> str:
        return _digest(_jsonable(asdict(self)))


@dataclass(frozen=True, slots=True)
class AttributionReadiness:
    job_id: UUID
    employee_ids: tuple[UUID, ...]
    state: EvidenceState
    duration_attribution: str
    value_attribution: str
    cost_attribution: str
    missing_inputs: tuple[str, ...]

    def __post_init__(self) -> None:
        if len(set(self.employee_ids)) != len(self.employee_ids):
            raise ValueError("duplicate Employee attribution")
        if len(self.employee_ids) > 1 and any(
            item == "primary_employee"
            for item in (
                self.duration_attribution,
                self.value_attribution,
                self.cost_attribution,
            )
        ):
            raise ValueError("multi-technician evidence cannot default to primary")


@dataclass(frozen=True, slots=True)
class MeasurementPacket:
    packet_id: UUID
    company_id: UUID
    branch_id: UUID | None
    period_start: date
    period_end: date
    facts: tuple[MeasurementFact, ...]
    attribution: tuple[AttributionReadiness, ...]
    source_matrix: tuple[dict[str, object], ...]
    created_at: datetime
    predecessor_packet_id: UUID | None = None
    correction_reason: str | None = None
    contract_version: str = CONTRACT_VERSION

    def __post_init__(self) -> None:
        if len(self.facts) > MAX_FACTS_PER_PACKET:
            raise ValueError("measurement packet exceeds bounded fact count")
        if self.period_end < self.period_start:
            raise ValueError("measurement period end precedes start")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        if self.predecessor_packet_id is not None and not self.correction_reason:
            raise ValueError("successor packet requires correction reason")
        for fact in self.facts:
            if fact.dimension.company_id != self.company_id:
                raise ValueError("foreign Company fact")
            if (
                self.branch_id is not None
                and fact.dimension.branch_id != self.branch_id
            ):
                raise ValueError("foreign or unbound Branch fact")
            if (
                fact.dimension.period_start < self.period_start
                or fact.dimension.period_end > self.period_end
            ):
                raise ValueError("fact falls outside packet period")

    @property
    def digest(self) -> str:
        body = asdict(self)
        body.pop("packet_id")
        return _digest(_jsonable(body))

    @property
    def source_version_digest(self) -> str:
        return _digest(
            sorted(
                (fact.source_authority, fact.source_version, fact.digest)
                for fact in self.facts
            )
        )

    def readiness(self) -> dict[str, object]:
        incomplete = tuple(
            sorted(
                {
                    item
                    for fact in self.facts
                    for item in (*fact.missing_inputs, *fact.conflicting_inputs)
                }
            )
        )
        return {
            "contract_version": self.contract_version,
            "packet_digest": self.digest,
            "fact_count": len(self.facts),
            "available_count": sum(
                f.state is EvidenceState.AVAILABLE for f in self.facts
            ),
            "incomplete_inputs": incomplete,
            "limitations": (
                "No canonical efficiency KPI is selected.",
                "No policy parameter, causal conclusion, recommendation, or owner decision is produced.",
                "Payment is not substituted for work or earned revenue.",
                "Planned material and Price Book assumptions are not substituted for actual cost or duration.",
            ),
        }


def source_matrix() -> tuple[dict[str, object], ...]:
    """Repository authority audit; conservative states are intentional."""
    rows = (
        (
            "employee_paid_time",
            "AVAILABLE",
            "timekeeping",
            "Approved workday time; Payroll cost remains protected.",
        ),
        (
            "timekeeping_breaks",
            "AVAILABLE",
            "timekeeping",
            "Punch and approved-entry evidence.",
        ),
        (
            "job_assignment",
            "AVAILABLE",
            "dispatch",
            "Assignment is not labor/value attribution.",
        ),
        (
            "appointment_schedule",
            "AVAILABLE",
            "scheduling",
            "Scheduled windows are not worked time.",
        ),
        (
            "dispatch_en_route_arrival",
            "AVAILABLE",
            "dispatch",
            "Lifecycle events; route duration may remain unknown.",
        ),
        (
            "job_work_start_completion",
            "AVAILABLE",
            "jobs",
            "Lifecycle timestamps where recorded.",
        ),
        (
            "job_pause_resume_history",
            "PARTIAL",
            "jobs",
            "Current pause state exists; complete interval history is not guaranteed.",
        ),
        (
            "job_value",
            "PARTIAL",
            "jobs",
            "Distinct from Estimate, Invoice, Payment, settlement, and cash.",
        ),
        (
            "estimate_presentation_acceptance",
            "AVAILABLE",
            "estimates",
            "Opportunity comparability and lead identity may be incomplete.",
        ),
        (
            "invoice",
            "AVAILABLE",
            "invoicing",
            "Invoice is not Payment or earned-work proof by itself.",
        ),
        (
            "payment",
            "AVAILABLE",
            "payments",
            "Cash event; never substituted for work performed.",
        ),
        (
            "material_consumption_return_adjustment",
            "AVAILABLE",
            "inventory",
            "Actual movement only; planned Price Book material excluded.",
        ),
        (
            "purchase_receipt_cost",
            "AVAILABLE",
            "purchasing",
            "Accounting classification remains separate.",
        ),
        (
            "inventory_cost_layer",
            "PARTIAL",
            "inventory",
            "Cost provenance exists where recorded; gaps remain explicit.",
        ),
        (
            "fleet_readiness_maintenance",
            "AVAILABLE",
            "operational_assets",
            "Readiness is not Fleet cost.",
        ),
        (
            "fleet_fuel_insurance_depreciation",
            "SOURCE_REQUIRED",
            "fleet_accounting",
            "No cost manufactured.",
        ),
        (
            "callback_rework_identity",
            "SOURCE_REQUIRED",
            "jobs_assets",
            "Corrective-work relationship is incomplete.",
        ),
        (
            "customer_service_category_branch",
            "AVAILABLE",
            "customers_jobs_platform",
            "Only authoritative typed dimensions.",
        ),
        (
            "communications",
            "AVAILABLE",
            "communications",
            "Delivery does not prove conversion.",
        ),
        (
            "marketing_lead_source",
            "PARTIAL",
            "commercial_sources",
            "Only accepted lead identities may be used.",
        ),
        (
            "travel_route_duration",
            "EXTERNAL_GATE",
            "routing_provider",
            "Unknown without admitted route/location evidence.",
        ),
        (
            "external_market_price_share",
            "EXTERNAL_GATE",
            "market_provider",
            "No market average or competitive claim.",
        ),
        (
            "labor_base_compensation",
            "AVAILABLE",
            "payroll",
            "Owner-authorized aggregate use only.",
        ),
        ("labor_burden_benefits", "PARTIAL", "payroll", "No burden rate inferred."),
        (
            "job_labor_attribution",
            "PARTIAL",
            "timekeeping_dispatch_payroll",
            "Assignment alone is insufficient.",
        ),
        (
            "overhead_amount_period_account",
            "PARTIAL",
            "accounting",
            "Classification readiness only; no allocation method.",
        ),
        (
            "price_book_composition",
            "AVAILABLE",
            "price_book",
            "Configured assumptions are not measured operations.",
        ),
    )
    return tuple(
        {
            "input": name,
            "state": state,
            "authority": authority,
            "limitation": limitation,
        }
        for name, state, authority, limitation in rows
    )


def ratio_input_readiness(
    facts: Iterable[MeasurementFact],
) -> tuple[dict[str, object], ...]:
    """Expose components for possible ratios without selecting or calculating one."""
    available = {f.measure for f in facts if f.state is EvidenceState.AVAILABLE}
    candidates = (
        (
            "active_job_time_over_paid_time",
            (TimeMeasure.ACTIVE_JOB_TIME, TimeMeasure.PAID_TIME),
        ),
        (
            "productive_time_over_available_time",
            (TimeMeasure.ACTIVE_JOB_TIME, TimeMeasure.AVAILABLE_TIME),
        ),
        (
            "completed_work_time_over_paid_time",
            ("COMPLETED_WORK_TIME", TimeMeasure.PAID_TIME),
        ),
        (
            "scheduled_utilization",
            (TimeMeasure.SCHEDULED_TIME, TimeMeasure.AVAILABLE_TIME),
        ),
        (
            "capacity_utilization",
            (TimeMeasure.ACTIVE_JOB_TIME, TimeMeasure.AVAILABLE_TIME),
        ),
    )
    return tuple(
        {
            "candidate": name,
            "state": "INPUTS_AVAILABLE"
            if all(
                (i.value if isinstance(i, TimeMeasure) else i) in available
                for i in inputs
            )
            else "MEASUREMENT_INCOMPLETE",
            "required_inputs": tuple(
                i.value if isinstance(i, TimeMeasure) else i for i in inputs
            ),
            "selected_as_company_kpi": False,
        }
        for name, inputs in candidates
    )


def _jsonable(value: object) -> object:
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (UUID, date, datetime, Decimal, StrEnum)):
        return str(value)
    return value


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
