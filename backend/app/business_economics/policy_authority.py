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


@dataclass(frozen=True)
class PolicyFamilyDefinition:
    key: str
    title: str
    definition_version: str = POLICY_DEFINITION_VERSION


_FAMILY_TITLES = {
    "job_lifecycle_cutoff": "Job lifecycle and cutoff",
    "revenue_recognition": "Revenue recognition",
    "payment_settlement_acceptance": "Payment and settlement acceptance",
    "direct_labor_measurement": "Direct labor measurement",
    "labor_burden": "Labor burden",
    "direct_material_costing": "Direct material costing",
    "other_attributable_direct_costs": "Other attributable direct costs",
    "overhead_pool_definitions": "Overhead pool definitions",
    "overhead_allocation": "Overhead allocation",
    "reconciliation_source_precedence": "Reconciliation and source precedence",
    "monetary_materiality": "Monetary materiality",
    "accounting_reconciliation_admission": "Accounting reconciliation admission",
}
POLICY_FAMILY_REGISTRY: Mapping[str, PolicyFamilyDefinition] = MappingProxyType(
    {key: PolicyFamilyDefinition(key, title) for key, title in _FAMILY_TITLES.items()}
)


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
    strategy_key: str
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
        if self.policy_version < 1 or not self.strategy_key:
            raise PolicyIntegrityError("invalid policy version or strategy")
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
    candidates = []
    for policy in policies:
        policy.validate()
        if (
            policy.company_id == company_id
            and policy.family_key == family_key
            and policy.lifecycle is PolicyLifecycle.APPROVED
            and policy.policy_id not in shadowed_ids
            and policy.effective_start <= as_of
            and (policy.effective_end is None or as_of < policy.effective_end)
        ):
            candidates.append(policy)
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
) -> PolicySnapshot:
    selected = tuple(
        resolve_policy(
            policies,
            company_id=company_id,
            family_key=family,
            as_of=as_of,
            branch_id=branch_id,
        )
        for family in sorted(set(required_families))
    )
    base = PolicySnapshot(
        company_id=company_id,
        branch_id=branch_id,
        subject_identity=subject_identity,
        reconciliation_key=reconciliation_key,
        as_of=as_of,
        policies=selected,
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
        definition_version=base.definition_version,
        snapshot_digest=canonical_digest(base.canonical_content()),
    )
    result.verify()
    return result
