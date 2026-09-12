"""Deterministic launch-readiness validation over existing Economics evidence.

This contract does not promote source records, select policy, or calculate profit.
It explains whether already-admitted evidence is fit for downstream consumption.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Final

from app.operational_measurement.labor_evidence import (
    Confidence,
    JobLaborEvidence,
    LaborEvidencePacket,
)

from .findings import FindingState
from .measurement_contract import MeasurementComponent, MeasurementEvidenceInput

CONTRACT_VERSION: Final = "eco.launch-evidence-readiness.v1"
MAX_EVIDENCE_INPUTS: Final = 100_000


class LaunchReadinessState(StrEnum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    ABSENT = "ABSENT"
    CONFLICTING = "CONFLICTING"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class SourcePopulationState(StrEnum):
    CONTRACT_VALIDATED = "CONTRACT_VALIDATED"
    SOURCE_PARTIAL = "SOURCE_PARTIAL"
    SOURCE_CURRENT = "SOURCE_CURRENT"
    SOURCE_MISSING = "SOURCE_MISSING"


class LaunchDomain(StrEnum):
    REVENUE = "Revenue"
    SETTLEMENT = "Settlement"
    DIRECT_LABOR = "Direct Labor"
    PAYROLL = "Payroll"
    DIRECT_MATERIAL = "Direct Material"
    OTHER_DIRECT_COST = "Other Direct Cost"
    OVERHEAD = "Overhead"
    JOB_IDENTITY = "Job Identity/Lifecycle"
    SERVICE_LINE = "Service Line / Category"
    ACCOUNTING = "Accounting"


class LaborEvidenceClass(StrEnum):
    JOB_ATTRIBUTABLE = "JOB_ATTRIBUTABLE"
    PAID_UNALLOCATED = "PAID_UNALLOCATED"
    SCHEDULED_ONLY = "SCHEDULED_ONLY"
    MISSING = "MISSING"
    CONFLICTING = "CONFLICTING"


class PrerequisiteState(StrEnum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    ABSENT = "ABSENT"
    CONFLICTING = "CONFLICTING"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True, slots=True)
class PayrollPrerequisite:
    name: str
    state: PrerequisiteState
    authority: str | None
    evidence_identity: str | None
    blocker: str | None = None

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Payroll prerequisite name is required")
        if self.state is PrerequisiteState.AVAILABLE and (
            not self.authority or not self.evidence_identity
        ):
            raise ValueError(
                "available Payroll prerequisite requires authority and identity"
            )


@dataclass(frozen=True, slots=True)
class LaborAttributionReadiness:
    employee_id: str
    job_id: str | None
    appointment_id: str | None
    classification: LaborEvidenceClass
    worked_minutes: int | None
    paid_overlap_minutes: int | None
    blockers: tuple[str, ...]
    evidence_digest: str


@dataclass(frozen=True, slots=True)
class DomainReadiness:
    domain: LaunchDomain
    state: LaunchReadinessState
    evidence_ids: tuple[str, ...]
    source_authorities: tuple[str, ...]
    smallest_blocker: str | None


@dataclass(frozen=True, slots=True)
class LaunchEvidenceReadinessPacket:
    contract_version: str
    source_population_state: SourcePopulationState
    domains: tuple[DomainReadiness, ...]
    labor_attribution: tuple[LaborAttributionReadiness, ...]
    payroll_prerequisites: tuple[PayrollPrerequisite, ...]
    policy_gates: tuple[str, ...]
    limitations: tuple[str, ...]
    packet_digest: str


_DOMAIN_COMPONENT = {
    LaunchDomain.REVENUE: MeasurementComponent.REVENUE_EARNED_VALUE,
    LaunchDomain.SETTLEMENT: MeasurementComponent.SETTLEMENT,
    LaunchDomain.DIRECT_LABOR: MeasurementComponent.DIRECT_LABOR,
    LaunchDomain.DIRECT_MATERIAL: MeasurementComponent.DIRECT_MATERIAL,
    LaunchDomain.OTHER_DIRECT_COST: MeasurementComponent.OTHER_DIRECT_COST,
    LaunchDomain.OVERHEAD: MeasurementComponent.OVERHEAD_ALLOCATION,
    LaunchDomain.JOB_IDENTITY: MeasurementComponent.JOB_CONTEXT,
    LaunchDomain.SERVICE_LINE: MeasurementComponent.SERVICE_LINE_ATTRIBUTION,
    LaunchDomain.ACCOUNTING: MeasurementComponent.ACCOUNTING_RECONCILIATION,
}

_VALUE_REQUIRED = {
    MeasurementComponent.REVENUE_EARNED_VALUE,
    MeasurementComponent.SETTLEMENT,
    MeasurementComponent.DIRECT_LABOR,
    MeasurementComponent.DIRECT_MATERIAL,
    MeasurementComponent.OTHER_DIRECT_COST,
}

REQUIRED_PAYROLL_PREREQUISITES: Final = (
    "compensation_effective_date",
    "employee_rate",
    "accepted_paid_time",
    "overtime_applicability",
    "payroll_period_identity",
    "revision_correction_state",
    "jurisdiction_and_tax_tables",
    "deduction_elections_where_relevant",
)

POLICY_GATES: Final = (
    "labor_burden_policy",
    "break_even_method",
    "overhead_allocation_method",
    "revenue_recognition_policy",
)

LIMITATIONS: Final = (
    "Scheduled duration never substitutes for worked duration.",
    "Generic paid time never acquires Job identity.",
    "Missing monetary or time evidence never becomes zero.",
    "Source-reported QBO evidence is not accepted economic truth.",
)


def build_launch_evidence_readiness(
    *,
    labor: LaborEvidencePacket,
    evidence: tuple[MeasurementEvidenceInput, ...],
    payroll_prerequisites: tuple[PayrollPrerequisite, ...],
    source_population_state: SourcePopulationState,
) -> LaunchEvidenceReadinessPacket:
    if len(evidence) > MAX_EVIDENCE_INPUTS:
        raise ValueError("launch evidence input exceeds bounded size")
    if any(item.company_id != labor.company_id for item in evidence):
        raise ValueError("foreign Company launch evidence")
    if len({item.input_id for item in evidence}) != len(evidence):
        raise ValueError("duplicate launch evidence identity")
    names = {item.name for item in payroll_prerequisites}
    if len(names) != len(payroll_prerequisites):
        raise ValueError("duplicate Payroll prerequisite")

    domains = tuple(
        _payroll_domain(payroll_prerequisites)
        if domain is LaunchDomain.PAYROLL
        else _measurement_domain(domain, evidence)
        for domain in LaunchDomain
    )
    labor_attribution = tuple(_classify_job(item) for item in labor.jobs)
    employee_job_ids = {item.employee_id for item in labor.jobs}
    labor_attribution += tuple(
        LaborAttributionReadiness(
            employee_id=str(item.employee_id),
            job_id=None,
            appointment_id=None,
            classification=(
                LaborEvidenceClass.CONFLICTING
                if item.confidence is Confidence.CONFLICTING
                else LaborEvidenceClass.PAID_UNALLOCATED
            ),
            worked_minutes=None,
            paid_overlap_minutes=None,
            blockers=item.conflicts,
            evidence_digest=item.evidence_digest,
        )
        for item in labor.employees
        if item.employee_id not in employee_job_ids and item.paid_minutes is not None
    )
    canonical = {
        "contract_version": CONTRACT_VERSION,
        "source_population_state": source_population_state,
        "labor_digest": labor.evidence_digest,
        "domains": [asdict(item) for item in domains],
        "labor_attribution": [asdict(item) for item in labor_attribution],
        "payroll_prerequisites": [asdict(item) for item in payroll_prerequisites],
        "policy_gates": POLICY_GATES,
        "limitations": LIMITATIONS,
    }
    digest = hashlib.sha256(
        json.dumps(
            canonical, sort_keys=True, separators=(",", ":"), default=str
        ).encode()
    ).hexdigest()
    return LaunchEvidenceReadinessPacket(
        CONTRACT_VERSION,
        source_population_state,
        domains,
        labor_attribution,
        payroll_prerequisites,
        POLICY_GATES,
        LIMITATIONS,
        digest,
    )


def _classify_job(item: JobLaborEvidence) -> LaborAttributionReadiness:
    if item.confidence is Confidence.CONFLICTING:
        classification = LaborEvidenceClass.CONFLICTING
    elif item.worked_minutes is not None:
        classification = LaborEvidenceClass.JOB_ATTRIBUTABLE
    elif item.scheduled_minutes is not None:
        classification = LaborEvidenceClass.SCHEDULED_ONLY
    else:
        classification = LaborEvidenceClass.MISSING
    return LaborAttributionReadiness(
        str(item.employee_id),
        str(item.job_id),
        str(item.appointment_id),
        classification,
        item.worked_minutes,
        item.paid_overlap_minutes,
        tuple(sorted((*item.missing_inputs, *item.conflicts))),
        item.evidence_digest,
    )


def _measurement_domain(
    domain: LaunchDomain, evidence: tuple[MeasurementEvidenceInput, ...]
) -> DomainReadiness:
    component = _DOMAIN_COMPONENT[domain]
    selected = tuple(item for item in evidence if item.component is component)
    ids = tuple(sorted(item.input_id for item in selected))
    authorities = tuple(sorted({item.source_authority for item in selected}))
    if not selected:
        blocker = (
            "approved_overhead_allocation_authority_absent"
            if domain is LaunchDomain.OVERHEAD
            else "required_evidence_absent_not_zero"
        )
        return DomainReadiness(domain, LaunchReadinessState.ABSENT, (), (), blocker)
    values_by_event: dict[str, set[str]] = {}
    for item in selected:
        values_by_event.setdefault(item.reconciliation_key, set()).add(
            item.value_digest
        )
    if any(len(values) > 1 for values in values_by_event.values()) or any(
        item.evidence_state is FindingState.CONFLICTING for item in selected
    ):
        return DomainReadiness(
            domain,
            LaunchReadinessState.CONFLICTING,
            ids,
            authorities,
            "same_reconciliation_component_has_conflicting_values",
        )
    if any(
        not item.accepted_for_measurement
        or item.evidence_state is not FindingState.READY
        or (component in _VALUE_REQUIRED and item.source_value is None)
        for item in selected
    ):
        return DomainReadiness(
            domain,
            LaunchReadinessState.PARTIAL,
            ids,
            authorities,
            "accepted_complete_measured_value_missing",
        )
    return DomainReadiness(
        domain, LaunchReadinessState.AVAILABLE, ids, authorities, None
    )


def _payroll_domain(
    prerequisites: tuple[PayrollPrerequisite, ...],
) -> DomainReadiness:
    by_name = {item.name: item for item in prerequisites}
    missing = tuple(
        name for name in REQUIRED_PAYROLL_PREREQUISITES if name not in by_name
    )
    if missing:
        return DomainReadiness(
            LaunchDomain.PAYROLL,
            LaunchReadinessState.ABSENT,
            (),
            (),
            f"payroll_prerequisite_missing:{missing[0]}",
        )
    ordered = tuple(by_name[name] for name in REQUIRED_PAYROLL_PREREQUISITES)
    conflict = next(
        (item for item in ordered if item.state is PrerequisiteState.CONFLICTING), None
    )
    if conflict:
        state, blocker = (
            LaunchReadinessState.CONFLICTING,
            conflict.blocker or conflict.name,
        )
    else:
        incomplete = next(
            (item for item in ordered if item.state is not PrerequisiteState.AVAILABLE),
            None,
        )
        if incomplete:
            state, blocker = (
                LaunchReadinessState.PARTIAL,
                incomplete.blocker or incomplete.name,
            )
        else:
            state, blocker = LaunchReadinessState.AVAILABLE, None
    return DomainReadiness(
        LaunchDomain.PAYROLL,
        state,
        tuple(
            sorted(item.evidence_identity for item in ordered if item.evidence_identity)
        ),
        tuple(sorted({item.authority for item in ordered if item.authority})),
        blocker,
    )
