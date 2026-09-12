"""Policy-neutral productive-hour readiness over authoritative labor evidence."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Final
from uuid import UUID

from .labor_evidence import (
    Confidence,
    EmployeeLaborEvidence,
    JobLaborEvidence,
    LaborEvidencePacket,
    ProvenanceRef,
)

CONTRACT_VERSION: Final = "economics.productive-hour-readiness.v1"
MAX_SUPPLEMENTAL_FACTS: Final = 50_000


class ReadinessState(StrEnum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    ABSENT = "ABSENT"
    CONFLICTING = "CONFLICTING"


class ProductiveHourMeasure(StrEnum):
    PAID_MINUTES = "PAID_MINUTES"
    SCHEDULED_MINUTES = "SCHEDULED_MINUTES"
    ACTUAL_WORKED_MINUTES = "ACTUAL_WORKED_MINUTES"
    JOBSITE_MINUTES = "JOBSITE_MINUTES"
    PRODUCTIVE_JOB_MINUTES = "PRODUCTIVE_JOB_MINUTES"
    TRAVEL_MINUTES = "TRAVEL_MINUTES"
    NONPRODUCTIVE_OPERATIONAL_MINUTES = "NONPRODUCTIVE_OPERATIONAL_MINUTES"
    UNCLASSIFIED_PAID_MINUTES = "UNCLASSIFIED_PAID_MINUTES"


@dataclass(frozen=True, slots=True)
class SupplementalTimeFact:
    company_id: UUID
    branch_id: UUID
    employee_id: UUID
    measure: ProductiveHourMeasure
    state: ReadinessState
    minutes: int | None
    provenance: tuple[ProvenanceRef, ...]
    job_id: UUID | None = None
    appointment_id: UUID | None = None
    missing_inputs: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.measure not in {
            ProductiveHourMeasure.TRAVEL_MINUTES,
            ProductiveHourMeasure.NONPRODUCTIVE_OPERATIONAL_MINUTES,
        }:
            raise ValueError("supplemental facts are limited to operational time")
        if self.state is ReadinessState.AVAILABLE and (
            self.minutes is None or self.minutes < 0 or not self.provenance
        ):
            raise ValueError(
                "available supplemental time requires minutes and provenance"
            )
        if self.state is not ReadinessState.AVAILABLE and self.minutes is not None:
            raise ValueError("incomplete supplemental evidence cannot claim minutes")
        if (self.job_id is None) != (self.appointment_id is None):
            raise ValueError("Job and Appointment identity must appear together")


@dataclass(frozen=True, slots=True)
class MeasureReadiness:
    measure: ProductiveHourMeasure
    state: ReadinessState
    minutes: int | None
    provenance: tuple[ProvenanceRef, ...]
    missing_inputs: tuple[str, ...]
    conflicts: tuple[str, ...]
    limitation: str


@dataclass(frozen=True, slots=True)
class ScopeReadiness:
    scope: str
    company_id: UUID
    branch_id: UUID | None
    employee_id: UUID | None
    job_id: UUID | None
    appointment_id: UUID | None
    measures: tuple[MeasureReadiness, ...]
    confidence: Confidence
    evidence_digest: str


@dataclass(frozen=True, slots=True)
class ProductiveHourReadinessPacket:
    contract_version: str
    labor_contract_version: str
    company_id: UUID
    company: ScopeReadiness
    branches: tuple[ScopeReadiness, ...]
    employees: tuple[ScopeReadiness, ...]
    jobs: tuple[ScopeReadiness, ...]
    downstream_contract: dict[str, object]
    evidence_digest: str


def build_productive_hour_readiness(
    labor: LaborEvidencePacket,
    *,
    supplemental: tuple[SupplementalTimeFact, ...] = (),
) -> ProductiveHourReadinessPacket:
    if len(supplemental) > MAX_SUPPLEMENTAL_FACTS:
        raise ValueError("supplemental evidence exceeds bounded size")
    if any(item.company_id != labor.company_id for item in supplemental):
        raise ValueError("foreign Company supplemental evidence")
    job_keys = {
        (item.branch_id, item.employee_id, item.job_id, item.appointment_id)
        for item in labor.jobs
    }
    for item in supplemental:
        if (
            item.job_id is not None
            and (
                item.branch_id,
                item.employee_id,
                item.job_id,
                item.appointment_id,
            )
            not in job_keys
        ):
            raise ValueError("supplemental Job evidence lacks labor relationship")

    by_job: dict[tuple[UUID, UUID, UUID, UUID], list[SupplementalTimeFact]] = (
        defaultdict(list)
    )
    by_employee: dict[UUID, list[SupplementalTimeFact]] = defaultdict(list)
    for item in supplemental:
        by_employee[item.employee_id].append(item)
        if item.job_id is not None and item.appointment_id is not None:
            by_job[
                (item.branch_id, item.employee_id, item.job_id, item.appointment_id)
            ].append(item)

    jobs = tuple(
        _job_scope(
            item,
            by_job[
                (item.branch_id, item.employee_id, item.job_id, item.appointment_id)
            ],
        )
        for item in labor.jobs
    )
    employees = tuple(
        _employee_scope(
            item,
            by_employee[item.employee_id],
            tuple(scope for scope in jobs if scope.employee_id == item.employee_id),
        )
        for item in labor.employees
    )
    branches = tuple(
        _aggregate_scope(
            "BRANCH",
            labor.company_id,
            branch_id,
            tuple(item for item in jobs if item.branch_id == branch_id),
        )
        for branch_id in sorted(
            {item.branch_id for item in jobs if item.branch_id is not None}, key=str
        )
    )
    company = _company_scope(labor.company_id, jobs, employees)
    downstream = downstream_contract()
    canonical = {
        "contract_version": CONTRACT_VERSION,
        "labor_contract_version": labor.contract_version,
        "labor_evidence_digest": labor.evidence_digest,
        "company": asdict(company),
        "branches": [asdict(x) for x in branches],
        "employees": [asdict(x) for x in employees],
        "jobs": [asdict(x) for x in jobs],
        "downstream_contract": downstream,
    }
    return ProductiveHourReadinessPacket(
        CONTRACT_VERSION,
        labor.contract_version,
        labor.company_id,
        company,
        branches,
        employees,
        jobs,
        downstream,
        _digest(canonical),
    )


def downstream_contract() -> dict[str, object]:
    return {
        "break_even_inputs": (
            "paid_minutes",
            "actual_worked_minutes",
            "productive_job_minutes",
            "travel_minutes",
            "nonproductive_operational_minutes",
            "unclassified_paid_minutes",
            "actual_labor_cost",
        ),
        "labor_cost_inputs": (
            "approved_paid_minutes",
            "actual_compensation",
            "actual_overtime",
            "actual_employer_cost_components",
        ),
        "policy_required": (
            "labor_burden_method",
            "break_even_method",
            "overhead_allocation",
            "productive_hour_definition",
        ),
        "prohibited_substitutions": (
            "scheduled_for_worked",
            "paid_for_job_work",
            "price_book_hours_for_actual_work",
            "missing_time_as_zero",
        ),
        "model_output": None,
        "recommendation": None,
        "employment_action": None,
        "pricing_action": None,
    }


def _job_scope(
    item: JobLaborEvidence, supplemental: list[SupplementalTimeFact]
) -> ScopeReadiness:
    values = (
        _labor_measure(
            ProductiveHourMeasure.PAID_MINUTES, item.paid_overlap_minutes, item
        ),
        _labor_measure(
            ProductiveHourMeasure.SCHEDULED_MINUTES, item.scheduled_minutes, item
        ),
        _labor_measure(
            ProductiveHourMeasure.ACTUAL_WORKED_MINUTES, item.worked_minutes, item
        ),
        _labor_measure(
            ProductiveHourMeasure.JOBSITE_MINUTES, item.jobsite_minutes, item
        ),
        _labor_measure(
            ProductiveHourMeasure.PRODUCTIVE_JOB_MINUTES, item.productive_minutes, item
        ),
        _supplemental_measure(ProductiveHourMeasure.TRAVEL_MINUTES, supplemental),
        _supplemental_measure(
            ProductiveHourMeasure.NONPRODUCTIVE_OPERATIONAL_MINUTES, supplemental
        ),
        _absent(
            ProductiveHourMeasure.UNCLASSIFIED_PAID_MINUTES,
            "Unclassified paid time remains Employee-level evidence.",
        ),
    )
    return _scope(
        "JOB",
        item.company_id,
        item.branch_id,
        item.employee_id,
        item.job_id,
        item.appointment_id,
        values,
    )


def _employee_scope(
    item: EmployeeLaborEvidence,
    supplemental: list[SupplementalTimeFact],
    jobs: tuple[ScopeReadiness, ...],
) -> ScopeReadiness:
    values = (
        _employee_measure(ProductiveHourMeasure.PAID_MINUTES, item.paid_minutes, item),
        _aggregate_measure(ProductiveHourMeasure.SCHEDULED_MINUTES, jobs),
        _aggregate_measure(ProductiveHourMeasure.ACTUAL_WORKED_MINUTES, jobs),
        _aggregate_measure(ProductiveHourMeasure.JOBSITE_MINUTES, jobs),
        _aggregate_measure(ProductiveHourMeasure.PRODUCTIVE_JOB_MINUTES, jobs),
        _supplemental_measure(ProductiveHourMeasure.TRAVEL_MINUTES, supplemental),
        _supplemental_measure(
            ProductiveHourMeasure.NONPRODUCTIVE_OPERATIONAL_MINUTES, supplemental
        ),
        _employee_measure(
            ProductiveHourMeasure.UNCLASSIFIED_PAID_MINUTES,
            item.unclassified_paid_minutes,
            item,
        ),
    )
    return _scope(
        "EMPLOYEE", item.company_id, None, item.employee_id, None, None, values
    )


def _aggregate_scope(
    scope: str,
    company_id: UUID,
    branch_id: UUID | None,
    children: tuple[ScopeReadiness, ...],
) -> ScopeReadiness:
    measures = tuple(
        _aggregate_measure(measure, children) for measure in ProductiveHourMeasure
    )
    return _scope(scope, company_id, branch_id, None, None, None, measures)


def _company_scope(
    company_id: UUID,
    jobs: tuple[ScopeReadiness, ...],
    employees: tuple[ScopeReadiness, ...],
) -> ScopeReadiness:
    """Keep total paid time Employee-bound instead of assigning it to Jobs."""
    employee_measures = {
        ProductiveHourMeasure.PAID_MINUTES,
        ProductiveHourMeasure.UNCLASSIFIED_PAID_MINUTES,
    }
    measures = tuple(
        _aggregate_measure(measure, employees if measure in employee_measures else jobs)
        for measure in ProductiveHourMeasure
    )
    return _scope("COMPANY", company_id, None, None, None, None, measures)


def _aggregate_measure(
    measure: ProductiveHourMeasure, children: tuple[ScopeReadiness, ...]
) -> MeasureReadiness:
    values = [
        next(x for x in child.measures if x.measure is measure) for child in children
    ]
    if not values:
        return _absent(
            measure, "No authoritative child evidence exists for this scope."
        )
    if any(x.state is ReadinessState.CONFLICTING for x in values):
        return MeasureReadiness(
            measure,
            ReadinessState.CONFLICTING,
            None,
            _provenance(values),
            (),
            tuple(sorted({c for x in values for c in x.conflicts})),
            "Conflicting child evidence prevents aggregation.",
        )
    available = [x for x in values if x.state is ReadinessState.AVAILABLE]
    if len(available) == len(values):
        return MeasureReadiness(
            measure,
            ReadinessState.AVAILABLE,
            sum(x.minutes or 0 for x in available),
            _provenance(available),
            (),
            (),
            "Sum of authoritative child measurements; no policy interpretation.",
        )
    if available:
        return MeasureReadiness(
            measure,
            ReadinessState.PARTIAL,
            None,
            _provenance(available),
            tuple(sorted({m for x in values for m in x.missing_inputs})),
            (),
            "Some child evidence is unavailable; no partial total is presented.",
        )
    return _absent(
        measure, "No available child measurement; missing evidence is not zero."
    )


def _labor_measure(
    measure: ProductiveHourMeasure, minutes: int | None, item: JobLaborEvidence
) -> MeasureReadiness:
    if item.confidence is Confidence.CONFLICTING:
        return MeasureReadiness(
            measure,
            ReadinessState.CONFLICTING,
            None,
            item.provenance,
            item.missing_inputs,
            item.conflicts,
            "Conflicting labor evidence prevents a precise measurement.",
        )
    if minutes is None:
        return MeasureReadiness(
            measure,
            ReadinessState.ABSENT,
            None,
            item.provenance,
            item.missing_inputs,
            (),
            "Required authoritative interval is absent.",
        )
    return MeasureReadiness(
        measure,
        ReadinessState.AVAILABLE,
        minutes,
        item.provenance,
        (),
        (),
        "Measured from accepted Employee/Job interval evidence.",
    )


def _employee_measure(
    measure: ProductiveHourMeasure,
    minutes: int | None,
    item: EmployeeLaborEvidence,
    *,
    empty_is_absent: bool = False,
) -> MeasureReadiness:
    if item.confidence is Confidence.CONFLICTING:
        return MeasureReadiness(
            measure,
            ReadinessState.CONFLICTING,
            None,
            item.paid_provenance,
            item.missing_inputs,
            item.conflicts,
            "Conflicting Employee evidence prevents a precise measurement.",
        )
    if minutes is None or empty_is_absent:
        return _absent(measure, "Required authoritative Employee evidence is absent.")
    return MeasureReadiness(
        measure,
        ReadinessState.AVAILABLE,
        minutes,
        item.paid_provenance,
        (),
        (),
        "Employee-specific measured evidence; no ranking or employment conclusion.",
    )


def _supplemental_measure(
    measure: ProductiveHourMeasure, facts: list[SupplementalTimeFact]
) -> MeasureReadiness:
    selected = [x for x in facts if x.measure is measure]
    if not selected:
        return _absent(measure, "No accepted operational evidence supplied.")
    if any(x.state is ReadinessState.CONFLICTING for x in selected):
        return MeasureReadiness(
            measure,
            ReadinessState.CONFLICTING,
            None,
            tuple(p for x in selected for p in x.provenance),
            tuple(m for x in selected for m in x.missing_inputs),
            tuple(c for x in selected for c in x.conflicts),
            "Conflicting operational evidence prevents measurement.",
        )
    available = [x for x in selected if x.state is ReadinessState.AVAILABLE]
    if len(available) != len(selected):
        return MeasureReadiness(
            measure,
            ReadinessState.PARTIAL,
            None,
            tuple(p for x in available for p in x.provenance),
            tuple(m for x in selected for m in x.missing_inputs),
            (),
            "Operational evidence is incomplete; no partial total is presented.",
        )
    return MeasureReadiness(
        measure,
        ReadinessState.AVAILABLE,
        sum(x.minutes or 0 for x in available),
        tuple(p for x in available for p in x.provenance),
        (),
        (),
        "Accepted operational time evidence.",
    )


def _absent(measure: ProductiveHourMeasure, limitation: str) -> MeasureReadiness:
    return MeasureReadiness(
        measure,
        ReadinessState.ABSENT,
        None,
        (),
        (measure.value.lower(),),
        (),
        limitation,
    )


def _scope(
    scope: str,
    company_id: UUID,
    branch_id: UUID | None,
    employee_id: UUID | None,
    job_id: UUID | None,
    appointment_id: UUID | None,
    measures: tuple[MeasureReadiness, ...],
) -> ScopeReadiness:
    confidence = (
        Confidence.CONFLICTING
        if any(x.state is ReadinessState.CONFLICTING for x in measures)
        else (
            Confidence.AUTHORITATIVE
            if all(x.state is ReadinessState.AVAILABLE for x in measures)
            else Confidence.PARTIAL
        )
    )
    body = {
        "scope": scope,
        "company_id": str(company_id),
        "branch_id": str(branch_id) if branch_id else None,
        "employee_id": str(employee_id) if employee_id else None,
        "job_id": str(job_id) if job_id else None,
        "appointment_id": str(appointment_id) if appointment_id else None,
        "measures": [asdict(x) for x in measures],
        "confidence": confidence,
    }
    return ScopeReadiness(
        scope,
        company_id,
        branch_id,
        employee_id,
        job_id,
        appointment_id,
        measures,
        confidence,
        _digest(body),
    )


def _provenance(values: list[MeasureReadiness]) -> tuple[ProvenanceRef, ...]:
    return tuple(
        sorted(
            {p for value in values for p in value.provenance},
            key=lambda x: (x.authority, x.record_id, x.digest),
        )
    )


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
