"""Read-only LIA composition over canonical Dispatch recommendations."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final
from uuid import UUID, uuid5

from app.dispatch.intelligence import (
    ConstraintResult,
    DispatchRecommendation,
    EvidenceRef,
    PlacementRecommendation,
)

CONTRACT_VERSION: Final = "lia.dispatch.reasoning.v1"
_NAMESPACE = UUID("c1ba99d1-7d64-4d51-8728-98e9706d0d6e")


class ResolutionState(StrEnum):
    RESOLVED = "RESOLVED"
    UNRESOLVED = "UNRESOLVED"


class GhostSlotClass(StrEnum):
    PRIMARY_GHOST_SLOT = "PRIMARY_GHOST_SLOT"
    ALTERNATE_GHOST_SLOT = "ALTERNATE_GHOST_SLOT"
    CONSTRAINED_OPTION = "CONSTRAINED_OPTION"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class CallFact:
    name: str
    value: str | None
    state: ResolutionState
    authority: str
    evidence: tuple[EvidenceRef, ...] = ()

    def __post_init__(self) -> None:
        if self.state is ResolutionState.RESOLVED and not self.value:
            raise ValueError("resolved call facts require a value")


@dataclass(frozen=True, slots=True)
class CallReasoningContext:
    company_id: UUID
    branch_id: UUID
    conversation_id: UUID
    revision: int
    service_intent: CallFact
    urgency: CallFact
    customer: CallFact
    location: CallFact
    membership: CallFact
    availability_constraint: CallFact
    as_of: datetime
    valid_until: datetime

    def __post_init__(self) -> None:
        if self.revision < 1:
            raise ValueError("call revision must be positive")
        if self.as_of.tzinfo is None or self.valid_until.tzinfo is None:
            raise ValueError("call evidence timestamps must be timezone-aware")
        if self.valid_until <= self.as_of:
            raise ValueError("call evidence validity must end after its as-of time")


@dataclass(frozen=True, slots=True)
class GhostSlot:
    slot_class: GhostSlotClass
    employee_id: UUID | None
    start_at: datetime | None
    end_at: datetime | None
    facts: tuple[str, ...]
    why: tuple[str, ...]
    limitations: tuple[str, ...]
    evidence: tuple[EvidenceRef, ...]


@dataclass(frozen=True, slots=True)
class LiaDispatchReasoning:
    reasoning_id: UUID
    contract_version: str
    company_id: UUID
    branch_id: UUID
    conversation_id: UUID
    revision: int
    service_intent: str | None
    urgency: str | None
    customer_state: ResolutionState
    location_state: ResolutionState
    next_question: str | None
    facts: tuple[str, ...]
    interpretation: str
    recommendation: str
    why: tuple[str, ...]
    primary: GhostSlot
    alternates: tuple[GhostSlot, ...]
    limitations: tuple[str, ...]
    evidence: tuple[EvidenceRef, ...]
    as_of: datetime
    expires_at: datetime
    supersedes_reasoning_id: UUID | None
    reasoning_digest: str
    mutation_authority: str = "none"


def reason_about_dispatch(
    context: CallReasoningContext,
    dispatch: DispatchRecommendation | None,
    *,
    evaluated_at: datetime,
    prior: LiaDispatchReasoning | None = None,
) -> LiaDispatchReasoning:
    """Compose call facts with Dispatch evidence without acquiring its authority."""

    if evaluated_at.tzinfo is None:
        raise ValueError("evaluation time must be timezone-aware")
    if dispatch is not None and (
        dispatch.company_id != context.company_id
        or dispatch.branch_id != context.branch_id
    ):
        raise ValueError("Dispatch recommendation does not match call scope")

    facts = _facts(context)
    next_question = _next_question(context)
    expired = evaluated_at >= context.valid_until
    limitations = list(_limitations(context))
    slots: tuple[GhostSlot, ...]
    if expired:
        slots = ()
        limitations.append("Call evidence expired; refresh before offering a slot.")
    elif dispatch is None:
        slots = ()
        limitations.append(
            "Canonical Dispatch evidence is not available for the current call facts."
        )
    else:
        slots = tuple(_slot(item, dispatch.evidence) for item in dispatch.candidates)
        limitations.extend(dispatch.limitations)

    primary = next(
        (item for item in slots if item.slot_class is GhostSlotClass.PRIMARY_GHOST_SLOT),
        _unavailable_slot(tuple(limitations)),
    )
    alternates = tuple(
        item for item in slots if item.slot_class is not GhostSlotClass.PRIMARY_GHOST_SLOT
    )
    if primary.slot_class is GhostSlotClass.PRIMARY_GHOST_SLOT:
        recommendation = "Offer the primary slot for human review; do not assign it automatically."
        interpretation = (
            "Canonical Dispatch evidence supports at least one currently eligible option."
        )
        why = primary.why
    else:
        recommendation = (
            "Continue clarification and refresh canonical availability before offering a slot."
        )
        interpretation = (
            "The current facts do not support an eligible primary Dispatch option."
        )
        why = tuple(limitations) or ("No eligible canonical option was returned.",)

    evidence = tuple(
        sorted(
            {
                item
                for fact in _call_facts(context)
                for item in fact.evidence
            }
            | set(dispatch.evidence if dispatch else ()),
            key=lambda item: (item.authority, item.identity, item.digest),
        )
    )
    payload = {
        "contract_version": CONTRACT_VERSION,
        "company_id": str(context.company_id),
        "branch_id": str(context.branch_id),
        "conversation_id": str(context.conversation_id),
        "revision": context.revision,
        "facts": facts,
        "next_question": next_question,
        "dispatch_digest": dispatch.recommendation_digest if dispatch else None,
        "slots": [_slot_payload(item) for item in slots],
        "limitations": sorted(set(limitations)),
        "evidence": tuple(
            (item.authority, item.identity, item.digest) for item in evidence
        ),
        "as_of": context.as_of.isoformat(),
        "expires_at": context.valid_until.isoformat(),
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    reasoning_id = uuid5(_NAMESPACE, digest)
    supersedes = (
        prior.reasoning_id
        if prior is not None and prior.reasoning_digest != digest
        else None
    )
    return LiaDispatchReasoning(
        reasoning_id=reasoning_id,
        contract_version=CONTRACT_VERSION,
        company_id=context.company_id,
        branch_id=context.branch_id,
        conversation_id=context.conversation_id,
        revision=context.revision,
        service_intent=context.service_intent.value,
        urgency=(
            context.urgency.value
            if context.urgency.state is ResolutionState.RESOLVED
            and bool(context.urgency.evidence)
            else None
        ),
        customer_state=context.customer.state,
        location_state=context.location.state,
        next_question=next_question,
        facts=facts,
        interpretation=interpretation,
        recommendation=recommendation,
        why=why,
        primary=primary,
        alternates=alternates,
        limitations=tuple(sorted(set(limitations))),
        evidence=evidence,
        as_of=context.as_of,
        expires_at=context.valid_until,
        supersedes_reasoning_id=supersedes,
        reasoning_digest=digest,
    )


def _facts(context: CallReasoningContext) -> tuple[str, ...]:
    return tuple(
        f"{item.name}: {_fact_display(item)}" for item in _call_facts(context)
    )


def _call_facts(context: CallReasoningContext) -> tuple[CallFact, ...]:
    return (
        context.service_intent,
        context.urgency,
        context.customer,
        context.location,
        context.membership,
        context.availability_constraint,
    )


def _fact_display(item: CallFact) -> str:
    if item.state is ResolutionState.UNRESOLVED:
        return "unresolved"
    if item.name == "URGENCY" and not item.evidence:
        return "unresolved (configured policy evidence required)"
    return item.value or "unresolved"


def _next_question(context: CallReasoningContext) -> str | None:
    if context.customer.state is ResolutionState.UNRESOLVED:
        return "Are you a previous customer? May I have the service address?"
    if context.location.state is ResolutionState.UNRESOLVED:
        return "What is the service address?"
    if context.service_intent.state is ResolutionState.UNRESOLVED:
        return "What problem can we help with today?"
    if context.availability_constraint.state is ResolutionState.UNRESOLVED:
        return "Is there a time today when you cannot meet the technician?"
    return None


def _limitations(context: CallReasoningContext) -> tuple[str, ...]:
    values = []
    if context.urgency.state is ResolutionState.RESOLVED and not context.urgency.evidence:
        values.append(
            "Urgency lacks configured policy evidence and is not used as a priority."
        )
    if context.location.state is ResolutionState.UNRESOLVED:
        values.append("Location-dependent eligibility and travel evidence are unavailable.")
    if context.membership.state is ResolutionState.UNRESOLVED:
        values.append("Membership entitlement is unresolved and is not assumed.")
    return tuple(values)


def _slot(
    item: PlacementRecommendation, global_evidence: tuple[EvidenceRef, ...]
) -> GhostSlot:
    if item.eligible and item.rank == 1:
        slot_class = GhostSlotClass.PRIMARY_GHOST_SLOT
    elif item.eligible:
        slot_class = GhostSlotClass.ALTERNATE_GHOST_SLOT
    elif any(
        constraint.result is ConstraintResult.FAIL for constraint in item.constraints
    ):
        slot_class = GhostSlotClass.CONSTRAINED_OPTION
    else:
        slot_class = GhostSlotClass.UNAVAILABLE
    passed = tuple(
        constraint.explanation
        for constraint in item.constraints
        if constraint.result is ConstraintResult.PASS
    )
    why = passed if item.eligible else tuple(
        constraint.explanation
        for constraint in item.constraints
        if constraint.result is not ConstraintResult.PASS
    )
    return GhostSlot(
        slot_class=slot_class,
        employee_id=item.employee_id,
        start_at=item.proposed_window.start_at,
        end_at=item.proposed_window.end_at,
        facts=tuple(
            f"{constraint.constraint}: {constraint.result.value}"
            for constraint in item.constraints
        ),
        why=why,
        limitations=(*item.limitations, *item.tradeoffs),
        evidence=global_evidence,
    )


def _unavailable_slot(limitations: tuple[str, ...]) -> GhostSlot:
    return GhostSlot(
        slot_class=GhostSlotClass.UNAVAILABLE,
        employee_id=None,
        start_at=None,
        end_at=None,
        facts=(),
        why=("No current eligible canonical Dispatch option is available.",),
        limitations=limitations,
        evidence=(),
    )


def _slot_payload(item: GhostSlot) -> dict[str, object]:
    return {
        "slot_class": item.slot_class.value,
        "employee_id": str(item.employee_id) if item.employee_id else None,
        "start_at": item.start_at.isoformat() if item.start_at else None,
        "end_at": item.end_at.isoformat() if item.end_at else None,
        "facts": item.facts,
        "why": item.why,
        "limitations": item.limitations,
        "evidence": tuple(
            (evidence.authority, evidence.identity, evidence.digest)
            for evidence in item.evidence
        ),
    }
