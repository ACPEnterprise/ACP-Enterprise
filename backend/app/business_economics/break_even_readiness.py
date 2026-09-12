"""Policy-neutral break-even input readiness; no model is selected or run."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Final
from uuid import UUID

from app.operational_measurement.productive_hour_readiness import (
    ProductiveHourMeasure,
    ProductiveHourReadinessPacket,
    ScopeReadiness,
)

from .findings import FindingState
from .measurement_contract import MeasurementComponent, MeasurementEvidenceInput

BREAK_EVEN_READINESS_VERSION: Final = "eco.break-even-input-readiness.v2"
MAX_EVIDENCE_INPUTS: Final = 100_000


class BreakEvenReadinessState(StrEnum):
    AVAILABLE = "AVAILABLE"
    PARTIAL = "PARTIAL"
    ABSENT = "ABSENT"
    CONFLICTING = "CONFLICTING"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class BreakEvenInputKind(StrEnum):
    EARNED_REVENUE = "earned_revenue"
    SETTLEMENT_AVAILABILITY = "settlement_availability"
    DIRECT_LABOR_HOURS = "direct_labor_hours"
    COMPENSATION_LABOR_COST_AUTHORITY = "compensation_labor_cost_authority"
    LABOR_BURDEN_PREREQUISITES = "labor_burden_prerequisites"
    DIRECT_MATERIALS = "direct_materials"
    MATERIAL_COSTING_PREREQUISITES = "material_costing_prerequisites"
    OTHER_ATTRIBUTABLE_DIRECT_COSTS = "other_attributable_direct_costs"
    OVERHEAD_ALLOCATION_PREREQUISITES = "overhead_allocation_prerequisites"
    PRODUCTIVE_HOURS = "productive_hours"
    COMPANY_BRANCH_SCOPE = "company_branch_scope"
    ACCOUNTING_SOURCE_RECONCILIATION = "accounting_source_reconciliation"
    # Compatibility facts retained from v1.
    PAID_MINUTES = "paid_minutes"
    PRODUCTIVE_JOB_MINUTES = "productive_job_minutes"
    ACTUAL_WORKED_MINUTES = "actual_worked_minutes"
    ACTUAL_LABOR_COST = "actual_labor_cost"
    ACTUAL_DIRECT_MATERIAL_COST = "actual_direct_material_cost"
    ACTUAL_OTHER_DIRECT_COST = "actual_other_direct_cost"
    OVERHEAD_SOURCE_POOL = "overhead_source_pool"
    EARNED_REVENUE_COMPARISON = "earned_revenue_comparison"


@dataclass(frozen=True, slots=True)
class BreakEvenInputFact:
    kind: BreakEvenInputKind
    state: str
    value: Decimal | None
    currency: str | None
    unit: str | None
    evidence_ids: tuple[str, ...]
    evidence_digests: tuple[str, ...]
    source_authorities: tuple[str, ...]
    source_dates: tuple[str, ...]
    confidence: str
    limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BreakEvenInputReadinessPacket:
    contract_version: str
    company_id: UUID
    branch_id: UUID | None
    period_start: date | None
    period_end: date | None
    productive_hour_evidence_digest: str
    facts: tuple[BreakEvenInputFact, ...]
    missing_inputs: tuple[str, ...]
    conflicting_inputs: tuple[str, ...]
    policy_gates: tuple[str, ...]
    model_output: None
    recommendation: None
    packet_digest: str


_COMPONENT_KIND = {
    MeasurementComponent.DIRECT_LABOR: BreakEvenInputKind.ACTUAL_LABOR_COST,
    MeasurementComponent.DIRECT_MATERIAL: BreakEvenInputKind.ACTUAL_DIRECT_MATERIAL_COST,
    MeasurementComponent.OTHER_DIRECT_COST: BreakEvenInputKind.ACTUAL_OTHER_DIRECT_COST,
    MeasurementComponent.OVERHEAD_ALLOCATION: BreakEvenInputKind.OVERHEAD_SOURCE_POOL,
    MeasurementComponent.REVENUE_EARNED_VALUE: BreakEvenInputKind.EARNED_REVENUE_COMPARISON,
}

_REQUIRED_COMPONENTS = {
    BreakEvenInputKind.EARNED_REVENUE: MeasurementComponent.REVENUE_EARNED_VALUE,
    BreakEvenInputKind.SETTLEMENT_AVAILABILITY: MeasurementComponent.SETTLEMENT,
    BreakEvenInputKind.COMPENSATION_LABOR_COST_AUTHORITY: MeasurementComponent.DIRECT_LABOR,
    BreakEvenInputKind.LABOR_BURDEN_PREREQUISITES: MeasurementComponent.LABOR_BURDEN,
    BreakEvenInputKind.DIRECT_MATERIALS: MeasurementComponent.DIRECT_MATERIAL,
    BreakEvenInputKind.MATERIAL_COSTING_PREREQUISITES: MeasurementComponent.MATERIAL_COSTING,
    BreakEvenInputKind.OTHER_ATTRIBUTABLE_DIRECT_COSTS: MeasurementComponent.OTHER_DIRECT_COST,
    BreakEvenInputKind.OVERHEAD_ALLOCATION_PREREQUISITES: MeasurementComponent.OVERHEAD_ALLOCATION,
    BreakEvenInputKind.ACCOUNTING_SOURCE_RECONCILIATION: MeasurementComponent.ACCOUNTING_RECONCILIATION,
}

_POLICY_GATES = (
    "break_even_method",
    "productive_hour_definition",
    "labor_burden_method",
    "overhead_allocation_method",
    "target_margin",
    "price_book_markup",
    "staffing_policy",
)


def break_even_input_contract() -> dict[str, object]:
    return {
        "contract_version": BREAK_EVEN_READINESS_VERSION,
        "required_inputs": tuple(item.value for item in _REQUIRED_COMPONENTS)
        + ("direct_labor_hours", "productive_hours", "company_branch_scope"),
        "fact_inputs": tuple(item.value for item in BreakEvenInputKind),
        "readiness_states": tuple(item.value for item in BreakEvenReadinessState),
        "policy_gates": _POLICY_GATES,
        "aggregation": "explicit_same_scope_same_period_same_currency_accepted_evidence_only",
        "canonical_break_even_rate": None,
        "model_output": None,
        "recommendation": None,
        "mutation_authority": "none",
    }


def build_break_even_input_readiness(
    productive_hours: ProductiveHourReadinessPacket,
    *,
    economic_evidence: tuple[MeasurementEvidenceInput, ...] = (),
    branch_id: UUID | None = None,
    period_start: date | None = None,
    period_end: date | None = None,
) -> BreakEvenInputReadinessPacket:
    """Seal factual inputs while leaving every consequential method unresolved."""
    if len(economic_evidence) > MAX_EVIDENCE_INPUTS:
        raise ValueError("break-even evidence input exceeds bounded size")
    if (period_start is None) != (period_end is None):
        raise ValueError("break-even period requires both boundaries")
    if period_start and period_end and period_start > period_end:
        raise ValueError("break-even period is inverted")
    company_id = productive_hours.company_id
    if any(item.company_id != company_id for item in economic_evidence):
        raise ValueError("foreign Company break-even evidence")
    if branch_id is None and any(
        item.branch_id is not None for item in economic_evidence
    ):
        raise ValueError("Company packet cannot silently aggregate Branch evidence")
    if branch_id is not None and any(
        item.branch_id != branch_id for item in economic_evidence
    ):
        raise ValueError("foreign Branch break-even evidence")
    if len({item.input_id for item in economic_evidence}) != len(economic_evidence):
        raise ValueError("duplicate break-even evidence identity")
    if any(item.subject_id != str(company_id) for item in economic_evidence):
        raise ValueError("break-even evidence subject is outside Company scope")
    if len({item.reconciliation_key for item in economic_evidence}) > 1:
        raise ValueError(
            "mixed reconciliation periods; evidence periods cannot be silently combined"
        )
    semantic_values = tuple(
        (item.component, item.value_digest) for item in economic_evidence
    )
    if len(set(semantic_values)) != len(semantic_values):
        raise ValueError(
            "duplicate break-even economic fact; duplicate value evidence"
        )

    scope = (
        next(
            (item for item in productive_hours.branches if item.branch_id == branch_id),
            None,
        )
        if branch_id
        else productive_hours.company
    )
    if scope is None:
        raise ValueError("Branch lacks productive-hour scope")
    paid = _time_fact(
        scope, ProductiveHourMeasure.PAID_MINUTES, BreakEvenInputKind.PAID_MINUTES
    )
    productive = _time_fact(
        scope,
        ProductiveHourMeasure.PRODUCTIVE_JOB_MINUTES,
        BreakEvenInputKind.PRODUCTIVE_JOB_MINUTES,
    )
    worked = _time_fact(
        scope,
        ProductiveHourMeasure.ACTUAL_WORKED_MINUTES,
        BreakEvenInputKind.ACTUAL_WORKED_MINUTES,
    )
    facts = [paid, productive, worked]
    facts.extend(
        (
            _alias_fact(worked, BreakEvenInputKind.DIRECT_LABOR_HOURS),
            _alias_fact(productive, BreakEvenInputKind.PRODUCTIVE_HOURS),
            _scope_fact(company_id, branch_id, productive_hours.evidence_digest),
        )
    )
    for kind, component in _REQUIRED_COMPONENTS.items():
        facts.append(_economic_fact(kind, component, economic_evidence))
    for component, kind in _COMPONENT_KIND.items():
        facts.append(_economic_fact(kind, component, economic_evidence))
    ordered = tuple(sorted(facts, key=lambda item: item.kind.value))
    missing = tuple(
        item.kind.value for item in ordered if item.state in {"ABSENT", "PARTIAL"}
    )
    conflicting = tuple(
        item.kind.value for item in ordered if item.state == "CONFLICTING"
    )
    canonical = {
        "contract_version": BREAK_EVEN_READINESS_VERSION,
        "company_id": str(company_id),
        "branch_id": str(branch_id) if branch_id else None,
        "period_start": period_start,
        "period_end": period_end,
        "productive_hour_evidence_digest": productive_hours.evidence_digest,
        "facts": [asdict(item) for item in ordered],
        "missing_inputs": missing,
        "conflicting_inputs": conflicting,
        "policy_gates": _POLICY_GATES,
        "model_output": None,
        "recommendation": None,
    }
    digest = _digest(canonical)
    return BreakEvenInputReadinessPacket(
        BREAK_EVEN_READINESS_VERSION,
        company_id,
        branch_id,
        period_start,
        period_end,
        productive_hours.evidence_digest,
        ordered,
        missing,
        conflicting,
        _POLICY_GATES,
        None,
        None,
        digest,
    )


def _time_fact(
    scope: ScopeReadiness, measure: ProductiveHourMeasure, kind: BreakEvenInputKind
) -> BreakEvenInputFact:
    source = next(item for item in scope.measures if item.measure is measure)
    authorities = tuple(sorted({item.authority for item in source.provenance}))
    return BreakEvenInputFact(
        kind,
        source.state.value,
        Decimal(source.minutes) if source.minutes is not None else None,
        None,
        "minute" if source.minutes is not None else None,
        tuple(
            sorted(
                f"{item.authority}:{item.record_id}:{item.version}"
                for item in source.provenance
            )
        ),
        tuple(sorted({item.digest for item in source.provenance})),
        authorities,
        (),
        scope.confidence.value,
        tuple(sorted({source.limitation, *source.missing_inputs, *source.conflicts})),
    )


def _alias_fact(
    source: BreakEvenInputFact, kind: BreakEvenInputKind
) -> BreakEvenInputFact:
    return BreakEvenInputFact(
        kind,
        source.state,
        source.value,
        source.currency,
        source.unit,
        source.evidence_ids,
        source.evidence_digests,
        source.source_authorities,
        source.source_dates,
        source.confidence,
        source.limitations,
    )


def _scope_fact(
    company_id: UUID, branch_id: UUID | None, digest: str
) -> BreakEvenInputFact:
    identity = f"company:{company_id}" + (f":branch:{branch_id}" if branch_id else "")
    return BreakEvenInputFact(
        BreakEvenInputKind.COMPANY_BRANCH_SCOPE,
        "AVAILABLE",
        None,
        None,
        None,
        (identity,),
        (digest,),
        ("acp_identity_authority",),
        (),
        "authoritative",
        ("Scope identity only; it contains no allocation policy.",),
    )


def _economic_fact(
    kind: BreakEvenInputKind,
    component: MeasurementComponent,
    evidence: tuple[MeasurementEvidenceInput, ...],
) -> BreakEvenInputFact:
    candidates = tuple(
        sorted(
            (x for x in evidence if x.component is component), key=lambda x: x.input_id
        )
    )
    conflicts = tuple(
        x for x in candidates if x.evidence_state is FindingState.CONFLICTING
    )
    accepted = tuple(
        x
        for x in candidates
        if x.accepted_for_measurement and x.source_value is not None
    )
    ready_without_value = tuple(x for x in candidates if x.accepted_for_measurement)
    if conflicts:
        state, value, currency, unit = "CONFLICTING", None, None, None
    elif not candidates:
        state, value, currency, unit = "ABSENT", None, None, None
    elif not ready_without_value:
        state, value, currency, unit = "PARTIAL", None, None, None
    elif component in {
        MeasurementComponent.LABOR_BURDEN,
        MeasurementComponent.MATERIAL_COSTING,
        MeasurementComponent.OVERHEAD_ALLOCATION,
        MeasurementComponent.ACCOUNTING_RECONCILIATION,
    }:
        state, value, currency, unit = "AVAILABLE", None, None, None
    elif len(accepted) != len(ready_without_value):
        state, value, currency, unit = "PARTIAL", None, None, None
    else:
        currencies, units = {x.currency for x in accepted}, {x.unit for x in accepted}
        if len(currencies) > 1 or len(units) > 1:
            state, value, currency, unit = "CONFLICTING", None, None, None
        else:
            state = "AVAILABLE"
            value = sum(
                (x.source_value for x in accepted if x.source_value is not None),
                Decimal(0),
            )
            currency, unit = next(iter(currencies)), next(iter(units))
    dates = tuple(sorted({_source_date(x) for x in candidates if _source_date(x)}))
    confidence = (
        "unknown"
        if not candidates
        else (
            "conflicting"
            if state == "CONFLICTING"
            else "available"
            if state == "AVAILABLE"
            and all(x.confidence.value == "available" for x in candidates)
            else "partial"
        )
    )
    limitations = {limit for item in candidates for limit in item.limitations}
    if state != "AVAILABLE":
        limitations.add("accepted_authoritative_evidence_required; missing is not zero")
    return BreakEvenInputFact(
        kind,
        state,
        value,
        currency,
        unit,
        tuple(x.input_id for x in candidates),
        tuple(sorted({x.evidence_digest for x in candidates})),
        tuple(sorted({x.source_authority for x in candidates})),
        dates,
        confidence,
        tuple(sorted(limitations)),
    )


def _source_date(item: MeasurementEvidenceInput) -> str:
    value: datetime | date | None = item.as_of or item.effective_date
    return value.isoformat() if value else ""


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
