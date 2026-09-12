"""Policy-neutral break-even inputs; this module never selects or runs a model."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Final
from uuid import UUID

from app.operational_measurement.productive_hour_readiness import (
    ProductiveHourMeasure,
    ProductiveHourReadinessPacket,
)

from .measurement_contract import MeasurementComponent, MeasurementEvidenceInput

BREAK_EVEN_READINESS_VERSION: Final = "eco.break-even-input-readiness.v1"


class BreakEvenInputKind(StrEnum):
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
    limitations: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BreakEvenInputReadinessPacket:
    contract_version: str
    company_id: UUID
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

_POLICY_GATES = (
    "break_even_method",
    "productive_hour_definition",
    "labor_burden_method",
    "overhead_allocation_method",
)


def break_even_input_contract() -> dict[str, object]:
    return {
        "contract_version": BREAK_EVEN_READINESS_VERSION,
        "fact_inputs": tuple(item.value for item in BreakEvenInputKind),
        "policy_gates": _POLICY_GATES,
        "aggregation": "explicit_same_scope_same_currency_accepted_evidence_only",
        "canonical_break_even_rate": None,
        "model_output": None,
        "recommendation": None,
        "mutation_authority": "none",
    }


def build_break_even_input_readiness(
    productive_hours: ProductiveHourReadinessPacket,
    *,
    economic_evidence: tuple[MeasurementEvidenceInput, ...] = (),
) -> BreakEvenInputReadinessPacket:
    """Seal factual inputs while leaving every consequential method unresolved."""
    company_id = productive_hours.company_id
    if any(item.company_id != company_id for item in economic_evidence):
        raise ValueError("foreign Company break-even evidence")
    if any(item.branch_id is not None for item in economic_evidence):
        raise ValueError("Company packet cannot silently aggregate Branch evidence")
    if len({item.input_id for item in economic_evidence}) != len(economic_evidence):
        raise ValueError("duplicate break-even evidence identity")
    if any(item.subject_id != str(company_id) for item in economic_evidence):
        raise ValueError("break-even evidence subject is outside Company scope")
    if len({item.reconciliation_key for item in economic_evidence}) > 1:
        raise ValueError("break-even evidence periods cannot be silently combined")
    semantic_values = tuple(
        (item.component, item.value_digest) for item in economic_evidence
    )
    if len(set(semantic_values)) != len(semantic_values):
        raise ValueError("duplicate break-even economic value evidence")

    facts = [
        _time_fact(productive_hours, ProductiveHourMeasure.PAID_MINUTES),
        _time_fact(productive_hours, ProductiveHourMeasure.PRODUCTIVE_JOB_MINUTES),
        _time_fact(productive_hours, ProductiveHourMeasure.ACTUAL_WORKED_MINUTES),
    ]
    for component, kind in _COMPONENT_KIND.items():
        facts.append(_economic_fact(kind, component, economic_evidence))
    ordered = tuple(sorted(facts, key=lambda item: item.kind.value))
    missing = tuple(
        item.kind.value for item in ordered if item.state in {"ABSENT", "UNKNOWN"}
    )
    conflicting = tuple(
        item.kind.value for item in ordered if item.state == "CONFLICTING"
    )
    canonical = {
        "contract_version": BREAK_EVEN_READINESS_VERSION,
        "company_id": str(company_id),
        "productive_hour_evidence_digest": productive_hours.evidence_digest,
        "facts": [asdict(item) for item in ordered],
        "missing_inputs": missing,
        "conflicting_inputs": conflicting,
        "policy_gates": _POLICY_GATES,
        "model_output": None,
        "recommendation": None,
    }
    digest = hashlib.sha256(
        json.dumps(
            canonical, sort_keys=True, separators=(",", ":"), default=str
        ).encode()
    ).hexdigest()
    return BreakEvenInputReadinessPacket(
        contract_version=BREAK_EVEN_READINESS_VERSION,
        company_id=company_id,
        productive_hour_evidence_digest=productive_hours.evidence_digest,
        facts=ordered,
        missing_inputs=missing,
        conflicting_inputs=conflicting,
        policy_gates=_POLICY_GATES,
        model_output=None,
        recommendation=None,
        packet_digest=digest,
    )


def _time_fact(
    packet: ProductiveHourReadinessPacket, measure: ProductiveHourMeasure
) -> BreakEvenInputFact:
    source = next(item for item in packet.company.measures if item.measure is measure)
    kind = BreakEvenInputKind(measure.value.lower())
    return BreakEvenInputFact(
        kind=kind,
        state=source.state.value,
        value=Decimal(source.minutes) if source.minutes is not None else None,
        currency=None,
        unit="minute" if source.minutes is not None else None,
        evidence_ids=tuple(
            sorted(
                f"{item.authority}:{item.record_id}:{item.version}"
                for item in source.provenance
            )
        ),
        evidence_digests=tuple(sorted({item.digest for item in source.provenance})),
        limitations=(source.limitation,),
    )


def _economic_fact(
    kind: BreakEvenInputKind,
    component: MeasurementComponent,
    evidence: tuple[MeasurementEvidenceInput, ...],
) -> BreakEvenInputFact:
    candidates = tuple(
        sorted(
            (item for item in evidence if item.component is component),
            key=lambda item: item.input_id,
        )
    )
    conflicts = tuple(
        item for item in candidates if item.evidence_state.value == "conflicting"
    )
    accepted = tuple(
        item
        for item in candidates
        if item.accepted_for_measurement and item.source_value is not None
    )
    if conflicts:
        state, value, currency, unit = "CONFLICTING", None, None, None
    elif not accepted:
        state, value, currency, unit = "UNKNOWN", None, None, None
    else:
        currencies = {item.currency for item in accepted}
        units = {item.unit for item in accepted}
        if len(currencies) > 1 or len(units) > 1:
            state, value, currency, unit = "CONFLICTING", None, None, None
        else:
            state = "AVAILABLE"
            value = sum(
                (
                    item.source_value
                    for item in accepted
                    if item.source_value is not None
                ),
                Decimal(0),
            )
            currency = next(iter(currencies))
            unit = next(iter(units))
    return BreakEvenInputFact(
        kind=kind,
        state=state,
        value=value,
        currency=currency,
        unit=unit,
        evidence_ids=tuple(item.input_id for item in candidates),
        evidence_digests=tuple(sorted({item.evidence_digest for item in candidates})),
        limitations=tuple(
            sorted(
                {limitation for item in candidates for limitation in item.limitations}
                | ({"accepted_cost_evidence_required"} if not accepted else set())
            )
        ),
    )
