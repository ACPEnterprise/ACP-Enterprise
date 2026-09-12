"""Operator readiness and explicitly non-authoritative policy preview."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, time, timezone
from enum import StrEnum
from typing import Final
from uuid import UUID

from .break_even_calculation import (
    GovernedBreakEvenCalculation,
    calculate_governed_break_even,
)
from .break_even_policy import (
    BreakEvenPolicySelection,
    BreakEvenPolicySnapshot,
    PolicyApprovalState,
    build_break_even_policy_snapshot,
    seal_break_even_policy,
)
from .break_even_scenario import MeasuredScenarioFact, ScenarioAssumption
from .owner_policy_operations import PolicyActor

READINESS_VERSION: Final = "eco.break-even-operator-readiness.v1"


class OperatorReadinessState(StrEnum):
    READY = "READY"
    BLOCKED = "BLOCKED"


class BlockerGroup(StrEnum):
    EVIDENCE_MISSING = "EVIDENCE_MISSING"
    EVIDENCE_CONFLICTING = "EVIDENCE_CONFLICTING"
    POLICY_UNSELECTED = "POLICY_UNSELECTED"
    POLICY_UNAPPROVED = "POLICY_UNAPPROVED"
    ACCOUNTING_NOT_RECONCILED = "ACCOUNTING_NOT_RECONCILED"
    SCOPE_INVALID = "SCOPE_INVALID"
    PERIOD_INVALID = "PERIOD_INVALID"
    OTHER_GOVERNED_BLOCKER = "OTHER_GOVERNED_BLOCKER"


@dataclass(frozen=True, slots=True)
class GroupedBlockers:
    group: BlockerGroup
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BreakEvenOperatorReadiness:
    contract_version: str
    state: OperatorReadinessState
    company_id: UUID
    branch_id: UUID | None
    service_line: str | None
    period_start: str | None
    period_end: str | None
    blocker_groups: tuple[GroupedBlockers, ...]
    calculation_digest: str
    readiness_digest: str


@dataclass(frozen=True, slots=True)
class DraftPolicyPreview:
    contract_version: str
    labels: tuple[str, ...]
    draft_policy_id: UUID
    draft_policy_version: int
    approved_baseline: GovernedBreakEvenCalculation
    calculated_preview: GovernedBreakEvenCalculation
    measured_evidence_unchanged: bool
    authoritative: bool
    preview_digest: str


def build_operator_readiness(
    calculation: GovernedBreakEvenCalculation,
    *,
    accounting_reconciled: bool,
) -> BreakEvenOperatorReadiness:
    grouped: dict[BlockerGroup, list[str]] = {}
    for blocker in calculation.blockers:
        group = _group(blocker)
        grouped.setdefault(group, []).append(blocker)
    if not accounting_reconciled:
        grouped.setdefault(BlockerGroup.ACCOUNTING_NOT_RECONCILED, []).append(
            "live_accounting_source_not_reconciled"
        )
    blockers = tuple(
        GroupedBlockers(group, tuple(sorted(set(reasons))))
        for group, reasons in sorted(grouped.items(), key=lambda item: item[0].value)
    )
    state = OperatorReadinessState.BLOCKED if blockers else OperatorReadinessState.READY
    body = {
        "contract_version": READINESS_VERSION,
        "state": state,
        "company_id": calculation.company_id,
        "branch_id": calculation.branch_id,
        "service_line": calculation.service_line,
        "period_start": calculation.period_start,
        "period_end": calculation.period_end,
        "blocker_groups": [asdict(x) for x in blockers],
        "calculation_digest": calculation.calculation_digest,
    }
    return BreakEvenOperatorReadiness(
        READINESS_VERSION,
        state,
        calculation.company_id,
        calculation.branch_id,
        calculation.service_line,
        calculation.period_start.isoformat() if calculation.period_start else None,
        calculation.period_end.isoformat() if calculation.period_end else None,
        blockers,
        calculation.calculation_digest,
        _digest(body),
    )


def preview_draft_policy(
    *,
    actor: PolicyActor,
    approved_policy: BreakEvenPolicySnapshot,
    draft: BreakEvenPolicySelection,
    measured_facts: tuple[MeasuredScenarioFact, ...],
    assumptions: tuple[ScenarioAssumption, ...] = (),
) -> DraftPolicyPreview:
    if "COMPANY_ECONOMICS_POLICY_READ" not in actor.permissions:
        raise ValueError("economics policy preview is not authorized")
    approved_policy.verify()
    draft.verify()
    if draft.approval_state not in {
        PolicyApprovalState.DRAFT,
        PolicyApprovalState.AWAITING_APPROVAL,
    }:
        raise ValueError("preview requires DRAFT or AWAITING_APPROVAL policy")
    if draft.company_id != actor.company_id or draft.branch_id != actor.branch_id:
        raise ValueError("foreign draft policy scope")
    baseline = calculate_governed_break_even(
        policy=approved_policy, measured_facts=measured_facts
    )
    synthetic = _preview_only_approved(draft, actor, approved_policy.as_of)
    selections = tuple(
        synthetic if item.kind is draft.kind else item
        for item in approved_policy.selections
    )
    preview_snapshot = build_break_even_policy_snapshot(
        selections,
        company_id=approved_policy.company_id,
        branch_id=approved_policy.branch_id,
        as_of=approved_policy.as_of,
    )
    preview = calculate_governed_break_even(
        policy=preview_snapshot, measured_facts=measured_facts
    )
    labels = (
        "ACTUAL_MEASURED",
        "APPROVED_POLICY",
        "DRAFT_POLICY",
        "SCENARIO_ASSUMPTION",
        "CALCULATED_PREVIEW",
    )
    unchanged = (
        baseline.measurement_evidence_digests == preview.measurement_evidence_digests
    )
    body = {
        "contract_version": READINESS_VERSION,
        "labels": labels,
        "draft_policy_digest": draft.policy_digest,
        "baseline_digest": baseline.calculation_digest,
        "preview_digest": preview.calculation_digest,
        "measured_evidence_unchanged": unchanged,
        "authoritative": False,
    }
    return DraftPolicyPreview(
        READINESS_VERSION,
        labels,
        draft.policy_id,
        draft.version,
        baseline,
        preview,
        unchanged,
        False,
        _digest(body),
    )


def _preview_only_approved(
    draft: BreakEvenPolicySelection, actor: PolicyActor, as_of: date
) -> BreakEvenPolicySelection:
    values = asdict(
        replace(
            draft,
            approval_state=PolicyApprovalState.APPROVED,
            approved_by_user_id=actor.user_id,
            approver_role=actor.role,
            approved_at=datetime.combine(as_of, time.min, tzinfo=timezone.utc),
        )
    )
    values.pop("policy_digest")
    return seal_break_even_policy(**values)


def _group(blocker: str) -> BlockerGroup:
    if blocker.startswith("missing_evidence:"):
        return BlockerGroup.EVIDENCE_MISSING
    if blocker.startswith("conflicting_evidence:"):
        return BlockerGroup.EVIDENCE_CONFLICTING
    if blocker.startswith("missing_policy:"):
        return BlockerGroup.POLICY_UNSELECTED
    if "policy" in blocker and "approved" in blocker:
        return BlockerGroup.POLICY_UNAPPROVED
    if "scope" in blocker or "branch" in blocker or "service_line" in blocker:
        return BlockerGroup.SCOPE_INVALID
    if "period" in blocker:
        return BlockerGroup.PERIOD_INVALID
    return BlockerGroup.OTHER_GOVERNED_BLOCKER


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
