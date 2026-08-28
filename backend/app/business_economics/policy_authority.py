"""Company-scoped Finance/Economics policy authority contracts.

The module resolves policy; it never accepts evidence or calculates economics.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from itertools import pairwise
from types import MappingProxyType
from typing import Any
from uuid import UUID

POLICY_DEFINITION_VERSION = "eco.finance-policy.v1"
SNAPSHOT_DEFINITION_VERSION = "eco.finance-policy-snapshot.v1"


class PolicyLifecycle(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    SUPERSEDED = "superseded"
    RETIRED = "retired"


class PolicyDisposition(StrEnum):
    SELECTED = "selected"
    DEFERRED = "deferred"


class PolicyResolutionState(StrEnum):
    APPROVED = "approved"
    DEFERRED = "deferred"
    UNRESOLVED = "unresolved"
    CONFLICT = "conflict"


@dataclass(frozen=True)
class PolicyFamilyDefinition:
    key: str
    title: str
    finance_decision_id: str
    supported_strategies: tuple[str, ...]
    parameter_types: Mapping[str, str]
    definition_version: str = POLICY_DEFINITION_VERSION


_FAMILIES = {
    "revenue_recognition": (
        "ECO-FIN-001",
        "Revenue recognition",
        (
            "invoice_issuance",
            "accepted_earned_value_at_completion",
            "approved_progress",
            "cash_settlement",
        ),
        {},
    ),
    "payment_settlement_acceptance": (
        "ECO-FIN-002",
        "Payment and settlement acceptance",
        ("accepted_payment_application", "bank_settlement", "cash_receipt"),
        {"freshness_days": "integer"},
    ),
    "direct_labor_measurement": (
        "ECO-FIN-003",
        "Direct labor measurement",
        ("approved_actual_job_time", "approved_standard_time"),
        {"time_unit": "string"},
    ),
    "labor_burden": (
        "ECO-FIN-004",
        "Labor burden",
        ("actual_burden", "standard_by_worker_class", "unburdened"),
        {"worker_class_rate_table_ref": "reference", "true_up_rule_ref": "reference"},
    ),
    "direct_material_costing": (
        "ECO-FIN-005",
        "Direct material costing",
        (
            "accepted_inventory_issue_layers",
            "approved_standard_cost",
            "accepted_specific_purchase_cost",
        ),
        {"cost_layer_method": "string"},
    ),
    "other_attributable_direct_costs": (
        "ECO-FIN-006",
        "Other attributable direct costs",
        ("category_inclusion_exclusion",),
        {"included_categories": "string_list", "excluded_categories": "string_list"},
    ),
    "overhead_pool_definitions": (
        "ECO-FIN-007",
        "Overhead pool definitions",
        ("approved_pool_set",),
        {"pool_definition_refs": "reference_list"},
    ),
    "overhead_allocation": (
        "ECO-FIN-008",
        "Overhead allocation",
        ("approved_allocation_drivers",),
        {"driver_definition_refs": "reference_list"},
    ),
    "reconciliation_source_precedence": (
        "ECO-FIN-009",
        "Reconciliation and source precedence",
        ("reject_conflicting_component", "fact_specific_approved_precedence"),
        {"precedence_rule_refs": "reference_list"},
    ),
    "monetary_materiality": (
        "ECO-FIN-010",
        "Monetary materiality",
        ("exact_exceptions", "approved_threshold"),
        {"threshold_minor_units": "integer", "currency": "string"},
    ),
    "accounting_reconciliation_admission": (
        "ECO-FIN-011",
        "Accounting reconciliation admission",
        ("integrity_reconciled_reviewed", "integrity_reconciled_provisional"),
        {"freshness_days": "integer"},
    ),
    "job_lifecycle_cutoff": (
        "ECO-FIN-012",
        "Job lifecycle and cutoff",
        ("completed_only", "approved_progress", "closed_period"),
        {},
    ),
}
POLICY_FAMILY_REGISTRY: Mapping[str, PolicyFamilyDefinition] = MappingProxyType(
    {
        key: PolicyFamilyDefinition(key, title, decision_id, strategies, parameters)
        for key, (decision_id, title, strategies, parameters) in _FAMILIES.items()
    }
)
STRATEGY_REQUIRED_PARAMETERS: Mapping[tuple[str, str], tuple[str, ...]] = (
    MappingProxyType(
        {
            ("labor_burden", "standard_by_worker_class"): (
                "worker_class_rate_table_ref",
                "true_up_rule_ref",
            ),
            ("other_attributable_direct_costs", "category_inclusion_exclusion"): (
                "included_categories",
                "excluded_categories",
            ),
            ("overhead_pool_definitions", "approved_pool_set"): (
                "pool_definition_refs",
            ),
            ("overhead_allocation", "approved_allocation_drivers"): (
                "driver_definition_refs",
            ),
            ("monetary_materiality", "approved_threshold"): (
                "threshold_minor_units",
                "currency",
            ),
        }
    )
)


def missing_required_parameters(policy: CompanyPolicyVersion) -> tuple[str, ...]:
    if policy.strategy_key is None:
        return ()
    required = STRATEGY_REQUIRED_PARAMETERS.get(
        (policy.family_key, policy.strategy_key), ()
    )
    return tuple(sorted(set(required) - set(policy.parameters)))


class PolicyAuthorityError(ValueError):
    pass


class PolicyResolutionError(PolicyAuthorityError):
    pass


class PolicyIntegrityError(PolicyAuthorityError):
    pass


class PolicyAuthorizationError(PolicyAuthorityError):
    pass


def canonical_digest(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class CompanyPolicyVersion:
    policy_id: UUID
    company_id: UUID
    branch_id: UUID | None
    family_key: str
    policy_version: int
    disposition: PolicyDisposition
    strategy_key: str | None
    parameters: Mapping[str, Any]
    evidence_acceptance_rule_refs: tuple[str, ...]
    effective_start: date
    effective_end: date | None
    lifecycle: PolicyLifecycle
    definition_version: str
    approved_by_user_id: UUID | None
    approved_at: datetime | None
    decision_evidence_digest: str
    supersedes_policy_id: UUID | None = None
    policy_digest: str = ""

    def canonical_content(self) -> dict[str, object]:
        return {
            "policy_id": str(self.policy_id),
            "company_id": str(self.company_id),
            "branch_id": str(self.branch_id) if self.branch_id else None,
            "family_key": self.family_key,
            "policy_version": self.policy_version,
            "disposition": self.disposition.value,
            "strategy_key": self.strategy_key,
            "parameters": dict(self.parameters),
            "evidence_acceptance_rule_refs": sorted(self.evidence_acceptance_rule_refs),
            "effective_start": self.effective_start.isoformat(),
            "effective_end": self.effective_end.isoformat()
            if self.effective_end
            else None,
            "lifecycle": self.lifecycle.value,
            "definition_version": self.definition_version,
            "approved_by_user_id": str(self.approved_by_user_id)
            if self.approved_by_user_id
            else None,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "decision_evidence_digest": self.decision_evidence_digest,
            "supersedes_policy_id": str(self.supersedes_policy_id)
            if self.supersedes_policy_id
            else None,
        }

    def validate(self) -> None:
        if self.family_key not in POLICY_FAMILY_REGISTRY:
            raise PolicyIntegrityError("unsupported policy family")
        if self.definition_version != POLICY_DEFINITION_VERSION:
            raise PolicyIntegrityError("unsupported policy definition version")
        if self.branch_id is not None:
            raise PolicyIntegrityError(
                "branch policy overrides are not supported in v1"
            )
        definition = POLICY_FAMILY_REGISTRY[self.family_key]
        if self.policy_version < 1:
            raise PolicyIntegrityError("invalid policy version")
        if self.disposition is PolicyDisposition.SELECTED:
            if self.strategy_key not in definition.supported_strategies:
                raise PolicyIntegrityError("unsupported policy strategy")
        elif self.strategy_key is not None or self.parameters:
            raise PolicyIntegrityError(
                "deferred policy cannot imply strategy or values"
            )
        _validate_parameter_types(self.parameters, definition.parameter_types)
        if (
            self.effective_end is not None
            and self.effective_end <= self.effective_start
        ):
            raise PolicyIntegrityError("invalid effective interval")
        if self.lifecycle in {
            PolicyLifecycle.APPROVED,
            PolicyLifecycle.SUPERSEDED,
            PolicyLifecycle.RETIRED,
        } and (self.approved_by_user_id is None or self.approved_at is None):
            raise PolicyIntegrityError(
                "policy lifecycle change lacks explicit approval"
            )
        if (
            self.lifecycle
            in {
                PolicyLifecycle.SUPERSEDED,
                PolicyLifecycle.RETIRED,
            }
            and self.supersedes_policy_id is None
        ):
            raise PolicyIntegrityError("terminal lifecycle record lacks predecessor")
        expected = canonical_digest(self.canonical_content())
        if self.policy_digest != expected:
            raise PolicyIntegrityError("policy digest mismatch")


def seal_policy(**values: Any) -> CompanyPolicyVersion:
    draft = CompanyPolicyVersion(**values, policy_digest="")
    return CompanyPolicyVersion(
        **values, policy_digest=canonical_digest(draft.canonical_content())
    )


def _validate_parameter_types(
    parameters: Mapping[str, Any], parameter_types: Mapping[str, str]
) -> None:
    unknown = set(parameters) - set(parameter_types)
    if unknown:
        raise PolicyIntegrityError("policy contains undefined parameters")
    for key, value in parameters.items():
        kind = parameter_types[key]
        valid = {
            "integer": isinstance(value, int) and not isinstance(value, bool),
            "string": isinstance(value, str),
            "reference": isinstance(value, str),
            "string_list": isinstance(value, list)
            and all(isinstance(item, str) for item in value),
            "reference_list": isinstance(value, list)
            and all(isinstance(item, str) for item in value),
        }[kind]
        if not valid:
            raise PolicyIntegrityError("policy parameter type mismatch")


@dataclass(frozen=True)
class PolicyResolution:
    company_id: UUID
    branch_id: UUID | None
    family_key: str
    as_of: date
    state: PolicyResolutionState
    policy: CompanyPolicyVersion | None
    reason: str


@dataclass(frozen=True)
class PolicyParameterRecord:
    parameter_id: UUID
    company_id: UUID
    branch_id: UUID | None
    family_key: str
    parameter_key: str
    parameter_version: int
    value: object
    effective_start: date
    effective_end: date | None
    approved_by_user_id: UUID
    approved_at: datetime
    definition_version: str
    parameter_digest: str

    def canonical_content(self) -> dict[str, object]:
        return {
            "parameter_id": str(self.parameter_id),
            "company_id": str(self.company_id),
            "branch_id": str(self.branch_id) if self.branch_id else None,
            "family_key": self.family_key,
            "parameter_key": self.parameter_key,
            "parameter_version": self.parameter_version,
            "value": self.value,
            "effective_start": self.effective_start.isoformat(),
            "effective_end": self.effective_end.isoformat()
            if self.effective_end
            else None,
            "approved_by_user_id": str(self.approved_by_user_id),
            "approved_at": self.approved_at.isoformat(),
            "definition_version": self.definition_version,
        }

    def validate(self) -> None:
        definition = POLICY_FAMILY_REGISTRY.get(self.family_key)
        if definition is None or self.parameter_key not in definition.parameter_types:
            raise PolicyIntegrityError("unsupported policy parameter")
        if self.branch_id is not None or self.parameter_version < 1:
            raise PolicyIntegrityError("invalid parameter scope or version")
        if (
            self.effective_end is not None
            and self.effective_end <= self.effective_start
        ):
            raise PolicyIntegrityError("invalid parameter effective interval")
        _validate_parameter_types(
            {self.parameter_key: self.value}, definition.parameter_types
        )
        if canonical_digest(self.canonical_content()) != self.parameter_digest:
            raise PolicyIntegrityError("policy parameter digest mismatch")


def seal_policy_parameter(**values: Any) -> PolicyParameterRecord:
    draft = PolicyParameterRecord(**values, parameter_digest="")
    return PolicyParameterRecord(
        **values, parameter_digest=canonical_digest(draft.canonical_content())
    )


@dataclass(frozen=True)
class PolicyParameterGap:
    gap_id: UUID
    company_id: UUID
    branch_id: UUID | None
    family_key: str
    gap_key: str
    requirement: str
    authority_dependency: str
    effective_start: date
    registered_by_user_id: UUID
    registered_at: datetime
    decision_evidence_digest: str
    gap_digest: str

    def canonical_content(self) -> dict[str, object]:
        return {
            "gap_id": str(self.gap_id),
            "company_id": str(self.company_id),
            "branch_id": str(self.branch_id) if self.branch_id else None,
            "family_key": self.family_key,
            "gap_key": self.gap_key,
            "requirement": self.requirement,
            "authority_dependency": self.authority_dependency,
            "effective_start": self.effective_start.isoformat(),
            "registered_by_user_id": str(self.registered_by_user_id),
            "registered_at": self.registered_at.isoformat(),
            "decision_evidence_digest": self.decision_evidence_digest,
            "state": "unresolved",
        }

    def validate(self) -> None:
        if self.family_key not in POLICY_FAMILY_REGISTRY or self.branch_id is not None:
            raise PolicyIntegrityError("invalid policy gap family or scope")
        if not self.gap_key or not self.requirement or not self.authority_dependency:
            raise PolicyIntegrityError(
                "policy gap identity and requirement are required"
            )
        if canonical_digest(self.canonical_content()) != self.gap_digest:
            raise PolicyIntegrityError("policy gap digest mismatch")


def seal_policy_gap(**values: Any) -> PolicyParameterGap:
    draft = PolicyParameterGap(**values, gap_digest="")
    return PolicyParameterGap(
        **values, gap_digest=canonical_digest(draft.canonical_content())
    )


def resolve_policy_authority(
    policies: Sequence[CompanyPolicyVersion],
    *,
    company_id: UUID,
    family_key: str,
    as_of: date,
    branch_id: UUID | None = None,
) -> PolicyResolution:
    if branch_id is not None:
        return PolicyResolution(
            company_id,
            branch_id,
            family_key,
            as_of,
            PolicyResolutionState.CONFLICT,
            None,
            "branch_policy_resolution_unsupported_v1",
        )
    applicable = _applicable_policies(policies, company_id, family_key, as_of)
    if not applicable:
        return PolicyResolution(
            company_id,
            None,
            family_key,
            as_of,
            PolicyResolutionState.UNRESOLVED,
            None,
            "no_applicable_approved_policy",
        )
    if len(applicable) > 1:
        return PolicyResolution(
            company_id,
            None,
            family_key,
            as_of,
            PolicyResolutionState.CONFLICT,
            None,
            "ambiguous_overlapping_policy",
        )
    policy = applicable[0]
    state = (
        PolicyResolutionState.DEFERRED
        if policy.disposition is PolicyDisposition.DEFERRED
        else PolicyResolutionState.APPROVED
    )
    return PolicyResolution(
        company_id,
        None,
        family_key,
        as_of,
        state,
        policy,
        "explicitly_deferred"
        if state is PolicyResolutionState.DEFERRED
        else "approved_applicable_policy",
    )


def _applicable_policies(
    policies: Sequence[CompanyPolicyVersion],
    company_id: UUID,
    family_key: str,
    as_of: date,
) -> list[CompanyPolicyVersion]:
    for policy in policies:
        policy.validate()
    shadowed_ids = {
        policy.supersedes_policy_id
        for policy in policies
        if policy.company_id == company_id
        and policy.family_key == family_key
        and policy.supersedes_policy_id is not None
        and policy.effective_start <= as_of
        and policy.lifecycle
        in {
            PolicyLifecycle.APPROVED,
            PolicyLifecycle.SUPERSEDED,
            PolicyLifecycle.RETIRED,
        }
    }
    return [
        policy
        for policy in policies
        if policy.company_id == company_id
        and policy.family_key == family_key
        and policy.lifecycle is PolicyLifecycle.APPROVED
        and policy.policy_id not in shadowed_ids
        and policy.effective_start <= as_of
        and (policy.effective_end is None or as_of < policy.effective_end)
    ]


def resolve_policy(
    policies: Sequence[CompanyPolicyVersion],
    *,
    company_id: UUID,
    family_key: str,
    as_of: date,
    branch_id: UUID | None = None,
) -> CompanyPolicyVersion:
    if branch_id is not None:
        raise PolicyResolutionError("branch policy resolution is not supported in v1")
    resolution = resolve_policy_authority(
        policies,
        company_id=company_id,
        family_key=family_key,
        as_of=as_of,
        branch_id=branch_id,
    )
    candidates = (
        [resolution.policy]
        if resolution.state is PolicyResolutionState.APPROVED and resolution.policy
        else []
    )
    if len(candidates) != 1:
        raise PolicyResolutionError(
            "required policy is missing or has ambiguous overlapping approval"
        )
    return candidates[0]


def validate_policy_set(policies: Sequence[CompanyPolicyVersion]) -> None:
    """Reject overlapping approved intervals within one Company/family."""
    approved: dict[tuple[UUID, str], list[CompanyPolicyVersion]] = {}
    for policy in policies:
        policy.validate()
        if policy.lifecycle is PolicyLifecycle.APPROVED:
            approved.setdefault((policy.company_id, policy.family_key), []).append(
                policy
            )
    for scoped in approved.values():
        ordered = sorted(scoped, key=lambda item: item.effective_start)
        for previous, current in pairwise(ordered):
            directly_supersedes = current.supersedes_policy_id == previous.policy_id
            if not directly_supersedes and (
                previous.effective_end is None
                or current.effective_start < previous.effective_end
            ):
                raise PolicyIntegrityError(
                    "approved policy effective intervals overlap"
                )


_ACTION_PERMISSION = {
    "read": "COMPANY_ECONOMICS_POLICY_READ",
    "draft": "COMPANY_ECONOMICS_POLICY_DRAFT",
    "approve": "COMPANY_ECONOMICS_POLICY_APPROVE",
    "retire": "COMPANY_ECONOMICS_POLICY_RETIRE",
    "supersede": "COMPANY_ECONOMICS_POLICY_APPROVE",
}


def require_policy_permission(action: str, permission_codes: frozenset[str]) -> None:
    required = _ACTION_PERMISSION.get(action)
    if required is None or required not in permission_codes:
        raise PolicyAuthorizationError("economics policy action is not authorized")


@dataclass(frozen=True)
class PolicySnapshot:
    company_id: UUID
    branch_id: UUID | None
    subject_identity: str
    reconciliation_key: str
    as_of: date
    policies: tuple[CompanyPolicyVersion, ...]
    deferred_family_keys: tuple[str, ...]
    parameter_gaps: tuple[PolicyParameterGap, ...]
    definition_version: str
    snapshot_digest: str

    def canonical_content(self) -> dict[str, object]:
        return {
            "company_id": str(self.company_id),
            "branch_id": str(self.branch_id) if self.branch_id else None,
            "subject_identity": self.subject_identity,
            "reconciliation_key": self.reconciliation_key,
            "as_of": self.as_of.isoformat(),
            "policy_digests": sorted(policy.policy_digest for policy in self.policies),
            "deferred_family_keys": sorted(self.deferred_family_keys),
            "parameter_gap_digests": sorted(
                gap.gap_digest for gap in self.parameter_gaps
            ),
            "definition_version": self.definition_version,
        }

    def verify(self) -> None:
        for policy in self.policies:
            policy.validate()
            if (
                policy.company_id != self.company_id
                or policy.branch_id != self.branch_id
            ):
                raise PolicyIntegrityError("policy snapshot scope mismatch")
        for gap in self.parameter_gaps:
            gap.validate()
            if gap.company_id != self.company_id or gap.branch_id != self.branch_id:
                raise PolicyIntegrityError("policy gap snapshot scope mismatch")
        if canonical_digest(self.canonical_content()) != self.snapshot_digest:
            raise PolicyIntegrityError("policy snapshot digest mismatch")


def build_policy_snapshot(
    policies: Sequence[CompanyPolicyVersion],
    *,
    company_id: UUID,
    branch_id: UUID | None,
    subject_identity: str,
    reconciliation_key: str,
    as_of: date,
    required_families: Sequence[str],
    parameter_gaps: Sequence[PolicyParameterGap] = (),
) -> PolicySnapshot:
    resolutions = tuple(
        resolve_policy_authority(
            policies,
            company_id=company_id,
            family_key=family,
            as_of=as_of,
            branch_id=branch_id,
        )
        for family in sorted(set(required_families))
    )
    if any(
        item.state in {PolicyResolutionState.UNRESOLVED, PolicyResolutionState.CONFLICT}
        for item in resolutions
    ):
        raise PolicyResolutionError(
            "policy snapshot has unresolved or conflicting family"
        )
    selected = tuple(item.policy for item in resolutions if item.policy is not None)
    relevant_gaps = tuple(
        sorted(
            (gap for gap in parameter_gaps if gap.family_key in required_families),
            key=lambda gap: (gap.family_key, gap.gap_key),
        )
    )
    base = PolicySnapshot(
        company_id=company_id,
        branch_id=branch_id,
        subject_identity=subject_identity,
        reconciliation_key=reconciliation_key,
        as_of=as_of,
        policies=selected,
        deferred_family_keys=tuple(
            item.family_key
            for item in resolutions
            if item.state is PolicyResolutionState.DEFERRED
        ),
        parameter_gaps=relevant_gaps,
        definition_version=SNAPSHOT_DEFINITION_VERSION,
        snapshot_digest="",
    )
    result = PolicySnapshot(
        company_id=base.company_id,
        branch_id=base.branch_id,
        subject_identity=base.subject_identity,
        reconciliation_key=base.reconciliation_key,
        as_of=base.as_of,
        policies=base.policies,
        deferred_family_keys=base.deferred_family_keys,
        parameter_gaps=base.parameter_gaps,
        definition_version=base.definition_version,
        snapshot_digest=canonical_digest(base.canonical_content()),
    )
    result.verify()
    return result
