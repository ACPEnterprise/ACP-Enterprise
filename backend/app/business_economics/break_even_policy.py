"""Typed owner/accountant policy boundary for break-even model evaluation."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Final
from uuid import UUID

CONTRACT_VERSION: Final = "eco.break-even-policy-contract.v1"
_SHA256 = re.compile(r"^[a-f0-9]{64}$")


class BreakEvenPolicyKind(StrEnum):
    PRODUCTIVE_HOUR_DEFINITION = "productive_hour_definition"
    LABOR_BURDEN_METHOD = "labor_burden_method"
    OVERHEAD_ALLOCATION_METHOD = "overhead_allocation_method"
    ALLOCATION_SCOPE = "company_branch_allocation_scope"
    OVERHEAD_CLASSIFICATION = "fixed_variable_overhead_classification"
    OWNER_COMPENSATION_TREATMENT = "owner_compensation_treatment"
    VEHICLE_EQUIPMENT_COST_TREATMENT = "vehicle_equipment_cost_treatment"
    MATERIAL_COSTING_BASIS = "material_costing_basis"
    LABOR_CLASSIFICATION = "direct_indirect_labor_treatment"
    CALLBACK_REWORK_TREATMENT = "callback_rework_treatment"
    MARKETING_ALLOCATION = "marketing_allocation"
    TARGET_GROSS_MARGIN = "target_gross_margin"
    TARGET_OPERATING_MARGIN = "target_net_operating_margin"
    CAPACITY_BUFFER = "capacity_buffer"
    UNPRODUCTIVE_TIME_TREATMENT = "unproductive_time_treatment"
    OVERTIME_PREMIUM_TREATMENT = "overtime_premium_treatment"
    SERVICE_LINE_ALLOCATION = "service_line_allocation_behavior"
    ROUNDING_RULE = "rounding_rule"


class PolicyApprovalState(StrEnum):
    UNSELECTED = "UNSELECTED"
    DRAFT = "DRAFT"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    SUPERSEDED = "SUPERSEDED"


class PolicyApproverRole(StrEnum):
    OWNER = "OWNER"
    ACCOUNTANT = "ACCOUNTANT"


@dataclass(frozen=True, slots=True)
class BreakEvenPolicySelection:
    policy_id: UUID
    company_id: UUID
    branch_id: UUID | None
    kind: BreakEvenPolicyKind
    version: int
    value: str | Decimal | int | None
    effective_start: date
    effective_end: date | None
    approval_state: PolicyApprovalState
    approved_by_user_id: UUID | None
    approver_role: PolicyApproverRole | None
    approved_at: datetime | None
    provenance: str
    provenance_digest: str
    rationale_notes: str
    supersedes_policy_id: UUID | None
    policy_digest: str

    def canonical_content(self) -> dict[str, object]:
        body = asdict(self)
        body.pop("policy_digest")
        return body

    def verify(self) -> None:
        if (
            self.version < 1
            or not self.provenance
            or not _SHA256.fullmatch(self.provenance_digest)
        ):
            raise ValueError("policy version and immutable provenance are required")
        if (
            self.effective_end is not None
            and self.effective_end <= self.effective_start
        ):
            raise ValueError("invalid policy effective interval")
        if self.approval_state is PolicyApprovalState.UNSELECTED:
            if self.value is not None or any(
                (self.approved_by_user_id, self.approver_role, self.approved_at)
            ):
                raise ValueError("unselected policy cannot imply a value or approval")
        elif self.approval_state is PolicyApprovalState.APPROVED:
            if self.value is None or not all(
                (self.approved_by_user_id, self.approver_role, self.approved_at)
            ):
                raise ValueError(
                    "approved policy requires explicit selection and approver"
                )
        elif (
            self.approval_state is PolicyApprovalState.SUPERSEDED and self.value is None
        ):
            raise ValueError("superseded policy must preserve its historical value")
        _validate_value(self.kind, self.value)
        if _digest(self.canonical_content()) != self.policy_digest:
            raise ValueError("break-even policy digest mismatch")


@dataclass(frozen=True, slots=True)
class BreakEvenPolicySnapshot:
    contract_version: str
    company_id: UUID
    branch_id: UUID | None
    as_of: date
    selections: tuple[BreakEvenPolicySelection, ...]
    missing_policy: tuple[BreakEvenPolicyKind, ...]
    snapshot_digest: str

    def verify(self) -> None:
        for item in self.selections:
            item.verify()
            if item.approval_state is not PolicyApprovalState.APPROVED:
                raise ValueError(
                    "authoritative policy snapshot contains unapproved policy"
                )
            if item.company_id != self.company_id or item.branch_id != self.branch_id:
                raise ValueError("foreign policy scope")
        expected_missing = tuple(
            kind
            for kind in BreakEvenPolicyKind
            if kind not in {item.kind for item in self.selections}
        )
        if self.missing_policy != expected_missing:
            raise ValueError("policy snapshot missing-state mismatch")
        expected = _digest(
            {
                "contract_version": self.contract_version,
                "company_id": self.company_id,
                "branch_id": self.branch_id,
                "as_of": self.as_of,
                "policy_digests": [x.policy_digest for x in self.selections],
                "missing_policy": self.missing_policy,
            }
        )
        if expected != self.snapshot_digest:
            raise ValueError("break-even policy snapshot digest mismatch")


_ENUM_VALUES: dict[BreakEvenPolicyKind, frozenset[str]] = {
    BreakEvenPolicyKind.PRODUCTIVE_HOUR_DEFINITION: frozenset(
        {
            "accepted_productive_job_time",
            "accepted_jobsite_time",
            "accepted_actual_job_time",
        }
    ),
    BreakEvenPolicyKind.LABOR_BURDEN_METHOD: frozenset(
        {"actual_components", "approved_rate", "exclude"}
    ),
    BreakEvenPolicyKind.OVERHEAD_ALLOCATION_METHOD: frozenset(
        {
            "productive_hours",
            "earned_revenue",
            "direct_labor_hours",
            "explicit_pool_driver",
        }
    ),
    BreakEvenPolicyKind.ALLOCATION_SCOPE: frozenset({"company", "branch"}),
    BreakEvenPolicyKind.OVERHEAD_CLASSIFICATION: frozenset(
        {"accepted_account_classification", "approved_pool_classification"}
    ),
    BreakEvenPolicyKind.OWNER_COMPENSATION_TREATMENT: frozenset(
        {"direct_labor", "fixed_overhead", "variable_overhead", "exclude"}
    ),
    BreakEvenPolicyKind.VEHICLE_EQUIPMENT_COST_TREATMENT: frozenset(
        {"direct_attributable", "fixed_overhead", "variable_overhead", "exclude"}
    ),
    BreakEvenPolicyKind.MATERIAL_COSTING_BASIS: frozenset(
        {"inventory_issue_layer", "specific_purchase_cost", "approved_standard_cost"}
    ),
    BreakEvenPolicyKind.LABOR_CLASSIFICATION: frozenset(
        {"job_attributable_direct", "approved_role_classification"}
    ),
    BreakEvenPolicyKind.CALLBACK_REWORK_TREATMENT: frozenset(
        {"originating_job", "corrective_job", "overhead", "separate_analysis"}
    ),
    BreakEvenPolicyKind.MARKETING_ALLOCATION: frozenset(
        {"fixed_overhead", "variable_by_revenue", "service_line_driver", "exclude"}
    ),
    BreakEvenPolicyKind.UNPRODUCTIVE_TIME_TREATMENT: frozenset(
        {"labor_burden", "fixed_overhead", "separate_capacity", "exclude"}
    ),
    BreakEvenPolicyKind.OVERTIME_PREMIUM_TREATMENT: frozenset(
        {"direct_job", "labor_burden", "overhead", "separate_analysis"}
    ),
    BreakEvenPolicyKind.SERVICE_LINE_ALLOCATION: frozenset(
        {"none_company_only", "direct_then_driver", "approved_service_line_driver"}
    ),
    BreakEvenPolicyKind.ROUNDING_RULE: frozenset(
        {"currency_half_even", "currency_half_up", "no_intermediate_rounding"}
    ),
}
_RATIO_KINDS = {
    BreakEvenPolicyKind.TARGET_GROSS_MARGIN,
    BreakEvenPolicyKind.TARGET_OPERATING_MARGIN,
    BreakEvenPolicyKind.CAPACITY_BUFFER,
}


def break_even_policy_decisions() -> dict[BreakEvenPolicyKind, dict[str, object]]:
    """Expose supported choices without selecting or preferring one."""
    return {
        kind: (
            {"value_type": "decimal_ratio", "supported_options": ()}
            if kind in _RATIO_KINDS
            else {
                "value_type": "enum",
                "supported_options": tuple(sorted(_ENUM_VALUES[kind])),
            }
        )
        for kind in BreakEvenPolicyKind
    }


def seal_break_even_policy(**values: object) -> BreakEvenPolicySelection:
    item = BreakEvenPolicySelection(**values, policy_digest="")  # type: ignore[arg-type]
    sealed = replace(item, policy_digest=_digest(item.canonical_content()))
    sealed.verify()
    return sealed


def build_break_even_policy_snapshot(
    selections: tuple[BreakEvenPolicySelection, ...],
    *,
    company_id: UUID,
    branch_id: UUID | None,
    as_of: date,
) -> BreakEvenPolicySnapshot:
    applicable = []
    for item in selections:
        item.verify()
        if item.company_id != company_id or item.branch_id != branch_id:
            raise ValueError("foreign Company/Branch policy")
        if item.effective_start <= as_of and (
            item.effective_end is None or as_of < item.effective_end
        ):
            applicable.append(item)
    by_kind: dict[BreakEvenPolicyKind, list[BreakEvenPolicySelection]] = {}
    shadowed = {
        item.supersedes_policy_id
        for item in applicable
        if item.supersedes_policy_id is not None
        and item.approval_state
        in {PolicyApprovalState.APPROVED, PolicyApprovalState.SUPERSEDED}
    }
    for item in applicable:
        if (
            item.approval_state is PolicyApprovalState.APPROVED
            and item.policy_id not in shadowed
        ):
            by_kind.setdefault(item.kind, []).append(item)
    if any(len(items) > 1 for items in by_kind.values()):
        raise ValueError("conflicting effective break-even policy")
    selected = tuple(
        sorted((items[0] for items in by_kind.values()), key=lambda x: x.kind.value)
    )
    missing = tuple(kind for kind in BreakEvenPolicyKind if kind not in by_kind)
    body = {
        "contract_version": CONTRACT_VERSION,
        "company_id": company_id,
        "branch_id": branch_id,
        "as_of": as_of,
        "policy_digests": [x.policy_digest for x in selected],
        "missing_policy": missing,
    }
    return BreakEvenPolicySnapshot(
        CONTRACT_VERSION, company_id, branch_id, as_of, selected, missing, _digest(body)
    )


def _validate_value(
    kind: BreakEvenPolicyKind, value: str | Decimal | int | None
) -> None:
    if value is None:
        return
    if kind in _RATIO_KINDS:
        if not isinstance(value, Decimal) or value < 0 or value >= 1:
            raise ValueError("ratio policy must be Decimal in [0, 1)")
    elif not isinstance(value, str) or value not in _ENUM_VALUES[kind]:
        raise ValueError("unsupported typed break-even policy selection")


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
