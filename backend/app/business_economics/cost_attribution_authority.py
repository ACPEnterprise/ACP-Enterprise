"""Governed owner/accountant decision contracts for cost attribution.

This module describes choices and certification boundaries. It neither selects a
choice nor performs an allocation. Certified, effective policy versions remain
the sole authority consumed by Economics.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from types import MappingProxyType
from typing import Final
from uuid import UUID

from .policy_authority import (
    POLICY_FAMILY_REGISTRY,
    CompanyPolicyVersion,
    PolicyLifecycle,
    PolicyResolutionState,
    resolve_policy_authority,
)

CONTRACT_VERSION: Final = "economics.cost-attribution-authority.v1"


class CertificationAuthority(StrEnum):
    OWNER = "owner"
    ACCOUNTANT = "accountant"
    OWNER_AND_ACCOUNTANT = "owner_and_accountant"


class CertificationState(StrEnum):
    UNSELECTED = "unselected"
    DRAFT = "draft"
    READY_FOR_CERTIFICATION = "ready_for_certification"
    CERTIFIED = "certified"
    SUPERSEDED = "superseded"
    INACTIVE = "inactive"
    CONFLICTING = "conflicting"


@dataclass(frozen=True)
class AttributionDecisionDefinition:
    family_key: str
    authority_required: CertificationAuthority
    implication: str
    evidence_required: tuple[str, ...]
    historical_replay_supported: bool
    limitations: tuple[str, ...]


_DECISIONS = (
    AttributionDecisionDefinition(
        "overtime_premium_allocation",
        CertificationAuthority.OWNER_AND_ACCOUNTANT,
        "Determines whether and how overtime premium becomes Job-attributable labor.",
        ("accepted_overtime_period", "accepted_employee_job_intervals"),
        True,
        ("No Job receives premium without certified allocation authority.",),
    ),
    AttributionDecisionDefinition(
        "salary_job_allocation",
        CertificationAuthority.OWNER_AND_ACCOUNTANT,
        "Determines whether salaried compensation participates in direct Job cost.",
        ("effective_compensation", "accepted_pay_period_time"),
        True,
        ("Generic workday time cannot silently acquire Job identity.",),
    ),
    AttributionDecisionDefinition(
        "non_job_paid_time_treatment",
        CertificationAuthority.OWNER_AND_ACCOUNTANT,
        "Classifies authoritative paid time that has no Job attribution.",
        ("accepted_paid_time", "job_attribution_completeness"),
        True,
        ("Unclassified paid time remains visible and non-zeroable.",),
    ),
    AttributionDecisionDefinition(
        "employer_burden_allocation",
        CertificationAuthority.ACCOUNTANT,
        "Selects component-specific allocation drivers for certified employer burden.",
        ("certified_burden_components", "component_effective_dates"),
        True,
        (
            "Missing burden components remain missing; one driver is not assumed for all.",
        ),
    ),
    AttributionDecisionDefinition(
        "owner_compensation_treatment",
        CertificationAuthority.OWNER_AND_ACCOUNTANT,
        "Separates management-economics treatment from accounting-book authority.",
        ("owner_compensation_source_evidence",),
        True,
        ("Certification does not alter payroll or accounting records.",),
    ),
    AttributionDecisionDefinition(
        "marketing_cost_treatment",
        CertificationAuthority.OWNER_AND_ACCOUNTANT,
        "Determines the management-economics scope of marketing cost.",
        ("reconciled_marketing_cost_evidence",),
        True,
        ("No Customer or Job attribution is inferred.",),
    ),
    AttributionDecisionDefinition(
        "fleet_equipment_cost_treatment",
        CertificationAuthority.OWNER_AND_ACCOUNTANT,
        "Determines when source-backed fleet/equipment cost enters overhead or capacity economics.",
        ("fleet_cost_evidence", "vehicle_job_relationship_if_allocated"),
        True,
        ("Depreciation and vehicle-to-Job relationships are never inferred.",),
    ),
    AttributionDecisionDefinition(
        "capacity_buffer",
        CertificationAuthority.OWNER,
        "Defines an explicit capacity assumption for governed scenario analysis.",
        ("measured_capacity_baseline",),
        True,
        ("A scenario assumption never becomes measured capacity.",),
    ),
)

DECISION_REGISTRY: Mapping[str, AttributionDecisionDefinition] = MappingProxyType(
    {item.family_key: item for item in _DECISIONS}
)


def certification_state(
    policies: tuple[CompanyPolicyVersion, ...],
    *,
    company_id: UUID,
    family_key: str,
    as_of: date,
) -> CertificationState:
    """Project the persisted lifecycle into owner-facing certification language."""
    resolution = resolve_policy_authority(
        policies, company_id=company_id, family_key=family_key, as_of=as_of
    )
    if resolution.state is PolicyResolutionState.APPROVED:
        return CertificationState.CERTIFIED
    if resolution.state is PolicyResolutionState.CONFLICT:
        return CertificationState.CONFLICTING
    scoped = tuple(
        item
        for item in policies
        if item.company_id == company_id and item.family_key == family_key
    )
    if any(item.lifecycle is PolicyLifecycle.DRAFT for item in scoped):
        return CertificationState.DRAFT
    if any(item.lifecycle is PolicyLifecycle.SUPERSEDED for item in scoped):
        return CertificationState.SUPERSEDED
    if any(item.lifecycle is PolicyLifecycle.RETIRED for item in scoped):
        return CertificationState.INACTIVE
    return CertificationState.UNSELECTED


def decision_packet(
    policies: tuple[CompanyPolicyVersion, ...],
    *,
    company_id: UUID,
    family_key: str,
    as_of: date,
) -> dict[str, object]:
    definition = DECISION_REGISTRY[family_key]
    family = POLICY_FAMILY_REGISTRY[family_key]
    return {
        "contract_version": CONTRACT_VERSION,
        "family_key": family_key,
        "title": family.title,
        "certification_state": certification_state(
            policies,
            company_id=company_id,
            family_key=family_key,
            as_of=as_of,
        ).value,
        "authority_required": definition.authority_required.value,
        "supported_choices": list(family.supported_strategies),
        "implication": definition.implication,
        "evidence_required": list(definition.evidence_required),
        "historical_replay_supported": definition.historical_replay_supported,
        "limitations": list(definition.limitations),
        "effective_as_of": as_of.isoformat(),
        "selection": None,
        "mutation_authority": "none",
    }
