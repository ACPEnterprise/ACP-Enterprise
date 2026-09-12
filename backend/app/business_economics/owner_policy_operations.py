"""Authorized append-only operations for governed break-even policy."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime
from decimal import Decimal
from typing import Final, Protocol
from uuid import UUID, uuid4

from app.platform.audit.service import AuditEntry

from .break_even_policy import (
    BreakEvenPolicyKind,
    BreakEvenPolicySelection,
    PolicyApprovalState,
    PolicyApproverRole,
    break_even_policy_decisions,
    seal_break_even_policy,
)
from .policy_authority import require_policy_permission

OPERATIONS_VERSION: Final = "eco.owner-policy-operations.v1"


@dataclass(frozen=True, slots=True)
class PolicyActor:
    user_id: UUID
    company_id: UUID
    branch_id: UUID | None
    permissions: frozenset[str]
    role: PolicyApproverRole


@dataclass(frozen=True, slots=True)
class PolicyOperationEvent:
    event_id: UUID
    company_id: UUID
    branch_id: UUID | None
    policy_id: UUID
    policy_version: int
    state: PolicyApprovalState
    actor_id: UUID
    occurred_at: datetime
    rationale: str
    prior_event_digest: str | None
    policy: BreakEvenPolicySelection
    event_digest: str


class PolicyOperationRepository(Protocol):
    def list_events(
        self, company_id: UUID, branch_id: UUID | None
    ) -> tuple[PolicyOperationEvent, ...]: ...

    def append(self, events: tuple[PolicyOperationEvent, ...]) -> None: ...


class InMemoryPolicyOperationRepository:
    """Qualification adapter; production persistence remains an explicit seam."""

    def __init__(self) -> None:
        self._events: list[PolicyOperationEvent] = []

    def list_events(
        self, company_id: UUID, branch_id: UUID | None
    ) -> tuple[PolicyOperationEvent, ...]:
        return tuple(
            x
            for x in self._events
            if x.company_id == company_id and x.branch_id == branch_id
        )

    def append(self, events: tuple[PolicyOperationEvent, ...]) -> None:
        known = {x.event_digest for x in self._events}
        if any(x.event_digest in known for x in events):
            raise ValueError("duplicate policy operation event")
        self._events.extend(events)


class OwnerPolicyOperationsService:
    def __init__(self, repository: PolicyOperationRepository) -> None:
        self.repository = repository

    def list_families(self, actor: PolicyActor, *, as_of: date) -> dict[str, object]:
        require_policy_permission("read", actor.permissions)
        current = self._current(actor.company_id, actor.branch_id, as_of)
        definitions = break_even_policy_decisions()
        return {
            "contract_version": OPERATIONS_VERSION,
            "company_id": str(actor.company_id),
            "branch_id": str(actor.branch_id) if actor.branch_id else None,
            "as_of": as_of.isoformat(),
            "families": tuple(
                {
                    "family": kind.value,
                    "state": current[kind].state.value
                    if kind in current
                    else PolicyApprovalState.UNSELECTED.value,
                    "current_version": current[kind].policy_version
                    if kind in current
                    else None,
                    "effective_start": current[kind].policy.effective_start.isoformat()
                    if kind in current
                    else None,
                    "rationale": current[kind].rationale if kind in current else None,
                    "provenance": current[kind].policy.provenance
                    if kind in current
                    else None,
                    "supported_options": definitions[kind]["supported_options"],
                    "value_type": definitions[kind]["value_type"],
                    "downstream_calculations": _downstream(kind),
                }
                for kind in BreakEvenPolicyKind
            ),
        }

    def draft(
        self,
        actor: PolicyActor,
        *,
        kind: BreakEvenPolicyKind,
        value: str | Decimal,
        effective_start: date,
        provenance: str,
        provenance_digest: str,
        rationale: str,
        occurred_at: datetime,
    ) -> PolicyOperationEvent:
        require_policy_permission("draft", actor.permissions)
        history = self.repository.list_events(actor.company_id, actor.branch_id)
        version = 1 + max(
            (x.policy_version for x in history if x.policy.kind is kind), default=0
        )
        prior = self._approved(kind, history, effective_start)
        policy = seal_break_even_policy(
            policy_id=uuid4(),
            company_id=actor.company_id,
            branch_id=actor.branch_id,
            kind=kind,
            version=version,
            value=value,
            effective_start=effective_start,
            effective_end=None,
            approval_state=PolicyApprovalState.DRAFT,
            approved_by_user_id=None,
            approver_role=None,
            approved_at=None,
            provenance=provenance,
            provenance_digest=provenance_digest,
            rationale_notes=rationale,
            supersedes_policy_id=prior.policy_id if prior else None,
        )
        event = _event(
            policy,
            actor,
            occurred_at,
            rationale,
            history[-1].event_digest if history else None,
        )
        self.repository.append((event,))
        return event

    def submit(
        self,
        actor: PolicyActor,
        *,
        policy_id: UUID,
        rationale: str,
        occurred_at: datetime,
    ) -> PolicyOperationEvent:
        require_policy_permission("draft", actor.permissions)
        latest = self._latest(actor, policy_id)
        if latest.state is not PolicyApprovalState.DRAFT:
            raise ValueError("only DRAFT policy may be submitted")
        policy = _reseal(
            replace(latest.policy, approval_state=PolicyApprovalState.AWAITING_APPROVAL)
        )
        event = _event(policy, actor, occurred_at, rationale, latest.event_digest)
        self.repository.append((event,))
        return event

    def approve(
        self,
        actor: PolicyActor,
        *,
        policy_id: UUID,
        rationale: str,
        occurred_at: datetime,
    ) -> PolicyOperationEvent:
        require_policy_permission("approve", actor.permissions)
        latest = self._latest(actor, policy_id)
        if latest.state is not PolicyApprovalState.AWAITING_APPROVAL:
            raise ValueError("only AWAITING_APPROVAL policy may be approved")
        history = self.repository.list_events(actor.company_id, actor.branch_id)
        prior = self._approved(
            latest.policy.kind, history, latest.policy.effective_start
        )
        events: list[PolicyOperationEvent] = []
        prior_digest = latest.event_digest
        if prior is not None and prior.policy_id != policy_id:
            prior_latest = self._latest(actor, prior.policy_id)
            superseded = _reseal(
                replace(
                    prior_latest.policy,
                    approval_state=PolicyApprovalState.SUPERSEDED,
                )
            )
            prior_event = _event(
                superseded,
                actor,
                occurred_at,
                rationale,
                prior_latest.event_digest,
            )
            events.append(prior_event)
            prior_digest = prior_event.event_digest
        approved = _reseal(
            replace(
                latest.policy,
                approval_state=PolicyApprovalState.APPROVED,
                approved_by_user_id=actor.user_id,
                approver_role=actor.role,
                approved_at=occurred_at,
            )
        )
        event = _event(approved, actor, occurred_at, rationale, prior_digest)
        events.append(event)
        self.repository.append(tuple(events))
        return event

    def history(self, actor: PolicyActor) -> tuple[PolicyOperationEvent, ...]:
        require_policy_permission("read", actor.permissions)
        return self.repository.list_events(actor.company_id, actor.branch_id)

    def _latest(self, actor: PolicyActor, policy_id: UUID) -> PolicyOperationEvent:
        matches = [
            x
            for x in self.repository.list_events(actor.company_id, actor.branch_id)
            if x.policy_id == policy_id
        ]
        if not matches:
            raise ValueError("policy does not exist in authorized scope")
        return matches[-1]

    def _current(
        self, company_id: UUID, branch_id: UUID | None, as_of: date
    ) -> dict[BreakEvenPolicyKind, PolicyOperationEvent]:
        latest: dict[UUID, PolicyOperationEvent] = {}
        for event in self.repository.list_events(company_id, branch_id):
            latest[event.policy_id] = event
        result: dict[BreakEvenPolicyKind, PolicyOperationEvent] = {}
        for event in latest.values():
            policy = event.policy
            if policy.effective_start <= as_of and (
                policy.effective_end is None or as_of < policy.effective_end
            ):
                current = result.get(policy.kind)
                if current is None or event.policy_version > current.policy_version:
                    result[policy.kind] = event
        return result

    @staticmethod
    def _approved(
        kind: BreakEvenPolicyKind,
        history: tuple[PolicyOperationEvent, ...],
        as_of: date,
    ) -> BreakEvenPolicySelection | None:
        latest: dict[UUID, PolicyOperationEvent] = {}
        for event in history:
            latest[event.policy_id] = event
        candidates = [
            x.policy
            for x in latest.values()
            if x.policy.kind is kind
            and x.state is PolicyApprovalState.APPROVED
            and x.policy.effective_start <= as_of
            and (x.policy.effective_end is None or as_of < x.policy.effective_end)
        ]
        return max(candidates, key=lambda x: x.version) if candidates else None


def _event(
    policy: BreakEvenPolicySelection,
    actor: PolicyActor,
    occurred_at: datetime,
    rationale: str,
    prior_digest: str | None,
) -> PolicyOperationEvent:
    if not rationale:
        raise ValueError("policy operation rationale is required")
    body = {
        "version": OPERATIONS_VERSION,
        "company_id": actor.company_id,
        "branch_id": actor.branch_id,
        "policy_digest": policy.policy_digest,
        "state": policy.approval_state,
        "actor_id": actor.user_id,
        "occurred_at": occurred_at,
        "rationale": rationale,
        "prior_event_digest": prior_digest,
    }
    return PolicyOperationEvent(
        uuid4(),
        actor.company_id,
        actor.branch_id,
        policy.policy_id,
        policy.version,
        policy.approval_state,
        actor.user_id,
        occurred_at,
        rationale,
        prior_digest,
        policy,
        _digest(body),
    )


def _reseal(policy: BreakEvenPolicySelection) -> BreakEvenPolicySelection:
    values = asdict(policy)
    values.pop("policy_digest")
    return seal_break_even_policy(**values)


def _downstream(kind: BreakEvenPolicyKind) -> tuple[str, ...]:
    common = ("break_even_revenue", "break_even_revenue_per_productive_hour")
    if kind in {
        BreakEvenPolicyKind.TARGET_GROSS_MARGIN,
        BreakEvenPolicyKind.TARGET_OPERATING_MARGIN,
    }:
        return (*common, "policy_target_margin_comparison")
    if kind in {
        BreakEvenPolicyKind.PRODUCTIVE_HOUR_DEFINITION,
        BreakEvenPolicyKind.CAPACITY_BUFFER,
    }:
        return (*common, "productive_hour_cost", "capacity_scenario")
    return common


def policy_operation_audit_entry(event: PolicyOperationEvent) -> AuditEntry:
    """Map an operation to ACP's existing audit infrastructure for persistence."""
    return AuditEntry(
        action=f"economics.policy.{event.state.value.lower()}",
        resource_type="break_even_policy",
        actor_user_id=event.actor_id,
        company_id=event.company_id,
        branch_id=event.branch_id,
        resource_id=event.policy_id,
        reason_code="owner_policy_operation",
        occurred_at=event.occurred_at,
        details={
            "policy_version": event.policy_version,
            "effective_date": event.policy.effective_start.isoformat(),
            "rationale": event.rationale,
            "prior_event_digest": event.prior_event_digest,
            "approval_identity": str(event.policy.approved_by_user_id)
            if event.policy.approved_by_user_id
            else None,
            "policy_digest": event.policy.policy_digest,
            "event_digest": event.event_digest,
        },
    )


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
